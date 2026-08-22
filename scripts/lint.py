#!/usr/bin/env python3
"""
lint.py — Review catalog.json for quality issues and improvement opportunities.

Usage:
    python3 scripts/lint.py

Checks for:
  - Books with no in_conversation_with relationships (isolated nodes)
  - Entries still marked needs_review
  - Potential duplicate entries (fuzzy title matching)
  - Theme clusters that might warrant new wiki pages
  - Broken in_conversation_with references (pointing to non-existent titles)
  - Entries missing key fields (synopsis, themes, author)

Prints suggestions for improving the knowledge base.
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from difflib import SequenceMatcher

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"

# Similarity threshold for fuzzy duplicate detection
DUPLICATE_THRESHOLD = 0.82


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH) as f:
        return json.load(f)


def check_isolated_nodes(catalog: list[dict]) -> list[dict]:
    """Find entries with no in_conversation_with relationships."""
    return [e for e in catalog if not e.get("in_conversation_with")]


def check_needs_review(catalog: list[dict]) -> list[dict]:
    """Find entries flagged needs_review."""
    return [e for e in catalog if e.get("needs_review")]


def check_broken_references(catalog: list[dict]) -> list[tuple[str, str]]:
    """Find in_conversation_with references to non-existent titles."""
    all_titles = {e["title"] for e in catalog}
    broken = []
    for e in catalog:
        for ref in e.get("in_conversation_with", []):
            if ref not in all_titles:
                broken.append((e["title"], ref))
    return broken


def check_duplicates(catalog: list[dict]) -> list[tuple[str, str, float]]:
    """Find potential duplicate entries via fuzzy title matching."""
    titles = [e["title"] for e in catalog]
    dupes = []
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            ratio = SequenceMatcher(None, titles[i].lower(), titles[j].lower()).ratio()
            if ratio >= DUPLICATE_THRESHOLD and titles[i] != titles[j]:
                dupes.append((titles[i], titles[j], ratio))
    dupes.sort(key=lambda x: x[2], reverse=True)
    return dupes


def check_missing_fields(catalog: list[dict]) -> dict[str, list[str]]:
    """Find entries missing key fields."""
    issues = defaultdict(list)
    for e in catalog:
        title = e.get("title", "???")
        if not e.get("author") and not e.get("director") and not e.get("artist"):
            issues["no creator"].append(title)
        if not e.get("synopsis"):
            issues["no synopsis"].append(title)
        if not e.get("themes"):
            issues["no themes"].append(title)
        if not e.get("year"):
            issues["no year"].append(title)
    return dict(issues)


def suggest_wiki_pages(catalog: list[dict]) -> list[tuple[str, int, list[str]]]:
    """Find theme clusters that might warrant new wiki pages.

    Looks for themes that appear 4+ times and don't map well to existing
    wiki page topics.
    """
    theme_counts = Counter()
    theme_books = defaultdict(list)
    for e in catalog:
        for t in e.get("themes", []):
            t_lower = t.lower()
            theme_counts[t_lower] += 1
            theme_books[t_lower].append(e["title"])

    # Themes already well-covered by existing wiki pages
    covered_keywords = {
        "video art", "moving image", "situationism", "spectacle", "everyday life",
        "beat generation", "cut-up", "digital art", "nfts", "blockchain", "net art",
        "new media", "french theory", "deleuze", "foucault", "phenomenology",
        "fluxus", "neo-dada", "instruction art", "performance art",
        "shape-note", "oral tradition", "folk art", "craft",
        "experimental music", "sound", "jazz", "improvisation",
        "sculpture", "installation", "land art", "materiality",
        "conceptual art", "rule-based", "algorithmic",
        "photography", "documentary",
        "anarchism", "political philosophy", "radical politics",
        "painting", "abstraction",
        "media theory", "digital culture", "platform",
        "film", "cinema", "experimental film",
        "feminism", "gender", "women artists",
        "environmentalism", "ecology", "nature", "wilderness",
        "american literature", "short fiction", "poetry",
        "existentialism", "modernism",
        "mythology", "spirituality", "religion",
        "art criticism", "aesthetics", "philosophy of art",
        "counterculture", "pedagogy",
        "architecture", "urbanism",
        "science fiction", "cyberpunk", "dystopia",
        "typography", "graphic design", "design",
    }

    suggestions = []
    for theme, count in theme_counts.most_common():
        if count >= 4:
            # Check if this theme is already covered
            is_covered = any(kw in theme for kw in covered_keywords)
            if not is_covered:
                examples = theme_books[theme][:5]
                suggestions.append((theme, count, examples))

    return suggestions


def main():
    catalog = load_catalog()
    total = len(catalog)
    issues_found = False

    print(f"Linting catalog.json ({total} entries)\n")
    print("=" * 60)

    # 1. Isolated nodes
    isolated = check_isolated_nodes(catalog)
    if isolated:
        issues_found = True
        print(f"\n⚠  ISOLATED NODES — {len(isolated)} entries with no relationships:")
        for e in isolated:
            print(f"   • {e['title']}")
        print(f"\n   These entries are disconnected from the relationship graph.")
        print(f"   Consider adding in_conversation_with links.")

    # 2. Needs review
    review = check_needs_review(catalog)
    if review:
        issues_found = True
        print(f"\n⚠  NEEDS REVIEW — {len(review)} entries flagged:")
        for e in review:
            print(f"   • {e['title']} (confidence: {e.get('confidence', '?')})")

    # 3. Broken references
    broken = check_broken_references(catalog)
    if broken:
        issues_found = True
        print(f"\n✗  BROKEN REFERENCES — {len(broken)} in_conversation_with links to non-existent titles:")
        for src, ref in broken[:20]:
            print(f"   • \"{src}\" → \"{ref}\"")
        if len(broken) > 20:
            print(f"   ... and {len(broken) - 20} more")

    # 4. Potential duplicates
    dupes = check_duplicates(catalog)
    if dupes:
        issues_found = True
        print(f"\n⚠  POTENTIAL DUPLICATES — {len(dupes)} pairs with ≥{DUPLICATE_THRESHOLD:.0%} title similarity:")
        for t1, t2, ratio in dupes[:15]:
            print(f"   • {ratio:.0%} \"{t1}\" ↔ \"{t2}\"")
        if len(dupes) > 15:
            print(f"   ... and {len(dupes) - 15} more")

    # 5. Missing fields
    missing = check_missing_fields(catalog)
    if missing:
        issues_found = True
        print(f"\n⚠  MISSING FIELDS:")
        for field, titles in sorted(missing.items()):
            print(f"   {field}: {len(titles)} entries")
            for t in titles[:5]:
                print(f"     • {t}")
            if len(titles) > 5:
                print(f"     ... and {len(titles) - 5} more")

    # 6. Wiki page suggestions
    suggestions = suggest_wiki_pages(catalog)
    if suggestions:
        print(f"\n💡 POTENTIAL WIKI PAGES — themes with 4+ entries not well-covered:")
        for theme, count, examples in suggestions[:10]:
            examples_str = ", ".join(examples[:3])
            print(f"   • \"{theme}\" ({count} entries): {examples_str}")

    # Summary
    print("\n" + "=" * 60)
    if not issues_found:
        print(f"\n✓  Catalog looks good! {total} entries, no issues found.")
    else:
        counts = []
        if isolated: counts.append(f"{len(isolated)} isolated")
        if review: counts.append(f"{len(review)} needs review")
        if broken: counts.append(f"{len(broken)} broken refs")
        if dupes: counts.append(f"{len(dupes)} potential dupes")
        if missing: counts.append(f"{sum(len(v) for v in missing.values())} missing fields")
        print(f"\n  Summary: {', '.join(counts)}")

    # Connection stats
    conn_counts = [len(e.get("in_conversation_with", [])) for e in catalog]
    avg_conns = sum(conn_counts) / len(conn_counts) if conn_counts else 0
    print(f"\n  Graph stats: {sum(conn_counts)} total connections, "
          f"avg {avg_conns:.1f} per entry, "
          f"max {max(conn_counts)} connections")

    # Confidence distribution
    conf = Counter(e.get("confidence", "unset") for e in catalog)
    print(f"  Confidence: {dict(conf)}")

    return 1 if broken else 0  # Exit 1 only for broken refs (actual errors)


if __name__ == "__main__":
    sys.exit(main())
