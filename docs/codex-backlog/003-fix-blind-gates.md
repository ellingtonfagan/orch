# 003 — Fix the two blind gates, and add one that reads the thing itself

## Context

The v0 auditor has two defects documented in `PLAN.md` §1. Both are the same species: the tool
reported clean while being structurally unable to see.

**Defect A — G6 cannot fire.** `scan.py` carries forward the standalone `{"type":"mode"}`
transcript record. Measured across all 34 transcripts that record is `normal` 617 times out of 617.
It has no `timestamp`, no `uuid` and no `parentUuid`, so it cannot be ordered against tool calls
even in principle. The sound field is `permissionMode`, which sits directly on `user` records and
is positioned in the normal stream. Ground truth on this machine:

```
permissionMode: {'acceptEdits': 3460, 'auto': 516, 'bypassPermissions': 162, 'default': 10}
```

162 tool calls ran with permission checks bypassed. G6 reported zero, silently.

**Defect B — subagent misattribution.** Subagent transcripts live at
`<session>/subagents/agent-<id>.jsonl` with `isSidechain: true`, an `agentId` field, the same
`sessionId` as the parent, and an `agent-<id>.meta.json` sidecar carrying `toolUseId`, `agentType`,
`spawnDepth` and `model`. `scan.py` already reads them via `rglob`, but derives `project` from
`path.parent.name`, so all 7 files land in a phantom project called `subagents`. The report also
wrongly claims in its blind-spots section that subagent reach is invisible.

**Defect C — the tool only reads reports.** This is the important one. Transcripts are a record of
what an agent *said it did through a tool call*. Anything that happened outside a tool call — a
subprocess spawned by a script the agent ran, a file written by a build it triggered — is invisible,
and ORCH will report clean. A sibling project already paid for this exact failure: a monitor
re-fetched the same status file for six days, confirming each time that nothing had changed, while
the answer sat in a log on the same machine. **Read the thing itself, not the report about it.**

## Scope

Modify: `scan.py`, `gates.py`, `report.py`.
Create: `orch/ground_truth.py`, `tests/test_scan.py`, `tests/test_gates.py`.
Touch nothing else. **Do not write `score.severity()`** — that is Ellington's, deliberately.

## Architecture

**A.** Replace the mode carry-forward. Attribute `permissionMode` from `user` records by position
in the stream, and record `mode_source` on each event (`"permissionMode"` or `"unknown"`) so an
unattributed event is visibly unattributed rather than silently defaulted. G6 fires on
`bypassPermissions` and on `acceptEdits` for mutating reach.

**B.** Derive `project` from the transcript's `cwd` field rather than the parent directory name,
falling back to the top-level project directory for subagent files. Read the `.meta.json` sidecar
and carry `agentType`, `spawnDepth` and the parent `toolUseId` onto subagent events, so delegated
reach is attributable to the call that spawned it. Correct the blind-spots section: subagent reach
is seen; what is not seen is reach outside a tool call.

**C.** `ground_truth.py` is the second estimator. For a session with a `cwd` inside a git
repository, compare what the transcript *claims* was written (`fs_write` targets, plus paths parsed
out of `Bash` redirects and heredocs) against what actually changed on disk in that window
(`git log --name-only`, `git diff --name-only`, and mtimes). Emit two independent sets and report
the disagreement in both directions:

- claimed-but-absent — the transcript says written, the repo shows nothing
- **present-but-unclaimed — the repo changed and no tool call accounts for it.** This is the finding
  the whole check exists for.

Disagreement is the signal, not either estimate alone. Do not reconcile them silently.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. `python3 run.py` over the real corpus produces a report where G6 has **at least one** finding.
   Ground truth: 162 calls ran under `bypassPermissions`.
3. No session in the report is attributed to a project named `subagents`.
4. Every event carries a `mode_source`; the count of `"unknown"` appears in the report.
5. `ground_truth.py` runs against at least one real session with a git `cwd` and reports both
   disagreement directions, with counts, even when both are zero.
6. The blind-spots section no longer claims subagent reach is invisible, and does state that reach
   outside a tool call is invisible.

## Do not touch

`score.py` (severity is Ellington's). `policy.json`. `PLAN.md`. `AGENTS.md`. Anything under
`$SOURCE_REPO/`. Do not commit; leave a working tree.
