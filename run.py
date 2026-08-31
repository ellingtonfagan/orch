"""CLI: python3 run.py [--project SUBSTR] [--policy policy.json] [--out PATH]

Findings never land inside this repository. An auditor that writes its results into its own
source tree is the same category error as a monitor that watches the monitor: the output becomes
part of the thing being measured, and it drags whatever the transcripts contained — hostnames,
paths, credentials in tool-call excerpts — into version control.

Default output is $ORCH_OUT, else ~/.orch/reports. Writing inside the repo is refused, not warned
about.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gates import evaluate, load_policy
from report import render
from scan import TRANSCRIPT_ROOT, scan_all

HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = Path(os.environ.get("ORCH_OUT", Path.home() / ".orch" / "reports"))


def _refuse_if_inside_repo(path: Path) -> Path:
    """Findings outside the operating scope. This is a gate, not a preference."""
    resolved = path.resolve()
    if resolved == HERE or HERE in resolved.parents:
        sys.exit(
            f"refusing to write findings inside the repository: {resolved}\n"
            f"findings belong outside the operating scope — try --out {DEFAULT_OUT_DIR}"
        )
    return resolved


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit what your agents actually reached.")
    ap.add_argument("--project", help="substring filter on the transcript project directory")
    ap.add_argument("--policy", type=Path, default=HERE / "policy.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR / "report.md")
    ap.add_argument("--events", type=Path, help="also dump raw events as JSONL")
    ap.add_argument("--root", type=Path, default=TRANSCRIPT_ROOT)
    args = ap.parse_args()

    out = _refuse_if_inside_repo(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    events = scan_all(args.root, args.project)
    violations = evaluate(events, load_policy(args.policy))
    out.write_text(render(events, violations))

    if args.events:
        # Event dumps carry tool-call excerpts verbatim and have been observed to contain live
        # credentials. Same rule, stated again because this is the more dangerous artifact.
        events_path = _refuse_if_inside_repo(args.events)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("w") as fh:
            for event in events:
                fh.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")

    print(f"{len(events)} events, {len(violations)} violations -> {out}")


if __name__ == "__main__":
    main()
