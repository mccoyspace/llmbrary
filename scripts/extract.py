#!/usr/bin/env python3
"""
extract.py — Extract titles from shelf photos using the Anthropic vision API.

Reads images from photos/processed/ (or specified paths), sends them to Claude
for visual extraction of book/film/music spine text, and writes results to
extracted_titles.json (merging with any existing entries).

Referenced as the "downstream vision extraction step" in ingest.py.

Requires: pip install anthropic --break-system-packages
For HEIC support: pip install pillow pillow-heif --break-system-packages

Usage:
    python3 scripts/extract.py                                  # all unextracted photos
    python3 scripts/extract.py photos/processed/IMG_3120.jpeg  # specific file(s)
    python3 scripts/extract.py --dry-run                        # list without calling API
    python3 scripts/extract.py --reprocess                      # re-extract logged photos
    python3 scripts/extract.py --media-hint film                # hint media type
    python3 scripts/extract.py --limit 5                        # process at most N photos
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = REPO_ROOT / "photos" / "processed"
EXTRACTION_LOG = REPO_ROOT / "extraction_log.json"
EXTRACTED_TITLES = REPO_ROOT / "extracted_titles.json"

DEFAULT_MODEL = "claude-opus-4-6"   # best vision accuracy
RATE_LIMIT_DELAY = 1.0              # seconds between images

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

SYSTEM_PROMPT = """You are extracting text from photographs of bookshelves, DVD/Blu-ray racks, or music shelves.

For each photo, identify every visible spine and extract the title and creator name. Include every item you can read, even partially.

Return a JSON array. Each element must have:
- "title": string (required — the book/film/album title)
- "author": string or null (author, director, or artist name visible on the spine, or null)
- "confidence": "high" (clearly legible), "medium" (partially obscured or inferred), or "low" (uncertain)

Include uncertain items at "low" confidence rather than omitting them.

Return ONLY valid JSON — no markdown fences, no preamble. Example:
[{"title": "Naked Lunch", "author": "William S. Burroughs", "confidence": "high"}, {"title": "Unknown Title", "author": null, "confidence": "low"}]"""


# ---------------------------------------------------------------------------
# Log and title file I/O
# ---------------------------------------------------------------------------

def load_extraction_log() -> dict:
    if EXTRACTION_LOG.exists():
        with open(EXTRACTION_LOG) as f:
            return json.load(f)
    return {"extracted": []}


def save_extraction_log(log: dict) -> None:
    with open(EXTRACTION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def already_extracted(filename: str, log: dict) -> bool:
    return any(e["filename"] == filename for e in log.get("extracted", []))


def load_extracted_titles() -> list[dict]:
    if EXTRACTED_TITLES.exists():
        with open(EXTRACTED_TITLES) as f:
            return json.load(f)
    return []


def save_extracted_titles(titles: list[dict]) -> None:
    with open(EXTRACTED_TITLES, "w") as f:
        json.dump(titles, f, indent=2, ensure_ascii=False)
    with open(EXTRACTED_TITLES, "a") as f:
        f.write("\n")


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

def encode_image(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type). Converts HEIC to JPEG if needed."""
    suffix = path.suffix.lower()

    if suffix == ".heic":
        try:
            import pillow_heif
            from PIL import Image
            import io as _io
            pillow_heif.register_heif_opener()
            img = Image.open(path)
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
        except ImportError:
            raise ImportError(
                "HEIC support requires: pip install pillow pillow-heif --break-system-packages"
            )

    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()
    return data, media_type


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def extract_from_image(path: Path, media_hint: str, client, model: str) -> list[dict] | None:
    try:
        data, media_type = encode_image(path)
    except ImportError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ✗ Encoding failed: {e}", file=sys.stderr)
        return None

    hint_note = {
        "film":  " This shelf contains DVDs or Blu-rays.",
        "music": " This shelf contains CDs or vinyl records.",
        "book":  " This shelf contains books.",
    }.get(media_hint, "")

    user_text = f"Extract all titles from the shelf spines in this photo.{hint_note}"

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        results = json.loads(raw)
        if not isinstance(results, list):
            print(f"  ✗ Expected list, got {type(results).__name__}", file=sys.stderr)
            return None

        # Tag each result with its source image
        for item in results:
            item["source_image"] = path.name

        return results

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ✗ API error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _key(item: dict) -> tuple[str, str]:
    return (item.get("title", "").lower().strip(), item.get("source_image", ""))


def merge_titles(
    existing: list[dict], new_items: list[dict]
) -> tuple[list[dict], int, int]:
    """Deduplicate by (normalized title, source_image) and merge."""
    seen = {_key(e) for e in existing}
    added, skipped = 0, 0
    merged = list(existing)

    for item in new_items:
        k = _key(item)
        if k in seen:
            skipped += 1
        else:
            merged.append(item)
            seen.add(k)
            added += 1

    return merged, added, skipped


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_unextracted(log: dict) -> list[Path]:
    if not PROCESSED_DIR.exists():
        return []
    return sorted(
        p for p in PROCESSED_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        and not already_extracted(p.name, log)
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract titles from shelf photos using the Anthropic vision API."
    )
    parser.add_argument(
        "images",
        nargs="*",
        help="Specific image files to process. Omit to auto-discover from photos/processed/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List photos to process without making API calls.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Re-extract photos already in the extraction log.",
    )
    parser.add_argument(
        "--media-hint",
        choices=["book", "film", "music", "mixed"],
        default="mixed",
        help="Hint for what kind of media the photos contain. Default: mixed.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of photos to process.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Anthropic model to use. Default: {DEFAULT_MODEL}",
    )
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    log = load_extraction_log()

    # Resolve image list
    if args.images:
        image_paths = [Path(p) for p in args.images]
        missing = [p for p in image_paths if not p.exists()]
        if missing:
            for p in missing:
                print(f"Error: not found: {p}", file=sys.stderr)
            sys.exit(1)
    elif args.reprocess:
        image_paths = sorted(
            p for p in PROCESSED_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ) if PROCESSED_DIR.exists() else []
    else:
        image_paths = find_unextracted(log)

    if args.limit:
        image_paths = image_paths[:args.limit]

    if not image_paths:
        print("✓ No new photos to process.")
        return

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}Processing {len(image_paths)} photo(s)\n")

    if args.dry_run:
        for p in image_paths:
            status = "(already extracted)" if already_extracted(p.name, log) else "(new)"
            size_kb = p.stat().st_size / 1024
            print(f"  {p.name}  {size_kb:.0f} KB  {status}")
        return

    try:
        import anthropic
    except ImportError:
        print("Error: anthropic not installed. Run: pip install anthropic --break-system-packages",
              file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()
    existing_titles = load_extracted_titles()

    total_added = 0
    total_errors = 0

    for idx, path in enumerate(image_paths, 1):
        print(f"[{idx}/{len(image_paths)}] {path.name}")

        results = extract_from_image(path, args.media_hint, client, args.model)

        if results is not None:
            existing_titles, added, skipped = merge_titles(existing_titles, results)
            total_added += added
            print(f"  ✓ {len(results)} titles found ({added} new, {skipped} duplicate)")

            log["extracted"].append({
                "filename": path.name,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "titles_found": len(results),
                "media_hint": args.media_hint,
            })

            save_extracted_titles(existing_titles)
            save_extraction_log(log)
        else:
            total_errors += 1

        if idx < len(image_paths):
            time.sleep(RATE_LIMIT_DELAY)

    print(f"\n✓ {total_added} new titles added to extracted_titles.json "
          f"({total_errors} errors)")
    if total_added:
        print("  Suggested next steps:")
        print("    Review extracted_titles.json, then:")
        print("    python3 scripts/merge_catalog.py new_extractions.json")
        print("    python3 scripts/enrich.py")
        print("    python3 scripts/regenerate.py")


if __name__ == "__main__":
    main()
