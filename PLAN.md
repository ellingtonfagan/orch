# ORCH — Build Plan (for audit, before any code)

**Status:** proposal. Nothing in this document has been built. Read section 7 first — that is
where your decisions are needed.

**What this is:** a plan to turn the ORCH v0 blast-radius auditor into a real tool, and to build
it using Codex under a deterministic control plane rather than by hand.

---

## 1. What the research changed

Three Sonnet researchers ran against the Codex CLI, orchestration prior art, and the Claude Code
enforcement surface. Four findings changed the plan. Two of them are bugs in the v0 already on disk.

### 1.1 ⚠️ The v0 has a gate that cannot fire

`gates.py` G6 (`tenancy`) reads the standalone `{"type":"mode"}` transcript record and carries it
forward. Measured across all 34 transcripts:

```
standalone "mode" records:   {'normal': 617}      <- every single one
permissionMode field:        {'acceptEdits': 3460, 'auto': 516,
                              'bypassPermissions': 162, 'default': 10}
```

**162 tool calls actually ran under `bypassPermissions`. G6 reported zero.** The standalone record
carries no timestamp, no `uuid`, no `parentUuid` — it cannot be ordered against tool calls even in
principle. The sound field is `permissionMode`, which sits directly on `user` records and is
positioned in the normal stream.

This is worth dwelling on: the gate failed **silently**. It did not error, it did not warn, it
produced a clean report with an empty row. That is precisely the failure mode the orchestration
research names — *policy violations that leave no error in the trace, so nothing signals what to
retry against*. An auditor that can be structurally blind and still look healthy is the thing this
project exists to prevent, and v0 shipped with one.

### 1.2 The v0's stated blind spot was wrong

`report.py` claims subagent reach is invisible. It is not. Subagent transcripts live at
`<session>/subagents/agent-<id>.jsonl` with `isSidechain: true` and an `agentId` field, under the
**same `sessionId`** as the parent, with a `.meta.json` sidecar carrying `toolUseId`, `agentType`,
`spawnDepth` and `model`. `scan.py` already picks them up via `rglob` — 7 files, 267 records.

But it mis-attributes them: `project` is derived from `path.parent.name`, so every subagent file
lands in a fake project called `subagents`. That is why the first report had a session attributed
to `subagents` instead of to the repo it ran in.

Net: reach is **over**-counted into a phantom project and the report **under**-claims what it sees.
Both directions of wrong, in one bug.

### 1.3 Live enforcement is a solved category — cut it

MCP-Scan, Invariant Gateway, MCPGuard, OPA/Rego agent gateways and Cisco AI Defense all sit in
front of tool calls and block. Building a `PreToolUse` enforcement layer re-derives a mature
product. **Dropped from the roadmap.**

What is *not* well covered: scoring a completed transcript against a named control taxonomy.
Langfuse, AgentOps, Phoenix and Traceloop capture traces; none score against OWASP / NIST / ATLAS
IDs. That is the niche, and it is the half already started.

### 1.4 Codex can be held to the Node Contracts mechanically

`codex exec` has `--output-schema <FILE>` (constrains the final message to a JSON Schema), `-o`
(writes it out) and `--json` (JSONL event stream). The the node contracts shapes stop being a
prompt request and become a process-boundary constraint.

**Verified on this machine, not assumed:**

| Fact | Value |
|---|---|
| Binary | `~/.npm-global/bin/codex` → **0.147.0** |
| Second binary | `/Applications/ChatGPT.app/Contents/Resources/codex` → **0.149.0-alpha.4.3** |
| On `PATH`? | **No**, in a non-login shell. Scripts must pin the absolute path. |
| Sandbox modes | `read-only`, `workspace-write`, `danger-full-access` |
| Current config | `sandbox_mode = "danger-full-access"` |
| Rollout corpus | **1,156** files under `~/.codex/sessions/2026/` |
| Rollout record types | `session_meta`, `event_msg`, `response_item`, `world_state`, `turn_context` |

**Correction to the research:** `-a/--ask-for-approval` does **not** exist on `codex exec` in
0.147.0. Only `--dangerously-bypass-approvals-and-sandbox` appears. The plan uses `-s` alone and
promises no approval policy.

---

## 2. Scope: what ORCH is, and is not

**ORCH is a retrospective reach auditor for agent fleets you already run.** It reads transcripts
that already exist, computes what each agent touched against a declared policy, and reports blast
radius in a vocabulary a security buyer recognises.

**In scope**
- Claude Code transcripts (`~/.claude/projects/**`), including subagent files
- Codex rollouts (`~/.codex/sessions/**`) — a second fleet, same question
- A declared policy with default-deny semantics
- Findings mapped to OWASP LLM Top 10 / Agentic ASI / MITRE ATLAS IDs
- A severity policy **you** write

**Explicitly not in scope**
- Live blocking or a `PreToolUse` gateway (§1.3)
- Anything touching a trading execution path
- A hosted service, a database, or a UI
- Reinventing the event vocabulary — see §4.3

---

## 3. The framework: activating Codex on ORCH

This instantiates the spec-driven build loop with the gaps the playbook leaves open
closed. Its own stated failure mode is *"writing specs faster than they get implemented"* — the
phase plan in §5 caps the backlog at three open specs.

### 3.1 The loop

1. **Claude writes a numbered spec** into `docs/codex-backlog/NNN-slug.md` — the format already
   proven at `$SOURCE_REPO/docs/codex-backlog/001-agent-lab-scaffold.md`: Context / Scope /
   Architecture / Acceptance, and explicitly *what not to touch*.
2. **Codex implements against the spec file, never against a chat message**, in an isolated git
   worktree, under `-s workspace-write`.
3. **The control plane gates the result** — schema, declared file scope, `git apply --check`,
   verification commands. Not Claude's judgement and not Codex's claim.
4. **Claude reviews the diff against the spec it wrote** — "is this the thing I asked for", not
   "is this good code".
5. **Standing instructions live in `AGENTS.md`.** Anything explained twice becomes a line there.

### 3.2 The invocation

```bash
~/.npm-global/bin/codex exec \
  -C "$WORKTREE" \
  -s workspace-write \
  -m gpt-5.5 \
  -c model_reasoning_effort=high \
  --json \
  --output-schema "$SCHEMA" \
  -o "$LAST_MSG" \
  "$(cat docs/codex-backlog/NNN-slug.md)" \
  > "$EVENTS"
```

Never `--ephemeral` — it suppresses the rollout file, which is the audit trail. Always pass
`-c model_reasoning_effort=` explicitly rather than trusting `config.toml`, which has drifted once
already.

### 3.3 The sandbox question, which is the first work item

Your Codex runs `danger-full-access`. The tool that is about to build a containment auditor has no
containment.

`workspace-write` confines writes to the working root and, per OpenAI's docs, **disables network by
default**. There is a documented macOS bug (GH #10390) where re-enabling network under
`workspace-write` silently fails. If that holds here, `workspace-write` *is* default-deny egress —
the article's second principle, for free, one flag.

**This is a claim, not a fact, until tested.** Spec 001 tests it empirically and the result decides
whether the build loop can run sandboxed. If it cannot, we say so rather than pretending.

---

## 4. Architecture

### 4.1 The control plane already exists — the decision is where it lives

`$SOURCE_REPO/src/the source package/dev_pipeline.py` (15.8KB) already implements fixed
`ROUTES`, `TaskRequest`, canonical-JSON `Artifact` with SHA-256, `GitPatchWorkspace`,
`SubprocessVerifier` and `PipelineRunner`. Its `NodeHandler = Callable[[NodeContext], Mapping]`
is an unfilled seam. **A Codex adapter is that seam** — which is exactly Phase 2 of
the source project's adoption plan, unbuilt.

Two options, and this is a real decision (§7, D1):

| | **A. Extract to ORCH** | **B. Import from the source package** |
|---|---|---|
| Coupling | ORCH standalone | ORCH depends on the trading repo |
| Risk | Two copies drift | A dev-tool change touches the repo holding trading code |
| Effort | ~half a day | ~an hour |
| Honesty | Matches "no callable edge into order authority" | Blurs it |

### 4.2 What gets built in ORCH

```
ORCH/
  AGENTS.md                  standing instructions for Codex
  docs/codex-backlog/        numbered specs, max 3 open
  schemas/                   JSON Schemas per node kind (--output-schema)
  orch/
    scan_claude.py           Claude transcripts -> events   (fix 1.1, 1.2)
    scan_codex.py            Codex rollouts -> events       (new)
    events.py                one normalised event type, OTel-aligned
    gates.py                 G1-G7, taxonomy-mapped
    policy.json              default-deny
    score.py                 YOURS
    report.py
  pipeline/
    codex_handler.py         the adapter: spec -> codex exec -> artifact
    run_spec.py              CLI
```

### 4.3 Steal, do not build

- **Event vocabulary:** OpenTelemetry GenAI semantic conventions (`gen_ai.agent.id`,
  `gen_ai.request.model`, `gen_ai.usage.*`) in a **CloudEvents** envelope. Write only the
  projection into **OCSF** classes (File / Network / Process / API Activity) — that projection is
  what lets a buyer's SIEM ingest findings, and it is the only layer worth writing.
- **Patch mechanics:** Aider's declared-file + diff format rather than a bespoke one.
- **Determinism test:** Temporal's replay-against-event-history, as the check that the control
  plane is actually deterministic.

### 4.4 Taxonomy mapping — the fundable vocabulary

Per the buyer-vocabulary argument, the same finding is worth more in the register the buyer
already uses:

| Gate | Maps to |
|---|---|
| G3 egress | OWASP **LLM10** Unbounded Consumption; NIST SP 800-53 **SC** |
| G4 ambient authority | OWASP **LLM06** Excessive Agency; OWASP Agentic **ASI03** Identity & Privilege Abuse; NIST **IA** |
| G5 blast radius | OWASP **LLM06**; MITRE **ATLAS** |
| G6 tenancy | CSA **MAESTRO** Layer 4 (Deployment Infrastructure) |
| G7 MCP scope | OWASP Agentic tool-misuse; CSA MAESTRO Layer 7 (Ecosystem Integration) |

Confidence is uneven — some IDs came back marked unverified. Each one gets checked against the
primary source before it ships in a report, or it ships without an ID.

---

## 5. Phases

Each phase is one spec, implemented by Codex, gated by the control plane, reviewed against the
spec. **Backlog capped at three open specs.**

**Spec 001 — Sandbox proof.** Run a bounded Codex task under `-s workspace-write` and empirically
determine (a) whether writes outside the working root are refused, (b) whether network egress is
denied, (c) whether GH #10390 reproduces here. *Acceptance:* a written result with the commands
run and their output. If egress is not denied, the plan changes and says so.

**Spec 002 — Fix the v0 bugs.** Replace the `mode` carry-forward with `permissionMode` off `user`
records; make G6 fire. Fix subagent project attribution via the `.meta.json` sidecar. Correct the
blind-spots section. *Acceptance:* G6 reports ≥1 finding across the corpus (ground truth: 162 calls
ran under `bypassPermissions`); no session is attributed to a project named `subagents`.

**Spec 003 — Codex handler.** Implement `NodeHandler` calling `codex exec` with `--output-schema`,
returning a validated artifact. No git, no commit, no push, no credentials. *Acceptance:* a
planning node round-trips a spec into `{steps: [...]}` that passes the existing gate.

**Spec 004 — Codex rollout scanner.** Parse `~/.codex/sessions/**` into the same normalised event
type. *Acceptance:* one report covering both fleets; Codex's own build runs appear in it.

**Spec 005 — Event schema + taxonomy.** OTel/CloudEvents alignment and OCSF projection; gate→ID
mapping with verified citations only.

**Spec 006 — Dogfood.** ORCH audits the Codex runs that built ORCH. *Acceptance:* the report shows
the sandbox mode each build ran under. This is the honest end state: the tool's first real finding
is about itself.

---

## 6. Risks

- **Fixed routes hard-fail** when one node's output does not fit the next node's contract, with no
  branch to recover. Mitigation: a rejected node stops the route and preserves the worktree.
- **Temperature 0 is not determinism** — ~70% output consistency is the reported figure. The route
  is deterministic; the artifacts are not. the deterministic-development method already says this.
- **Schema drift**: transcripts span Claude Code `2.1.128`–`2.1.247`, 15 patch versions. Parsing
  must be defensive.
- **Codex version skew**: two binaries, different versions. Pin one; record which.
- **The taxonomy IDs may be wrong.** Several came back unverified. Unchecked IDs do not ship.
- **The backlog outruns the build** — the named failure mode of the spec-driven build loop.
  Cap is three.

---

## 7. Decisions I need from you

**D1 — Control plane: extract or import?** §4.1. My lean: **extract**. `dev_pipeline.py` currently
lives inside the package that also holds trading execution, and the whole point of
the execution-path principle is that no callable edge crosses into order authority. A dev tool
that must be edited to build an unrelated project should not live there.

**D2 — Does Codex get to write ORCH at all?** The honest alternative is that I write it directly
and Codex reviews. Using Codex is the more interesting demonstration and the slower path. Your call
whether this is a product or a proof.

**D3 — Do we change your global `sandbox_mode`?** I would rather pass `-s workspace-write` per
invocation and leave `~/.codex/config.toml` alone, so nothing about your other work changes without
you deciding. Say if you want the global default changed too.

**D4 — One fleet or two?** Scoping to Claude transcripts is a script. Adding the 1,156 Codex
rollouts makes it a tool that audits agents generically. Two costs roughly one extra spec.

**D5 — Severity policy.** `score.severity()` is still unwritten. Nothing downstream is honest until
it exists, and I am not writing it — see the signature-is-not-a-check problem.

---

## 8. What I will not do without asking

Commit, push, open a PR, change `~/.claude/settings.json`, change `~/.codex/config.toml`, touch
anything under `$SOURCE_REPO/src/the source package/` other than reading it, or run `codex exec` with
`danger-full-access`.
