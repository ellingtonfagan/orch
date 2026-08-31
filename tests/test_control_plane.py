from __future__ import annotations

from pathlib import Path
from typing import Sequence

from orch.control_plane import (
    CommandResult,
    NodeContext,
    NodeKind,
    NodeRecord,
    NodeStatus,
    PipelineRunner,
    ROUTES,
    TaskKind,
    TaskRequest,
)


PATCH = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-old
+new
"""


class RecordingWorkspace:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.applied: list[str] = []

    def apply(self, patch: str) -> CommandResult:
        self.applied.append(patch)
        return CommandResult(command="apply", returncode=0)


class FixedVerifier:
    def __init__(self, repo_root: Path, returncodes: Sequence[int] = (0,)):
        self.repo_root = repo_root
        self.returncodes = tuple(returncodes)
        self.commands_seen: list[tuple[str, ...]] = []

    def run(self, commands: Sequence[str]) -> Sequence[CommandResult]:
        command_tuple = tuple(commands)
        self.commands_seen.append(command_tuple)
        return tuple(
            CommandResult(command=command, returncode=returncode)
            for command, returncode in zip(command_tuple, self.returncodes, strict=False)
        )


def task(
    kind: TaskKind,
    *,
    allowed_files: tuple[str, ...] = ("app.py",),
    verification_commands: tuple[str, ...] = ("python3 -m pytest",),
) -> TaskRequest:
    return TaskRequest(
        task_id="task-1",
        kind=kind,
        description="exercise the control plane",
        allowed_files=allowed_files,
        verification_commands=verification_commands,
    )


def test_route_selection_is_fixed_per_task_kind() -> None:
    assert ROUTES == {
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


def test_out_of_allowlist_path_in_patch_is_rejected(tmp_path: Path) -> None:
    workspace = RecordingWorkspace(tmp_path)
    runner = PipelineRunner(
        handlers={
            NodeKind.PLAN: lambda _context: {"steps": ["change app"]},
            NodeKind.GENERATE: lambda _context: {
                "patch": PATCH,
                "changed_files": ["app.py"],
            },
        },
        verifier=FixedVerifier(tmp_path),
        workspace=workspace,
    )

    result = runner.run(task(TaskKind.CODE_GENERATION, allowed_files=("other.py",)))

    assert result.completed is False
    assert result.failed_node is NodeKind.GENERATE
    assert result.records[-1].status is NodeStatus.REJECTED
    assert result.records[-1].errors == ("patch exceeds allowed_files: ['app.py']",)
    assert workspace.applied == []


def test_declared_changed_files_must_match_parsed_diff(tmp_path: Path) -> None:
    workspace = RecordingWorkspace(tmp_path)
    runner = PipelineRunner(
        handlers={
            NodeKind.PLAN: lambda _context: {"steps": ["change app"]},
            NodeKind.GENERATE: lambda _context: {
                "patch": PATCH,
                "changed_files": ["other.py"],
            },
        },
        verifier=FixedVerifier(tmp_path),
        workspace=workspace,
    )

    result = runner.run(task(TaskKind.CODE_GENERATION))

    assert result.completed is False
    assert result.failed_node is NodeKind.GENERATE
    assert result.records[-1].status is NodeStatus.REJECTED
    assert result.records[-1].errors == ("changed_files do not match patch paths: ['app.py']",)
    assert workspace.applied == []


def test_non_zero_verification_exit_stops_the_route(tmp_path: Path) -> None:
    def handler(context: NodeContext) -> dict[str, object]:
        if context.node is NodeKind.PLAN:
            return {"steps": ["change app"]}
        if context.node is NodeKind.GENERATE:
            return {"patch": PATCH, "changed_files": ["app.py"]}
        if context.node is NodeKind.TEST_GENERATE:
            return {"patch": PATCH, "changed_files": ["app.py"]}
        raise AssertionError(f"unexpected node: {context.node}")

    runner = PipelineRunner(
        handlers={
            NodeKind.PLAN: handler,
            NodeKind.GENERATE: handler,
            NodeKind.TEST_GENERATE: handler,
        },
        verifier=FixedVerifier(tmp_path, returncodes=(1,)),
        workspace=RecordingWorkspace(tmp_path),
    )

    result = runner.run(task(TaskKind.CODE_GENERATION))

    assert result.completed is False
    assert result.failed_node is NodeKind.VERIFY
    assert [record.node for record in result.records] == [
        NodeKind.PLAN,
        NodeKind.GENERATE,
        NodeKind.TEST_GENERATE,
        NodeKind.VERIFY,
    ]
    assert result.records[-1].status is NodeStatus.REJECTED
    assert result.records[-1].errors == ("verification failed (1): python3 -m pytest",)


def test_high_finding_rejects_mutating_route(tmp_path: Path) -> None:
    def handler(context: NodeContext) -> dict[str, object]:
        if context.node is NodeKind.PLAN:
            return {"steps": ["change app"]}
        if context.node in {NodeKind.GENERATE, NodeKind.TEST_GENERATE, NodeKind.DOCUMENT}:
            return {"patch": PATCH, "changed_files": ["app.py"]}
        if context.node is NodeKind.REVIEW:
            return {"findings": [{"severity": "high", "message": "still broken"}]}
        raise AssertionError(f"unexpected node: {context.node}")

    runner = PipelineRunner(
        handlers={
            NodeKind.PLAN: handler,
            NodeKind.GENERATE: handler,
            NodeKind.TEST_GENERATE: handler,
            NodeKind.DOCUMENT: handler,
            NodeKind.REVIEW: handler,
        },
        verifier=FixedVerifier(tmp_path),
        workspace=RecordingWorkspace(tmp_path),
    )

    result = runner.run(task(TaskKind.CODE_GENERATION))

    assert result.completed is False
    assert result.failed_node is NodeKind.REVIEW
    assert result.records[-1] == NodeRecord(
        node=NodeKind.REVIEW,
        status=NodeStatus.REJECTED,
        artifact=result.records[-1].artifact,
        errors=("review blocked by high finding: still broken",),
    )


def test_high_finding_passes_review_only_task(tmp_path: Path) -> None:
    runner = PipelineRunner(
        handlers={
            NodeKind.REVIEW: lambda _context: {
                "findings": [{"severity": "high", "message": "still broken"}]
            },
        },
        verifier=FixedVerifier(tmp_path),
    )

    request = TaskRequest(
        task_id="review-1",
        kind=TaskKind.CODE_REVIEW,
        description="review only",
    )

    result = runner.run(request)

    assert result.completed is True
    assert result.failed_node is None
    assert result.records[0].status is NodeStatus.PASSED
