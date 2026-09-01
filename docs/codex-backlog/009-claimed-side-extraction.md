# 009 — The claimed side is parsing prose as filenames

## Context

Spec 008 fixed the repository-side estimator. The transcript-side estimator is still wrong, and it
is wrong in the way this project has been warned about.

`claimed_but_absent` currently holds 29 entries. Roughly two thirds are not paths:

```
"That is the [[I Initiate in Seasons]] pattern in its purest form:)"
"$SB/smoke.out"
"$SP/QUEUED-on-spec-004.md"
"40:"
```

Three distinct defects, and they need different fixes:

1. **Heredoc bodies are being read as write targets.** `_bash_write_targets()` scans Bash commands
   for `>`, `>>` and `tee`. Inside a `python3 - <<'PY' ... PY` block, prose containing a `>` is
   matched and the following words become a filename. This is the exact defect class the earlier
   bookkeeper build shipped six of — heredoc syntax leaking into extracted fields — and it has now
   recurred in a different tool.
2. **Unexpanded shell variables are recorded as paths.** `$SB/smoke.out` is not a path; it is a
   path the parser cannot know without shell expansion. Recording it as claimed-but-absent asserts
   a file is missing when the truth is the target was never resolved.
3. **Fragments.** `40:` is a grep line prefix that reached the target list.

**Why this matters as much as spec 008 did.** `claimed-but-absent` is the direction that says *the
agent said it wrote something and the repository disagrees* — a tamper or hallucination signal. A
two-thirds-garbage list means that signal cannot be read at all, and worse, it reads as if it can.

## Scope

Modify: `scan.py` (the `_bash_write_targets` helper only), `orch/ground_truth.py`, `tests/`.
Do not modify `gates.py`, `score.py`, `report.py`, `orch/control_plane.py`.

## Architecture

**1. Do not parse inside heredocs.** Before scanning for redirects, strip heredoc bodies from the
command: find `<<` or `<<-` followed by an optionally-quoted delimiter, and drop everything to the
closing delimiter. Nested and multiple heredocs in one command both occur in the real corpus.

**2. Do not claim what you cannot resolve.** A target containing `$VAR`, backticks or `$(...)` is
unresolved, not missing. Classify it `unresolved` and count it separately. Never place it in
`claimed_but_absent`.

**3. Validate the shape of a target before recording it.** A write target is a path. Reject
anything with newlines, wikilink brackets, or a trailing `:` line-number artifact. Rejections are
counted and reported, not dropped silently — a parser that quietly discards is how the count starts
lying again.

**4. Report the three buckets.** `claimed`, `unresolved`, `rejected`. A reader must be able to see
how much of the claimed side was actually interpretable.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. A test feeds a real-shaped Bash command containing a `python3 - <<'PY'` heredoc whose body
   contains a `>` character and prose, and proves no part of the heredoc body appears as a write
   target. **Demonstrate this test fails against the current implementation, behaviourally** — the
   assertion that fails must be the one about targets, not an AttributeError on a new field. Put
   the behavioural assertion first in the test.
3. Against the real corpus, every remaining entry in `claimed_but_absent` is a plausible relative
   path: no newlines, no `[[`, no `$`, no trailing `:`. Assert this programmatically and show the
   command.
4. Report the counts of `unresolved` and `rejected`, and confirm the numbers add up against the
   pre-change total of 29.
5. Sample five surviving `claimed_but_absent` entries and argue one line each for whether the file
   genuinely does not exist. **At least four of five must be defensible.** If they are not, say so
   — that is the successful outcome of this spec, not a failure of it.

## Do not touch

`score.py`. Do not commit, branch, or push.

---

**Note on the test in spec 008.** Its regression test asserted `burst_count` before asserting the
behaviour, so against the old implementation it died with an `AttributeError` rather than failing
on the thing it was testing. The behaviour was confirmed separately and the fix is real, but the
test as written proves less than it appears to. Put behavioural assertions first.
