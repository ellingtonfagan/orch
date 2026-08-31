# 004 — Window the ground-truth estimator

## Context

Spec 003 added `orch/ground_truth.py` as a second, independent estimator: compare what a session's
transcript *claims* was written against what actually changed in the repository. Disagreement is
the signal, and the direction that matters is **present-but-unclaimed** — the repo changed and no
tool call accounts for it.

It currently reports **2,769 present-but-unclaimed across ten sessions**, which is not a finding.
It is an artifact. In `present_change_paths()`:

```python
present.update(_git(repo_root, ["diff", "--name-only"]))
present.update(_git(repo_root, ["diff", "--cached", "--name-only"]))
```

Neither call takes a time window. They return the repository's **current** working-tree and index
state, which is then attributed to every historical session regardless of when that session ran. A
repository that is dirty today contributes every dirty path to a session from three weeks ago. One
audited repository has ~2,500 uncommitted paths; every session measured against it inherits all of
them.

The `git log --since/--until` and mtime estimators in the same function *are* correctly windowed.
These two are not.

**Why this one matters more than its size.** This check exists specifically to be the trustworthy
half — the one that reads the machine instead of the transcript. A number that looks like a finding
and is not is the exact failure the whole tool is built to catch, and it has now occurred five
times in this project's short history: a gate that could not fire, a shell audit that scanned
nothing, a probe script that reported complete after four of five probes never ran, this, and a
link check that matched a stale copy. Each one produced well-formed output standing in for a real
result.

## Scope

Modify: `orch/ground_truth.py`, `report.py` (only if the rendered section needs a new field),
`tests/` (add coverage).

Touch nothing else. Do not modify `scan.py`, `gates.py`, `score.py`, `policy.example.json`,
`PLAN.md` or `AGENTS.md`.

## Architecture

**1. Every estimator must be windowed, or excluded and labelled.**

The uncommitted working tree has no timestamp, so it cannot honestly be attributed to a past
session. Two acceptable resolutions — pick one and say which in your final message:

- include `git diff` output **only** when the session's window is the most recent one for that
  repository, and label those paths as `unattributed_dirty` rather than folding them into
  `present`; or
- drop the unwindowed calls entirely and rely on `git log` plus mtime, both of which are bounded.

Either way the count reported as `present-but-unclaimed` must contain only paths that can be tied
to the session's own time window.

**2. Report what was excluded.** A silently narrower check is how this class of bug survives. The
rendered section must state how many paths were dropped as unattributable and why. A check that
quietly stops looking is the same failure in a new coat.

**3. Make the empty case loud.** If a session's window yields zero present-side paths because the
repository has no commits in range and no files with in-range mtimes, say so explicitly rather than
rendering `0` — `0` reads as "clean" and "could not measure" reads as itself.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. A test proves the specific bug is gone: given a repository with uncommitted changes whose mtimes
   fall **outside** a session's window, those paths do not appear in that session's
   `present-but-unclaimed`. This test must fail against the current implementation — say so, and
   show that it does.
3. Run against the real corpus. `present-but-unclaimed` must drop substantially from 2,769. Report
   the new number and, for the largest remaining session, show three example paths and argue in one
   line each why they are genuinely unaccounted rather than noise.
4. The rendered report states the count of paths excluded as unattributable.
5. A session that cannot be measured is rendered as not-measured, not as zero.

## Do not touch

`score.py`. Anything outside this repository. Do not commit, branch, or push.
