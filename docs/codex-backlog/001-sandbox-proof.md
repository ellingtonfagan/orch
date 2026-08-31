# 001 — Sandbox proof

## Context

Ellington's Codex runs with `sandbox_mode = "danger-full-access"` in `~/.codex/config.toml`. Every
ORCH build task will instead pass `-s workspace-write` per invocation, overriding that global
without editing it.

The plan assumes `workspace-write` gives us two of the article's principles for free: writes
confined to the working root, and **network egress denied by default**. OpenAI's docs say egress is
off unless `[sandbox_workspace_write] network_access = true`, and there is a reported macOS bug
(GH #10390) where enabling it silently fails under the seatbelt sandbox.

**That is a claim, not a fact, on this machine.** Every later spec's safety argument rests on it,
so it gets tested before anything else is built. If egress is not actually denied, we say so and
the plan changes.

## Scope

Create exactly two files:

- `docs/sandbox-proof.md` — the written result
- `pipeline/probe_sandbox.sh` — the probe script, so the result is reproducible

Touch nothing else.

## Architecture

`probe_sandbox.sh` runs a series of bounded probes and records each command and its real output.
It must not use Codex to *report on* Codex — run the probes and read the actual filesystem and
network results. A probe that reports success without evidence is a failed probe.

Probes, each under `-s workspace-write` with `-C` set to a scratch directory:

1. **Write inside the root** — create a file in the working root. Expect: succeeds.
2. **Write outside the root** — attempt to create a file in `$HOME` outside the working root and
   outside any `--add-dir`. Expect: refused. Record the exact refusal.
3. **Egress, default config** — attempt an outbound request to a known-reachable host. Expect:
   refused. Record the exact error.
4. **Egress, with the flag on** — repeat probe 3 with `-c sandbox_workspace_write.network_access=true`.
   This is the GH #10390 test. Record whether the flag takes effect or is silently ignored.
5. **Read outside the root** — attempt to read a file in `$HOME` outside the root. Record the
   result; document whether reads are confined at all, since a credential file being *readable* is
   the finding that matters most for this repository.

Pin the binary explicitly: `~/.npm-global/bin/codex` (0.147.0). Record the
version in the output. Do not use the ChatGPT.app binary — it is a different version.

Note: `-a/--ask-for-approval` does not exist on `codex exec` in 0.147.0. Do not pass it.

## Acceptance

`docs/sandbox-proof.md` contains, for each of the five probes: the literal command, the literal
output, and a one-line verdict. It ends with a section titled "What this means for ORCH" stating
plainly whether `-s workspace-write` can be relied on for (a) write confinement and (b) egress
denial on this machine.

A probe that could not be run is recorded as not-run with the reason. **Do not infer a result from
documentation.** If probe 4 is ambiguous, say it is ambiguous.

## Do not touch

`~/.codex/config.toml`, `~/.claude/settings.json`, any existing file in this repository, anything
under `$SOURCE_REPO`. Do not run any probe with `danger-full-access` or
`--dangerously-bypass-approvals-and-sandbox`.
