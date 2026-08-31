# AGENTS.md — standing instructions for Codex in this repository

You are implementing ORCH: a retrospective auditing and agentic-oversight tool. Read the spec you
were given in `docs/codex-backlog/`. That spec is the contract. This file is everything you should
not have to be told twice.

## What this repository is

ORCH answers one question about agents that have already run: **what did they actually reach?**
It reads agent transcripts — Claude Code sessions and Codex rollouts — normalises them into reach
events, gates those events against a declared default-deny policy, and reports blast radius.

Read `PLAN.md` before your first task. Section 1 lists two known defects; do not "fix" them
opportunistically, they have their own specs.

## The hard rules

1. **Implement the spec, not the idea behind it.** If the spec is wrong, say so in your final
   message and stop. Do not widen scope because the wider thing is obviously better.
2. **Never write outside the files the spec's Scope section names.** If the work genuinely requires
   another file, stop and say which one and why.
3. **Never commit, push, create a branch, open a PR, or run `gh`.** Promotion is a separate
   authority. Your output is a working tree and a final message.
4. **Never read, print, or copy credentials.** `.env` files, `~/.aws`, `~/.ssh`, keychain, and any
   `*_API_KEY`/`*_TOKEN` value are out of bounds even when they appear in test data. This repository
   parses transcripts that contain live secrets in cleartext — if you encounter one, do not echo it.
5. **Never commit generated artifacts.** `*.jsonl` is gitignored because event dumps carry
   tool-call excerpts verbatim, including a live API key. Do not add exceptions.
6. **Do not touch `~/.claude/settings.json` or `~/.codex/config.toml`.** ORCH reads the machine; it
   does not configure it.
7. **Do not import from, or add a dependency on, `$SOURCE_REPO`.** The control plane is being
   extracted into this repo precisely so that no edge crosses into the repository that holds
   trading execution.

## Style

Match the code already here. Standard library only unless the spec says otherwise. Type hints on
public functions. Module docstrings that say what the module refuses to do, not just what it does —
`scan.py` and `gates.py` are the reference for tone.

Comments explain *why a boundary exists*, not what the line does. If a function encodes a policy
judgement rather than a mechanism, say so in the docstring and name who owns it.

## The separation this repo is built on

Extraction and gating must be trustworthy independently of the policy:

- `scan_*.py` extracts facts. **It judges nothing.** No severity, no thresholds, no opinions.
- `gates.py` applies declared policy. Deterministic. No model calls, no heuristics that drift.
- `score.py` is judgement and belongs to Ellington. **Do not write `severity()`.** If it is still a
  placeholder, leave it. That is deliberate, not an oversight.

## Verification

Run the commands the spec declares, exactly as written. Do not substitute an easier command,
narrow a test selection, or report a pass you did not observe. If the suite was already failing
before your change, say so explicitly and name which tests — "it was already red" is context, not
a pass.

## The failure mode this repository exists to prevent

An oversight tool that reads *reports about* a system rather than the system itself produces a
closed loop that looks like diligence. It has already happened here once, in a sibling project:
a monitor re-fetched the same stale status file for six days and confirmed each time that nothing
had changed, while the answer sat in a log on the same machine.

A gate that cannot fire is worse than no gate, because it reports clean. When you add a check, ask
what would make it silently return nothing, and make that condition loud.
