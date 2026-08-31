# 008 — The session window is wrong, and it is contaminating the only honest check

## Context

Spec 004 fixed one half of the ground-truth estimator and uncovered the other half.

`_window()` computes a session's time range as `[min_timestamp, max_timestamp]` across its events.
For a session that ran once, that is correct. For a **resumed** session it is badly wrong: the
largest audited session spans **15 days** with activity on four of them, and
`git log --since/--until` across that span sweeps in every unrelated commit that landed in the
multi-day gaps.

Spec 004 asserted that the `git log` estimator was "correctly windowed" and told the implementer to
leave it alone. That assertion was wrong. Measured result: `present-but-unclaimed` fell only
2,769 → 2,614, and on three sampled paths from the largest session **two were still noise** — a
subagent-config commit and a bulk unrelated addition, both landing hours after a multi-day gap.

**Why this is the most important open defect.** `ground_truth.py` exists to be the half of the tool
that reads the machine instead of the transcript. Every other check in ORCH is transcript-derived
and shares the transcript's blind spots; this one was supposed to be independent evidence. A
contaminated number here is worse than no number, because it is the one a reader would trust most.

## Scope

Modify: `orch/ground_truth.py`, `report.py`, `tests/test_ground_truth.py`.
Touch nothing else. Do not modify `scan.py`, `gates.py`, `score.py`, `orch/control_plane.py`.

## Architecture

**1. Sessions are not intervals. They are unions of activity bursts.**

Replace the single `[min, max]` window with a set of intervals derived from the event stream:
split whenever the gap between consecutive events exceeds a threshold (start at 2 hours; make it a
named constant with the reasoning in a comment, not a magic number). Query git once per burst and
union the results, rather than once across the whole span.

**2. Report the window you actually used.** Each session's row states how many bursts it was split
into and the total measured duration versus wall-clock span. A session measured as 4 hours across
4 bursts inside a 15-day span is a very different claim from one measured across 15 days, and the
reader cannot tell which they are looking at today.

**3. Attribute commits by author time, and say when you cannot.** A commit landing inside a burst is
attributable; a commit inside a gap is not. Gap commits are excluded and counted, the same way
spec 004 handled unattributed dirty state.

**4. Do not let the number shrink into meaninglessness either.** If bursts are so narrow that
nothing is measurable, the correct output is not-measured, not zero. Spec 004 already established
that rendering; reuse it rather than inventing a second one.

## Acceptance

1. `python3 -m pytest -q tests/` exits zero.
2. A test constructs a session with two bursts separated by a multi-day gap, plus a commit inside
   the gap, and proves that commit does **not** appear in present-but-unclaimed. Demonstrate that
   this test FAILS against the current implementation — a regression test that passes on the broken
   code proves nothing.
3. Re-run against the real corpus. Report the new `present-but-unclaimed`.
4. **The number is not the acceptance criterion. The paths are.** For the largest remaining
   session, sample five paths and argue one line each for whether they are genuinely unaccounted.
   **At least four of five must be defensible as real.** If they are not, report that plainly —
   a smaller contaminated number is still contaminated, and saying so is the successful outcome of
   this spec, not a failure of it.
5. The report states bursts-per-session and measured-versus-span duration.

## Do not touch

`score.py`. Do not commit, branch, or push.

---

**Backlog note.** This makes four open specs against a cap of three. That cap exists because
writing specs faster than they get implemented turns the backlog into a wish list. 008 jumps the
queue ahead of 005-007 because it repairs shipped code that currently prints a number a reader
would believe. Nothing new gets written until it is done.
