"""Render a blast radius report: reach inventory, then violations, then radius."""
from __future__ import annotations

from collections import Counter, defaultdict

from gates import Violation
from orch.ground_truth import audit_events, format_duration
from scan import Event
from score import PROVISIONAL, SEVERITIES, session_radius, severity


def _table(rows: list[tuple], headers: tuple) -> list[str]:
    if not rows:
        return ["_none_", ""]
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return out + [""]


def render(events: list[Event], violations: list[Violation]) -> str:
    lines: list[str] = ["# Blast Radius Report", ""]
    if PROVISIONAL:
        lines += ["> [!warning] Severities are provisional.",
                  "> `score.severity()` is still the placeholder. Every rating below is a guess "
                  "until you write the policy yourself.", ""]

    executed = [e for e in events if not e.errored]
    lines += [
        f"**{len(events)}** tool calls across **{len({e.session for e in events})}** sessions "
        f"in **{len({e.project for e in events})}** projects. "
        f"{len(events) - len(executed)} were denied or errored and are excluded from reach.",
        "",
        "## What the agents could reach", "",
    ]

    kinds = Counter(e.kind for e in executed)
    lines += _table(sorted(kinds.items(), key=lambda x: -x[1]), ("reach kind", "calls"))

    hosts = Counter(h for e in executed for h in e.hosts)
    lines += ["### Network egress, observed", ""]
    lines += _table(hosts.most_common(25), ("host", "calls"))

    servers = Counter(e.mcp_server for e in executed if e.kind == "mcp" and e.mcp_server)
    lines += ["### External services reached via MCP", ""]
    lines += _table(servers.most_common(), ("server id", "calls"))

    signals = Counter(s for e in executed for s in e.signals)
    lines += ["### Capability signals", ""]
    lines += _table(signals.most_common(), ("signal", "calls"))

    mode_sources = Counter(e.mode_source for e in events)
    lines += ["### Permission mode attribution", ""]
    lines += _table(
        sorted(mode_sources.items(), key=lambda x: (x[0] != "unknown", x[0])),
        ("mode_source", "calls"),
    )

    subagents = Counter(e.agent_type for e in executed if e.agent_type)
    lines += ["### Subagent reach attribution", ""]
    lines += _table(subagents.most_common(), ("agent type", "calls"))

    lines += ["## Violations", ""]
    by_gate: dict[str, list[Violation]] = defaultdict(list)
    for v in violations:
        by_gate[v.gate].append(v)
    lines += _table(
        sorted(((g, len(vs), Counter(severity(v) for v in vs).most_common(1)[0][0])
                for g, vs in by_gate.items()), key=lambda x: -x[1]),
        ("gate", "violations", "modal severity"),
    )

    lines += ["### Worst findings", ""]
    ranked = sorted(violations, key=lambda v: SEVERITIES.index(severity(v)))
    seen: set[str] = set()
    top: list[tuple] = []
    for v in ranked:
        if v.key in seen:
            continue
        seen.add(v.key)
        top.append((severity(v), v.gate, v.reason[:90], v.event.project[:40], v.event.mode))
        if len(top) == 20:
            break
    lines += _table(top, ("severity", "gate", "reason", "project", "mode"))

    lines += ["## Blast radius by session", ""]
    per_session: dict[str, list[Violation]] = defaultdict(list)
    for v in violations:
        per_session[v.event.session].append(v)
    rows = []
    for session, vs in per_session.items():
        radius = session_radius(vs)
        rows.append((session[:8], vs[0].event.project[:38], radius["worst"],
                     radius["capability_count"], radius["total"]))
    rows.sort(key=lambda r: (-r[3], -r[4]))
    lines += _table(rows[:30], ("session", "project", "worst", "distinct capabilities", "violations"))

    lines += ["## Ground truth disagreement", ""]
    ground_truth = audit_events(executed)
    claimed_absent = sum(len(r.claimed_but_absent) for r in ground_truth)
    present_unclaimed = sum(len(r.present_but_unclaimed) for r in ground_truth)
    unattributed_dirty = sum(len(r.unattributed_dirty) for r in ground_truth)
    gap_changes = sum(len(r.gap_changes_excluded) for r in ground_truth)
    not_measured = sum(1 for r in ground_truth if not r.present_side_measured)
    lines += _table(
        [
            ("audited_sessions", len(ground_truth)),
            ("claimed-but-absent", claimed_absent),
            ("present-but-unclaimed", present_unclaimed),
            ("unattributed-dirty-excluded", unattributed_dirty),
            ("gap-commit-paths-excluded", gap_changes),
            ("not-measured-sessions", not_measured),
        ],
        ("direction", "count"),
    )
    lines += [
        "Current working-tree and index paths are excluded as unattributed_dirty because git gives "
        "them no timestamp that ties them to a historical session.",
        "Committed paths whose author time lands between activity bursts are excluded as gap "
        "commits, not attributed to the resumed session.",
        "",
    ]
    lines += _table(
        [
            (
                r.session[:8],
                r.project[:38],
                r.burst_count,
                f"{format_duration(r.measured_duration_seconds)}/"
                f"{format_duration(r.wall_clock_span_seconds)}",
                len(r.claimed_writes),
                len(r.present_changes),
                len(r.unattributed_dirty),
                len(r.gap_changes_excluded),
                "measured" if r.present_side_measured else "not-measured",
                len(r.claimed_but_absent),
                len(r.present_but_unclaimed) if r.present_side_measured else "not-measured",
            )
            for r in ground_truth[:30]
        ],
        (
            "session",
            "project",
            "bursts",
            "measured/span",
            "claimed writes",
            "present changes",
            "excluded dirty",
            "excluded gap",
            "present side",
            "claimed-but-absent",
            "present-but-unclaimed",
        ),
    )

    lines += ["## What this does not see", "",
              "- Reach outside a tool call is invisible: subprocesses spawned by scripts, build steps, "
              "hooks, and other side effects that no tool call records.",
              "- Subagent reach is included when its transcript exists; missing or rotated transcripts "
              "remain outside the evidence set.",
              "- Whether a credential was actually *used*, only that a path or variable name touched one.",
              "- Sessions from before transcript logging, or transcripts already rotated out.",
              "- Blast radius of a tool call that succeeded but whose effect landed elsewhere "
              "(a `git push` is one line here and unbounded in the world).",
              "- Its own source. Writing `scan.py` trips `scan.py`'s regexes, so ORCH sessions "
              "carry self-inflicted signals. Read them as noise, not reach.", ""]
    return "\n".join(lines)
