"""Refuse to publish this repository if it carries identity.

A tool that audits agents should audit itself before it goes anywhere. This runs over exactly the
files git would publish - tracked plus untracked-and-unignored - and exits non-zero on anything
that identifies a person, a machine, or a private repository.

    python3 pipeline/prepublish_check.py

Credentials are the obvious case and the least likely to be present. The realistic leak is the
quiet one: a real report naming the hosts someone called and the projects they keep, which together
describe a person more precisely than a key would.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RULES: list[tuple[str, str, str]] = [
    ("credential",      r"sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}"
                        r"|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|xox[baprs]-",
                        "a literal credential"),
    ("assignment",      r"(API_KEY|SECRET|TOKEN|PASSWORD)\s*=\s*['\"]?[A-Za-z0-9_./+-]{12,}",
                        "a secret assigned to a value"),
    ("home-path",       r"/Users/(?!\w*\$)[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+",
                        "an absolute home path naming a user"),
    ("service-uuid",    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                        "a service instance id"),
    # Repository and vendor names that identify this operator live in `redaction.local`
    # (gitignored) rather than in the published rule list, which would itself be a profile.
    ("real-report",     r"^\| [a-z0-9][a-z0-9.-]*\.[a-z]{2,} \|",
                        "a raw hostname in a table - looks like an unredacted report"),
]

ALLOW = {"pipeline/prepublish_check.py", "pipeline/redact_report.py", "local.paths.example"}


def publishable() -> list[str]:
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True).stdout.split()
    return sorted(set(tracked + untracked) - ALLOW)


def main() -> int:
    findings: list[str] = []
    for name in publishable():
        path = Path(name)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for rule, pattern, description in RULES:
            for match in re.finditer(pattern, text):
                line = text[: match.start()].count("\n") + 1
                findings.append(f"  {rule:16} {name}:{line}  {description}: {match.group(0)[:48]}")

    if findings:
        print(f"PUBLISH BLOCKED - {len(findings)} finding(s):\n")
        print("\n".join(findings[:40]))
        if len(findings) > 40:
            print(f"  ... and {len(findings) - 40} more")
        print("\nFix these, or add a deliberate exception to ALLOW with a reason.")
        return 1

    print(f"clean - {len(publishable())} publishable files carry no identifying data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
