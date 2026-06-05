#!/usr/bin/env python3
"""
build.py — Core build logic for CV templates.

Called by cv.py; can also be imported directly.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, StrictUndefined
from rich.console import Console

console = Console()

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
TEMPLATES_DIR = REPO_ROOT / "templates"
OUTPUT_DIR = REPO_ROOT / "output"

# Registry of all available templates.
# Key: template name. Value: dict with format ('pdf' | 'html') and any extra config.
TEMPLATES: dict[str, dict] = {
    "rcn": {"format": "pdf", "entry": "template.tex.j2"},
    "earlycareer": {"format": "pdf", "entry": "template.tex.j2"},
    "classic": {"format": "pdf", "entry": "template.tex.j2"},
    "industry": {"format": "pdf", "entry": "template.tex.j2"},
    "html": {"format": "html", "entry": "template.html.j2"},
}


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    """Load all YAML files in data/ into a merged context dict."""
    # Keys whose YAML root is a list
    list_keys = [
        "education",
        "experience",
        "publications",
        "grants",
        "talks",
        "teaching",
        "awards",
        "references",
        "mobility",
        "collaborations",
        "memberships",
        "service",
    ]
    # Keys whose YAML root is a dict
    dict_keys = ["profile", "skills", "supervision", "scholar_stats", "narrative"]

    ctx: dict = {}
    for key in list_keys:
        path = DATA_DIR / f"{key}.yaml"
        if path.exists():
            with open(path) as f:
                ctx[key] = yaml.safe_load(f) or []
        else:
            ctx[key] = []
            console.print(f"[yellow]Warning:[/] {path} not found — using empty list.")

    for key in dict_keys:
        path = DATA_DIR / f"{key}.yaml"
        if path.exists():
            with open(path) as f:
                ctx[key] = yaml.safe_load(f) or {}
        else:
            ctx[key] = {}
            console.print(f"[yellow]Warning:[/] {path} not found — using empty dict.")
    # Normalise publications: ensure year and citations are always ints
    for pub in ctx.get("publications", []):
        if pub.get("year") is None:
            pub["year"] = 0
        if pub.get("citations") is None:
            pub["citations"] = 0

        # Flatten group: {rcn: causal} → rcn_group=causal (and any future CV keys)
        if isinstance(pub.get("group"), dict):
            for cv, val in pub["group"].items():
                pub[f"{cv}_group"] = val   # e.g. rcn_group = "causal"
        elif pub.get("group"):             # legacy plain string — keep working
            pub["rcn_group"] = pub["group"]

        # Flatten num: {rcn: 8} → rcn_num=8
        if isinstance(pub.get("num"), dict):
            for cv, val in pub["num"].items():
                pub[f"{cv}_num"] = val     # e.g. rcn_num = 8

        # Flatten featured: [earlycareer, rcn] → featured_earlycareer=True, featured=True
        feat = pub.get("featured")
        if isinstance(feat, list):
            for cv in feat:
                pub[f"featured_{cv}"] = True
            pub["featured"] = bool(feat)  # truthy for any-CV featured
        # (bool valued featured stays as-is for backward compat)

        # Flatten selected: [rcn] → selected_rcn=True, selected=True
        sel = pub.get("selected")
        if isinstance(sel, list):
            for cv in sel:
                pub[f"selected_{cv}"] = True
            pub["selected"] = bool(sel)

        # Ensure per-CV flags always exist so Jinja2 selectattr never hits UndefinedError
        pub.setdefault("featured_earlycareer", False)
        pub.setdefault("featured_rcn", False)
        pub.setdefault("selected_rcn", False)

    # Auto-derive supervision_institutions from unique institutions in supervision.yaml
    # Format: "Institution A / Institution B, Country" — stays in sync automatically.
    sup = ctx.get("supervision", {})
    _all_supervised = (sup.get("phd") or []) + (sup.get("postdoc") or [])
    if _all_supervised:
        _seen: dict[str, str] = {}  # institution_name → full string
        for _p in _all_supervised:
            _full = (_p.get("institution") or "").strip()
            # "University Name, City, Country" → key is just the institution name
            _name = _full.split(",")[0].strip()
            if _name and _name not in _seen:
                _seen[_name] = _name
        if _seen:
            ctx["narrative"]["supervision_institutions"] = " / ".join(_seen.keys()) + ", Norway"

    # Build citekey → rcn_num map and resolve [citekey] in narrative strings
    import re as _re
    citekey_map: dict[str, int] = {
        p["citekey"]: p["rcn_num"]
        for p in ctx.get("publications", [])
        if p.get("citekey") and p.get("rcn_num")
    }

    def _resolve(text: str) -> str:
        """Replace [citekey] with [rcn_num]; leave unknown keys untouched."""
        def _sub(m: "re.Match") -> str:
            key = m.group(1)
            return f"[{citekey_map[key]}]" if key in citekey_map else m.group(0)
        return _re.sub(r"\[([A-Za-z][A-Za-z0-9_]*)\]", _sub, text)

    # Build EC citekey → EC-enumerate position map.
    # Groups are rendered in the same order as the earlycareer template enumerate.
    _ec_group_order = ["nca", "spatial_nav", "causal", "neuroscience"]
    _ec_pubs: list[dict] = []
    for _grp in _ec_group_order:
        _grp_pubs = [
            p for p in ctx.get("publications", [])
            if p.get("featured_earlycareer") and p.get("rcn_group") == _grp
        ]
        _grp_pubs.sort(key=lambda p: p.get("rcn_num", 0))
        _ec_pubs.extend(_grp_pubs)
    ec_citekey_map: dict[str, int] = {
        p["citekey"]: i + 1
        for i, p in enumerate(_ec_pubs)
        if p.get("citekey")
    }

    def _resolve_ec(text: str) -> str:
        """Replace [citekey] with EC enumerate position; fall back to rcn_num."""
        def _sub(m: "re.Match") -> str:
            key = m.group(1)
            if key in ec_citekey_map:
                return f"[{ec_citekey_map[key]}]"
            if key in citekey_map:
                return f"[{citekey_map[key]}]"
            return m.group(0)
        return _re.sub(r"\[([A-Za-z][A-Za-z0-9_]*)\]", _sub, text)

    def _resolve_obj(obj, *, ec: bool = False):
        resolver = _resolve_ec if ec else _resolve
        if isinstance(obj, str):
            return resolver(obj)
        if isinstance(obj, dict):
            return {k: _resolve_obj(v, ec=(ec or k.startswith("ec_"))) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve_obj(i, ec=ec) for i in obj]
        return obj

    # ── Computed stats dict available as {stats.xxx} in narrative strings ──────
    _pubs = ctx.get("publications", [])
    _journals = [p for p in _pubs if p.get("type") == "journal"]
    _confs    = [p for p in _pubs if p.get("type") == "conference"]
    _preprints= [p for p in _pubs if p.get("type") == "preprint"]
    _sc = ctx.get("scholar_stats") or {}
    ctx["stats"] = {
        "pub_count":      len(_journals) + len(_confs),
        "journal_count":  len(_journals),
        "conf_count":     len(_confs),
        "preprint_count": len(_preprints),
        "h_index":        _sc.get("h_index", ""),
        "total_citations":_sc.get("total_citations", ""),
        "fetched_date":   _sc.get("fetched_date", ""),
    }

    # Build citekey → pub map for {citekey.field} lookups
    _ck_pub_map: dict[str, dict] = {
        p["citekey"]: p for p in _pubs if p.get("citekey")
    }

    def _resolve_ctx_vars(text: str) -> str:
        """Replace {key.subkey} or {key} with values from the build context.

        Resolution order:
          1. ctx[key][subkey]  (e.g. {scholar_stats.h_index}, {stats.pub_count})
          2. citekey_pub[key][subkey]  (e.g. {sensor_nca.citations})
          3. Leave unchanged if not found.

        Uses a strict identifier pattern so LaTeX braces with spaces or special
        characters (\\textbf{…}, \\href{…}) are never accidentally matched.
        """
        def _sub(m: "re.Match") -> str:
            expr = m.group(1)
            parts = expr.split(".", 1)
            top_key = parts[0]
            sub_key = parts[1] if len(parts) == 2 else None

            # 1. Context dict lookup
            top_val = ctx.get(top_key)
            if top_val is not None:
                if sub_key is None:
                    return str(top_val)
                if isinstance(top_val, dict):
                    v = top_val.get(sub_key)
                    if v is not None:
                        return str(v)

            # 2. Per-publication field lookup (e.g. {sensor_nca.citations})
            if top_key in _ck_pub_map and sub_key:
                v = _ck_pub_map[top_key].get(sub_key)
                if v is not None:
                    return str(v)

            return m.group(0)  # leave unchanged

        # Pattern: {identifier} or {identifier.identifier}
        # Requires the content to be a dotted alphanumeric identifier (no spaces)
        return _re.sub(r"\{([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?)\}", _sub, text)

    def _resolve_all(text: str, *, ec: bool = False) -> str:
        """Apply citekey resolution then context-variable resolution."""
        text = (_resolve_ec if ec else _resolve)(text)
        return _resolve_ctx_vars(text)

    def _resolve_obj(obj, *, ec: bool = False):  # noqa: F811 (redefine intentional)
        if isinstance(obj, str):
            return _resolve_all(obj, ec=ec)
        if isinstance(obj, dict):
            return {k: _resolve_obj(v, ec=(ec or k.startswith("ec_"))) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve_obj(i, ec=ec) for i in obj]
        return obj

    ctx["narrative"] = _resolve_obj(ctx.get("narrative", {}))

    ctx["build_date"] = date.today().isoformat()
    return ctx


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_template(template_name: str, ctx: dict) -> str:
    """Render a Jinja2 template and return the rendered string."""
    tmpl_dir = TEMPLATES_DIR / template_name
    if not tmpl_dir.exists():
        console.print(f"[bold red]Error:[/] Template directory not found: {tmpl_dir}")
        sys.exit(1)

    cfg = TEMPLATES[template_name]
    entry = cfg.get("entry", "template.tex.j2")

    is_latex = entry.endswith(".tex.j2")
    env = Environment(
        loader=FileSystemLoader(str(tmpl_dir)),
        undefined=StrictUndefined if is_latex else ChainableUndefined,
        # For LaTeX templates we need to change the Jinja delimiters
        # so they don't clash with LaTeX syntax.
        **(
            dict(
                block_start_string=r"\BLOCK{",
                block_end_string="}",
                variable_start_string=r"\VAR{",
                variable_end_string="}",
                comment_start_string=r"\#{",
                comment_end_string="}",
                trim_blocks=True,
                autoescape=False,
            )
            if is_latex
            else dict(autoescape=True, trim_blocks=True, lstrip_blocks=True)
        ),
    )

    def latex_escape(s: str) -> str:
        """Escape LaTeX special characters in a string."""
        if not isinstance(s, str):
            return s
        replacements = [
            ("\\", r"\textbackslash{}"),
            ("%",  r"\%"),
            ("&",  r"\&"),
            ("#",  r"\#"),
            ("$",  r"\$"),
            ("_",  r"\_"),
            ("~",  r"\textasciitilde{}"),
            ("^",  r"\textasciicircum{}"),
        ]
        for char, escaped in replacements:
            s = s.replace(char, escaped)
        return s

    if is_latex:
        env.filters["latex_escape"] = latex_escape
        env.globals["latex_escape"] = latex_escape

        def abbrev_authors(authors: list, pi: str = "Lepperød") -> str:
            """Abbreviate a list of authors to 'Surname, F.M.' format.
            The author matching *pi* is wrapped in \\textbf{...}.
            """
            parts = []
            for author in authors:
                tokens = author.strip().split()
                if not tokens:
                    continue
                surname = tokens[-1]
                initials = "".join(t[0] + "." for t in tokens[:-1] if t)
                abbrev = f"{surname} {initials}" if initials else surname
                if pi.lower() in surname.lower():
                    abbrev = r"\textbf{" + abbrev + "}"
                parts.append(abbrev)
            return ", ".join(parts)

        env.filters["abbrev_authors"] = abbrev_authors
        env.globals["abbrev_authors"] = abbrev_authors


    try:
        tmpl = env.get_template(entry)
    except Exception as e:
        console.print(f"[bold red]Template error:[/] {e}")
        sys.exit(1)

    return tmpl.render(**ctx)


# ── PDF Compilation ───────────────────────────────────────────────────────────

def compile_pdf(tex_path: Path, output_dir: Path) -> Path:
    """Run pdflatex on tex_path and return path to produced PDF."""
    if shutil.which("pdflatex") is None:
        console.print(
            "[bold red]Error:[/] `pdflatex` not found. "
            "Install MacTeX (macOS): brew install --cask mactex-no-gui"
        )
        sys.exit(1)

    # Run twice to resolve cross-references
    for run in range(2):
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory",
                str(output_dir),
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(output_dir),
        )
        if result.returncode != 0 and run == 1:
            console.print("[bold red]pdflatex failed.[/] Log:")
            console.print(result.stdout[-3000:])
            sys.exit(1)

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    # Clean auxiliary files
    for ext in [".aux", ".log", ".out", ".toc"]:
        aux = output_dir / tex_path.with_suffix(ext).name
        if aux.exists():
            aux.unlink()

    return pdf_path


# ── Main Build Entry Point ────────────────────────────────────────────────────

def build(template_name: str) -> Path:
    """Build a single template. Returns path to output file."""
    if template_name not in TEMPLATES:
        console.print(
            f"[bold red]Unknown template:[/] '{template_name}'. "
            f"Available: {', '.join(TEMPLATES)}"
        )
        sys.exit(1)

    cfg = TEMPLATES[template_name]
    fmt = cfg["format"]

    console.print(f"[bold cyan]Building[/] [bold]{template_name}[/] ({fmt.upper()})...")

    ctx = load_data()
    rendered = render_template(template_name, ctx)

    out_dir = OUTPUT_DIR / template_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "pdf":
        # Write .tex
        tex_path = out_dir / "cv.tex"
        tex_path.write_text(rendered, encoding="utf-8")
        # Copy style file if present
        sty_src = TEMPLATES_DIR / template_name / "style.sty"
        if sty_src.exists():
            shutil.copy(sty_src, out_dir / "style.sty")
        # Compile
        pdf_path = compile_pdf(tex_path, out_dir)
        console.print(f"[bold green]✓[/] PDF written to [underline]{pdf_path}[/]")
        return pdf_path

    elif fmt == "html":
        html_path = out_dir / "index.html"
        html_path.write_text(rendered, encoding="utf-8")
        # Copy CSS if present
        css_src = TEMPLATES_DIR / template_name / "style.css"
        if css_src.exists():
            shutil.copy(css_src, out_dir / "style.css")
        console.print(f"[bold green]✓[/] HTML written to [underline]{html_path}[/]")
        return html_path

    else:
        console.print(f"[bold red]Unknown format:[/] {fmt}")
        sys.exit(1)


def build_all() -> None:
    for name in TEMPLATES:
        build(name)
