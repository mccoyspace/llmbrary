# llmbrary

Turn a physical media collection into a portable knowledge base for LLMs.

This repository creates a structured catalog of books, films, and music extracted from photographs of shelves and imported from text lists. The catalog is designed to be loaded into LLM context windows, giving AI assistants awareness of the intellectual background behind a conversation — the books that shaped how you think, the films that informed your visual language, the music that soundtracks your practice.

## Why

LLMs are general-purpose by default. They don't know what you've read, watched, or listened to, what intellectual traditions matter to you, or what conceptual vocabulary you actually use. Giving a model access to your collection doesn't make it an expert — but it does let it recognize when a project intersects with something on your shelves, trace thematic connections you might not have articulated, and meet you closer to where you actually are.

## Multi-Media Support

The catalog supports three media types, each with shared core fields and type-specific metadata:

| Media Type | Creator Field | Type-Specific Fields |
|---|---|---|
| `book` | `author` | `publisher` |
| `film` | `director` | `cast`, `format` (DVD/Blu-ray/digital) |
| `music` | `artist` | `album`, `label`, `format` (CD/vinyl/digital) |

All entries share: `title`, `media_type`, `year`, `synopsis`, `themes`, `confidence`, `needs_review`, `in_conversation_with`, and `source_image`. The `in_conversation_with` field supports cross-media connections — a film can be in conversation with a book or an album.

If `media_type` is missing from an entry, it defaults to `"book"` for backward compatibility.

## Repository Structure

```
llmbrary/
├── catalog.json              # Enriched catalog entries (structured data)
├── CONTEXT.md                # Full catalog as markdown (~40K tokens)
├── CONTEXT_COMPACT.md        # One-line per entry with groupings (~5K tokens)
├── CONTEXT_OVERVIEW.md       # Intellectual profile only (~500 tokens)
├── schema.json               # JSON Schema for catalog validation
├── extracted_titles.json     # Raw extraction data from vision processing
├── unreadable.json           # Items that couldn't be identified from photos
├── photos/
│   ├── inbox/                # Drop new shelf photos here (books, DVDs, CDs)
│   └── processed/            # Photos move here after processing
├── wiki/                     # Synthesized thematic pages (generated)
│   ├── INDEX.md              # Table of contents for all wiki pages
│   └── *.md                  # ~25 thematic essays tracing intellectual threads
├── scripts/
│   ├── ingest.py             # Scan inbox for new photos, build processing manifest
│   ├── import_text.py        # Import books from a plain text list
│   ├── import_media.py       # Import films or music from a plain text list
│   ├── merge_catalog.py      # Merge new extractions into catalog with deduplication
│   ├── regenerate.py         # Regenerate all context files + wiki from catalog.json
│   ├── generate_wiki.py      # Wiki page generation engine
│   └── lint.py               # Catalog quality review and suggestions
├── claude/                   # Claude-specific skill integration
│   └── SKILL.md              # Skill wrapper with tiered loading strategy
└── README.md
```

## Catalog Format

Each entry in `catalog.json` contains:

| Field | Type | Description |
|---|---|---|
| `title` | string | Title of the work |
| `media_type` | "book"\|"film"\|"music" | Type of media (defaults to "book") |
| `author` | string\|null | Author or editor (books) |
| `director` | string\|null | Director (films) |
| `artist` | string\|null | Artist or band (music) |
| `year` | integer\|null | Publication/release year |
| `synopsis` | string | Description and intellectual context |
| `themes` | string[] | Key themes and subjects |
| `source_image` | string | Reference photograph filename |
| `confidence` | "high"\|"medium"\|"low" | Identification confidence |
| `needs_review` | boolean | Whether entry needs verification |
| `in_conversation_with` | string[] | Related titles in the collection (max 5, cross-media) |
| `cast` | string[] | Cast members (films, optional) |
| `label` | string\|null | Record label (music, optional) |
| `publisher` | string\|null | Publisher (books, optional) |
| `format` | string\|null | Physical/digital format |

The `in_conversation_with` field maps relationships between works — not citations, but thematic, methodological, or historical resonance. These relationships allow traversal of intellectual lineages across the collection and across media types.

The full schema is defined in `schema.json`.

## Wiki Layer

The `wiki/` directory contains synthesized thematic pages that trace intellectual threads across the collection. Inspired by Karpathy's LLM Knowledge Base pattern, these are not per-entry pages but essay-length syntheses that map how ideas flow between titles.

Each wiki page covers a theme, movement, or conceptual thread — for example, a page on a philosophical movement would synthesize across primary texts, critical commentary, and related artistic practices in the collection. Pages cross-link to each other where threads intersect, and cite specific titles from the catalog.

Wiki pages are generated from `catalog.json` by `scripts/generate_wiki.py` and regenerated alongside the context tiers. They're useful for LLM context when you want to understand the intellectual landscape of a topic area rather than individual entries. See `wiki/INDEX.md` for the full table of contents.

## Querying the Collection

The Claude skill (`claude/SKILL.md`) includes a query mode for asking questions *about* the collection — its contents, thematic threads, cross-media connections, and gaps. When the skill is loaded, questions like "What do I have about surveillance?" or "Trace the thread from Situationism through my collection" trigger a structured search across `catalog.json` themes, synopses, the `in_conversation_with` graph, and synthesized wiki pages.

Query mode returns structured answers that cite specific titles, note cross-media connections (book X relates to film Y relates to album Z), group results by sub-theme, and identify gaps — areas where the collection has thin coverage or where one media type dominates.

See the "Query Mode" section in `claude/SKILL.md` for the full protocol and example queries.

## Filing Insights Back

Useful outputs from conversation — thematic analyses, comparisons, gap reports — can be saved back into the knowledge base.

### Wiki filing

Save a new thematic wiki page from a markdown file or stdin:

```bash
# From a file
python3 scripts/file_wiki.py "Surveillance Across Media" content.md

# From stdin
echo "..." | python3 scripts/file_wiki.py "Surveillance Across Media" --stdin

# Preview without writing
python3 scripts/file_wiki.py "Surveillance Across Media" content.md --dry-run

# Overwrite existing page
python3 scripts/file_wiki.py "Surveillance Across Media" content.md --force
```

The script writes the page to `wiki/`, generates a summary blurb, and updates `wiki/INDEX.md`. It's stdlib-only with no external dependencies.

When using the Claude skill, Claude will offer to file conversation outputs as wiki pages when it produces something worth persisting — comparisons, traced lineages, gap analyses. It handles the writing and filing automatically.

### Catalog filing

New entries can be added to `catalog.json` during conversation. When Claude encounters a title the user owns that isn't in the catalog, it offers to create a properly formatted entry with synopsis, themes, and `in_conversation_with` links, then appends it to the catalog. Run `scripts/regenerate.py` afterward to rebuild context tiers and wiki pages.

See the "Filing Protocol" section in `claude/SKILL.md` for the full protocol.

## Catalog Quality

Run `scripts/lint.py` to review the catalog for issues: isolated entries with no relationships, broken cross-references, potential duplicates (fuzzy title matching), missing fields, and theme clusters that might warrant new wiki pages.

```bash
python3 scripts/lint.py
```

## Context Tiers

The catalog is rendered at three levels of detail, designed for different token budgets and use cases.

| Tier | File | Size | Tokens | Contains |
|---|---|---|---|---|
| Overview | `CONTEXT_OVERVIEW.md` | ~3 KB | ~500 | Intellectual profile, major clusters, cross-cutting threads |
| Compact | `CONTEXT_COMPACT.md` | ~18 KB | ~5K | One-line per entry (title/creator/year) organized by grouping |
| Full | `CONTEXT.md` | ~226 KB | ~40K | Complete synopses, themes, and relationship annotations |

Non-book entries are tagged with `[film]` or `[music]` in the context files for easy identification. Within each thematic grouping, entries are organized by media type (books first, then films, then music).

**Choosing a tier:**

- **Small context window** (8K-32K tokens): Use Overview. It gives the model the vocabulary to recognize thematic overlaps without consuming significant budget.
- **Medium context window** (32K-128K tokens): Use Compact. Every entry is listed with enough structure to identify relevance.
- **Large context window** (128K+ tokens): Can use Full, or load the Overview as baseline and pull specific sections from Full as needed.
- **Structured/programmatic access**: Use `catalog.json` directly for filtering, graph traversal, and tool-building.

The Claude skill wrapper in `claude/SKILL.md` implements a selective loading strategy: always load Overview, escalate to Compact or Full sections based on task requirements, and use catalog.json for structured queries.

## Using with LLMs

### Direct context injection (any LLM)

Pick the appropriate tier for your context budget and paste it into the system prompt or upload as a file. The Overview (~500 tokens) is small enough to always include as baseline context; the Compact version fits comfortably in any modern context window; the Full version is best for models with 128K+ token windows.

### Structured queries

Load `catalog.json` for programmatic access — filtering by theme, media type, creator, year, or traversing the `in_conversation_with` relationship graph. Useful for building tools on top of the catalog or for selective context loading.

### Claude skill integration

The `claude/SKILL.md` file is a skill wrapper for Claude Code and Cowork that implements smart tiered loading. It instructs Claude on when to use each tier, how to walk the relationship graph, and how to surface relevant works during projects.

To use it, add the `claude/` directory to your Claude Code or Cowork skills path.

## Extraction Methodology

The catalog was built through a multi-stage pipeline:

1. **Photography** — Photographs of shelves capturing spine text at readable resolution (book spines, DVD/Blu-ray cases, CD jewel cases, vinyl sleeves)
2. **Vision extraction** — LLM vision models identified titles and creators from spine images, producing `extracted_titles.json`. When the physical format is identifiable (DVD case vs. book spine vs. CD jewel case), entries are tagged with the appropriate `media_type`.
3. **Enrichment** — Each identified title was enriched with year, synopsis, themes, and confidence scoring
4. **Relationship mapping** — `in_conversation_with` links were generated by analyzing thematic overlap across the full collection (cross-media connections supported)
5. **Context generation** — `scripts/regenerate.py` renders the structured catalog into the markdown format in `CONTEXT.md`, organized into 30 thematic categories

Some items could not be identified from photographs (recorded in `unreadable.json`). Entries with `confidence: "medium"` or `needs_review: true` may contain inaccuracies.

## Workflow

Adding new items follows a three-stage pipeline: ingest photos, extract and merge titles, then regenerate the context file.

### 1. Drop photos

Place new shelf photographs in `photos/inbox/`. Any `.jpg`, `.jpeg`, `.png`, or `.heic` files will be picked up. Photos can contain book spines, DVD/Blu-ray cases, CD jewel cases, or vinyl sleeves.

### 2. Run ingestion

```bash
# Preview what's new
python3 scripts/ingest.py --dry-run

# Log new images and produce inbox_manifest.json
python3 scripts/ingest.py

# Hint that these photos are DVD shelves (helps downstream extraction)
python3 scripts/ingest.py --media-hint film

# After extraction, move processed images out of inbox
python3 scripts/ingest.py --move
```

The script writes `processing_log.json` so images are never processed twice. The `--media-hint` flag records what kind of physical media the photos contain, which helps the vision extraction step tag entries correctly.

### Text import — books

If you have a list of books as plain text, you can skip the photo pipeline entirely:

```bash
# Preview what will be parsed
python3 scripts/import_text.py booklist.txt --dry-run

# Import — writes new_extractions.json
python3 scripts/import_text.py booklist.txt

# Force a specific format instead of auto-detecting
python3 scripts/import_text.py booklist.txt --format dash

# Adjust dedup sensitivity
python3 scripts/import_text.py booklist.txt --threshold 0.80
```

The script auto-detects line format from the following:

| Format | Example |
|---|---|
| Dash | `Title - Author` or `Title — Author` |
| By | `Title by Author` |
| Comma | `Title, Author` |
| Parenthetical | `Title (Author)` |
| Colon | `Author: Title` |
| Tab-separated | `Title\tAuthor` |
| CSV | `"Title","Author","Year"` |
| Title only | `Title` |

### Text import — films and music

Use `import_media.py` for films and music:

```bash
# Import films
python3 scripts/import_media.py --type film films.txt
python3 scripts/import_media.py --type film films.txt --dry-run
python3 scripts/import_media.py --type film films.txt --format dash

# Import music
python3 scripts/import_media.py --type music albums.txt
python3 scripts/import_media.py --type music albums.txt --format by
```

Film formats:

| Format | Example |
|---|---|
| Dash | `Title (Year) - Director` or `Title - Director` |
| Colon | `Director: Title (Year)` |
| Title-year | `Title (Year)` or just `Title` |

Music formats:

| Format | Example |
|---|---|
| Dash | `Artist - Album (Year)` or `Artist - Album` |
| By | `Album by Artist` |
| CSV | `"Artist","Album","Year"` |
| Title only | `Album` or `Title` |

Deduplication is scoped by media_type — a book titled "Drive" won't conflict with a film titled "Drive". Output goes to `new_extractions.json` with the appropriate `media_type` set.

### Browser-based import

You can also import items directly in the browser using the **Text Import** tab in `review.html`. Select the media type (Book/Film/Music), paste a list, preview the parsed results, and add them to the catalog in one step.

### 3. Extract titles

Use your preferred vision extraction method (LLM vision, manual, etc.) to produce a `new_extractions.json` file — an array of objects following `schema.json`. At minimum each entry needs a `title`; include `media_type` to indicate the type. Missing enrichment fields will be flagged for review.

### 4. Merge into catalog

```bash
# Preview the merge
python3 scripts/merge_catalog.py new_extractions.json --dry-run

# Merge for real
python3 scripts/merge_catalog.py new_extractions.json
```

The merge script deduplicates by fuzzy title matching within the same media_type (configurable threshold via `--threshold`) and flags entries that need enrichment with `needs_review: true`.

### 5. Regenerate context files and wiki

```bash
# Regenerate everything (context tiers + wiki pages)
python3 scripts/regenerate.py

# Regenerate wiki pages only
python3 scripts/regenerate.py --wiki

# Regenerate context tiers only
python3 scripts/regenerate.py --context
```

This rebuilds all three context tiers (`CONTEXT.md`, `CONTEXT_COMPACT.md`, `CONTEXT_OVERVIEW.md`) and the `wiki/` directory from the current state of `catalog.json`, preserving thematic groupings and organizing entries by media type within each group. It prints file sizes for verification.

## Contributing

To add items manually, append entries to `catalog.json` following the schema in `schema.json`. Then regenerate the context file:

```bash
python3 scripts/regenerate.py
```

When adding entries:

- Set `media_type` to `"book"`, `"film"`, or `"music"`
- Use the appropriate creator field (`author`, `director`, or `artist`)
- Set `confidence` to `"high"` for manually verified entries
- Include `in_conversation_with` references to existing titles where thematic connections exist (max 5, cross-media allowed)
- Write synopses that capture intellectual context, not just plot summary
- Choose themes that reflect how the work functions in a broader intellectual landscape

## License

The catalog data (synopses, themes, relationships) is original work. Titles and creator names are factual information. Source photographs are not included in the distributed catalog.
