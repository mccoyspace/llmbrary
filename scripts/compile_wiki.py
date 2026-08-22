#!/usr/bin/env python3
"""
compile_wiki.py — Compile wiki_src/*.md into wiki/ pages.

Essays live as plain markdown in wiki_src/. Citations to catalog holdings are
written as [[Title]] markers. At build time every marker is resolved against
catalog.json and rendered with the entry's live author/year metadata:

    [[The Interpretation of Dreams]]
        -> *The Interpretation of Dreams* (Sigmund Freud, 1899)

This keeps synthesis (human/LLM-authored prose, editable without touching
code) separate from rendering (deterministic, stdlib-only, hallucination-
proof: a [[Title]] that doesn't exist in the catalog is reported and left
unresolved rather than silently fabricated).

Usage:
    python3 scripts/compile_wiki.py            # compile all pages + INDEX.md
    python3 scripts/compile_wiki.py --check    # verify only; exit 1 on problems

Stdlib-only. No external dependencies.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"
SRC_DIR = REPO_ROOT / "wiki_src"
WIKI_DIR = REPO_ROOT / "wiki"

CITE_RE = re.compile(r"\[\[(.+?)\]\]")


# ---------------------------------------------------------------------------
# Catalog loading and reference formatting
# ---------------------------------------------------------------------------

def load_catalog() -> dict:
    """Load catalog.json keyed by exact title."""
    import json
    with open(CATALOG_PATH) as f:
        entries = json.load(f)
    by_title = {}
    for e in entries:
        by_title[e["title"]] = e  # last wins, matching legacy build_indices
    return by_title


def format_book_ref(entry: dict) -> str:
    """Format a catalog entry as an inline markdown reference."""
    author = entry.get("author") or ""
    year = entry.get("year")
    parts = [f"*{entry['title']}*"]
    if author:
        parts[0] += f" ({author}"
        if year:
            parts[0] += f", {year}"
        parts[0] += ")"
    elif year:
        parts[0] += f" ({year})"
    return parts[0]


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def compile_page(text: str, by_title: dict, src_name: str):
    """Resolve [[Title]] markers in one source page.

    Returns (compiled_text, missing_titles).
    """
    missing = []

    def repl(m):
        title = m.group(1).strip()
        entry = by_title.get(title)
        if entry is None:
            # tolerate accent/case drift before failing
            entry = _fuzzy_lookup(title, by_title)
        if entry is None:
            missing.append(title)
            return m.group(0)  # leave the marker visible
        return format_book_ref(entry)

    compiled = CITE_RE.sub(repl, text)
    return compiled, missing


def _fuzzy_lookup(title: str, by_title: dict):
    """Exact-match fallbacks for common authoring drift."""
    lowered = {t.lower(): t for t in by_title}
    t = lowered.get(title.lower())
    if t:
        return by_title[t]
    import unicodedata
    def norm(s):
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return " ".join("".join(c if c.isalnum() else " " for c in s).split()).lower()
    n = norm(title)
    for cand_t, orig in lowered.items():
        if norm(cand_t) == n:
            return by_title[orig]
    return None


def extract_summary(content: str) -> str:
    """First sentence of first paragraph, for INDEX.md blurbs."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()
                  and not p.strip().startswith("#")
                  and not p.strip().startswith("See also:")
                  and not p.strip().startswith("## Key")
                  and not p.strip().startswith("-")]
    desc = ""
    if paragraphs:
        first = paragraphs[0].replace("\n", " ")
        for i, ch in enumerate(first):
            if ch == "." and i < len(first) - 1 and first[i + 1] == " ":
                desc = first[:i + 1]
                break
        if not desc:
            desc = first[:120] + "..."
    return desc


def generate_index(pages: list) -> str:
    """Generate INDEX.md from compiled pages: [(title, filename, content)]."""
    lines = [
        "# Wiki Index",
        "",
        "Synthesized thematic pages tracing intellectual threads across the library.",
        "Each page synthesizes across multiple books rather than documenting individual titles.",
        "",
        "Compiled from `wiki_src/*.md` citations resolved against `catalog.json`",
        "by `scripts/compile_wiki.py`.",
        "",
        "---",
        "",
    ]
    for title, filename, content in sorted(pages, key=lambda x: x[0]):
        lines.append(f"- [{title}]({filename}) — {extract_summary(content)}")
    lines.append("")
    return "\n".join(lines)


def slugify(stem: str) -> str:
    """Filename is already slugged at authoring time; pass through validation."""
    s = stem.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", s):
        raise ValueError(
            f"Source filename '{stem}.md' must be lowercase-hyphen-slugged "
            f"(it becomes wiki/{stem}.md)")
    return s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compile wiki_src/ into wiki/.")
    parser.add_argument("--check", action="store_true",
                        help="Verify citations only; write nothing.")
    args = parser.parse_args()

    if not SRC_DIR.exists():
        print(f"Error: {SRC_DIR} not found.", file=sys.stderr)
        sys.exit(1)

    by_title = load_catalog()

    pages, all_missing = [], []
    for src_path in sorted(SRC_DIR.glob("*.md")):
        stem = src_path.stem
        raw = src_path.read_text()
        # Page title = first H1; filename derives from source filename.
        m = re.match(r"#\s+(.+)", raw)
        title = m.group(1).strip() if m else stem.replace("-", " ").title()
        try:
            filename = slugify(stem) + ".md"
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        compiled, missing = compile_page(raw, by_title, src_path.name)
        if missing:
            for t in missing:
                all_missing.append((src_path.name, t))
                print(f"  UNRESOLVED in {src_path.name}: [[{t}]]", file=sys.stderr)
        pages.append((title, filename, compiled))

    if args.check:
        total_cites = sum(len(CITE_RE.findall(p[2])) for p in pages)
        unresolved = len(all_missing)
        print(f"{len(pages)} pages checked; "
              f"{total_cites} unresolved citation(s)." if unresolved else
              f"{len(pages)} pages checked; all citations resolved.")
        sys.exit(1 if unresolved else 0)

    WIKI_DIR.mkdir(exist_ok=True)
    for _, filename, compiled in pages:
        (WIKI_DIR / filename).write_text(compiled)
    (WIKI_DIR / "INDEX.md").write_text(generate_index(pages))

    print(f"Compiled {len(pages)} pages into wiki/ (+INDEX.md)")
    if all_missing:
        print(f"WARNING: {len(all_missing)} unresolved citation(s) "
              f"— see UNRESOLVED lines above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
