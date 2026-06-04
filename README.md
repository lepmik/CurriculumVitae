# CV Management System — Mikkel Elle Lepperød

A Python-based system to maintain a single canonical source of truth for all CV data and render it into multiple output formats (PDF via LaTeX, HTML) using Jinja2 templates. Publications can be auto-synced from Google Scholar.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Build HTML CV (no LaTeX needed)
python cv.py build --template html

# Build all formats
python cv.py build --all

# Sync publications from Google Scholar
python cv.py fetch-pubs

# Interactively add a new entry
python cv.py add experience
python cv.py add publication

# List available templates
python cv.py list-templates

# Open latest output
python cv.py open --template html
```

## Prerequisites

- Python 3.9+
- `pdflatex` (for LaTeX → PDF builds) — install via [MacTeX](https://www.tug.org/mactex/) or `brew install --cask mactex-no-gui`
- Python dependencies: `pip install -r requirements.txt`

## Project Structure

```
CorriculumVitae/
├── data/                     # Canonical source of truth (YAML)
│   ├── profile.yaml          # Personal info, contact, Scholar ID
│   ├── education.yaml
│   ├── experience.yaml
│   ├── publications.yaml     # Auto-synced from Google Scholar
│   ├── grants.yaml
│   ├── talks.yaml
│   ├── teaching.yaml
│   ├── awards.yaml
│   ├── skills.yaml
│   └── references.yaml
├── templates/                # Jinja2 templates per output format
│   ├── rcn/                  # Norwegian Research Council format
│   ├── classic/              # Default academic CV style
│   └── html/                 # Web-viewable version
├── output/                   # Generated files (git-ignored)
├── scripts/
│   ├── fetch_publications.py
│   └── build.py
├── cv.py                     # Main CLI
└── requirements.txt
```

## Adding a New Template

1. Create `templates/<name>/` directory
2. Add `template.tex.j2` (LaTeX) or `template.html.j2` (HTML)
3. Register it in `scripts/build.py` in the `TEMPLATES` dict
4. Run `python cv.py build --template <name>`

## Updating CV Data

Edit the relevant `data/*.yaml` file. All templates read from the same data — you only ever need to update one place. See `CLAUDE.md` for full YAML schemas.

## Publication Sync

```bash
python cv.py fetch-pubs
```

Reads `scholar_id` from `data/profile.yaml`, fetches from Google Scholar via `scholarly`, and merges with existing `data/publications.yaml` (no duplicates, manual edits preserved). Citation counts are updated on each sync.

> **Note:** Google Scholar may rate-limit or CAPTCHA requests. The script exits gracefully without overwriting data if this happens.
