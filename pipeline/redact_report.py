"""Turn a real ORCH report into a shareable sample.

Structure and counts survive; identity does not. Hostnames become categories, MCP server ids
become stable short hashes, absolute paths lose the user. Run this rather than hand-copying a
report, so redaction is mechanical and repeatable instead of a judgement made once under time
pressure.

    python3 pipeline/redact_report.py ~/.orch/reports/report.md docs/sample-report.md
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

CATEGORY_FILE = Path(__file__).resolve().parent.parent / "redaction.local"

# Generic buckets only. The vendors a given machine actually calls are themselves a profile, so
# they live in `redaction.local` (gitignored), one `pattern = category` per line.
CATEGORY: list[tuple[str, str]] = [
    (r"(localhost|127\.0\.0\.1|0\.0\.0\.0)", "localhost"),
    (r"(github|gitlab|bitbucket|githubusercontent|gist)", "code-host"),
    (r"(anthropic|openai|googleapis|azure|cohere)", "model-provider"),
    (r"(pypi|npmjs|rubygems|crates\.io|pythonhosted)", "package-registry"),
]


def _load_local() -> None:
    """Machine-specific vendor patterns, kept out of the published tree."""
    if not CATEGORY_FILE.exists():
        return
    for line in CATEGORY_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        pattern, _, name = line.partition("=")
        CATEGORY.insert(0, (pattern.strip(), name.strip()))


_load_local()


def category(host: str) -> str:
    for pattern, name in CATEGORY:
        if re.search(pattern, host, re.I):
            return name
    return "third-party-host"


def short(value: str) -> str:
    return "mcp-" + hashlib.sha256(value.encode()).hexdigest()[:8]


def redact(text: str) -> str:
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                  lambda m: short(m.group(0)), text)
    text = re.sub(r"/Users/[^/\s|`]+", "~", text)
    text = re.sub(r"^\| ([a-z0-9][a-z0-9._-]*\.[a-z]{2,}) \|",
                  lambda m: f"| {category(m.group(1))} |", text, flags=re.M)
    # Project directories are derived from real paths and name private repositories.
    # Map each to a stable pseudonym so counts stay comparable across a report.
    seen: dict[str, str] = {}

    def pseudonym(match: re.Match) -> str:
        raw = match.group(0)
        if raw not in seen:
            seen[raw] = f"project-{len(seen) + 1:02d}"
        return seen[raw]

    text = re.sub(r"(-Users-|project-)[A-Za-z0-9._-]+", pseudonym, text)
    text = re.sub(r"\bsubagents\b", "project-sub", text)
    return text


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]).expanduser(), Path(sys.argv[2])
    body = redact(src.read_text())
    header = (
        "# Sample report (redacted)\n\n"
        "> Generated from a real run, then passed through `pipeline/redact_report.py`.\n"
        "> Counts and structure are real. Hostnames are replaced by category, MCP server ids by\n"
        "> stable short hashes, and absolute paths by `~`. This is what the tool produces; it is\n"
        "> not a record of any particular machine.\n\n---\n\n"
    )
    dst.write_text(header + body.split("\n", 1)[1].lstrip("\n"))
    print(f"redacted {src} -> {dst}")


if __name__ == "__main__":
    main()
