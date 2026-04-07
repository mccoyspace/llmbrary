#!/usr/bin/env python3
"""
import_text.py — Import books from a plain text file into llmbrary.

Supports multiple line formats (auto-detected or forced via --format):
  - dash:       Title - Author  or  Title — Author
  - by:         Title by Author
  - comma:      Title, Author
  - paren:      Title (Author)
  - colon:      Author: Title
  - tab:        Title\\tAuthor
  - csv:        "Title","Author"  or  "Title","Author","Year"
  - title-only: Just the title on its own line

Usage:
    python3 scripts/import_text.py booklist.txt
    python3 scripts/import_text.py booklist.txt --dry-run
    python3 scripts/import_text.py booklist.txt --format dash
    python3 scripts/import_text.py booklist.txt --threshold 0.80

Deduplicates against catalog.json using fuzzy matching (difflib.SequenceMatcher).
Outputs new_extractions.json with entries marked source: "text_import".
"""

import argparse
import csv
import io
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
OUTPUT_PATH = REPO_ROOT / "new_extractions.json"

# ── Fuzzy matching (same approach as merge_catalog.py) ──────────────────────

def normalize_title(title: str) -> str:
    """Lowercase, strip whitespace, remove leading articles."""
    t = title.lower().strip()
    for prefix in ("the ", "a ", "an "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return t


def find_duplicate(new_title: str, existing_titles: list[str], threshold: float) -> str | None:
    """Find best fuzzy match above threshold. Returns matching title or None."""
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


# ── Line parsers ────────────────────────────────────────────────────────────

def parse_csv_line(line: str) -> dict | None:
    """Parse CSV-style: "Title","Author" or "Title","Author","Year" """
    try:
        reader = csv.reader(io.StringIO(line))
        fields = next(reader)
    except (csv.Error, StopIteration):
        return None
    if len(fields) < 1 or not fields[0].strip():
        return None
    result = {"title": fields[0].strip(), "author": None, "year": None}
    if len(fields) >= 2 and fields[1].strip():
        result["author"] = fields[1].strip()
    if len(fields) >= 3 and fields[2].strip():
        try:
            result["year"] = int(fields[2].strip())
        except ValueError:
            pass
    return result


def parse_tab_line(line: str) -> dict | None:
    """Parse tab-separated: Title\\tAuthor or Title\\tAuthor\\tYear"""
    parts = line.split("\t")
    if len(parts) < 2:
        return None
    result = {"title": parts[0].strip(), "author": None, "year": None}
    if not result["title"]:
        return None
    if len(parts) >= 2 and parts[1].strip():
        result["author"] = parts[1].strip()
    if len(parts) >= 3 and parts[2].strip():
        try:
            result["year"] = int(parts[2].strip())
        except ValueError:
            pass
    return result


def parse_dash_line(line: str) -> dict | None:
    """Parse: Title - Author  or  Title — Author"""
    # Split on em-dash or spaced en/hyphen dash
    for sep in (" — ", " – ", " - "):
        if sep in line:
            parts = line.split(sep, 1)
            title = parts[0].strip()
            author = parts[1].strip() if len(parts) > 1 else None
            if title:
                return {"title": title, "author": author or None, "year": None}
    return None


def parse_by_line(line: str) -> dict | None:
    """Parse: Title by Author"""
    # Match ' by ' as separator — case insensitive, but 'by' must be standalone
    m = re.match(r"^(.+?)\s+by\s+(.+)$", line, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip()
        if title:
            return {"title": title, "author": author or None, "year": None}
    return None


def parse_comma_line(line: str) -> dict | None:
    """Parse: Title, Author"""
    if "," not in line:
        return None
    parts = line.split(",", 1)
    title = parts[0].strip()
    author = parts[1].strip() if len(parts) > 1 else None
    if title:
        return {"title": title, "author": author or None, "year": None}
    return None


def parse_paren_line(line: str) -> dict | None:
    """Parse: Title (Author)"""
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", line)
    if m:
        title = m.group(1).strip()
        author = m.group(2).strip()
        if title:
            return {"title": title, "author": author or None, "year": None}
    return None


def parse_colon_line(line: str) -> dict | None:
    """Parse: Author: Title"""
    if ":" not in line:
        return None
    parts = line.split(":", 1)
    author = parts[0].strip()
    title = parts[1].strip() if len(parts) > 1 else None
    if title and author:
        return {"title": title, "author": author, "year": None}
    return None


def parse_title_only(line: str) -> dict | None:
    """Parse: just the title."""
    title = line.strip()
    if title:
        return {"title": title, "author": None, "year": None}
    return None


# ── Format detection ────────────────────────────────────────────────────────

# Known author surnames/patterns used to disambiguate "Author: Title" vs other
# colon-containing titles. We detect colon format if the left side looks like
# a person name (1-3 short words, no common title-words).
_TITLE_WORDS = {
    "the", "a", "an", "of", "in", "on", "for", "and", "to", "with",
    "introduction", "guide", "history", "art", "how", "why", "what",
}


def _looks_like_name(text: str) -> bool:
    """Heuristic: does this look like a person's name rather than a title fragment?"""
    words = text.lower().split()
    if not words or len(words) > 4:
        return False
    # Names don't usually start with articles or common title words
    if words[0] in _TITLE_WORDS:
        return False
    # Names are typically short words, often capitalized
    return all(len(w) < 20 for w in words)


def detect_format(line: str) -> str:
    """Auto-detect the most likely format for a single line."""
    stripped = line.strip()

    # CSV: starts with quote
    if stripped.startswith('"'):
        return "csv"

    # Tab-separated
    if "\t" in stripped:
        return "tab"

    # Parenthetical author: ends with (Something)
    if re.search(r"\([^)]+\)\s*$", stripped):
        return "paren"

    # Dash-separated: contains spaced dash/em-dash
    for sep in (" — ", " – ", " - "):
        if sep in stripped:
            return "dash"

    # "by" separator
    if re.search(r"\s+by\s+", stripped, re.IGNORECASE):
        return "by"

    # Colon — only if left side looks like a name
    if ":" in stripped:
        left = stripped.split(":", 1)[0].strip()
        if _looks_like_name(left):
            return "colon"

    # Comma — only if there's exactly one comma and right side looks like a name
    if "," in stripped:
        parts = stripped.split(",")
        if len(parts) == 2 and _looks_like_name(parts[1].strip()):
            return "comma"

    return "title-only"


FORMAT_PARSERS = {
    "dash": parse_dash_line,
    "by": parse_by_line,
    "comma": parse_comma_line,
    "paren": parse_paren_line,
    "colon": parse_colon_line,
    "tab": parse_tab_line,
    "csv": parse_csv_line,
    "title-only": parse_title_only,
}


def parse_line(line: str, forced_format: str | None = None) -> dict | None:
    """Parse a single line, auto-detecting format unless forced."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if forced_format:
        parser = FORMAT_PARSERS.get(forced_format)
        if parser:
            result = parser(stripped)
            # Fall back to title-only if forced parser fails
            return result if result else parse_title_only(stripped)
        return parse_title_only(stripped)

    fmt = detect_format(stripped)
    parser = FORMAT_PARSERS.get(fmt, parse_title_only)
    result = parser(stripped)
    return result if result else parse_title_only(stripped)


# ── Year extraction from title ──────────────────────────────────────────────

def extract_year_from_title(entry: dict) -> dict:
    """If title ends with a parenthetical year like (2019), extract it."""
    title = entry.get("title", "")
    m = re.search(r"\s*\((\d{4})\)\s*$", title)
    if m and entry.get("year") is None:
        entry["year"] = int(m.group(1))
        entry["title"] = title[:m.start()].strip()
    return entry


# ── Entry builder ───────────────────────────────────────────────────────────

def make_catalog_entry(parsed: dict) -> dict:
    """Build a catalog-format entry from parsed line data."""
    return {
        "title": parsed["title"],
        "author": parsed.get("author"),
        "year": parsed.get("year"),
        "source": "text_import",
        "confidence": "medium",
        "synopsis": "",
        "themes": [],
        "in_conversation_with": [],
        "needs_review": True,
        "enrichment_needed": True,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import books from a plain text file into llmbrary."
    )
    parser.add_argument(
        "input_file",
        help="Path to text file containing book list.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview parsed results without writing output file.",
    )
    parser.add_argument(
        "--format",
        choices=list(FORMAT_PARSERS.keys()),
        default=None,
        help="Force a specific line format instead of auto-detecting.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match threshold for deduplication (0.0–1.0). Default: 0.85.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=f"Output file path. Default: {OUTPUT_PATH.name}",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else OUTPUT_PATH

    # Load existing catalog for dedup
    existing_titles = []
    if CATALOG_PATH.exists():
        with open(CATALOG_PATH, "r") as f:
            catalog = json.load(f)
        existing_titles = [e["title"] for e in catalog if e.get("title")]

    # Read and parse input file
    with open(input_path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    total_lines = 0
    skipped_blank = 0
    skipped_comment = 0
    parsed_entries = []
    parse_failures = []

    for lineno, line in enumerate(raw_lines, 1):
        stripped = line.strip()
        if not stripped:
            skipped_blank += 1
            continue
        if stripped.startswith("#"):
            skipped_comment += 1
            continue

        total_lines += 1
        result = parse_line(stripped, args.format)
        if result and result.get("title"):
            result = extract_year_from_title(result)
            parsed_entries.append(result)
        else:
            parse_failures.append((lineno, stripped))

    # Deduplicate against catalog and within batch
    new_entries = []
    duplicates = []
    seen_titles = list(existing_titles)  # copy to track intra-batch dupes

    for parsed in parsed_entries:
        title = parsed["title"]
        match = find_duplicate(title, seen_titles, args.threshold)
        if match:
            duplicates.append((title, match))
            continue
        entry = make_catalog_entry(parsed)
        new_entries.append(entry)
        seen_titles.append(title)

    # Summary
    print(f"Text Import Summary ({input_path.name}):")
    print(f"  Lines processed:    {total_lines}")
    print(f"  Blank/comment:      {skipped_blank + skipped_comment}")
    print(f"  Successfully parsed:{len(parsed_entries):>4}")
    print(f"  New books found:    {len(new_entries)}")
    print(f"  Duplicates skipped: {len(duplicates)}")
    if parse_failures:
        print(f"  Parse failures:     {len(parse_failures)}")

    if duplicates:
        print("\nDuplicates skipped:")
        for title, match in duplicates:
            print(f"  ✗ \"{title}\" ≈ \"{match}\"")

    if parse_failures:
        print("\nCould not parse:")
        for lineno, text in parse_failures:
            print(f"  line {lineno}: {text}")

    if new_entries:
        print(f"\nNew entries to import:")
        for e in new_entries:
            author_part = f" — {e['author']}" if e["author"] else ""
            year_part = f" ({e['year']})" if e["year"] else ""
            print(f"  + {e['title']}{author_part}{year_part}")

    if args.dry_run:
        print(f"\n[dry-run] Would write {len(new_entries)} entries to {output_path.name}. Nothing written.")
        sys.exit(0)

    if not new_entries:
        print("\nNo new entries to import.")
        sys.exit(0)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_entries, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n✓ Wrote {len(new_entries)} entries to {output_path.name}")
    print("  Next: review the output, then run:")
    print(f"    python3 scripts/merge_catalog.py {output_path.name}")


if __name__ == "__main__":
    main()
