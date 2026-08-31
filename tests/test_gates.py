from __future__ import annotations

from gates import evaluate
from scan import Event


def _event(mode: str, kind: str, *, errored: bool = False) -> Event:
    return Event(
        ts="2026-08-31T12:00:00Z",
        session="s1",
        project="repo",
        cwd="/tmp/repo",
        git_branch="main",
        mode=mode,
        tool="Read" if kind == "fs_read" else "Bash",
        kind=kind,
        targets=["relative.txt"] if kind == "fs_write" else [],
        errored=errored,
        mode_source="permissionMode",
    )


def test_g6_fires_on_any_bypass_permissions_reach() -> None:
    violations = evaluate([_event("bypassPermissions", "fs_read")], {})

    assert [v.gate for v in violations] == ["G6.tenancy"]
    assert violations[0].reason == "fs_read under mode=bypassPermissions"


def test_g6_fires_on_accept_edits_for_mutating_reach_only() -> None:
    violations = evaluate([
        _event("acceptEdits", "fs_read"),
        _event("acceptEdits", "fs_write"),
    ], {})

    assert [v.gate for v in violations] == ["G6.tenancy"]
    assert violations[0].reason == "fs_write under mode=acceptEdits"


def test_g6_ignores_errored_reach() -> None:
    violations = evaluate([_event("bypassPermissions", "exec", errored=True)], {})

    assert violations == []
