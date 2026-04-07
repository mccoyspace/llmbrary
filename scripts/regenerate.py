#!/usr/bin/env python3
"""
regenerate.py — Regenerate tiered context files and wiki from catalog.json.

Supports multi-media catalogs (books, films, music). Each media type is
organized within the thematic groupings, with type labels in the output.

Usage:
    python3 scripts/regenerate.py           # Regenerate everything (context + wiki)
    python3 scripts/regenerate.py --wiki    # Regenerate wiki pages only
    python3 scripts/regenerate.py --context # Regenerate context tiers only

Produces three context tiers from catalog.json:
  - CONTEXT.md          Full version with complete synopses (~150KB, ~40K tokens)
  - CONTEXT_COMPACT.md  One-line per entry with groupings (~15-20KB, ~5K tokens)
  - CONTEXT_OVERVIEW.md Intellectual profile only (~2-3KB, ~500 tokens)

And a wiki/ directory of synthesized thematic pages tracing intellectual
threads across the collection (via generate_wiki.py).

Run this after any changes to catalog.json to keep all generated files in sync.
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
CONTEXT_PATH = REPO_ROOT / "CONTEXT.md"
COMPACT_PATH = REPO_ROOT / "CONTEXT_COMPACT.md"
OVERVIEW_PATH = REPO_ROOT / "CONTEXT_OVERVIEW.md"

VALID_MEDIA_TYPES = {"book", "film", "music"}

# Media type display labels and icons
MEDIA_LABELS = {
    "book": "\U0001F4D6",   # open book emoji
    "film": "\U0001F3AC",   # clapper board
    "music": "\U0001F3B5",  # musical note
}

# ---------------------------------------------------------------------------
# Thematic groupings — each entry is assigned to the best-matching group
# based on keyword scoring across title, author/director/artist, themes,
# and synopsis.
# ---------------------------------------------------------------------------
GROUPINGS = [
    {
        "name": "Video Art & Moving Image",
        "keywords": ["video", "moving image", "Paik", "Viola", "Gary Hill", "Joan Jonas",
                      "Videofreex", "Vostell", "Broken Screen", "Echo"],
    },
    {
        "name": "Film Theory & Cinema",
        "keywords": ["film", "cinema", "Godard", "Frampton", "Marker", "Lynch",
                      "La Jetée", "Film Art", "Circles of Confusion"],
    },
    {
        "name": "Performance Art & Body",
        "keywords": ["performance", "Acconci", "Yoko Ono", "body", "Artaud", "United States"],
    },
    {
        "name": "Fluxus, Neo-Dada & Experimental Art",
        "keywords": ["Fluxus", "Beuys", "Rauschenberg", "Dieter Roth",
                      "Niki de Saint Phalle", "Maciunas", "Neo-Dada"],
    },
    {
        "name": "Conceptual & Rule-Based Art",
        "keywords": ["conceptual", "rule-based", "Sophie Calle", "Glenn Ligon",
                      "David Diao", "Logical Conclusions", "Mechanism of Meaning"],
    },
    {
        "name": "Sculpture, Installation & Space",
        "keywords": ["sculpture", "installation", "Eva Hesse", "Nancy Graves", "Ruth Asawa",
                      "Boltanski", "Maya Lin", "Matta-Clark", "Richard Long", "Drawing",
                      "Architecture"],
    },
    {
        "name": "Painting, Abstraction & Color",
        "keywords": ["painting", "abstraction", "Jack Whitten", "Ninth Street Women",
                      "Terry Winters", "Richter", "Penck", "Bulatov"],
    },
    {
        "name": "Photography & Image",
        "keywords": ["photography", "photo", "Naked City", "Dirty Windows",
                      "Hidden Mother", "Women Photographers"],
    },
    {
        "name": "Digital Art, New Media & NFTs",
        "keywords": ["digital", "new media", "NFT", "Processing", "Rhizome",
                      "Collective Intelligence", "Surfing with Satoshi"],
    },
    {
        "name": "Typography, Design & Visual Language",
        "keywords": ["typography", "design", "typographic", "Tibor Kalman",
                      "Graphic Design", "2nd Sight", "Elements of Typographic"],
    },
    {
        "name": "Architecture, Urbanism & Built Environment",
        "keywords": ["architecture", "urban", "Rural Studio", "Off the Grid",
                      "building", "space", "dwelling"],
    },
    {
        "name": "Craft, Material Culture & Objects",
        "keywords": ["craft", "material", "Anni Albers", "Knit Like", "Art Deco",
                      "ceramic", "weaving"],
    },
    {
        "name": "Music: Experimental, Jazz & Sound Studies",
        "keywords": ["music", "jazz", "sound", "Coltrane", "Arcana", "Soundscape",
                      "Musician", "Ken Burns", "Voice in the Headphones", "Soloists"],
    },
    {
        "name": "Sacred Singing & Oral Tradition",
        "keywords": ["Sacred Harp", "shape-note", "Shenandoah", "Haida",
                      "Bringhurst", "oral"],
    },
    {
        "name": "Situationism, Spectacle & Everyday Life",
        "keywords": ["Situationism", "Debord", "SI", "Everyday Life",
                      "All That Is Solid", "spectacle", "Egress"],
    },
    {
        "name": "Critical Theory & Philosophy",
        "keywords": ["Benjamin", "Foucault", "Deleuze", "Wittgenstein", "Danto",
                      "Hickey", "Krauss", "Scarry", "Nagel", "DeLanda", "Rancière",
                      "theory", "philosophy"],
    },
    {
        "name": "Media Theory & Digital Culture",
        "keywords": ["media", "electronic", "digital", "Protocol", "Social Media",
                      "Body Invaders", "Flusser", "Commodity Aesthetics"],
    },
    {
        "name": "Political Philosophy & Radical Thought",
        "keywords": ["political", "Caliban", "Witch", "Art of Not Being Governed",
                      "Multitude", "Crypto", "Achieving Our Country", "Freedom",
                      "Detroit", "City of Quartz"],
    },
    {
        "name": "Feminism, Gender & Identity",
        "keywords": ["feminist", "feminism", "gender", "Room of One's Own",
                      "Xenofeminism", "Species Meet", "Woman Destroyed", "Women"],
    },
    {
        "name": "Literature: Beat Generation & Experimental Writing",
        "keywords": ["Burroughs", "Gysin", "Beat", "Letters"],
    },
    {
        "name": "Literature: American Canon",
        "keywords": ["Twain", "Saunders", "Carver", "Faulkner", "Lowell", "Sexton",
                      "Dickinson", "Bowles", "Delights", "Century of Fiction"],
    },
    {
        "name": "Literature: European & World Voices",
        "keywords": ["Woolf", "Kundera", "Brontë", "Celan", "Rilke", "Pavese",
                      "Coetzee", "Kazantzakis", "Erpenbeck"],
    },
    {
        "name": "Science Fiction & Speculative Imagination",
        "keywords": ["Ubik", "Software", "Lovecraft", "St. Clair", "Ministry for the Future",
                      "Ballard", "speculative", "fiction"],
    },
    {
        "name": "Drama, Theater & Narrative",
        "keywords": ["drama", "theater", "Macbeth", "Good Woman", "Setzuan",
                      "Idea of a Theater"],
    },
    {
        "name": "Myth, Religion & Spirituality",
        "keywords": ["myth", "religion", "Hero", "Thousand Faces", "Norse", "Saga",
                      "Temptation", "Augustine", "Meditation", "spiritual"],
    },
    {
        "name": "Psychology & Mind",
        "keywords": ["psychology", "Interpretation of Dreams", "dream", "unconscious"],
    },
    {
        "name": "Art World, Institutions & Discourse",
        "keywords": ["Best Art", "I Like Your Work", "Art School", "Art Spirit",
                      "Inside the Studio", "Biennial", "Museum", "Gallery"],
    },
    {
        "name": "Environmentalism, Nature & Land",
        "keywords": ["Wilderness", "American Mind", "Against the Machine", "This Land",
                      "Low Tech", "environment", "nature", "land"],
    },
    {
        "name": "Comics, Graphic Narrative & Visual Storytelling",
        "keywords": ["comics", "graphic", "Walking Dead", "Nat Turner", "narrative"],
    },
    {
        "name": "Miscellaneous & Reference",
        "keywords": ["self-help", "astrology", "health", "cooking", "industrial",
                      "counterculture", "Blueprint", "Sing Backwards"],
    },
]

# ---------------------------------------------------------------------------
# Shared intellectual overview
# ---------------------------------------------------------------------------
INTRO = (
    "This collection spans the artistic, theoretical, and cultural territories that "
    "have shaped contemporary creative practice. It is a deeply curated library that "
    "moves fluidly across visual art and cinema, performance and embodiment, "
    "theoretical philosophy and experimental literature, craft traditions and digital "
    "media. The collection maps a landscape where Fluxus gestures meet algorithmic "
    "thinking, where Situationist critique encounters net culture, where the "
    "hand-made and the digital, the sacred and the profane, coexist in productive "
    "tension. It treats art history, media theory, radical politics, music, "
    "mythology, and material practice as interconnected dimensions of a single, "
    "evolving intellectual project — spanning books, films, and music."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_media_type(entry: dict) -> str:
    """Get the media_type of an entry, defaulting to 'book'."""
    mt = entry.get("media_type", "book")
    return mt if mt in VALID_MEDIA_TYPES else "book"


def get_creator(entry: dict) -> str:
    """Get the primary creator field based on media_type."""
    mt = get_media_type(entry)
    if mt == "film":
        return (entry.get("director") or "").strip()
    elif mt == "music":
        return (entry.get("artist") or "").strip()
    else:
        return (entry.get("author") or "").strip()


def get_creator_label(entry: dict) -> str:
    """Get the label for the creator field based on media_type."""
    mt = get_media_type(entry)
    if mt == "film":
        return "dir."
    elif mt == "music":
        return "by"
    return ""  # books use em-dash convention


def media_type_tag(entry: dict) -> str:
    """Return a short tag like [film] or [music] for non-book entries."""
    mt = get_media_type(entry)
    if mt == "book":
        return ""
    return f"[{mt}] "


# ---------------------------------------------------------------------------
# Data loading & categorization
# ---------------------------------------------------------------------------

def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, "r") as f:
        return json.load(f)


def categorize(entry: dict) -> int:
    """Score entry against each grouping, return index of best match."""
    title = entry.get("title", "").lower()
    creator = get_creator(entry).lower()
    themes = [t.lower() for t in entry.get("themes", [])]
    synopsis = entry.get("synopsis", "").lower()
    combined = f"{title} {creator} {' '.join(themes)} {synopsis}"

    best_score, best_idx = -1, len(GROUPINGS) - 1  # default to Misc

    for idx, group in enumerate(GROUPINGS):
        score = 0
        for kw in group["keywords"]:
            kw_lower = kw.lower()
            if kw_lower in title:
                score += 10
            elif kw_lower in creator or kw_lower in themes:
                score += 8
            elif kw_lower in combined:
                score += 3
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def build_buckets(catalog: list[dict]) -> dict[int, list[dict]]:
    """Categorize all entries into grouping buckets, sorted by media type then title."""
    buckets: dict[int, list[dict]] = {i: [] for i in range(len(GROUPINGS))}
    for entry in catalog:
        buckets[categorize(entry)].append(entry)
    # Sort: books first, then films, then music; alphabetical within each type
    type_order = {"book": 0, "film": 1, "music": 2}
    for idx in buckets:
        buckets[idx].sort(key=lambda e: (
            type_order.get(get_media_type(e), 9),
            e.get("title", "").lower()
        ))
    return buckets


# ---------------------------------------------------------------------------
# TIER 1: CONTEXT.md — Full version with complete synopses
# ---------------------------------------------------------------------------

def format_entry_full(entry: dict, all_titles: set) -> list[str]:
    """Format a single catalog entry as full markdown lines."""
    lines = []
    mt = get_media_type(entry)
    title = entry.get("title", "").strip()
    creator = get_creator(entry)
    year = entry.get("year")
    synopsis = entry.get("synopsis", "").strip()
    themes = entry.get("themes", [])
    connections = entry.get("in_conversation_with", [])

    # Title line with media type tag for non-books
    tag = media_type_tag(entry)
    parts = [f"{tag}**{title}**"]
    if creator:
        parts[0] += f" — {creator}"
    if year:
        parts[0] += f" ({year})"
    lines.append(parts[0])

    # Film-specific: cast
    if mt == "film":
        cast = entry.get("cast", [])
        if cast:
            lines.append(f"**Cast:** {', '.join(cast)}")
        fmt = entry.get("format")
        if fmt:
            lines.append(f"**Format:** {fmt}")

    # Music-specific: label, format
    if mt == "music":
        label = entry.get("label")
        if label:
            lines.append(f"**Label:** {label}")
        fmt = entry.get("format")
        if fmt:
            lines.append(f"**Format:** {fmt}")

    if synopsis:
        lines.append(synopsis)
    if themes:
        lines.append(f"**Themes:** {', '.join(themes)}")

    valid_conns = [c for c in connections if c in all_titles]
    if valid_conns:
        lines.append(f"**In conversation with:** {', '.join(valid_conns)}")

    lines.append("")
    return lines


def generate_full(catalog: list[dict], buckets: dict[int, list[dict]]) -> int:
    """Generate CONTEXT.md — full version with complete synopses."""
    all_titles = {e["title"] for e in catalog}

    # Count by media type
    type_counts = Counter(get_media_type(e) for e in catalog)
    type_summary_parts = []
    for mt in ["book", "film", "music"]:
        if type_counts[mt]:
            label = "books" if mt == "book" else "films" if mt == "film" else "albums"
            type_summary_parts.append(f"{type_counts[mt]} {label}")
    type_summary = ", ".join(type_summary_parts)

    md = [
        "# Collection — Intellectual Context (Full)",
        "",
        f"*{len(catalog)} entries ({type_summary}) across "
        f"{sum(1 for b in buckets.values() if b)} thematic groupings. "
        "This is the full rendering with complete synopses, themes, and relationship annotations. "
        "For lighter versions, see CONTEXT_COMPACT.md (~5K tokens) or CONTEXT_OVERVIEW.md (~500 tokens).*",
        "",
        INTRO,
        "",
        "## Catalog",
        "",
    ]

    entry_count = 0
    active_groups = 0

    for idx, group in enumerate(GROUPINGS):
        entries = buckets[idx]
        if not entries:
            continue
        active_groups += 1
        md.append(f"### {group['name']}")
        md.append("")
        for entry in entries:
            md.extend(format_entry_full(entry, all_titles))
            entry_count += 1

    CONTEXT_PATH.write_text("\n".join(md))
    return entry_count


# ---------------------------------------------------------------------------
# TIER 2: CONTEXT_COMPACT.md — One-line per entry with groupings
# ---------------------------------------------------------------------------

def format_entry_compact(entry: dict, all_titles: set) -> str:
    """Format a single entry as one compact line: [type] title, creator, year."""
    mt = get_media_type(entry)
    title = entry.get("title", "").strip()
    creator = get_creator(entry)
    year = entry.get("year")

    tag = f"[{mt}] " if mt != "book" else ""
    line = f"- {tag}{title}"
    if creator:
        line += f" — {creator}"
    if year:
        line += f" ({year})"

    return line


def generate_compact(catalog: list[dict], buckets: dict[int, list[dict]]) -> int:
    """Generate CONTEXT_COMPACT.md — one-line per entry with groupings."""
    all_titles = {e["title"] for e in catalog}

    type_counts = Counter(get_media_type(e) for e in catalog)
    type_summary_parts = []
    for mt in ["book", "film", "music"]:
        if type_counts[mt]:
            label = "books" if mt == "book" else "films" if mt == "film" else "albums"
            type_summary_parts.append(f"{type_counts[mt]} {label}")
    type_summary = ", ".join(type_summary_parts)

    md = [
        "# Collection — Compact Reference",
        "",
        f"*{len(catalog)} entries ({type_summary}). One-line entries with themes and relationship pointers. "
        "For full synopses see CONTEXT.md; for intellectual profile only see CONTEXT_OVERVIEW.md.*",
        "",
    ]

    entry_count = 0

    for idx, group in enumerate(GROUPINGS):
        entries = buckets[idx]
        if not entries:
            continue
        md.append(f"### {group['name']}")
        md.append("")
        for entry in entries:
            md.append(format_entry_compact(entry, all_titles))
            entry_count += 1
        md.append("")

    COMPACT_PATH.write_text("\n".join(md))
    return entry_count


# ---------------------------------------------------------------------------
# TIER 3: CONTEXT_OVERVIEW.md — Intellectual profile only
# ---------------------------------------------------------------------------

def generate_overview(catalog: list[dict], buckets: dict[int, list[dict]]) -> None:
    """Generate CONTEXT_OVERVIEW.md — pure intellectual fingerprint."""
    total = len(catalog)
    type_counts = Counter(get_media_type(e) for e in catalog)
    active_groups = [(GROUPINGS[i]["name"], len(entries))
                     for i, entries in buckets.items() if entries]
    active_groups.sort(key=lambda x: x[1], reverse=True)

    def representatives(group_idx: int, n: int = 4) -> list[str]:
        entries = buckets[group_idx]
        scored = sorted(entries,
                        key=lambda e: len(e.get("in_conversation_with", [])),
                        reverse=True)
        return [e["title"] for e in scored[:n]]

    # Year range
    years = [e["year"] for e in catalog if e.get("year")]
    year_range = f"{min(years)}\u2013{max(years)}" if years else "various"

    # Media breakdown
    type_summary_parts = []
    for mt in ["book", "film", "music"]:
        if type_counts[mt]:
            label = "books" if mt == "book" else "films" if mt == "film" else "albums"
            type_summary_parts.append(f"{type_counts[mt]} {label}")
    type_summary = ", ".join(type_summary_parts)

    md = [
        "# Collection — Intellectual Profile",
        "",
        f"*{total} entries ({type_summary}) spanning {year_range}. Lightweight overview for baseline context "
        "loading. For entries see CONTEXT_COMPACT.md or CONTEXT.md.*",
        "",
        INTRO,
        "",
        "The collection's center of gravity: the post-Fluxus tradition of art as instruction, "
        "event, and system; critical theory from Situationism through media studies to digital "
        "culture critique; and a persistent attention to craft and embodied practice. Not an "
        "institutional survey \u2014 a working artist's shelves shaped by decades of practice.",
        "",
        "## Major Clusters",
        "",
    ]

    sized = [(idx, len(buckets[idx])) for idx in range(len(GROUPINGS)) if buckets[idx]]
    sized.sort(key=lambda x: x[1], reverse=True)
    for idx, count in sized[:15]:
        reps = representatives(idx, 2)
        short_reps = [r if len(r) < 40 else r[:37] + "..." for r in reps]
        md.append(f"- **{GROUPINGS[idx]['name']}** ({count}) \u2014 {', '.join(short_reps)}")

    md.append("")
    md.append(
        "Cross-cutting threads: technology and the body; spectacle and resistance; "
        "institutional art vs. autonomous practice; archives, memory, and documentation; "
        "craft survival in a dematerializing culture. The `in_conversation_with` graph "
        "in the full catalog traces these connections across books, films, and music."
    )
    md.append("")

    OVERVIEW_PATH.write_text("\n".join(md))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate():
    catalog = load_catalog()
    buckets = build_buckets(catalog)

    # Generate all three tiers
    full_count = generate_full(catalog, buckets)
    compact_count = generate_compact(catalog, buckets)
    generate_overview(catalog, buckets)

    # Report
    active = sum(1 for b in buckets.values() if b)
    type_counts = Counter(get_media_type(e) for e in catalog)
    type_parts = []
    for mt in ["book", "film", "music"]:
        if type_counts[mt]:
            type_parts.append(f"{type_counts[mt]} {mt}s")

    print(f"Generated {len(catalog)} entries ({', '.join(type_parts)}) across {active} groupings:\n")

    for path, label in [
        (CONTEXT_PATH, "CONTEXT.md (full)"),
        (COMPACT_PATH, "CONTEXT_COMPACT.md (compact)"),
        (OVERVIEW_PATH, "CONTEXT_OVERVIEW.md (overview)"),
    ]:
        size = path.stat().st_size
        lines = len(path.read_text().splitlines())
        if size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        print(f"  {label:40s} {size_str:>10s}  ({lines} lines)")

    return full_count, compact_count


def generate_wiki_pages():
    """Generate wiki pages by delegating to generate_wiki.py."""
    from generate_wiki import generate_wiki
    pages = generate_wiki()

    print(f"\nGenerated {len(pages)} wiki pages + INDEX.md in wiki/\n")
    for title, filename, content in sorted(pages, key=lambda x: x[0]):
        size = len(content)
        lines = content.count('\n')
        print(f"  {filename:55s} {size:>6d} bytes  ({lines} lines)")

    wiki_dir = REPO_ROOT / "wiki"
    index_size = (wiki_dir / "INDEX.md").stat().st_size
    print(f"\n  {'INDEX.md':55s} {index_size:>6d} bytes")
    return pages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate context files and wiki from catalog.json")
    parser.add_argument("--wiki", action="store_true", help="Regenerate wiki pages only")
    parser.add_argument("--context", action="store_true", help="Regenerate context tiers only")
    args = parser.parse_args()

    # Default: regenerate everything
    do_context = not args.wiki or args.context
    do_wiki = not args.context or args.wiki
    if not args.wiki and not args.context:
        do_context = True
        do_wiki = True

    ok = True

    if do_context:
        full_count, compact_count = generate()
        catalog = load_catalog()
        expected = len(catalog)

        for label, count in [("full", full_count), ("compact", compact_count)]:
            if count == expected:
                print(f"\n  {label}: all {expected} entries included \u2713")
            else:
                print(f"\n  {label}: expected {expected} entries, got {count} \u2717", file=sys.stderr)
                ok = False

    if do_wiki:
        # Add scripts dir to path so generate_wiki can be imported
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        generate_wiki_pages()

    if not ok:
        sys.exit(1)
