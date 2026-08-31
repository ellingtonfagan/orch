# 006 — Drive the build loop through the control plane

## Context

Specs 001-004 were implemented by Codex, but the loop around Codex was a subagent following a
written brief. That works and it is not deterministic: what advanced the work was a subagent's
judgement about whether acceptance criteria were met.

`NodeHandler = Callable[[NodeContext], Mapping[str, Any]]` in `orch/control_plane.py` is the seam
built for this. This spec fills it, so future specs run through gates rather than through judgement.

## Scope

Create: `pipeline/codex_handler.py`, `pipeline/run_spec.py`, `tests/test_codex_handler.py`.
Do not modify `orch/control_plane.py`, `scan.py`, `gates.py`, `score.py`.

## Architecture

`codex_handler.py` implements a `NodeHandler` that:

1. builds a prompt from the frozen `TaskRequest` plus accepted artifacts so far
2. invokes the pinned Codex binary with `-s workspace-write`, `--output-schema <schema for this
   node kind>`, `-o <last message file>`, `--json`, stdin closed, never `--ephemeral`
3. parses the final message, validates it against the schema in `schemas/`, and returns it

**The handler gets no capabilities.** No git, no commit, no push, no network, no credentials. Its
only product is a proposal returned to the control plane. The control plane applies patches,
enforces scope, and runs verification — the handler never does.

**Sandbox flags are passed explicitly on every invocation and never inherited from
`~/.codex/config.toml`.** Spec 001 established why: `workspace-write` denies egress by default, but
the flag that re-enables it works on this machine, so default-deny is a choice that must keep being
made.

`run_spec.py` takes a spec file, builds a `TaskRequest` with `allowed_files` parsed from the spec's
Scope section and `verification_commands` from its Acceptance section, and runs the fixed route.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero, with the Codex invocation stubbed — no test may call
   a model.
2. A planning node round-trips a real spec into `{"steps": [...]}` that passes the existing gate.
3. A handler returning JSON that violates the schema is **rejected by the control plane**, not
   accepted and repaired. Demonstrate with a deliberately malformed response.
4. A patch touching a file outside the spec's Scope section is rejected. Demonstrate.
5. The handler cannot commit: show that `git log` is unchanged after a full route.
6. One real end-to-end run against a trivial spec, with the journal attached.

## Do not touch

`score.py`. `~/.codex/config.toml`. Do not commit, branch, or push.
