# 002 — Extract the control plane into ORCH

## Context

A working deterministic control plane already exists at
`$SOURCE_REPO/src/the source package/dev_pipeline.py` (~15.8KB). It
provides fixed `ROUTES`, `TaskRequest`, canonical-JSON `Artifact` with SHA-256 hashing,
`GitPatchWorkspace`, `SubprocessVerifier` and `PipelineRunner`. Its
`NodeHandler = Callable[[NodeContext], Mapping[str, Any]]` is an unfilled seam.

It currently lives inside the Python package that also contains trading execution. Ellington's
standing principle is that no callable edge crosses into order authority. A development tool that
must be edited to build an unrelated project should not live in that package.

**This is a move, not a rewrite.** Behaviour must not change.

## Scope

Create:

- `orch/control_plane.py` — the extracted module
- `tests/test_control_plane.py` — tests that pin the behaviour

Read, but do not modify, `$SOURCE_REPO/src/the source package/dev_pipeline.py`. Do not add ORCH as a
dependency of that repo, or that repo as a dependency of ORCH.

## Architecture

Copy the module. Change only what the move requires:

- module docstring updated to say where it came from and why it moved
- imports adjusted if any are `the source package`-relative
- nothing renamed, no signatures changed, no routes altered, no gates loosened

The extracted module keeps every invariant from the original: a node never writes outside
`allowed_files`; a failed node ends the route immediately; high and blocker findings reject
mutating routes; artifacts are hashed after canonical JSON serialisation; the workspace receiving
patches is the workspace running verification.

Add nothing. In particular do **not** implement a Codex handler here — that is spec 003.

## Acceptance

1. `python3 -m pytest -q tests/test_control_plane.py` exits zero.
2. Tests cover, at minimum: route selection is fixed per task kind; an out-of-allowlist path in a
   patch is rejected; a declared `changed_files` list that disagrees with the parsed diff is
   rejected; a non-zero verification exit stops the route; a `high` finding rejects a mutating
   route but is a successful result for a review-only task.
3. A diff of `orch/control_plane.py` against the original shows only the changes listed above.
   Include that diff summary in your final message.

## Do not touch

Anything under `$SOURCE_REPO/` (read-only). `scan.py`, `gates.py`, `score.py`, `report.py`,
`run.py`, `policy.json` — those are spec 003's territory.
