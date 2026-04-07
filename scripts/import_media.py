#!/usr/bin/env python3
"""
import_media.py — Import films or music from a plain text file into llmbrary.

Supports multiple line formats per media type:

  Films:
    - "Title (Year) - Director"
    - "Title - Director"
    - "Title (Year)"
    - Just "Title"
    - "Director: Title (Year)"

  Music:
    - "Artist - Album (Year)"
    - "Artist - Album"
    - "Album by Artist"
    - "Album by Artist (Year)"
    - Just "Album" or "Title"

Usage:
    python3 scripts/import_media.py --type film films.txt
    python3 scripts/import_media.py --type music albums.txt
    python3 scripts/import_media.py --type film films.txt --dry-run
    python3 scripts/import_media.py --type music albums.txt --format dash
    python3 scripts/import_media.py --type film films.txt --threshold 0.80

Deduplicates against catalog.json entries of the same media_type using fuzzy matching.
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


# ── Fuzzy matching (same approach as import_text.py / merge_catalog.py) ──────

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


# ── Year extraction ──────────────────────────────────────────────────────────

_YEAR_PAREN_RE = re.compile(r"\s*\((\d{4})\)\s*$")
_YEAR_TRAILING_RE = re.compile(r",?\s+(\d{4})\s*$")


def extract_year(text: str) -> tuple[str, int | None]:
    """Extract trailing (YYYY) or , YYYY from text. Returns (cleaned_text, year)."""
    m = _YEAR_PAREN_RE.search(text)
    if m:
        return text[:m.start()].strip(), int(m.group(1))
    m = _YEAR_TRAILING_RE.search(text)
    if m:
        yr = int(m.group(1))
        if 1800 <= yr <= 2100:
            return text[:m.start()].strip(), yr
    return text, None


# ── Film parsers ─────────────────────────────────────────────────────────────

def parse_film_dash(line: str) -> dict | None:
    """Parse: Title (Year) - Director  or  Title - Director"""
    for sep in (" — ", " – ", " - "):
        if sep in line:
            parts = line.split(sep, 1)
            title_part = parts[0].strip()
            director = parts[1].strip() if len(parts) > 1 else None
            title, year = extract_year(title_part)
            if title:
                return {"title": title, "director": director or None, "year": year}
    return None


def parse_film_colon(line: str) -> dict | None:
    """Parse: Director: Title (Year)"""
    if ":" not in line:
        return None
    parts = line.split(":", 1)
    director = parts[0].strip()
    title_part = parts[1].strip() if len(parts) > 1 else ""
    if not title_part or not director:
        return None
    # Director names are short (1-4 words)
    words = director.split()
    if len(words) > 5:
        return None
    title, year = extract_year(title_part)
    return {"title": title, "director": director, "year": year}


def parse_film_title_year(line: str) -> dict | None:
    """Parse: Title (Year) — just title with optional year."""
    title, year = extract_year(line)
    if title:
        return {"title": title, "director": None, "year": year}
    return None


def detect_film_format(line: str) -> str:
    """Auto-detect film line format."""
    for sep in (" — ", " – ", " - "):
        if sep in line:
            return "dash"
    if ":" in line:
        left = line.split(":", 1)[0].strip()
        if len(left.split()) <= 4:
            return "colon"
    return "title-year"


FILM_PARSERS = {
    "dash": parse_film_dash,
    "colon": parse_film_colon,
    "title-year": parse_film_title_year,
}


def parse_film_line(line: str, forced_format: str | None = None) -> dict | None:
    """Parse a single film line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if forced_format and forced_format in FILM_PARSERS:
        result = FILM_PARSERS[forced_format](stripped)
        return result if result else parse_film_title_year(stripped)

    fmt = detect_film_format(stripped)
    parser = FILM_PARSERS.get(fmt, parse_film_title_year)
    result = parser(stripped)
    return result if result else parse_film_title_year(stripped)


# ── Music parsers ────────────────────────────────────────────────────────────

def parse_music_dash(line: str) -> dict | None:
    """Parse: Artist - Album (Year)  or  Artist - Album"""
    for sep in (" — ", " – ", " - "):
        if sep in line:
            parts = line.split(sep, 1)
            artist = parts[0].strip()
            album_part = parts[1].strip() if len(parts) > 1 else ""
            if not album_part:
                return None
            album, year = extract_year(album_part)
            if album and artist:
                return {"title": album, "artist": artist, "year": year}
    return None


def parse_music_by(line: str) -> dict | None:
    """Parse: Album by Artist (Year)"""
    m = re.match(r"^(.+?)\s+by\s+(.+)$", line, re.IGNORECASE)
    if m:
        album_part = m.group(1).strip()
        artist_part = m.group(2).strip()
        album, year_from_album = extract_year(album_part)
        artist, year_from_artist = extract_year(artist_part)
        year = year_from_artist or year_from_album
        if album and artist:
            return {"title": album, "artist": artist, "year": year}
    return None


def parse_music_csv(line: str) -> dict | None:
    """Parse: "Artist","Album","Year" """
    try:
        reader = csv.reader(io.StringIO(line))
        fields = next(reader)
    except (csv.Error, StopIteration):
        return None
    if len(fields) < 2 or not fields[0].strip():
        return None
    result = {"title": fields[1].strip(), "artist": fields[0].strip(), "year": None}
    if len(fields) >= 3 and fields[2].strip():
        try:
            result["year"] = int(fields[2].strip())
        except ValueError:
            pass
    return result


def parse_music_title_only(line: str) -> dict | None:
    """Parse: just the album/title."""
    title, year = extract_year(line)
    if title:
        return {"title": title, "artist": None, "year": year}
    return None


def detect_music_format(line: str) -> str:
    """Auto-detect music line format."""
    if line.startswith('"'):
        return "csv"
    for sep in (" — ", " – ", " - "):
        if sep in line:
            return "dash"
    if re.search(r"\s+by\s+", line, re.IGNORECASE):
        return "by"
    return "title-only"


MUSIC_PARSERS = {
    "dash": parse_music_dash,
    "by": parse_music_by,
    "csv": parse_music_csv,
    "title-only": parse_music_title_only,
}


def parse_music_line(line: str, forced_format: str | None = None) -> dict | None:
    """Parse a single music line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if forced_format and forced_format in MUSIC_PARSERS:
        result = MUSIC_PARSERS[forced_format](stripped)
        return result if result else parse_music_title_only(stripped)

    fmt = detect_music_format(stripped)
    parser = MUSIC_PARSERS.get(fmt, parse_music_title_only)
    result = parser(stripped)
    return result if result else parse_music_title_only(stripped)


# ── Entry builders ───────────────────────────────────────────────────────────

def make_film_entry(parsed: dict) -> dict:
    """Build a catalog-format entry for a film."""
    return {
        "title": parsed["title"],
        "media_type": "film",
        "director": parsed.get("director"),
        "year": parsed.get("year"),
        "source": "text_import",
        "confidence": "medium",
        "synopsis": "",
        "themes": [],
        "in_conversation_with": [],
        "needs_review": True,
        "enrichment_needed": True,
    }


def make_music_entry(parsed: dict) -> dict:
    """Build a catalog-format entry for a music album."""
    return {
        "title": parsed["title"],
        "media_type": "music",
        "artist": parsed.get("artist"),
        "year": parsed.get("year"),
        "source": "text_import",
        "confidence": "medium",
        "synopsis": "",
        "themes": [],
        "in_conversation_with": [],
        "needs_review": True,
        "enrichment_needed": True,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import films or music from a plain text file into llmbrary."
    )
    parser.add_argument(
        "input_file",
        help="Path to text file containing media list.",
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["film", "music"],
        dest="media_type",
        help="Type of media to import: film or music.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview parsed results without writing output file.",
    )
    parser.add_argument(
        "--format",
        default=None,
        help="Force a specific line format instead of auto-detecting. "
             "Films: dash, colon, title-year. Music: dash, by, csv, title-only.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match threshold for deduplication (0.0-1.0). Default: 0.85.",
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

    # Validate format flag
    if args.format:
        valid_formats = list(FILM_PARSERS.keys()) if args.media_type == "film" else list(MUSIC_PARSERS.keys())
        if args.format not in valid_formats:
            print(f"Error: invalid format '{args.format}' for --type {args.media_type}. "
                  f"Valid formats: {', '.join(valid_formats)}", file=sys.stderr)
            sys.exit(1)

    # Select parser and entry builder
    if args.media_type == "film":
        parse_fn = parse_film_line
        make_entry = make_film_entry
        creator_field = "director"
    else:
        parse_fn = parse_music_line
        make_entry = make_music_entry
        creator_field = "artist"

    # Load existing catalog for dedup — only match within same media_type
    existing_titles = []
    if CATALOG_PATH.exists():
        with open(CATALOG_PATH, "r") as f:
            catalog = json.load(f)
        existing_titles = [
            e["title"] for e in catalog
            if e.get("title") and e.get("media_type", "book") == args.media_type
        ]

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
        result = parse_fn(stripped, args.format)
        if result and result.get("title"):
            parsed_entries.append(result)
        else:
            parse_failures.append((lineno, stripped))

    # Deduplicate against catalog and within batch
    new_entries = []
    duplicates = []
    seen_titles = list(existing_titles)

    for parsed in parsed_entries:
        title = parsed["title"]
        match = find_duplicate(title, seen_titles, args.threshold)
        if match:
            duplicates.append((title, match))
            continue
        entry = make_entry(parsed)
        new_entries.append(entry)
        seen_titles.append(title)

    # Summary
    type_label = "films" if args.media_type == "film" else "albums"
    print(f"Media Import Summary ({args.media_type}: {input_path.name}):")
    print(f"  Lines processed:    {total_lines}")
    print(f"  Blank/comment:      {skipped_blank + skipped_comment}")
    print(f"  Successfully parsed:{len(parsed_entries):>4}")
    print(f"  New {type_label} found:  {len(new_entries)}")
    print(f"  Duplicates skipped: {len(duplicates)}")
    if parse_failures:
        print(f"  Parse failures:     {len(parse_failures)}")

    if duplicates:
        print(f"\nDuplicates skipped:")
        for title, match in duplicates:
            print(f"  \u2717 \"{title}\" \u2248 \"{match}\"")

    if parse_failures:
        print("\nCould not parse:")
        for lineno, text in parse_failures:
            print(f"  line {lineno}: {text}")

    if new_entries:
        print(f"\nNew entries to import:")
        for e in new_entries:
            creator = e.get(creator_field)
            creator_part = f" \u2014 {creator}" if creator else ""
            year_part = f" ({e['year']})" if e["year"] else ""
            print(f"  + {e['title']}{creator_part}{year_part}")

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

    print(f"\n\u2713 Wrote {len(new_entries)} entries to {output_path.name}")
    print("  Next: review the output, then run:")
    print(f"    python3 scripts/merge_catalog.py {output_path.name}")


if __name__ == "__main__":
    main()
