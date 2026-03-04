#!/usr/bin/env python3
"""Pre-commit hook: verify pyproject.toml version has an entry in RELEASE_NOTES.md.

Run automatically by pre-commit on every commit.  Exits non-zero (blocking the
commit) if the version declared in pyproject.toml does not have a matching
heading in RELEASE_NOTES.md.

Expected RELEASE_NOTES heading format: ## v0.1.2  (date is optional)
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main() -> int:
    """Check that the version in pyproject.toml has a matching heading in RELEASE_NOTES.md."""
    # ── Read version from pyproject.toml ──────────────────────────────────────
    toml_path = ROOT / "pyproject.toml"
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)

    try:
        version = data["tool"]["poetry"]["version"]
    except KeyError:
        print("ERROR: could not find [tool.poetry].version in pyproject.toml")
        return 1

    # ── Check RELEASE_NOTES.md has a matching heading ─────────────────────────
    notes_path = ROOT / "RELEASE_NOTES.md"
    if not notes_path.exists():
        print(f"ERROR: {notes_path.name} not found")
        return 1

    content = notes_path.read_text()

    # Match "## v0.1.2" with optional trailing date/text on the same line
    pattern = re.compile(rf"^##\s+v{re.escape(version)}\b", re.MULTILINE)
    if not pattern.search(content):
        print(
            f"ERROR: RELEASE_NOTES.md has no heading for v{version}.\n"
            f"       Add a '## v{version}' section before committing."
        )
        return 1

    print(f"OK: v{version} found in RELEASE_NOTES.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
