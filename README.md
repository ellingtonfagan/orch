# ORCH — Blast Radius Auditor

Answers one question about agents that have already run: **what did they actually reach?**

Built from *The Untrusted Tenant* (Zenla & Huang, Jul 2026) and the Deterministic
Agentic Development playbooks in MASTER. Those playbooks govern what an agent may
**propose**. This governs what an agent **touched**.

## The premise

> An LLM's output is untrusted data. If you are executing actions based on that
> output, you are executing untrusted code.

So the question is not "is the model safe" (a property of weights, unenforceable)
but "what can it reach" (a property of the runtime, enforceable). The condition is
**ambient authority** — standing access the agent never had to earn. This tool
measures that, retrospectively, against transcripts you already have.

## Layout

| File | Role | Trust |
|---|---|---|
| `scan.py` | Extract reach events from `~/.claude/projects/**.jsonl` | Facts. Judges nothing. |
| `policy.example.json` | Write roots, egress allowlist, MCP servers, accepted signals | **Default-deny.** Copy to `policy.json` (gitignored) and edit. |
| `gates.py` | G1–G7. One gate, one meaning, one failure. | Deterministic. No model opinion. |
| `score.py` | Severity + blast radius per session | **Judgement. Currently a placeholder.** |
| `report.py` | Renders inventory → violations → radius → blind spots | Presentation only. |
| `run.py` | CLI | |

The split is the point, and it is the same split as `Control Plane Architecture`:
extraction and gating can be trusted independently of the policy, because neither
one contains an opinion.

## The gates

| Gate | Fails when | Article principle |
|---|---|---|
| G1 `write_scope` | An agent wrote outside `allowed_write_roots` | Tenant isolation |
| G2 `protected_path` | Anything touched a path on the never-list | Tenant isolation |
| G3 `egress` | A host was reached that policy never named | Default-deny the network |
| G4 `ambient_authority` | A credential path or token variable appeared | Kill ambient authority |
| G5 `blast_radius` | Destructive, publishing, escalating or dynamic-exec reach | Measure blast radius |
| G6 `tenancy` | Reach taken while permission checks were off | Assume breach |
| G7 `mcp_scope` | An undeclared external service was invoked | Per-session identity |

## Run it

```bash
cp policy.example.json policy.json      # then edit it for your machine
python3 run.py
```

Findings are written to `~/.orch/reports/` (override with `$ORCH_OUT` or `--out`). **Writing them
inside this repository is refused, not warned about** — an auditor whose output lands in its own
source tree drags whatever the transcripts contained into version control, and stops being able to
audit itself cleanly. `docs/sample-report.md` shows the output shape, redacted.

Filter to one project, which is how you write a policy without drowning:

```bash
python3 run.py --project some-repo --out ~/.orch/reports/some-repo.md
```

Before sharing anything from this repo:

```bash
python3 pipeline/prepublish_check.py    # exits non-zero if identity leaked back in
```

## Order of operations

1. **Scan wide, no policy.** The first report is an inventory, not a verdict.
2. **Write `policy.json` from what you see.** An allowlist guessed in advance is theatre.
3. **Write `score.severity()`.** Until then every rating prints as provisional.
4. Only then consider enforcement (`PreToolUse` hooks) — the allowlist has to be
   real before denying anything is anything but annoying.

## Known blind spots

Listed in every generated report, and kept there deliberately. The largest: this
sees what the transcript recorded, so subagent-internal reach and hook execution
are invisible, and it sees that a credential was *named*, never that it was *used*.
It also trips its own regexes when writing its own source.
