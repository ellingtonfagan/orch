# Sample report (redacted)

> Generated from a real run, then passed through `pipeline/redact_report.py`.
> Counts and structure are real. Hostnames are replaced by category, MCP server ids by
> stable short hashes, and absolute paths by `~`. This is what the tool produces; it is
> not a record of any particular machine.

---

> [!warning] Severities are provisional.
> `score.severity()` is still the placeholder. Every rating below is a guess until you write the policy yourself.

**5926** tool calls across **24** sessions in **16** projects. 112 were denied or errored and are excluded from reach.

## What the agents could reach

| reach kind | calls |
|---|---|
| exec | 4678 |
| fs_write | 432 |
| other | 288 |
| fs_read | 204 |
| mcp | 155 |
| net | 53 |
| agent | 4 |

### Network egress, observed

| host | calls |
|---|---|
| market-data-vendor | 98 |
| code-host | 16 |
| market-data-vendor | 15 |
| 127.0.0.1 | 12 |
| sports-data-api | 9 |
| market-data-vendor | 8 |
| recruiting-api | 8 |
| model-provider | 8 |
| code-host | 8 |
| market-data-vendor | 5 |
| market-data-vendor | 5 |
| sports-data-api | 5 |
| model-provider | 5 |
| model-provider | 4 |
| sports-data-api | 4 |
| model-provider | 3 |
| recruiting-api | 3 |
| third-party-host | 3 |
| code-host | 3 |
| code-host | 3 |
| third-party-host | 2 |
| localhost | 2 |
| third-party-host | 2 |
| model-provider-2 | 2 |
| model-provider | 2 |

### External services reached via MCP

| server id | calls |
|---|---|
| mcp-beb2dda8 | 63 |
| mcp-6cf6f058 | 20 |
| Claude_Browser | 17 |
| mcp-a2e2c0eb | 15 |
| visualize | 14 |
| ccd_session | 6 |
| mcp-310b93b9 | 5 |
| mcp-3f23fd55 | 4 |
| scheduled-tasks | 4 |
| mcp-registry | 3 |
| mcp-d56d7983 | 3 |
| Claude_in_Chrome | 1 |

### Capability signals

| signal | calls |
|---|---|
| identity.token_var | 1525 |
| third-party-host | 152 |
| third-party-host | 88 |
| third-party-host | 67 |
| network.git_remote | 66 |
| third-party-host | 47 |
| third-party-host | 46 |
| third-party-host | 39 |
| third-party-host | 26 |
| third-party-host | 13 |
| runtime.dynamic_exec | 9 |
| third-party-host | 4 |
| network.mcp_egress | 3 |
| third-party-host | 2 |

## Violations

| gate | violations | modal severity |
|---|---|---|
| G4.ambient_authority | 1594 | high |
| G5.blast_radius | 275 | medium |
| G3.egress | 261 | low |
| G7.mcp_scope | 155 | low |
| G1.write_scope | 28 | medium |

### Worst findings

| severity | gate | reason | project | mode |
|---|---|---|---|---|
| high | G4.ambient_authority | identity.dotenv in Bash | project-01 | unknown |
| high | G4.ambient_authority | identity.token_var in Bash | project-01 | unknown |
| high | G4.ambient_authority | identity.keychain in Bash | project-01 | unknown |
| high | G4.ambient_authority | identity.dotenv in Read | project-02 | unknown |
| high | G4.ambient_authority | identity.dotenv in Edit | project-03 | normal |
| high | G4.ambient_authority | identity.dotenv in AskUserQuestion | project-03 | normal |
| high | G4.ambient_authority | identity.token_var in TaskCreate | project-03 | normal |
| high | G4.ambient_authority | identity.dotenv in Write | project-03 | unknown |
| high | G4.ambient_authority | identity.token_var in CronCreate | project-03 | unknown |
| medium | G5.blast_radius | network.install in Bash | project-04 | normal |
| medium | G5.blast_radius | network.fetch in Bash | project-04 | normal |
| medium | G5.blast_radius | runtime.destructive in Bash | project-04 | normal |
| medium | G5.blast_radius | environment.global in Bash | project-05 | unknown |
| medium | G1.write_scope | wrote outside allowed roots: ~/claude-workflows/AGENTS.md | project-05 | unknown |
| medium | G1.write_scope | wrote outside allowed roots: ~/claude-workflows/README.md | project-05 | unknown |
| medium | G1.write_scope | wrote outside allowed roots: ~/claude-workflows/.gitignore | project-05 | unknown |
| medium | G5.blast_radius | network.mcp_egress in mcp__scheduled-tasks__create_scheduled_task | project-05 | unknown |
| medium | G5.blast_radius | network.mcp_egress in mcp__scheduled-tasks__update_scheduled_task | project-05 | unknown |
| medium | G1.write_scope | wrote outside allowed roots: ~/.claude/projects/project-06 | project-05 | unknown |
| medium | G1.write_scope | wrote outside allowed roots: ~/.claude/projects/project-06 | project-05 | unknown |

## Blast radius by session

| session | project | worst | distinct capabilities | violations |
|---|---|---|---|---|
| 1816497f | project-07 | high | 5 | 284 |
| 77df7f38 | project-08 | high | 5 | 44 |
| 7bf0d6a7 | project-07 | high | 4 | 1499 |
| cb84b226 | project-sub | high | 4 | 183 |
| 85242cce | project-04 | medium | 4 | 111 |
| 8f940e01 | project-09 | high | 4 | 57 |
| bedc851f | project-10 | high | 3 | 40 |
| 60c29028 | project-07 | medium | 3 | 26 |
| 416960d4 | project-01 | high | 3 | 14 |
| bb212446 | project-04 | medium | 3 | 12 |
| 16d32d17 | project-04 | medium | 3 | 12 |
| 13502b53 | project-04 | medium | 3 | 8 |
| 60359fa1 | project-04 | low | 2 | 10 |
| 19be2638 | project-04 | low | 2 | 5 |
| 0313e92c | project-07 | medium | 2 | 3 |
| a251ed9e | project-07 | medium | 1 | 2 |
| 280a1a30 | project-04 | low | 1 | 1 |
| cf275713 | project-07 | medium | 1 | 1 |
| e33966bb | project-09 | medium | 1 | 1 |

## What this does not see

- Reach the transcript never recorded: anything a subagent did in its own context, and anything a hook ran outside a tool call.
- Whether a credential was actually *used*, only that a path or variable name touched one.
- Sessions from before transcript logging, or transcripts already rotated out.
- Blast radius of a tool call that succeeded but whose effect landed elsewhere (a `git push` is one line here and unbounded in the world).
- Its own source. Writing `scan.py` trips `scan.py`'s regexes, so ORCH sessions carry self-inflicted signals. Read them as noise, not reach.
