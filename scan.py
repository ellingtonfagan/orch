"""Extract reach events from Claude Code transcripts.

An LLM's output is untrusted data; acting on it is executing untrusted code.
This module judges nothing. It answers one question per tool call: what did the
agent actually touch? Judgement lives in gates.py; severity lives in score.py.

Kept deliberately separate so the extractor can be trusted independently of the
policy, the same split as Control Plane Architecture: synthesis vs. authority.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}
NET_TOOLS = {"WebFetch", "WebSearch"}

# (signal, category, pattern). Categories map to the article's escape paths:
# runtime, network, identity, environment.
SIGNALS: list[tuple[str, str, re.Pattern]] = [
    ("network.fetch",        "network",     re.compile(r"\b(curl|wget|nc|ssh|scp|rsync)\b")),
    ("network.install",      "network",     re.compile(r"\b(pip3?|uv|npm|pnpm|yarn|brew|cargo|go)\s+(install|add|get)\b")),
    ("network.git_remote",   "network",     re.compile(r"\bgit\s+(push|pull|fetch|clone|remote)\b")),
    ("identity.dotenv",      "identity",    re.compile(r"(^|[\s/\"'])\.env\b|\.aws/credentials|\.ssh/|id_rsa|\.netrc|\.pgpass")),
    ("identity.token_var",   "identity",    re.compile(r"\b[A-Z0-9_]*(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z0-9_]*\b")),
    ("identity.keychain",    "identity",    re.compile(r"\bsecurity\s+find-\w*password\b|\bkeychain\b|\bgh\s+auth\s+token\b")),
    ("runtime.destructive",  "runtime",     re.compile(r"\brm\s+-[a-z]*[rf]|\bgit\s+(clean\s+-[a-z]*f|reset\s+--hard)|\btrash\b|\bDROP\s+TABLE\b|--delete\b|\bshred\b|\btruncate\b")),
    ("runtime.publish",      "runtime",     re.compile(r"\bgit\s+push\b|\bgh\s+(pr\s+create|release|repo\s+create)\b|\bnpm\s+publish\b|\btwine\s+upload\b")),
    ("runtime.commit",       "runtime",     re.compile(r"\bgit\s+commit\b")),
    ("runtime.dynamic_exec", "runtime",     re.compile(r"\|\s*(sudo\s+)?(ba)?sh\b|\beval\s|\bbash\s+<\(|\bcurl[^|]*\|\s*python")),
    ("runtime.escalate",     "runtime",     re.compile(r"\bsudo\b|\bchmod\s+777\b|\blaunchctl\b|\bdefaults\s+write\b|\bcsrutil\b")),
    ("environment.global",   "environment", re.compile(r"\bcrontab\b|~/\.zshrc|~/\.bashrc|~/\.claude/settings|/Library/LaunchAgents")),
]

# MCP tool verbs that leave the machine or cannot be undone from here.
MCP_EGRESS_VERB = re.compile(
    r"(send|reply|forward|post|publish|share|create|update|delete|trash|deploy|invoke|upload|spam)",
    re.I,
)

URL_HOST = re.compile(r"https?://([A-Za-z0-9._\-]+)")


@dataclass
class Event:
    """One thing an agent reached for. Not yet a finding."""
    ts: str
    session: str
    project: str
    cwd: str
    git_branch: str | None
    mode: str                      # permission mode in force when it ran
    tool: str
    kind: str                      # fs_write | fs_read | exec | net | mcp | agent
    targets: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    mcp_server: str | None = None
    errored: bool = False          # denied or failed -> reached for, did not reach
    excerpt: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _signals_for(text: str) -> list[str]:
    return [name for name, _cat, pat in SIGNALS if pat.search(text)]


def _blocks(record: dict) -> list[dict]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _errored_tool_ids(records: list[dict]) -> set[str]:
    """Tool calls whose result came back an error, including permission denials."""
    bad: set[str] = set()
    for record in records:
        for block in _blocks(record):
            if block.get("type") == "tool_result" and block.get("is_error"):
                bad.add(block.get("tool_use_id"))
    return bad


def _classify(tool: str, tool_input: dict) -> tuple[str, list[str], list[str], list[str], str | None]:
    """-> (kind, targets, hosts, signals, mcp_server)"""
    blob = json.dumps(tool_input, ensure_ascii=False)
    hosts = sorted(set(URL_HOST.findall(blob)))

    if tool.startswith("mcp__"):
        parts = tool.split("__")
        server = parts[1] if len(parts) > 2 else "unknown"
        verb = parts[-1]
        signals = ["network.mcp_egress"] if MCP_EGRESS_VERB.search(verb) else []
        return "mcp", [verb], hosts, signals, server

    if tool in WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return "fs_write", [path] if path else [], hosts, _signals_for(path), None

    if tool in READ_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("pattern") or ""
        return "fs_read", [path] if path else [], hosts, _signals_for(path), None

    if tool in NET_TOOLS:
        url = tool_input.get("url") or tool_input.get("query") or ""
        return "net", [url], hosts or sorted(set(URL_HOST.findall(url))), [], None

    if tool == "Bash":
        command = tool_input.get("command", "")
        return "exec", [], hosts, _signals_for(command), None

    if tool in {"Agent", "Workflow", "Task"}:
        # A subagent inherits the parent's reach without re-approving it.
        return "agent", [tool_input.get("subagent_type") or tool_input.get("description", "")], hosts, ["runtime.delegated"], None

    return "other", [], hosts, _signals_for(blob), None


def scan_file(path: Path) -> list[Event]:
    records: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    errored = _errored_tool_ids(records)
    project = path.parent.name
    mode = "unknown"
    events: list[Event] = []

    for record in records:
        # Mode records are emitted inline; carry the last one forward. A run in
        # bypassPermissions is ambient authority by definition.
        if record.get("type") == "mode" and record.get("mode"):
            mode = record["mode"]
            continue

        for block in _blocks(record):
            if block.get("type") != "tool_use":
                continue
            tool = block.get("name", "")
            tool_input = block.get("input") or {}
            kind, targets, hosts, signals, server = _classify(tool, tool_input)
            excerpt = json.dumps(tool_input, ensure_ascii=False)[:300]
            events.append(Event(
                ts=record.get("timestamp", ""),
                session=record.get("sessionId", path.stem),
                project=project,
                cwd=record.get("cwd", ""),
                git_branch=record.get("gitBranch"),
                mode=mode,
                tool=tool,
                kind=kind,
                targets=[t for t in targets if t],
                hosts=hosts,
                signals=signals,
                mcp_server=server,
                errored=block.get("id") in errored,
                excerpt=excerpt,
            ))
    return events


def scan_all(root: Path = TRANSCRIPT_ROOT, project_filter: str | None = None) -> list[Event]:
    events: list[Event] = []
    for path in sorted(root.rglob("*.jsonl")):
        if project_filter and project_filter not in path.parent.name:
            continue
        events.extend(scan_file(path))
    return events
