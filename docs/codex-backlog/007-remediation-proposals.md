# 007 — Turn findings into gated remediation proposals

## Context

ORCH currently reports what an agent reached and stops. The operator then has to work out what to
change. Most of that work is mechanical: the same twelve hosts appear two hundred times and are not
in the egress allowlist; a write root is missing; an MCP server is undeclared.

This spec closes the loop — findings produce a **proposed policy diff**, gated the same way any
other patch is. It does not apply anything.

## Scope

Create: `orch/remediate.py`, `tests/test_remediate.py`.
Modify: `report.py` (render the proposal section).
Do not modify `scan.py`, `gates.py`, `score.py`, `orch/control_plane.py`.

## Architecture

Given a set of violations, propose the smallest policy change that would resolve the largest number
of them, as a unified diff against `policy.json`:

- **G3 egress** — hosts seen N or more times, grouped, with the count as justification
- **G1 write scope** — a write root that would cover a cluster of out-of-scope writes
- **G7 MCP scope** — servers actually invoked, listed for the operator to name
- **G4 ambient authority / G5 blast radius** — these get a **recommendation in prose, never a
  proposed allowlist entry.** Silencing a credential finding by adding it to `accepted_signals` is
  the tool helping you stop looking.

**Every proposal states what it would stop catching.** A proposal that only says what it fixes is
an argument for its own adoption. The operator needs the cost.

**Rank by violations-resolved-per-line-of-policy.** A one-line change that clears 200 violations
and a twelve-line change that clears 205 are not equivalent.

**Nothing is applied.** Output is a diff and a rationale. The operator applies it, or does not.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. Against the real corpus, the tool emits a valid unified diff against `policy.json` that
   `git apply --check` accepts.
3. Applying the top proposal and re-running the audit reduces violations by the predicted count,
   within a stated tolerance. Show predicted versus actual.
4. No proposal ever adds an `identity.*` signal to `accepted_signals`. Prove with a test.
5. Every proposal renders with: violations resolved, lines of policy added, and **what it would
   stop catching**.

## Do not touch

`score.py`. Do not apply any proposal. Do not commit, branch, or push.
