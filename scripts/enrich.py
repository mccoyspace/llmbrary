#!/usr/bin/env python3
"""
enrich.py — Enrich catalog.json entries using the Anthropic API.

For entries missing synopsis, themes, year, or in_conversation_with,
calls Claude to fill in the gaps using knowledge of each work and
the broader collection's intellectual context.

Requires: pip install anthropic --break-system-packages

Usage:
    python3 scripts/enrich.py                        # enrich all needs_review entries
    python3 scripts/enrich.py --title "Exact Title"  # enrich a specific entry
    python3 scripts/enrich.py --limit 10             # process at most 10 entries
    python3 scripts/enrich.py --dry-run              # show what would be enriched, no API calls
    python3 scripts/enrich.py --connections-only     # only update in_conversation_with links
    python3 scripts/enrich.py --force                # re-enrich even fully enriched entries
    python3 scripts/enrich.py --model claude-haiku-4-5-20251001  # cheaper model
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"

DEFAULT_MODEL = "claude-opus-5"
RATE_LIMIT_DELAY = 0.5  # seconds between API calls

ENRICHMENT_FIELDS = ["synopsis", "themes", "year"]

SYSTEM_PROMPT = """You are enriching entries in a personal library catalog spanning video art and cinema, performance and embodiment, critical theory, experimental literature, craft traditions, digital media, music, and architecture.

For each entry, produce a JSON object with exactly these fields:
- "synopsis": A single dense paragraph (5–7 sentences) describing the work's content, argument, and significance. Be specific and situate the work within its discipline or movement. Avoid filler phrases.
- "themes": An array of 5–8 lowercase keyword strings (e.g. ["video art", "performance", "media theory"]).
- "year": Publication or release year as an integer, or null if genuinely unknown.
- "in_conversation_with": An array of 0–7 title strings chosen from the catalog list provided. Select titles with genuine intellectual, formal, or historical resonance — not just genre proximity. Use exact titles as given.

Return ONLY valid JSON — no markdown fences, no commentary. Example:
{"synopsis": "...", "themes": ["theme a", "theme b"], "year": 1984, "in_conversation_with": ["Title A", "Title B"]}"""


# ---------------------------------------------------------------------------
# Catalog I/O
# ---------------------------------------------------------------------------

def load_catalog() -> list[dict]:
    with open(CATALOG_PATH) as f:
        return json.load(f)


def save_catalog(catalog: list[dict]) -> None:
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    with open(CATALOG_PATH, "a") as f:
        f.write("\n")


# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------

def get_creator(entry: dict) -> str:
    mt = entry.get("media_type", "book")
    if mt == "film":
        return (entry.get("director") or "").strip()
    elif mt == "music":
        return (entry.get("artist") or "").strip()
    return (entry.get("author") or "").strip()


def needs_enrichment(entry: dict) -> bool:
    if entry.get("needs_review"):
        return True
    if not entry.get("synopsis") or len(entry.get("synopsis", "").strip()) < 30:
        return True
    if not entry.get("themes"):
        return True
    return False


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_user_message(entry: dict, all_titles: list[str]) -> str:
    mt = entry.get("media_type", "book")
    title = entry["title"]
    creator = get_creator(entry)
    year = entry.get("year")

    creator_label = {"book": "Author", "film": "Director", "music": "Artist"}.get(mt, "Creator")

    lines = [f"Title: {title}", f"Type: {mt}"]
    if creator:
        lines.append(f"{creator_label}: {creator}")
    if year:
        lines.append(f"Year: {year}")

    existing_synopsis = (entry.get("synopsis") or "").strip()
    if len(existing_synopsis) > 30:
        lines.append(f"Existing synopsis (improve if possible): {existing_synopsis}")

    existing_themes = entry.get("themes") or []
    if existing_themes:
        lines.append(f"Existing themes (refine if needed): {', '.join(existing_themes)}")

    existing_conns = entry.get("in_conversation_with") or []
    if existing_conns:
        lines.append(f"Existing connections (keep or improve): {', '.join(existing_conns)}")

    lines.append(f"\nCatalog titles available for in_conversation_with:")
    lines.append(json.dumps(all_titles))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def enrich_entry(entry: dict, all_titles: list[str], client, model: str) -> dict | None:
    user_msg = build_user_message(entry, all_titles)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences if the model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ✗ API error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Apply enrichment
# ---------------------------------------------------------------------------

def apply_enrichment(entry: dict, enriched: dict, connections_only: bool = False) -> dict:
    updated = dict(entry)

    if not connections_only:
        synopsis = (enriched.get("synopsis") or "").strip()
        if len(synopsis) > 30:
            updated["synopsis"] = synopsis

        themes = enriched.get("themes")
        if isinstance(themes, list) and themes:
            updated["themes"] = [str(t).lower().strip() for t in themes if t]

        # Only fill year if absent — don't overwrite a known year
        new_year = enriched.get("year")
        if isinstance(new_year, int) and not entry.get("year"):
            updated["year"] = new_year

    conns = enriched.get("in_conversation_with")
    if isinstance(conns, list):
        updated["in_conversation_with"] = conns

    # Clear review flags when key fields are present
    if updated.get("synopsis") and updated.get("themes") and not connections_only:
        updated["needs_review"] = False
        updated.pop("enrichment_needed", None)

    return updated


# ---------------------------------------------------------------------------
# Entry selection
# ---------------------------------------------------------------------------

def select_indices(catalog: list[dict], args) -> list[int]:
    if args.title:
        exact = [i for i, e in enumerate(catalog) if e["title"] == args.title]
        if exact:
            return exact
        lower = args.title.lower()
        partial = [i for i, e in enumerate(catalog) if lower in e["title"].lower()]
        if not partial:
            print(f"Error: no entry found matching: {args.title!r}", file=sys.stderr)
            sys.exit(1)
        return partial

    if args.force:
        indices = list(range(len(catalog)))
    else:
        indices = [i for i, e in enumerate(catalog) if needs_enrichment(e)]

    if args.limit:
        indices = indices[:args.limit]

    return indices


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Enrich catalog.json entries via the Anthropic API."
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Enrich a specific entry by title (exact or partial match).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of entries to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which entries would be enriched without making API calls.",
    )
    parser.add_argument(
        "--connections-only",
        action="store_true",
        help="Only update in_conversation_with links (skip synopsis/themes/year).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich all entries, even those that appear complete.",
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

    catalog = load_catalog()
    all_titles = [e["title"] for e in catalog]
    indices = select_indices(catalog, args)

    if not indices:
        print("✓ No entries need enrichment.")
        return

    prefix = "[dry-run] " if args.dry_run else ""
    mode = " (connections only)" if args.connections_only else ""
    print(f"{prefix}Enriching {len(indices)} entr{'y' if len(indices) == 1 else 'ies'}{mode}\n")

    if args.dry_run:
        for i in indices:
            e = catalog[i]
            creator = get_creator(e)
            label = e["title"] + (f" — {creator}" if creator else "")
            mt = e.get("media_type", "book")
            missing = [f for f in ("synopsis", "themes", "year", "in_conversation_with")
                       if not e.get(f)]
            flag = " [needs_review]" if e.get("needs_review") else ""
            print(f"  [{mt}] {label}{flag}")
            if missing:
                print(f"       missing: {', '.join(missing)}")
        return

    try:
        import anthropic
    except ImportError:
        print("Error: anthropic not installed. Run: pip install anthropic --break-system-packages",
              file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()
    enriched_count = 0
    error_count = 0

    for seq, catalog_idx in enumerate(indices, 1):
        entry = catalog[catalog_idx]
        creator = get_creator(entry)
        label = entry["title"] + (f" — {creator}" if creator else "")
        print(f"[{seq}/{len(indices)}] {label}")

        result = enrich_entry(entry, all_titles, client, args.model)

        if result:
            catalog[catalog_idx] = apply_enrichment(entry, result, args.connections_only)
            enriched_count += 1

            synopsis = (result.get("synopsis") or "").strip()
            if synopsis:
                print(f"  ✓ synopsis ({len(synopsis)} chars)")
            themes = result.get("themes") or []
            if themes:
                preview = ", ".join(themes[:4]) + ("…" if len(themes) > 4 else "")
                print(f"  ✓ themes: {preview}")
            new_year = result.get("year")
            if isinstance(new_year, int) and not entry.get("year"):
                print(f"  ✓ year: {new_year}")
            conns = result.get("in_conversation_with") or []
            if conns:
                preview = ", ".join(conns[:3]) + ("…" if len(conns) > 3 else "")
                print(f"  ✓ connections: {preview}")

            save_catalog(catalog)
        else:
            error_count += 1

        if seq < len(indices):
            time.sleep(RATE_LIMIT_DELAY)

    print(f"\n✓ Enriched {enriched_count}/{len(indices)} entries ({error_count} errors)")
    if enriched_count:
        print("  Run 'python3 scripts/regenerate.py' to update CONTEXT.md and wiki/")


if __name__ == "__main__":
    main()
