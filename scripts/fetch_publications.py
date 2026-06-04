#!/usr/bin/env python3
"""
fetch_publications.py — Sync publications + author stats from Google Scholar

Usage:
    python cv.py fetch-pubs

What it does:
  1. Fetches author-level stats (total citations, h-index, i10-index) → data/scholar_stats.yaml
  2. Fetches all publications with per-paper citation counts → merges into data/publications.yaml
     (existing manual fields like rcn_group, rcn_num, selected are preserved)
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()
DATA_DIR = Path(__file__).parent.parent / "data"
PUBLICATIONS_FILE = DATA_DIR / "publications.yaml"
PROFILE_FILE      = DATA_DIR / "profile.yaml"
STATS_FILE        = DATA_DIR / "scholar_stats.yaml"


def load_yaml(path: Path) -> dict | list:
    with open(path) as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, data) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def normalize_title(title: str) -> str:
    """Lowercase + collapse whitespace for fuzzy dedup."""
    return " ".join(title.lower().split())


def fetch_from_scholar(scholar_id: str) -> tuple[dict, list[dict]]:
    """
    Returns:
        (author_stats, publications)
        author_stats: dict with total_citations, h_index, i10_index, fetched_date
        publications:  list of dicts with title, authors, venue, year, citations, ...
    """
    try:
        from scholarly import scholarly as _scholarly
    except ImportError:
        console.print(
            "[bold red]Error:[/] `scholarly` is not installed. "
            "Run: pip install scholarly"
        )
        sys.exit(1)

    console.print(f"[cyan]Fetching Google Scholar profile for ID:[/] {scholar_id}")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Querying author profile...", total=None)

            author = _scholarly.search_author_id(scholar_id)
            _scholarly.fill(author, sections=["basics", "indices", "publications"])

            # ── Author-level stats ───────────────────────────────────────────
            citedby  = author.get("citedby", 0)
            hindex   = author.get("hindex", 0)
            i10index = author.get("i10index", 0)

            author_stats = {
                "total_citations": citedby,
                "h_index":         hindex,
                "i10_index":       i10index,
                "fetched_date":    str(date.today()),
            }

            console.print(
                f"  [green]Stats:[/] {citedby} citations · h-index {hindex} · i10-index {i10index}"
            )

            # ── Per-paper details ────────────────────────────────────────────
            pubs = author.get("publications", [])
            progress.update(task, description=f"Found {len(pubs)} publications, fetching details...")

            fetched = []
            for i, pub in enumerate(pubs):
                try:
                    filled = _scholarly.fill(pub)
                    bib    = filled.get("bib", {})

                    authors_raw = bib.get("author", "")
                    if isinstance(authors_raw, str):
                        authors = [a.strip() for a in authors_raw.split(" and ")]
                    elif isinstance(authors_raw, list):
                        authors = authors_raw
                    else:
                        authors = []

                    venue    = bib.get("journal", "") or bib.get("booktitle", "") or ""
                    pub_type = _guess_type(venue, bib)

                    record = {
                        "title":     bib.get("title", ""),
                        "authors":   authors,
                        "venue":     venue,
                        "year":      int(bib.get("pub_year", 0)) if bib.get("pub_year") else None,
                        "url":       filled.get("pub_url", ""),
                        "type":      pub_type,
                        "selected":  False,
                        "citations": filled.get("num_citations", 0),
                    }
                    fetched.append(record)
                    progress.update(
                        task,
                        description=f"[{i+1}/{len(pubs)}] {bib.get('title', '')[:60]}..."
                    )
                    time.sleep(0.3)   # be polite to Scholar
                except Exception as e:
                    console.print(f"[yellow]Warning:[/] Could not fill publication: {e}")

    except Exception as e:
        console.print(f"[bold red]Error fetching from Scholar:[/] {e}")
        console.print("[yellow]This may be a CAPTCHA or rate-limiting issue. Exiting without overwriting data.[/]")
        sys.exit(1)

    return author_stats, fetched


def _guess_type(venue: str, bib: dict) -> str:
    venue_l = venue.lower()
    # Explicit preprints
    if "arxiv" in venue_l or "biorxiv" in venue_l or "preprint" in venue_l:
        return "preprint"
    # Conference proceedings books / abstract collections
    if "proceedings of" in venue_l or "workshop" in venue_l:
        return "abstract"
    # Nordic Machine Intelligence is a commentary/viewpoint venue, not peer-reviewed
    if "nordic machine intelligence" in venue_l:
        return "abstract"
    # Conference papers (booktitle set, no journal)
    if bib.get("booktitle") and not bib.get("journal"):
        return "conference"
    if "encyclopedia" in venue_l or "handbook" in venue_l:
        return "book_chapter"
    # No venue at all → likely scraped abstract
    if not venue.strip():
        return "abstract"
    return "journal"


def _title_words(title: str) -> set:
    """Bag of significant words for fuzzy title matching."""
    stop = {"the", "a", "an", "of", "in", "and", "or", "for", "to", "by",
            "with", "on", "from", "is", "are", "its", "an"}
    import re
    return set(re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).split()) - stop


def _title_similarity(t1: str, t2: str) -> float:
    """Jaccard similarity between word sets of two titles."""
    w1, w2 = _title_words(t1), _title_words(t2)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def merge_publications(existing: list[dict], fetched: list[dict],
                       sim_threshold: float = 0.6) -> tuple[list[dict], int]:
    """Merge fetched into existing, deduplicating by fuzzy title similarity.
    Existing manual fields (rcn_group, rcn_num, selected, etc.) are preserved.
    Only `citations` is updated from Scholar when the fetched count is higher.
    Returns (merged_list, n_added).
    """
    merged  = list(existing)
    n_added = 0

    for pub in fetched:
        # Find best-matching existing entry by title similarity
        best_score, best_idx = 0.0, None
        for idx, ep in enumerate(merged):
            score = _title_similarity(pub.get("title", ""), ep.get("title", ""))
            if score > best_score:
                best_score, best_idx = score, idx

        if best_score >= sim_threshold:
            # Duplicate found — update citation count only if Scholar has more
            fetched_cit  = pub.get("citations") or 0
            existing_cit = merged[best_idx].get("citations") or 0
            if fetched_cit > existing_cit:
                merged[best_idx]["citations"] = fetched_cit
        else:
            # Genuinely new paper
            pub["_source"] = "scholar"   # tag so we can identify it later
            merged.append(pub)
            n_added += 1

    return merged, n_added


def main() -> None:
    profile    = load_yaml(PROFILE_FILE)
    scholar_id = profile.get("scholar_id", "").strip()

    if not scholar_id:
        console.print("[bold red]Error:[/] `scholar_id` not set in data/profile.yaml")
        sys.exit(1)

    existing: list[dict] = []
    if PUBLICATIONS_FILE.exists():
        existing = load_yaml(PUBLICATIONS_FILE) or []

    author_stats, fetched = fetch_from_scholar(scholar_id)

    # Save author-level stats
    save_yaml(STATS_FILE, author_stats)
    console.print(
        f"[bold green]✓[/] Scholar stats written to [cyan]data/scholar_stats.yaml[/]"
    )

    # Merge publications
    merged, n_added = merge_publications(existing, fetched)
    merged.sort(key=lambda p: p.get("year") or 0, reverse=True)
    save_yaml(PUBLICATIONS_FILE, merged)
    console.print(
        f"[bold green]✓[/] Publications updated: [bold]{n_added}[/] new · "
        f"[bold]{len(merged)}[/] total · citations refreshed."
    )


if __name__ == "__main__":
    main()
