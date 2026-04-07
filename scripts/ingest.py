#!/usr/bin/env python3
"""
ingest.py — Scan photos/inbox/ for new shelf images and prepare them for processing.

Supports multi-media: shelf photos may contain book spines, DVD/Blu-ray spines,
or CD/vinyl spines. The vision extraction step downstream should tag entries with
the appropriate media_type ("book", "film", or "music") when identifiable from
the physical format (DVD cases, CD jewel cases, vinyl sleeves, etc.).

Usage:
    python3 scripts/ingest.py              # list new images awaiting processing
    python3 scripts/ingest.py --dry-run    # preview without writing anything
    python3 scripts/ingest.py --move       # move processed images to photos/processed/
    python3 scripts/ingest.py --media-hint film  # hint that these photos are DVD/Blu-ray shelves

Reads and writes processing_log.json to avoid reprocessing images.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX = REPO_ROOT / "photos" / "inbox"
PROCESSED = REPO_ROOT / "photos" / "processed"
LOG_FILE = REPO_ROOT / "processing_log.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}


def load_log() -> dict:
    """Load the processing log, or return an empty structure."""
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "last_run": None}


def save_log(log: dict) -> None:
    """Write the processing log to disk."""
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def already_processed(filename: str, log: dict) -> bool:
    """Check if a filename has already been processed."""
    return any(entry["filename"] == filename for entry in log["processed"])


def _sweep_inbox(inbox_files: list[Path], log: dict) -> int:
    """Move already-processed files still in inbox to processed/."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    moved = 0
    for f in inbox_files:
        if already_processed(f.name, log):
            dst = PROCESSED / f.name
            f.rename(dst)
            moved += 1
            print(f"  ↦ {f.name} → photos/processed/")
    return moved


def scan_inbox() -> list[Path]:
    """Return all image files in the inbox, sorted by name."""
    if not INBOX.exists():
        return []
    return sorted(
        p for p in INBOX.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def build_manifest(files: list[Path], log: dict) -> list[dict]:
    """Build a manifest of new (unprocessed) images."""
    manifest = []
    for f in files:
        if already_processed(f.name, log):
            continue
        stat = f.stat()
        manifest.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "media_hint": "mixed",  # overridden at write time with CLI arg
        })
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Scan photos/inbox/ for new bookshelf images to process."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be processed without writing anything.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move images from inbox/ to processed/ after logging them.",
    )
    parser.add_argument(
        "--titles-extracted",
        type=int,
        default=0,
        help="Number of titles extracted (for log bookkeeping after extraction).",
    )
    parser.add_argument(
        "--media-hint",
        choices=["book", "film", "music", "mixed"],
        default="mixed",
        help="Hint about what kind of physical media these photos contain. "
             "Default: mixed (let vision extraction decide per-item). "
             "Use 'film' for DVD/Blu-ray shelves, 'music' for CD/vinyl shelves.",
    )
    args = parser.parse_args()

    log = load_log()
    inbox_files = scan_inbox()

    if not inbox_files:
        print("📭 No images found in photos/inbox/")
        sys.exit(0)

    manifest = build_manifest(inbox_files, log)

    if not manifest:
        # If --move, sweep any already-logged files still sitting in inbox
        if args.move:
            swept = _sweep_inbox(inbox_files, log)
            if swept:
                print(f"✓ Moved {swept} already-processed image(s) from inbox/ to processed/")
            else:
                print("✓ All images in inbox/ have already been processed and moved.")
        else:
            print("✓ All images in inbox/ have already been processed.")
        sys.exit(0)

    # Display manifest
    print(f"Found {len(manifest)} new image(s) to process:\n")
    for i, entry in enumerate(manifest, 1):
        size_kb = entry["size_bytes"] / 1024
        print(f"  {i}. {entry['filename']}  ({size_kb:.0f} KB, modified {entry['modified']})")

    if args.dry_run:
        print(f"\n[dry-run] Would process {len(manifest)} image(s). No files written or moved.")
        sys.exit(0)

    # Record in processing log
    now = datetime.now(timezone.utc).isoformat()
    for entry in manifest:
        log["processed"].append({
            "filename": entry["filename"],
            "processed_at": now,
            "titles_extracted": args.titles_extracted,
            "media_hint": args.media_hint,
        })
    log["last_run"] = now

    save_log(log)
    print(f"\n✓ Logged {len(manifest)} image(s) to processing_log.json")

    # Optionally move to processed/
    if args.move:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        moved = 0
        for entry in manifest:
            src = Path(entry["path"])
            dst = PROCESSED / entry["filename"]
            if src.exists():
                src.rename(dst)
                moved += 1
                print(f"  ↦ {entry['filename']} → photos/processed/")
        print(f"\n✓ Moved {moved} image(s) to photos/processed/")
    else:
        print("\nTip: run with --move to move processed images out of inbox/.")

    # Write manifest for downstream tools — include media hint from CLI
    for entry in manifest:
        entry["media_hint"] = args.media_hint
    manifest_path = REPO_ROOT / "inbox_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"✓ Wrote manifest to inbox_manifest.json ({len(manifest)} entries)")


if __name__ == "__main__":
    main()
