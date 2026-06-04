#!/usr/bin/env python3
"""
cv.py — Main CLI entry point for the CorriculumVitae system.

Usage:
    python cv.py build --template rcn
    python cv.py build --template classic
    python cv.py build --template html
    python cv.py build --all
    python cv.py fetch-pubs
    python cv.py list-templates
    python cv.py open --template html
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

# Ensure the repo root is on sys.path so `scripts` is importable
sys.path.insert(0, str(Path(__file__).parent))

console = Console()

REPO_ROOT = Path(__file__).parent
OUTPUT_DIR = REPO_ROOT / "output"


@click.group()
def cli():
    """CV Management System — build CVs from canonical YAML data."""
    pass


# ── build ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--template", "-t", default=None, help="Template name (rcn, classic, html, ...)")
@click.option("--all", "build_all_flag", is_flag=True, help="Build all registered templates")
def build(template: str | None, build_all_flag: bool):
    """Build one or all CV templates."""
    from scripts.build import build as _build, build_all, TEMPLATES

    if build_all_flag:
        build_all()
    elif template:
        if template not in TEMPLATES:
            console.print(
                f"[bold red]Unknown template:[/] '{template}'. "
                f"Available: {', '.join(TEMPLATES)}"
            )
            sys.exit(1)
        _build(template)
    else:
        console.print("[bold red]Error:[/] Specify --template <name> or --all")
        sys.exit(1)


# ── fetch-pubs ────────────────────────────────────────────────────────────────

@cli.command("fetch-pubs")
def fetch_pubs():
    """Sync publications from Google Scholar to data/publications.yaml."""
    from scripts.fetch_publications import main as _fetch
    _fetch()


# ── list-templates ────────────────────────────────────────────────────────────

@cli.command("list-templates")
def list_templates():
    """List all registered templates."""
    from scripts.build import TEMPLATES

    table = Table(title="Available Templates", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Format")
    table.add_column("Output")

    for name, cfg in TEMPLATES.items():
        fmt = cfg["format"].upper()
        ext = "pdf" if fmt == "PDF" else "html"
        out = str(OUTPUT_DIR / name / f"cv.{ext}")
        table.add_row(name, fmt, out)

    console.print(table)


# ── open ──────────────────────────────────────────────────────────────────────

@cli.command("open")
@click.option("--template", "-t", required=True, help="Template name")
def open_output(template: str):
    """Open the built output file for a template."""
    from scripts.build import TEMPLATES

    if template not in TEMPLATES:
        console.print(f"[bold red]Unknown template:[/] '{template}'")
        sys.exit(1)

    cfg = TEMPLATES[template]
    fmt = cfg["format"]
    ext = "pdf" if fmt == "pdf" else "html"
    out_path = OUTPUT_DIR / template / f"cv.{ext}"

    if not out_path.exists():
        console.print(
            f"[bold red]Output not found:[/] {out_path}. "
            f"Run: python cv.py build --template {template}"
        )
        sys.exit(1)

    subprocess.run(["open", str(out_path)])


# ── add ───────────────────────────────────────────────────────────────────────

@cli.command("add")
@click.argument("section", type=click.Choice(
    ["experience", "education", "publication", "grant", "talk", "award", "teaching"],
    case_sensitive=False,
))
def add_entry(section: str):
    """Interactively add a new entry to a YAML data section."""
    import yaml

    data_file = REPO_ROOT / "data" / f"{section}s.yaml"
    if section == "education":
        data_file = REPO_ROOT / "data" / "education.yaml"
    elif section == "publication":
        data_file = REPO_ROOT / "data" / "publications.yaml"
    elif section == "award":
        data_file = REPO_ROOT / "data" / "awards.yaml"

    console.print(f"[bold cyan]Adding new entry to:[/] {data_file.name}")
    console.print("[dim]Leave blank to skip optional fields.[/]\n")

    entry: dict = {}

    if section == "experience":
        entry["title"] = click.prompt("Job title")
        entry["institution"] = click.prompt("Institution")
        entry["location"] = click.prompt("Location")
        entry["start"] = click.prompt("Start (YYYY-MM)")
        entry["end"] = click.prompt("End (YYYY-MM or 'present')", default="present")
        entry["description"] = click.prompt("Description (optional)", default="") or None
        entry["highlights"] = []
        console.print("[dim]Enter highlights one by one. Empty line to stop.[/]")
        while True:
            h = click.prompt("  Highlight", default="")
            if not h:
                break
            entry["highlights"].append(h)

    elif section == "education":
        entry["degree"] = click.prompt("Degree")
        entry["institution"] = click.prompt("Institution")
        entry["location"] = click.prompt("Location")
        entry["start"] = click.prompt("Start year (YYYY)")
        entry["end"] = click.prompt("End year (YYYY or 'present')")
        entry["thesis"] = click.prompt("Thesis title (optional)", default="") or None
        entry["supervisor"] = click.prompt("Supervisor (optional)", default="") or None

    elif section == "publication":
        entry["title"] = click.prompt("Title")
        authors = []
        console.print("[dim]Enter authors one by one. Empty line to stop.[/]")
        while True:
            a = click.prompt("  Author", default="")
            if not a:
                break
            authors.append(a)
        entry["authors"] = authors
        entry["venue"] = click.prompt("Venue/Journal")
        entry["year"] = int(click.prompt("Year"))
        entry["type"] = click.prompt(
            "Type", type=click.Choice(["journal", "conference", "preprint", "book_chapter"])
        )
        entry["doi"] = click.prompt("DOI (optional)", default="") or ""
        entry["url"] = click.prompt("URL (optional)", default="") or ""
        entry["selected"] = click.confirm("Mark as selected/highlighted?", default=False)

    elif section == "grant":
        entry["title"] = click.prompt("Grant title")
        entry["funder"] = click.prompt("Funder")
        entry["role"] = click.prompt("Your role (PI / Co-PI / Researcher)")
        entry["amount"] = click.prompt("Amount (e.g. NOK 10M)")
        entry["start"] = click.prompt("Start year")
        entry["end"] = click.prompt("End year (or 'present')", default="")
        entry["status"] = click.prompt(
            "Status", type=click.Choice(["funded", "not_funded", "submitted"]), default="funded"
        )
        entry["description"] = click.prompt("Description (optional)", default="") or None

    elif section == "talk":
        entry["title"] = click.prompt("Talk title")
        entry["event"] = click.prompt("Event/Conference name")
        entry["location"] = click.prompt("Location")
        entry["date"] = click.prompt("Date (YYYY-MM)")
        entry["invited"] = click.confirm("Was this an invited talk?", default=True)
        entry["url"] = click.prompt("URL (optional)", default="") or ""

    elif section == "award":
        entry["title"] = click.prompt("Award title")
        entry["issuer"] = click.prompt("Issuer")
        entry["year"] = click.prompt("Year")
        entry["description"] = click.prompt("Description (optional)", default="") or None

    # Load existing, prepend new entry, save
    existing = []
    if data_file.exists():
        with open(data_file) as f:
            existing = yaml.safe_load(f) or []

    existing.insert(0, entry)

    with open(data_file, "w") as f:
        yaml.dump(existing, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    console.print(f"\n[bold green]✓ Added to {data_file.name}[/]")


if __name__ == "__main__":
    cli()
