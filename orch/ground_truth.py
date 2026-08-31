"""Compare transcript write claims against the repository itself.

Transcripts are claims about tool calls, not a complete account of side effects.
This module refuses to treat either the transcript or git state as authoritative:
the signal is the disagreement between the two independent estimators.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scan import TRANSCRIPT_ROOT, Event, scan_all


@dataclass
class GroundTruthResult:
    session: str
    project: str
    cwd: str
    repo_root: str
    claimed_writes: set[str]
    present_changes: set[str]
    unattributed_dirty: set[str]
    present_side_measured: bool
    claimed_but_absent: set[str]
    present_but_unclaimed: set[str]

    def as_dict(self) -> dict:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, set):
                data[key] = sorted(value)
        return data


def _git(cwd: Path, args: list[str]) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _repo_root(cwd: str) -> Path | None:
    if not cwd:
        return None
    cwd_path = Path(cwd).expanduser()
    if not cwd_path.exists():
        return None
    roots = _git(cwd_path, ["rev-parse", "--show-toplevel"])
    return Path(roots[0]).resolve() if roots else None


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window(events: list[Event]) -> tuple[datetime | None, datetime | None]:
    stamps = [ts for ts in (_parse_ts(e.ts) for e in events) if ts is not None]
    if not stamps:
        return None, None
    return min(stamps) - timedelta(seconds=1), max(stamps) + timedelta(seconds=1)


def _relative_to_repo(target: str, cwd: Path, repo_root: Path) -> str | None:
    if not target:
        return None
    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = cwd / target_path
    resolved = target_path.resolve(strict=False)
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return None


def claimed_write_paths(events: list[Event], cwd: Path, repo_root: Path) -> set[str]:
    """Transcript-side write estimator: explicit writes plus Bash redirect targets."""
    claimed: set[str] = set()
    for event in events:
        if event.errored:
            continue
        if event.kind != "fs_write" and event.tool != "Bash":
            continue
        event_cwd = Path(event.cwd).expanduser() if event.cwd else cwd
        for target in event.targets:
            relative = _relative_to_repo(target, event_cwd, repo_root)
            if relative:
                claimed.add(relative)
    return claimed


def _mtime_changes(repo_root: Path, since: datetime | None, until: datetime | None) -> set[str]:
    if since is None or until is None:
        return set()
    changed: set[str] = set()
    for relative in _git(repo_root, ["ls-files", "-co", "--exclude-standard"]):
        path = repo_root / relative
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=since.tzinfo)
        except OSError:
            continue
        if since <= mtime <= until:
            changed.add(Path(relative).as_posix())
    return changed


def _unattributed_dirty_paths(repo_root: Path) -> set[str]:
    dirty = set(_git(repo_root, ["diff", "--name-only"]))
    dirty.update(_git(repo_root, ["diff", "--cached", "--name-only"]))
    return {Path(path).as_posix() for path in dirty if path}


def present_change_paths(repo_root: Path, since: datetime | None, until: datetime | None) -> set[str]:
    """Repository-side estimator using only windowed repository evidence."""
    present: set[str] = set()
    if since is not None and until is not None:
        present.update(_git(
            repo_root,
            [
                "log",
                "--name-only",
                "--pretty=format:",
                f"--since={since.isoformat()}",
                f"--until={until.isoformat()}",
            ],
        ))
    present.update(_mtime_changes(repo_root, since, until))
    return {Path(path).as_posix() for path in present if path}


def audit_session(events: list[Event]) -> GroundTruthResult | None:
    """Audit one session only when its cwd is a live git worktree."""
    cwd_value = next((e.cwd for e in events if e.cwd), "")
    repo_root = _repo_root(cwd_value)
    if repo_root is None:
        return None
    cwd = Path(cwd_value).expanduser()
    since, until = _window(events)
    claimed = claimed_write_paths(events, cwd, repo_root)
    present = present_change_paths(repo_root, since, until)
    unattributed_dirty = _unattributed_dirty_paths(repo_root)
    present_side_measured = bool(present)
    return GroundTruthResult(
        session=events[0].session,
        project=events[0].project,
        cwd=str(cwd),
        repo_root=str(repo_root),
        claimed_writes=claimed,
        present_changes=present,
        unattributed_dirty=unattributed_dirty,
        present_side_measured=present_side_measured,
        claimed_but_absent=claimed - present,
        present_but_unclaimed=(present - claimed) if present_side_measured else set(),
    )


def audit_events(events: list[Event], max_results: int | None = None) -> list[GroundTruthResult]:
    by_session: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_session[event.session].append(event)

    results: list[GroundTruthResult] = []
    for _session, session_events in sorted(by_session.items()):
        result = audit_session(session_events)
        if result is None:
            continue
        results.append(result)
        if max_results is not None and len(results) >= max_results:
            break
    return results


def render_results(results: list[GroundTruthResult]) -> str:
    claimed_absent = sum(len(r.claimed_but_absent) for r in results)
    present_unclaimed = sum(len(r.present_but_unclaimed) for r in results)
    unattributed_dirty = sum(len(r.unattributed_dirty) for r in results)
    not_measured = sum(1 for r in results if not r.present_side_measured)
    lines = [
        "# Ground Truth Disagreement",
        "",
        f"audited_sessions: {len(results)}",
        f"claimed-but-absent: {claimed_absent}",
        f"present-but-unclaimed: {present_unclaimed}",
        f"unattributed-dirty-excluded: {unattributed_dirty}",
        f"not-measured-sessions: {not_measured}",
        "",
        "unattributed-dirty-excluded are current working-tree or index paths; git gives them no session timestamp, so they are excluded from present-but-unclaimed.",
        "",
        "| session | project | claimed writes | present changes | excluded dirty | present side | claimed-but-absent | present-but-unclaimed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        present_side = "measured" if result.present_side_measured else "not-measured"
        present_unclaimed = (
            len(result.present_but_unclaimed) if result.present_side_measured else "not-measured"
        )
        lines.append(
            f"| {result.session[:8]} | {result.project[:40]} | "
            f"{len(result.claimed_writes)} | {len(result.present_changes)} | "
            f"{len(result.unattributed_dirty)} | {present_side} | "
            f"{len(result.claimed_but_absent)} | {present_unclaimed} |"
        )
    if not results:
        lines.append("| _none_ | _none_ | 0 | 0 | 0 | not-measured | 0 | not-measured |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare transcript write claims to git state.")
    ap.add_argument("--root", type=Path, default=TRANSCRIPT_ROOT)
    ap.add_argument("--project", help="substring filter on transcript cwd/project")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    events = scan_all(args.root, args.project)
    results = audit_events(events, max_results=args.limit)
    print(render_results(results))


if __name__ == "__main__":
    main()
