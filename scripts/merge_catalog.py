#!/usr/bin/env python3
"""
merge_catalog.py — Merge new extractions into catalog.json with deduplication.

Supports multi-media entries (books, films, music). Deduplication is scoped
to entries of the same media_type — a book and a film can share a title.

Usage:
    python3 scripts/merge_catalog.py new_extractions.json
    python3 scripts/merge_catalog.py new_extractions.json --dry-run
    python3 scripts/merge_catalog.py new_extractions.json --threshold 0.8

Expects new_extractions.json to be an array of objects with at least a "title" field,
following the schema defined in schema.json. Entries missing enrichment fields
(synopsis, themes, etc.) are flagged with needs_review: true.

Deduplication uses difflib.SequenceMatcher for fuzzy title matching.
"""

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
SCHEMA_PATH = REPO_ROOT / "schema.json"

# Fields that indicate an entry is fully enriched
ENRICHMENT_FIELDS = ["synopsis", "themes", "year"]

VALID_MEDIA_TYPES = {"book", "film", "music"}


def load_json(path: Path) -> list | dict:
    with open(path, "r") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Ensure trailing newline
    with open(path, "a") as f:
        f.write("\n")


def normalize_title(title: str) -> str:
    """Normalize a title for comparison: lowercase, strip whitespace/articles."""
    t = title.lower().strip()
    for prefix in ("the ", "a ", "an "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t


def fuzzy_match(a: str, b: str) -> float:
    """Return similarity ratio between two normalized titles."""
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def find_duplicate(new_title: str, existing_titles: list[str], threshold: float) -> str | None:
    """Find the best fuzzy match above threshold. Returns the matching existing title or None."""
    best_ratio = 0.0
    best_match = None
    norm_new = normalize_title(new_title)

    for existing in existing_titles:
        ratio = SequenceMatcher(None, norm_new, normalize_title(existing)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = existing

    if best_ratio >= threshold:
        return best_match
    return None


def needs_enrichment(entry: dict) -> bool:
    """Check if an entry is missing key enrichment fields."""
    for field in ENRICHMENT_FIELDS:
        val = entry.get(field)
        if val is None:
            return True
        if field == "synopsis" and (not val or len(val.strip()) < 20):
            return True
        if field == "themes" and (not val or len(val) == 0):
            return True
    return False


def get_media_type(entry: dict) -> str:
    """Get the media_type of an entry, defaulting to 'book' for backward compatibility."""
    mt = entry.get("media_type", "book")
    return mt if mt in VALID_MEDIA_TYPES else "book"


def build_title_index_by_media_type(catalog: list[dict]) -> dict[str, list[str]]:
    """Build a dict mapping media_type -> list of titles for dedup scoping."""
    index: dict[str, list[str]] = {"book": [], "film": [], "music": []}
    for entry in catalog:
        mt = get_media_type(entry)
        title = entry.get("title", "")
        if title:
            index[mt].append(title)
    return index


# ── Default fields per media type ────────────────────────────────────────────

DEFAULTS_COMMON = {
    "year": None,
    "synopsis": "",
    "themes": [],
    "confidence": "medium",
    "needs_review": True,
    "in_conversation_with": [],
}

DEFAULTS_BY_TYPE = {
    "book": {"author": None},
    "film": {"director": None},
    "music": {"artist": None},
}


def apply_defaults(entry: dict) -> None:
    """Apply default field values based on media_type."""
    mt = get_media_type(entry)
    for field, default in DEFAULTS_COMMON.items():
        entry.setdefault(field, default)
    for field, default in DEFAULTS_BY_TYPE.get(mt, {}).items():
        entry.setdefault(field, default)


def main():
    parser = argparse.ArgumentParser(
        description="Merge new extractions into catalog.json with fuzzy deduplication. "
                    "Deduplication is scoped by media_type."
    )
    parser.add_argument(
        "input_file",
        help="Path to new_extractions.json (array of catalog entries).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview merge without modifying catalog.json.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match threshold (0.0-1.0). Default: 0.85.",
    )
    args = parser.parse_args()

    # Load data
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    new_entries = load_json(input_path)
    if not isinstance(new_entries, list):
        print("Error: input file must contain a JSON array.", file=sys.stderr)
        sys.exit(1)

    catalog = load_json(CATALOG_PATH)
    title_index = build_title_index_by_media_type(catalog)

    # Process each new entry
    added = []
    skipped = []
    flagged = []

    for entry in new_entries:
        title = entry.get("title", "").strip()
        if not title:
            skipped.append({"entry": entry, "reason": "missing title"})
            continue

        mt = get_media_type(entry)

        # Check for duplicates within the same media_type
        existing_titles = title_index.get(mt, [])
        match = find_duplicate(title, existing_titles, args.threshold)
        if match:
            skipped.append({"title": title, "media_type": mt, "reason": f"duplicate of '{match}'"})
            continue

        # Ensure media_type is set
        entry["media_type"] = mt

        # Apply defaults
        apply_defaults(entry)

        # Flag if missing enrichment
        if needs_enrichment(entry):
            entry["needs_review"] = True
            flagged.append(title)

        added.append(entry)
        title_index[mt].append(title)  # prevent intra-batch duplicates

    # Report
    print(f"Merge summary for {input_path.name}:")
    print(f"  Total new entries:  {len(new_entries)}")
    print(f"  Added:              {len(added)}")
    print(f"  Skipped (dupes):    {len([s for s in skipped if 'duplicate' in s.get('reason', '')])}")
    print(f"  Skipped (other):    {len([s for s in skipped if 'duplicate' not in s.get('reason', '')])}")
    print(f"  Needs enrichment:   {len(flagged)}")

    # Breakdown by media type
    type_counts = {}
    for e in added:
        mt = get_media_type(e)
        type_counts[mt] = type_counts.get(mt, 0) + 1
    if type_counts:
        parts = [f"{count} {mt}{'s' if count != 1 else ''}" for mt, count in sorted(type_counts.items())]
        print(f"  By type:            {', '.join(parts)}")

    if skipped:
        print("\nSkipped entries:")
        for s in skipped:
            title = s.get("title", "(no title)")
            mt = s.get("media_type", "")
            mt_label = f" [{mt}]" if mt else ""
            print(f"  \u2717 {title}{mt_label} \u2014 {s['reason']}")

    if flagged:
        print("\nFlagged for enrichment:")
        for t in flagged:
            print(f"  \u2691 {t}")

    if added:
        print("\nNew entries to add:")
        for e in added:
            mt = get_media_type(e)
            print(f"  + [{mt}] {e['title']}")

    if args.dry_run:
        print(f"\n[dry-run] Would add {len(added)} entries to catalog.json. Nothing written.")
        sys.exit(0)

    if not added:
        print("\nNothing to add. Catalog unchanged.")
        sys.exit(0)

    # Merge and save
    catalog.extend(added)
    save_json(CATALOG_PATH, catalog)
    print(f"\n\u2713 catalog.json updated: {len(catalog)} total entries (was {len(catalog) - len(added)})")
    print("  Run 'python3 scripts/regenerate.py' to update CONTEXT.md")


if __name__ == "__main__":
    main()
