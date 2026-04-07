#!/usr/bin/env python3
"""
import_filenames.py — Import films from a directory listing of filenames.

Parses messy filenames to extract title, year, and director. Handles:
- Dot-separated names (The.Godfather.1972.mkv)
- Bracketed metadata ([1080p], [BluRay], [Director])
- Parenthetical years and directors
- "Director - Title" and "Title - Director" patterns
- Resolution/codec junk stripping
- Deduplication against existing catalog.json

Usage:
    python3 scripts/import_filenames.py films.txt
    python3 scripts/import_filenames.py films.txt --dry-run
"""

import json
import re
import sys
import os
from difflib import SequenceMatcher
from pathlib import Path

# --- Configuration ---
EXTENSIONS = {'.mkv', '.avi', '.mp4', '.m4v', '.mov', '.wmv', '.flv', '.webm', '.ts', '.mpg', '.mpeg', '.srt'}
JUNK_PATTERNS = [
    # Resolution and quality
    r'\b(1080[pi]|720[pi]|2160[pi]|4[Kk]|UHD)\b',
    r'\b(BluRay|Blu-Ray|BDRip|BRRip|DVDRip|HDRip|WEBRip|WEB-DL|HDTV|PDTV|CAM|TS|DVDSCR)\b',
    r'\b(x264|x265|h\.?264|h\.?265|HEVC|AVC|AAC|AC3|DTS|FLAC|MP3|LPCM)\b',
    r'\b(REMUX|REMASTERED|PROPER|EXTENDED|UNRATED|DIRECTORS\.?CUT)\b',
    r'\b(10bit|8bit|HDR|HDR10|Atmos|TrueHD|DDP?5\.1|2\.0|7\.1)\b',
    r'\b(ENG|SUBS?|SUBBED|DUBBED|MULTI|FRENCH|GERMAN|ITALIAN|SPANISH|JAPANESE)\b',
    r'\b(FULL\s*MOVIE)\b',
    r'\[(?:1080p|720p|2160p|4K|BluRay|BDRip|x264|x265|HEVC)\]',
    # Common release group tags
    r'\b(YIFY|RARBG|FGT|EVO|SPARKS|GECKOS|AMIABLE|PublicHD|GalaxyRG)\b',
    r'-\s*\w{2,10}$',  # trailing release group like "- SPARKS"
]
SKIP_ENTRIES = {'untitled', 'tiamarco_final_h264', 'out of the funrace'}

# Star Wars name corrections (filenames have swapped episode names)
STAR_WARS_CORRECTIONS = {
    'attack of the clones': ('Star Wars: Episode I - The Phantom Menace', 1999),
    'the phantom menace': ('Star Wars: Episode II - Attack of the Clones', 2002),
    'revenge of the sith': ('Star Wars: Episode III - Revenge of the Sith', 2005),
}


def normalize_title(title):
    """Normalize for comparison: lowercase, strip articles, punctuation."""
    t = title.lower().strip()
    t = re.sub(r'^(the|a|an)\s+', '', t)
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def fuzzy_match(a, b, threshold=0.85):
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= threshold


def strip_extension(filename):
    """Remove known video file extensions."""
    for ext in EXTENSIONS:
        if filename.lower().endswith(ext):
            return filename[:-len(ext)]
    # Also strip if it ends with a dot-extension pattern
    m = re.match(r'^(.+)\.(mkv|avi|mp4|m4v|mov|wmv|flv|webm|srt|ts|mpg|mpeg)$', filename, re.I)
    if m:
        return m.group(1)
    return filename


def strip_junk(text):
    """Remove resolution, codec, and release group info."""
    for pattern in JUNK_PATTERNS:
        text = re.sub(pattern, ' ', text, flags=re.I)
    # Clean up multiple spaces and trailing hyphens/dots
    text = re.sub(r'\s*-\s*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def dots_to_spaces(text):
    """Convert dot-separated names to spaces, preserving decimal numbers."""
    # If text has multiple dots and few spaces, it's dot-separated
    if text.count('.') >= 2 and text.count(' ') < text.count('.'):
        # Preserve things like "Dr." or "Mr." or decimal numbers
        text = re.sub(r'\.(?=[A-Za-z])', ' ', text)
        text = re.sub(r'(?<=[A-Za-z])\.(?=\d)', ' ', text)
        text = re.sub(r'(?<=\d)\.(?=[A-Za-z])', ' ', text)
    return text


def extract_year(text):
    """Extract a 4-digit year (1900-2029) from text. Returns (cleaned_text, year)."""
    # Try parenthesized year first: (1972), [1972]
    m = re.search(r'[\(\[]\s*(19\d{2}|20[0-2]\d)\s*[\)\]]', text)
    if m:
        year = int(m.group(1))
        cleaned = text[:m.start()] + text[m.end():]
        return cleaned.strip(), year

    # Try bare year at end or separated by spaces/dots
    m = re.search(r'\b(19\d{2}|20[0-2]\d)\b', text)
    if m:
        year = int(m.group(1))
        cleaned = text[:m.start()] + text[m.end():]
        return cleaned.strip(), year

    return text, None


def extract_director(text):
    """Try to extract director from filename patterns. Returns (cleaned_text, director)."""
    director = None

    # Pattern: "Director NAME - Title" (all caps last name before dash)
    m = re.match(r'^([A-Z][a-z]+\s+[A-Z]{2,}(?:\s+[A-Z]{2,})*)\s*[-–—]\s*(.+)$', text)
    if m:
        director_candidate = m.group(1).strip()
        # Title-case the all-caps parts
        parts = director_candidate.split()
        director = ' '.join(p.capitalize() if p.isupper() and len(p) > 1 else p for p in parts)
        return m.group(2).strip(), director

    # Pattern: "LASTNAME Director - Title" with mixed case
    m = re.match(r'^([A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+)\s*[-–—]\s*(.+)$', text)
    if m:
        candidate = m.group(1).strip()
        rest = m.group(2).strip()
        # Only treat as director if the candidate looks like a name (2 words, title case)
        words = candidate.split()
        if len(words) == 2 and all(w[0].isupper() for w in words):
            # Check if the rest looks like a title (starts with capital, has substance)
            if rest and rest[0].isupper() and len(rest) > 3:
                director = candidate
                return rest, director

    # Pattern: [Director Name] in brackets
    m = re.search(r'\[([A-Z][a-z]+(?:\s+[A-Za-z]+){1,3})\]', text)
    if m:
        candidate = m.group(1)
        # Make sure it's not a resolution or codec
        if not re.match(r'^\d+p$|^BluRay$|^HDR', candidate, re.I):
            director = candidate
            cleaned = text[:m.start()] + text[m.end():]
            return cleaned.strip(), director

    # Pattern: (Director Name, YYYY) — director with year in parens
    m = re.search(r'\(([A-Z][a-z]+(?:\s+[A-Za-z]+){1,3}),\s*\d{4}\)', text)
    if m:
        director = m.group(1)
        cleaned = text[:m.start()] + text[m.end():]
        return cleaned.strip(), director

    # Pattern: "Title (Director, Year)" like "BICYCLE THIEF (Vittorio DeSica, 1948)"
    m = re.search(r'\(([A-Z][a-zA-Z]+(?:\s+[A-Za-z]+){1,3}),?\s*(19\d{2}|20[0-2]\d)?\)', text)
    if m:
        candidate = m.group(1)
        if not re.match(r'^(Part|Vol|Episode|Season|Disc|Disk)\b', candidate, re.I):
            director = candidate
            cleaned = text[:m.start()] + text[m.end():]
            return cleaned.strip(), director

    return text, director


def clean_title(title):
    """Final title cleanup."""
    # Remove leading/trailing punctuation and whitespace
    title = re.sub(r'^[\s\-–—:,.\[\]()]+', '', title)
    title = re.sub(r'[\s\-–—:,.\[\]()]+$', '', title)
    # Fix double spaces
    title = re.sub(r'\s+', ' ', title).strip()
    # Fix unicode colons/special chars
    title = title.replace('：', ':').replace('_', ' ')
    # Title case if ALL CAPS (but preserve mixed case)
    if title == title.upper() and len(title) > 3:
        # Title-case but preserve small words
        words = title.split()
        small_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor',
                       'at', 'by', 'in', 'of', 'on', 'to', 'up', 'is', 'it'}
        result = []
        for i, w in enumerate(words):
            if i == 0 or w.lower() not in small_words:
                result.append(w.capitalize())
            else:
                result.append(w.lower())
        title = ' '.join(result)
    return title


def parse_filename(line):
    """Parse a single filename line into (title, year, director)."""
    text = line.strip()
    if not text:
        return None

    # Skip known non-film entries
    if any(skip in text.lower() for skip in SKIP_ENTRIES):
        return None

    # Strip extension
    text = strip_extension(text)

    # Convert dots to spaces
    text = dots_to_spaces(text)

    # Strip codec/resolution junk
    text = strip_junk(text)

    # Extract year (do this before director extraction)
    text, year = extract_year(text)

    # Extract director
    text, director = extract_director(text)

    # If we didn't get a year but there's still one hidden, try again
    if year is None:
        text, year = extract_year(text)

    # Clean up the title
    title = clean_title(text)

    if not title or len(title) < 2:
        return None

    # Check Star Wars corrections
    title_lower = title.lower().strip()
    for sw_key, (sw_title, sw_year) in STAR_WARS_CORRECTIONS.items():
        if sw_key in title_lower:
            title = sw_title
            year = sw_year
            break

    return {
        'title': title,
        'year': year,
        'director': director,
    }


def load_existing_titles(catalog_path):
    """Load existing film titles from catalog for deduplication."""
    if not os.path.exists(catalog_path):
        return []
    with open(catalog_path) as f:
        catalog = json.load(f)
    return [e['title'] for e in catalog if e.get('media_type') == 'film']


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_filenames.py <filename_list.txt> [--dry-run]")
        sys.exit(1)

    input_file = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    # Paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    catalog_path = project_dir / 'catalog.json'
    output_path = project_dir / 'new_extractions.json'

    # Load existing titles for dedup
    existing_titles = load_existing_titles(catalog_path)
    print(f"Existing films in catalog: {len(existing_titles)}")

    # Read input file
    with open(input_file) as f:
        lines = f.readlines()
    print(f"Input lines: {len(lines)}")

    # Parse all lines
    parsed = []
    skipped = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        result = parse_filename(line)
        if result is None:
            skipped.append((i, line))
            continue
        result['_source_line'] = line
        parsed.append(result)

    print(f"Parsed: {len(parsed)}")
    print(f"Skipped: {len(skipped)}")

    # Deduplicate within parsed results (by normalized title)
    seen = {}
    unique = []
    internal_dupes = 0
    for entry in parsed:
        norm = normalize_title(entry['title'])
        if norm in seen:
            internal_dupes += 1
            # Keep the one with more info
            existing = seen[norm]
            if (entry.get('year') and not existing.get('year')) or \
               (entry.get('director') and not existing.get('director')):
                seen[norm] = entry
                unique = [e for e in unique if normalize_title(e['title']) != norm]
                unique.append(entry)
        else:
            seen[norm] = entry
            unique.append(entry)

    print(f"Internal duplicates removed: {internal_dupes}")

    # Deduplicate against existing catalog
    new_entries = []
    catalog_dupes = 0
    for entry in unique:
        is_dupe = False
        for existing in existing_titles:
            if fuzzy_match(entry['title'], existing, threshold=0.82):
                catalog_dupes += 1
                is_dupe = True
                break
        if not is_dupe:
            new_entries.append(entry)

    print(f"Catalog duplicates removed: {catalog_dupes}")
    print(f"New entries to add: {len(new_entries)}")

    # Build output
    extractions = []
    for entry in new_entries:
        obj = {
            'title': entry['title'],
            'media_type': 'film',
            'year': entry.get('year'),
            'director': entry.get('director'),
            'synopsis': '',
            'themes': [],
            'needs_review': True,
            'confidence': 'medium',
            'source': 'filename_import',
        }
        extractions.append(obj)

    # Sort by title
    extractions.sort(key=lambda x: x['title'].lower())

    if dry_run:
        print("\n--- DRY RUN (first 30 entries) ---")
        for e in extractions[:30]:
            director_str = f" [{e['director']}]" if e.get('director') else ""
            year_str = f" ({e['year']})" if e.get('year') else ""
            print(f"  {e['title']}{year_str}{director_str}")
        print(f"\n  ... and {len(extractions) - 30} more" if len(extractions) > 30 else "")
    else:
        with open(output_path, 'w') as f:
            json.dump(extractions, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(extractions)} entries to {output_path}")

    # Print skipped entries
    if skipped:
        print(f"\n--- Skipped entries ({len(skipped)}) ---")
        for line_num, line in skipped:
            print(f"  Line {line_num}: {line}")

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Input lines:      {len(lines)}")
    print(f"Blank/skipped:    {len(skipped) + len(lines) - len([l for l in lines if l.strip()])}")
    print(f"Parsed:           {len(parsed)}")
    print(f"Internal dupes:   {internal_dupes}")
    print(f"Catalog dupes:    {catalog_dupes}")
    print(f"New extractions:  {len(extractions)}")
    with_year = sum(1 for e in extractions if e.get('year'))
    with_director = sum(1 for e in extractions if e.get('director'))
    print(f"With year:        {with_year}")
    print(f"With director:    {with_director}")
    print(f"Missing director: {len(extractions) - with_director}")


if __name__ == '__main__':
    main()
