# 005 — Run the audit itself as a gated route

## Context

`orch/control_plane.py` is extracted, tested, and reachable from nothing. This spec makes the
auditor run *through* it, so an ORCH finding stops being a line of prose in a markdown file and
becomes an artifact with a hash, a route, and a journal behind it.

The reason is the vault's own: a review is only worth something when the reader gets the request,
the evidence, the verification record and the findings **together**. A finding you cannot replay is
a claim. A finding with a hashed artifact chain is evidence.

## Scope

Create: `orch/audit_route.py`, `tests/test_audit_route.py`.
Modify: `run.py` (to drive the route), `report.py` (to render provenance).
Do not modify `scan.py`, `gates.py`, `score.py`, `orch/control_plane.py`, `orch/ground_truth.py`.

## Architecture

Add an `AUDIT` task kind whose fixed route is:

```
scan -> gate -> ground-truth -> score -> report
```

Each stage is a node returning a structured artifact that the control plane hashes with the
existing canonical-JSON SHA-256 path. Reuse `Artifact`, `NodeRecord` and the JSONL journal as they
are — do not fork them.

Node contracts:

- `scan`   -> `{"events": [...], "counts": {...}}`
- `gate`   -> `{"violations": [...], "policy_hash": "..."}`
- `ground-truth` -> the existing disagreement record
- `score`  -> `{"severities": {...}, "provisional": true|false}`
- `report` -> `{"path": "...", "content_hash": "..."}`

**The policy must be hashed and recorded.** A finding is only interpretable against the policy that
produced it; a report that does not name its policy version is not replayable.

**Nothing here may call a model.** Every node is deterministic. This route exists to make the
audit reproducible, and a model in the chain removes exactly that property.

`score` stays provisional until `score.severity()` is written; the route records
`provisional: true` rather than pretending.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. Running the audit twice over an unchanged corpus and an unchanged policy produces **identical
   artifact hashes** for every node. Show both runs' hashes.
3. Changing one line of the policy changes the `gate` artifact hash and the `policy_hash`, and
   nothing else changes that should not. Show the before and after.
4. The journal is a valid JSONL file with one record per node, each carrying node kind, status and
   artifact hash.
5. The rendered report names the policy hash and the route's artifact hashes.
6. A failing node stops the route and the journal shows where it stopped.

## Do not touch

`score.py`. Anything outside this repository. Do not commit, branch, or push.
