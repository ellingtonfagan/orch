from __future__ import annotations

import json
from pathlib import Path

from scan import scan_file


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


def test_permission_mode_is_carried_from_user_record(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    transcript = tmp_path / "claude-project" / "session.jsonl"
    _write_jsonl(transcript, [
        {"type": "mode", "mode": "normal", "sessionId": "s1"},
        {
            "type": "user",
            "sessionId": "s1",
            "cwd": str(cwd),
            "permissionMode": "bypassPermissions",
            "message": {"content": []},
        },
        {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-08-31T12:00:00Z",
            "cwd": str(cwd),
            "gitBranch": "main",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Bash",
                        "input": {"command": "printf hi > out.txt && printf bye >> logs/out.log"},
                    }
                ]
            },
        },
    ])

    events = scan_file(transcript)

    assert len(events) == 1
    assert events[0].mode == "bypassPermissions"
    assert events[0].mode_source == "permissionMode"
    assert events[0].project == "repo"
    assert events[0].targets == ["logs/out.log", "out.txt"]


def test_event_without_permission_mode_is_explicitly_unknown(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    transcript = tmp_path / "claude-project" / "session.jsonl"
    _write_jsonl(transcript, [
        {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-08-31T12:00:00Z",
            "cwd": str(cwd),
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "a.py"}}
                ]
            },
        },
    ])

    events = scan_file(transcript)

    assert events[0].mode == "unknown"
    assert events[0].mode_source == "unknown"


def test_subagent_project_and_sidecar_attribution(tmp_path: Path) -> None:
    cwd = tmp_path / "real-project"
    cwd.mkdir()
    transcript = tmp_path / "claude-project" / "session-id" / "subagents" / "agent-a.jsonl"
    transcript.with_suffix(".meta.json").parent.mkdir(parents=True, exist_ok=True)
    transcript.with_suffix(".meta.json").write_text(json.dumps({
        "toolUseId": "parent-tool",
        "agentType": "general-purpose",
        "spawnDepth": 1,
        "model": "sonnet",
    }))
    _write_jsonl(transcript, [
        {
            "type": "user",
            "sessionId": "s1",
            "cwd": str(cwd),
            "permissionMode": "acceptEdits",
            "message": {"content": []},
        },
        {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-08-31T12:00:00Z",
            "cwd": str(cwd),
            "isSidechain": True,
            "agentId": "agent-a",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "Write", "input": {"file_path": "a.py"}}
                ]
            },
        },
    ])

    events = scan_file(transcript)

    assert events[0].project == "real-project"
    assert events[0].agent_type == "general-purpose"
    assert events[0].spawn_depth == 1
    assert events[0].parent_tool_use_id == "parent-tool"


def test_subagent_without_cwd_falls_back_to_top_level_project(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-project" / "session-id" / "subagents" / "agent-a.jsonl"
    _write_jsonl(transcript, [
        {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-08-31T12:00:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "a.py"}}
                ]
            },
        },
    ])

    events = scan_file(transcript)

    assert events[0].project == "claude-project"
