"""Deterministic gates over extracted reach events.

One gate, one meaning, one failure — the shape of the DAD Acceptance and Failure
Policy, pointed at runtime reach instead of at patches. No model opinion enters
here. A gate either matched the policy or it did not.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scan import Event


@dataclass
class Violation:
    gate: str
    reason: str
    event: Event

    @property
    def key(self) -> str:
        return f"{self.gate}|{self.reason}"


def load_policy(path: Path) -> dict:
    return json.loads(path.read_text())


def _under(path: str, roots: list[str]) -> bool:
    expanded = [str(Path(r).expanduser()) for r in roots]
    return any(path.startswith(r.rstrip("/") + "/") or path == r for r in expanded)


def evaluate(events: list[Event], policy: dict) -> list[Violation]:
    """Every gate runs against every event. Reached-for-but-errored is not reach."""
    write_roots = policy.get("allowed_write_roots", [])
    protected = [str(Path(p).expanduser()) for p in policy.get("protected_paths", [])]
    egress = set(policy.get("egress_allowlist", []))
    servers = set(policy.get("allowed_mcp_servers", {}))
    accepted = set(policy.get("accepted_signals", []))

    out: list[Violation] = []
    for event in events:
        if event.errored:
            continue

        # G1 write scope — the agent wrote outside the territory it was given.
        for target in event.targets if event.kind == "fs_write" else []:
            if target.startswith("/") and not _under(target, write_roots):
                out.append(Violation("G1.write_scope", f"wrote outside allowed roots: {target}", event))

        # G2 protected path — untouchable regardless of root.
        for target in event.targets:
            if any(target.startswith(p) for p in protected):
                out.append(Violation("G2.protected_path", f"touched protected path: {target}", event))

        # G3 egress — default-deny. Hosts the agent reached that policy never named.
        for host in event.hosts:
            if host not in egress:
                out.append(Violation("G3.egress", f"unallowlisted host: {host}", event))

        # G4/G5 signals — ambient credentials, destructive and publishing actions.
        for signal in event.signals:
            if signal in accepted:
                continue
            gate = "G4.ambient_authority" if signal.startswith("identity.") else "G5.blast_radius"
            out.append(Violation(gate, f"{signal} in {event.tool}", event))

        # G6 tenancy — reach taken while permission checks were off.
        if event.mode in {"bypassPermissions", "acceptEdits"} and event.kind in {"exec", "fs_write", "mcp"}:
            out.append(Violation("G6.tenancy", f"{event.kind} under mode={event.mode}", event))

        # G7 mcp scope — an unnamed external service is standing access by another name.
        if event.kind == "mcp" and event.mcp_server not in servers:
            out.append(Violation("G7.mcp_scope", f"undeclared MCP server: {event.mcp_server}", event))

    return out
