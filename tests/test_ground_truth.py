from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from orch.ground_truth import audit_session, render_results
from report import render
from scan import Event


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**os.environ, **env} if env else None,
    )


def _event(cwd: Path, *, ts: str = "2030-01-01T12:00:00Z") -> Event:
    return Event(
        ts=ts,
        session="s1",
        project="repo",
        cwd=str(cwd),
        git_branch="main",
        mode="acceptEdits",
        tool="Read",
        kind="fs_read",
        targets=["README.md"],
        mode_source="permissionMode",
    )


def test_gap_commit_is_not_present_but_unclaimed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    first = repo / "first-burst.txt"
    first.write_text("first\n")
    _git(repo, "add", "first-burst.txt")
    _git(
        repo,
        "commit",
        "-m",
        "first burst",
        env={
            "GIT_AUTHOR_DATE": "2030-01-01T12:30:00+00:00",
            "GIT_COMMITTER_DATE": "2030-01-01T12:30:00+00:00",
        },
    )

    gap = repo / "gap-commit.txt"
    gap.write_text("gap\n")
    _git(repo, "add", "gap-commit.txt")
    _git(
        repo,
        "commit",
        "-m",
        "gap commit",
        env={
            "GIT_AUTHOR_DATE": "2030-01-03T12:00:00+00:00",
            "GIT_COMMITTER_DATE": "2030-01-03T12:00:00+00:00",
        },
    )

    second = repo / "second-burst.txt"
    second.write_text("second\n")
    _git(repo, "add", "second-burst.txt")
    _git(
        repo,
        "commit",
        "-m",
        "second burst",
        env={
            "GIT_AUTHOR_DATE": "2030-01-05T12:30:00+00:00",
            "GIT_COMMITTER_DATE": "2030-01-05T12:30:00+00:00",
        },
    )

    events = [
        _event(repo, ts="2030-01-01T12:00:00Z"),
        _event(repo, ts="2030-01-01T13:00:00Z"),
        _event(repo, ts="2030-01-05T12:00:00Z"),
        _event(repo, ts="2030-01-05T13:00:00Z"),
    ]

    result = audit_session(events)

    assert result is not None
    assert result.burst_count == 2
    assert result.measured_duration_seconds == 7200
    assert result.wall_clock_span_seconds == 349200
    assert "first-burst.txt" in result.present_but_unclaimed
    assert "second-burst.txt" in result.present_but_unclaimed
    assert "gap-commit.txt" not in result.present_but_unclaimed
    assert result.gap_changes_excluded == {"gap-commit.txt"}


def test_dirty_paths_outside_window_are_not_present_but_unclaimed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    dirty = repo / "dirty.txt"
    dirty.write_text("committed\n")
    _git(repo, "add", "dirty.txt")
    _git(repo, "commit", "-m", "initial")

    dirty.write_text("uncommitted\n")
    outside_window = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(dirty, (outside_window, outside_window))

    result = audit_session([_event(repo)])

    assert result is not None
    assert "dirty.txt" not in result.present_but_unclaimed
    assert result.unattributed_dirty == {"dirty.txt"}
    assert result.present_side_measured is False


def test_ground_truth_render_reports_excluded_and_not_measured(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    dirty = repo / "dirty.txt"
    dirty.write_text("committed\n")
    _git(repo, "add", "dirty.txt")
    _git(repo, "commit", "-m", "initial")
    dirty.write_text("uncommitted\n")

    result = audit_session([_event(repo)])

    assert result is not None
    rendered = render_results([result])
    assert "unattributed-dirty-excluded: 1" in rendered
    assert "gap-commit-paths-excluded: 0" in rendered
    assert "not-measured-sessions: 1" in rendered
    assert "not-measured" in rendered
    assert "bursts | measured/span" in rendered

    report = render([_event(repo)], [])
    assert "unattributed-dirty-excluded" in report
    assert "gap-commit-paths-excluded" in report
    assert "bursts | measured/span" in report
    assert "not-measured" in report
