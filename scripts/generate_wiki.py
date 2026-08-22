#!/usr/bin/env python3
"""
generate_wiki.py — DEPRECATED direct-generation engine, kept as a thin
compatibility wrapper around scripts/compile_wiki.py.

Wiki essays now live as editable markdown in `wiki_src/*.md`, with catalog
citations written as [[Title]] markers. Running this module (or calling
generate_wiki()) compiles those sources into wiki/, resolving every marker
against catalog.json at build time.

To edit or add pages, edit/create files in wiki_src/ — do not add code here.
See `scripts/compile_wiki.py` for the compilation contract.

Usage:
    python3 scripts/generate_wiki.py     # same effect as compile_wiki.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import json

from compile_wiki import (
    CATALOG_PATH,
    SRC_DIR,
    WIKI_DIR,
    compile_page,
    extract_summary,
    format_book_ref,
    generate_index,
    load_catalog,
)


def generate_wiki():
    """Compile wiki_src/ -> wiki/. Returns [(title, filename, content)].

    Kept for backward compatibility with regenerate.py, which imports this
    function and prints per-page statistics.
    """
    if not SRC_DIR.exists():
        raise FileNotFoundError(
            f"{SRC_DIR} not found — nothing to compile. "
            f"Wiki sources should live in wiki_src/*.md")

    by_title = load_catalog()
    import re
    pages = []
    unresolved = []
    for src_path in sorted(SRC_DIR.glob("*.md")):
        raw = src_path.read_text()
        m = re.match(r"#\s+(.+)", raw)
        title = m.group(1).strip() if m else src_path.stem.replace("-", " ").title()
        compiled, missing = compile_page(raw, by_title, src_path.name)
        for t in missing:
            unresolved.append((src_path.name, t))
            print(f"  UNRESOLVED citation in {src_path.name}: [[{t}]]",
                  file=sys.stderr)
        pages.append((title, src_path.stem + ".md", compiled))

    WIKI_DIR.mkdir(exist_ok=True)
    for _, filename, compiled in pages:
        (WIKI_DIR / filename).write_text(compiled)
    (WIKI_DIR / "INDEX.md").write_text(generate_index(pages))

    return pages


if __name__ == "__main__":
    pages = generate_wiki()
    print(f"\nCompiled {len(pages)} wiki pages + INDEX.md in wiki/\n")
    for title, filename, content in sorted(pages, key=lambda x: x[0]):
        size = len(content)
        lines = content.count('\n')
        print(f"  {filename:55s} {size:>6d} bytes  ({lines} lines)")

    index_size = (WIKI_DIR / "INDEX.md").stat().st_size
    print(f"\n  {'INDEX.md':55s} {index_size:>6d} bytes")
