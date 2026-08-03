#!/usr/bin/env python3
"""
build_family_slugs.py

Generates site/src/data/family_slugs.json mapping family slugs to requirement markdown contents.
"""

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REQ_DIR = ROOT_DIR / "docs" / "requirements" / "60-problem-families"
OUTPUT_PATH = ROOT_DIR / "site" / "src" / "data" / "family_slugs.json"


def main():
    slugs_data = {}
    if REQ_DIR.exists():
        for req_file in REQ_DIR.glob("*.md"):
            if req_file.name == "template-family.md":
                continue
            slug = req_file.stem
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            slugs_data[slug] = {
                "slug": slug,
                "filename": req_file.name,
                "content": content
            }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(slugs_data, f, indent=2)

    print(f"Generated family_slugs.json with {len(slugs_data)} requirement specs at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
