# CorriculumVitae — Agent Guide

This project is a **modular CV management system**. A single canonical YAML data store drives multiple output templates (PDF via LaTeX, HTML, etc.). Do not hard-code CV content into templates — all data lives in `data/`.

---

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
│   │   ├── template.tex.j2
│   │   └── style.sty
│   ├── classic/              # Old/default CV style
│   │   ├── template.tex.j2
│   │   └── style.sty
│   └── html/                 # Web-viewable version
│       ├── template.html.j2
│       └── style.css
├── output/                   # Generated files — DO NOT EDIT (git-ignored)
├── scripts/
│   ├── fetch_publications.py # Syncs publications from Google Scholar
│   └── build.py              # Core build logic (called by cv.py)
├── cv.py                     # Main CLI entry point
├── requirements.txt
├── CLAUDE.md                 # This file
└── README.md
```

---

## Core Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Fetch/update publications from Google Scholar
python cv.py fetch-pubs

# Build a specific template
python cv.py build --template rcn       # → output/rcn/cv.pdf
python cv.py build --template classic   # → output/classic/cv.pdf
python cv.py build --template html      # → output/html/index.html

# Build all templates at once
python cv.py build --all
```

---

## Data Layer Rules

- **All CV content lives in `data/*.yaml`**. Never hard-code names, dates, or descriptions into templates.
- When adding a new CV entry (e.g. a new paper, a new job), edit the appropriate YAML file.
- `publications.yaml` is auto-managed by `fetch_publications.py`. Manual edits are allowed but will be merged (not overwritten) on next sync.
- The `scholar_id` in `data/profile.yaml` is the Google Scholar user ID used for publication sync.

### YAML Schemas

**`profile.yaml`**
```yaml
name: string
title: string
email: string
phone: string (optional)
orcid: string (optional)
scholar_id: string          # Google Scholar user ID
website: string (optional)
address: string (optional)
summary: string             # Short bio / research statement
```

**`publications.yaml`** (list)
```yaml
- title: string
  authors: [string, ...]
  venue: string
  year: int
  doi: string (optional)
  url: string (optional)
  type: journal | conference | preprint | book_chapter
  selected: bool (optional, default false)
```

**`experience.yaml`** (list, newest first)
```yaml
- title: string
  institution: string
  location: string
  start: YYYY-MM
  end: YYYY-MM | present
  description: string | null
  highlights: [string, ...]  # Bullet points
```

**`education.yaml`** (list, newest first)
```yaml
- degree: string
  institution: string
  location: string
  start: YYYY
  end: YYYY | present
  thesis: string (optional)
  supervisor: string (optional)
  gpa: string (optional)
```

**`grants.yaml`** (list)
```yaml
- title: string
  funder: string
  role: PI | Co-PI | Researcher
  amount: string (e.g. "NOK 4.5M")
  start: YYYY
  end: YYYY
  description: string (optional)
```

**`talks.yaml`** (list)
```yaml
- title: string
  event: string
  location: string
  date: YYYY-MM
  invited: bool
  url: string (optional)
```

**`teaching.yaml`** (list)
```yaml
- role: string              # e.g. "Lecturer", "Teaching Assistant"
  course: string
  institution: string
  year: YYYY | YYYY-YYYY
  description: string (optional)
```

**`awards.yaml`** (list)
```yaml
- title: string
  issuer: string
  year: YYYY
  description: string (optional)
```

---

## Template Rules

- Templates live in `templates/<name>/template.<ext>.j2`
- Templates use **Jinja2** syntax
- The build system loads all `data/*.yaml` and passes a merged context dict to the template
- Available context keys in templates:
  - `profile`, `education`, `experience`, `publications`, `grants`, `talks`, `teaching`, `awards`, `skills`, `references`
  - `build_date` — ISO date string of build time
- For LaTeX templates: after rendering `.tex`, `pdflatex` is run automatically
- Do NOT put LaTeX preamble boilerplate in `style.sty` if it belongs in the template and vice versa

---

## Adding a New Template

1. Create `templates/<name>/` directory
2. Add `template.tex.j2` (or `.html.j2`)
3. Register the template name in `scripts/build.py` in the `TEMPLATES` dict
4. Run `python cv.py build --template <name>` to test

---

## Publication Sync

The `fetch_publications.py` script uses the `scholarly` Python library to query Google Scholar. It:
1. Reads `scholar_id` from `data/profile.yaml`
2. Fetches all publications for that author
3. Merges with existing `data/publications.yaml` (matching on title, no duplicates)
4. Writes updated `data/publications.yaml`

If Scholar is rate-limiting or returning CAPTCHAs, the script will print a clear warning and exit without overwriting data.

---

## Dependencies

See `requirements.txt`. Key libraries:
- `jinja2` — templating
- `pyyaml` — YAML parsing
- `click` — CLI
- `scholarly` — Google Scholar scraping
- `rich` — pretty terminal output

System requirement: `pdflatex` must be installed for PDF output (via `texlive` or `MacTeX`).

---

## Conventions

- Keep `output/` git-ignored — only source data and templates are version-controlled
- Dates: use `YYYY-MM` for month precision, `YYYY` for year-only, `"present"` for ongoing
- Publications: `selected: true` marks papers to highlight in short-form CVs
- When in doubt about which section a new entry belongs to, check the YAML schemas above
