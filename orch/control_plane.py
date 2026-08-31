"""Extracted deterministic control plane for model-assisted development workflows.

This module was copied from the source trading package's dev_pipeline.py so ORCH
can audit and build without a callable edge into order authority. Model-backed
handlers may propose plans, patches, reviews, and documentation. The pipeline
itself owns routing, artifact validation, verification, and journaling so no
synthesis node can decide whether its own output advances.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence


class TaskKind(str, Enum):
    CODE_GENERATION = "code-generation"
    CODE_FIXING = "code-fixing"
    TEST_GENERATION = "test-generation"
    CODE_REVIEW = "code-review"
    DOCUMENTATION = "documentation"
    PLANNING = "planning"


class NodeKind(str, Enum):
    PLAN = "plan"
    GENERATE = "generate"
    FIX = "fix"
    TEST_GENERATE = "test-generate"
    VERIFY = "verify"
    REVIEW = "review"
    DOCUMENT = "document"


class NodeStatus(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    ERROR = "error"


ROUTES: Mapping[TaskKind, tuple[NodeKind, ...]] = {
    TaskKind.CODE_GENERATION: (
        NodeKind.PLAN,
        NodeKind.GENERATE,
        NodeKind.TEST_GENERATE,
        NodeKind.VERIFY,
        NodeKind.DOCUMENT,
        NodeKind.VERIFY,
        NodeKind.REVIEW,
    ),
    TaskKind.CODE_FIXING: (
        NodeKind.PLAN,
        NodeKind.FIX,
        NodeKind.TEST_GENERATE,
        NodeKind.VERIFY,
        NodeKind.DOCUMENT,
        NodeKind.VERIFY,
        NodeKind.REVIEW,
    ),
    TaskKind.TEST_GENERATION: (
        NodeKind.PLAN,
        NodeKind.TEST_GENERATE,
        NodeKind.VERIFY,
        NodeKind.REVIEW,
    ),
    TaskKind.CODE_REVIEW: (NodeKind.REVIEW,),
    TaskKind.DOCUMENTATION: (
        NodeKind.DOCUMENT,
        NodeKind.VERIFY,
        NodeKind.REVIEW,
    ),
    TaskKind.PLANNING: (NodeKind.PLAN, NodeKind.REVIEW),
}

PATCH_NODES = {
    NodeKind.GENERATE,
    NodeKind.FIX,
    NodeKind.TEST_GENERATE,
    NodeKind.DOCUMENT,
}
MUTATING_TASKS = {
    TaskKind.CODE_GENERATION,
    TaskKind.CODE_FIXING,
    TaskKind.TEST_GENERATION,
    TaskKind.DOCUMENTATION,
}
BLOCKING_SEVERITIES = {"blocker", "high"}


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe_repo_path(raw: str) -> str | None:
    normalized = raw.removeprefix("a/").removeprefix("b/")
    path = PurePosixPath(normalized)
    if not normalized or normalized == "/dev/null" or path.is_absolute() or ".." in path.parts:
        return None
    return str(path)


def patch_paths(patch: str) -> tuple[str, ...]:
    """Extract normalized file paths from a unified diff."""
    paths: set[str] = set()
    in_file_header = True
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            in_file_header = True
            continue
        if line.startswith("@@ "):
            in_file_header = False
            continue
        if not in_file_header:
            continue
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0].strip()
        path = _safe_repo_path(raw)
        if path is not None:
            paths.add(path)
    return tuple(sorted(paths))


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    kind: TaskKind
    description: str
    allowed_files: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.description.strip():
            raise ValueError("task_id and description are required")
        invalid = [path for path in self.allowed_files if _safe_repo_path(path) != path]
        if invalid:
            raise ValueError(f"allowed_files must be repository-relative: {invalid}")
        if self.kind in MUTATING_TASKS and not self.verification_commands:
            raise ValueError("mutating tasks require at least one verification command")


@dataclass(frozen=True)
class Artifact:
    node: NodeKind
    payload: Mapping[str, Any]
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        encoded = _canonical_json(self.payload)
        object.__setattr__(self, "payload", json.loads(encoded))
        object.__setattr__(self, "content_hash", hashlib.sha256(encoded.encode()).hexdigest())


@dataclass(frozen=True)
class NodeContext:
    request: TaskRequest
    node: NodeKind
    artifacts: tuple[Artifact, ...]
    workspace_root: Path | None = None


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class NodeRecord:
    node: NodeKind
    status: NodeStatus
    artifact: Artifact | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    task_id: str
    completed: bool
    records: tuple[NodeRecord, ...]

    @property
    def failed_node(self) -> NodeKind | None:
        for record in self.records:
            if record.status is not NodeStatus.PASSED:
                return record.node
        return None


NodeHandler = Callable[[NodeContext], Mapping[str, Any]]


class Verifier(Protocol):
    def run(self, commands: Sequence[str]) -> Sequence[CommandResult]: ...


class PatchWorkspace(Protocol):
    repo_root: Path

    def apply(self, patch: str) -> CommandResult: ...


class GitPatchWorkspace:
    """Apply accepted patch artifacts to an explicit Git worktree."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def apply(self, patch: str) -> CommandResult:
        started = time.monotonic()
        for args in (("git", "apply", "--check", "-"), ("git", "apply", "-")):
            try:
                proc = subprocess.run(
                    args,
                    cwd=self.repo_root,
                    input=patch,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                return CommandResult(
                    command=" ".join(args),
                    returncode=127,
                    stderr=str(exc),
                    duration_seconds=round(time.monotonic() - started, 6),
                )
            if proc.returncode != 0:
                return CommandResult(
                    command=" ".join(args),
                    returncode=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    duration_seconds=round(time.monotonic() - started, 6),
                )
        return CommandResult(
            command="git apply -",
            returncode=0,
            duration_seconds=round(time.monotonic() - started, 6),
        )


class SubprocessVerifier:
    """Run configured argv-style checks without invoking a shell."""

    def __init__(self, repo_root: Path, *, timeout_seconds: int = 300, output_limit: int = 20_000):
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit

    def run(self, commands: Sequence[str]) -> Sequence[CommandResult]:
        results = []
        for command in commands:
            started = time.monotonic()
            try:
                proc = subprocess.run(
                    shlex.split(command),
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                result = CommandResult(
                    command=command,
                    returncode=proc.returncode,
                    stdout=proc.stdout[-self.output_limit :],
                    stderr=proc.stderr[-self.output_limit :],
                    duration_seconds=round(time.monotonic() - started, 6),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                result = CommandResult(
                    command=command,
                    returncode=124 if isinstance(exc, subprocess.TimeoutExpired) else 127,
                    stderr=str(exc)[-self.output_limit :],
                    duration_seconds=round(time.monotonic() - started, 6),
                )
            results.append(result)
            if result.returncode != 0:
                break
        return results


class PipelineRunner:
    def __init__(
        self,
        handlers: Mapping[NodeKind, NodeHandler],
        verifier: Verifier,
        *,
        workspace: PatchWorkspace | None = None,
        journal_path: Path | None = None,
    ):
        self.handlers = handlers
        self.verifier = verifier
        self.workspace = workspace
        self.journal_path = journal_path
        verifier_root = getattr(verifier, "repo_root", None)
        workspace_root = getattr(workspace, "repo_root", None)
        if verifier_root is not None and workspace_root is not None:
            if Path(verifier_root).resolve() != Path(workspace_root).resolve():
                raise ValueError("workspace and verifier must use the same repository root")

    def run(self, request: TaskRequest) -> PipelineResult:
        artifacts: list[Artifact] = []
        records: list[NodeRecord] = []
        for node in ROUTES[request.kind]:
            record = self._run_node(request, node, tuple(artifacts))
            records.append(record)
            self._journal(request, record)
            if record.status is not NodeStatus.PASSED:
                break
            if record.artifact is not None:
                artifacts.append(record.artifact)
        return PipelineResult(
            task_id=request.task_id,
            completed=len(records) == len(ROUTES[request.kind]) and all(
                record.status is NodeStatus.PASSED for record in records
            ),
            records=tuple(records),
        )

    def _run_node(
        self,
        request: TaskRequest,
        node: NodeKind,
        artifacts: tuple[Artifact, ...],
    ) -> NodeRecord:
        if node is NodeKind.VERIFY:
            results = list(self.verifier.run(request.verification_commands))
            payload = {
                "commands": [
                    {
                        "command": result.command,
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                    for result in results
                ]
            }
            errors = tuple(
                f"verification failed ({result.returncode}): {result.command}"
                for result in results
                if result.returncode != 0
            )
            return NodeRecord(
                node=node,
                status=NodeStatus.REJECTED if errors else NodeStatus.PASSED,
                artifact=Artifact(node, payload),
                errors=errors,
            )

        handler = self.handlers.get(node)
        if handler is None:
            return NodeRecord(node, NodeStatus.ERROR, errors=(f"missing handler: {node.value}",))
        try:
            workspace_root = getattr(self.workspace, "repo_root", None)
            payload = dict(handler(NodeContext(request, node, artifacts, workspace_root)))
        except Exception as exc:
            return NodeRecord(node, NodeStatus.ERROR, errors=(f"{exc.__class__.__name__}: {exc}",))

        errors = self._validate(request, node, payload)
        try:
            artifact = Artifact(node, payload)
        except (TypeError, ValueError) as exc:
            return NodeRecord(
                node=node,
                status=NodeStatus.REJECTED,
                errors=(f"node output must be finite JSON: {exc}",),
            )
        if not errors and node in PATCH_NODES:
            if self.workspace is None:
                errors.append("patch node requires an explicit workspace")
            else:
                applied = self.workspace.apply(str(payload["patch"]))
                if applied.returncode != 0:
                    detail = applied.stderr.strip() or applied.stdout.strip() or "unknown error"
                    errors.append(f"patch application failed ({applied.returncode}): {detail}")
        return NodeRecord(
            node=node,
            status=NodeStatus.REJECTED if errors else NodeStatus.PASSED,
            artifact=artifact,
            errors=tuple(errors),
        )

    @staticmethod
    def _validate(request: TaskRequest, node: NodeKind, payload: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        if node is NodeKind.PLAN:
            steps = payload.get("steps")
            if not isinstance(steps, list) or not steps or not all(
                isinstance(step, str) and step.strip() for step in steps
            ):
                errors.append("plan must contain a non-empty string list in steps")
        elif node in PATCH_NODES:
            patch = payload.get("patch")
            declared = payload.get("changed_files")
            if not isinstance(patch, str) or not patch.strip():
                errors.append("patch node must return a non-empty unified diff")
            if not isinstance(declared, list) or not all(isinstance(path, str) for path in declared):
                errors.append("patch node must declare changed_files")
            elif isinstance(patch, str):
                actual = patch_paths(patch)
                if not actual:
                    errors.append("patch does not contain repository file headers")
                if tuple(sorted(set(declared))) != actual:
                    errors.append(f"changed_files do not match patch paths: {list(actual)}")
                allowed = set(request.allowed_files)
                if allowed and not set(actual).issubset(allowed):
                    errors.append(f"patch exceeds allowed_files: {sorted(set(actual) - allowed)}")
        elif node is NodeKind.REVIEW:
            findings = payload.get("findings")
            if not isinstance(findings, list):
                errors.append("review must contain a findings list")
            else:
                for index, finding in enumerate(findings):
                    if not isinstance(finding, dict) or not str(finding.get("message") or "").strip():
                        errors.append(f"review finding {index} requires a message")
                        continue
                    severity = str(finding.get("severity") or "").lower()
                    if severity not in {"blocker", "high", "medium", "low", "nit"}:
                        errors.append(f"review finding {index} has invalid severity")
                    elif request.kind in MUTATING_TASKS and severity in BLOCKING_SEVERITIES:
                        errors.append(f"review blocked by {severity} finding: {finding['message']}")
        return errors

    def _journal(self, request: TaskRequest, record: NodeRecord) -> None:
        if self.journal_path is None:
            return
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "task_id": request.task_id,
            "task_kind": request.kind.value,
            "node": record.node.value,
            "status": record.status.value,
            "artifact_hash": record.artifact.content_hash if record.artifact else None,
            "errors": list(record.errors),
        }
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
