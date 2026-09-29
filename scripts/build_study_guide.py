"""Build the interview study guides from Markdown sources.

- Full edition:  docs/study-guide/*.md        -> docs/Interview-Study-Guide.pdf
- Short edition: docs/study-guide-short/*.md  -> docs/Interview-Study-Guide-Short.pdf

Pipeline: Graphviz diagrams (.dot -> .svg) -> Markdown -> HTML (with a title page,
a table of contents and print CSS) -> PDF via WeasyPrint.

Usage:
    make study-guide                                        # both editions, in a tools container
    make study-guide ARGS="--edition short --preview 1,2"   # one edition + PNG previews of pages

Section files are named NN-title.md and included in order; notes.md (collected
while building the app) is appended as an appendix.
"""

# ruff: noqa: E501, S607  (long lines are embedded CSS; dot/pdftoppm come from the tools image PATH)
import argparse
import html
import re
import subprocess
from pathlib import Path

import markdown
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "docs" / "study-guide" / "diagrams"  # shared by both editions

# edition -> (source folder, output PDF, title-page subtitle)
EDITIONS = {
    "full": (
        ROOT / "docs" / "study-guide",
        ROOT / "docs" / "Interview-Study-Guide.pdf",
        "How the project works, why every decision was made, and the fundamentals behind it — "
        "AI/LLMs, backend, frontend, databases, security, scaling, testing and DevOps.",
    ),
    "short": (
        ROOT / "docs" / "study-guide-short",
        ROOT / "docs" / "Interview-Study-Guide-Short.pdf",
        "The project, the decisions, the essential concepts and the most likely questions — "
        "everything you need, readable in a day.",
    ),
}

CSS = """
@page {
  size: A4;
  margin: 22mm 20mm 22mm 20mm;
  @bottom-center { content: counter(page); font: 9pt "Noto Sans", "DejaVu Sans", sans-serif; color: #5a6475; }
  @top-right { content: string(section); font: 8.5pt "Noto Sans", "DejaVu Sans", sans-serif; color: #5a6475; }
}
@page :first { @bottom-center { content: none; } @top-right { content: none; } }
@page toc { @top-right { content: none; } }

html { font-family: "Noto Serif", "DejaVu Serif", serif; font-size: 10.5pt; line-height: 1.5; color: #1b2433; }
h1, h2, h3, h4, .title, .toc a { font-family: "Noto Sans", "DejaVu Sans", sans-serif; }
h1 { string-set: section content(); page-break-before: always; font-size: 21pt; line-height: 1.2;
     margin: 0 0 12pt; padding-bottom: 6pt; border-bottom: 2.5pt solid #f7e27a; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; color: #1f3a8a; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; page-break-after: avoid; }
h4 { font-size: 10.5pt; margin: 10pt 0 3pt; page-break-after: avoid; }
p { margin: 0 0 7pt; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 7pt; padding-left: 16pt; }
li { margin: 2pt 0; }
strong { color: #111a2b; }
a { color: #1f3a8a; text-decoration: none; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.6pt; background: #f1f3f6;
       padding: 0.5pt 2.5pt; border-radius: 2pt; }
pre { background: #f6f7f9; border: 0.75pt solid #dce0e7; border-left: 3pt solid #1f3a8a;
      border-radius: 3pt; padding: 7pt 9pt; margin: 4pt 0 9pt; white-space: pre-wrap;
      word-wrap: break-word; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.1pt; line-height: 1.42; }
blockquote { margin: 6pt 0 9pt; padding: 6pt 10pt; background: #fbf1bd; border-left: 3pt solid #e0c34a; }
blockquote p:last-child { margin-bottom: 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 10pt; font-size: 9pt;
        font-family: "Noto Sans", "DejaVu Sans", sans-serif; page-break-inside: auto; }
th, td { border: 0.6pt solid #dce0e7; padding: 3.5pt 5pt; vertical-align: top; text-align: left; }
th { background: #eef1f6; }
tr { page-break-inside: avoid; }
img { max-width: 100%; display: block; margin: 6pt auto 10pt; }
figure { margin: 6pt 0 10pt; page-break-inside: avoid; }
.diagram { max-height: 190mm; }

/* One-page cheat sheet: compact type so it fits on a single page */
.cheat { font-size: 8.4pt; line-height: 1.32; }
.cheat p { margin: 0 0 3.5pt; }
.cheat ul, .cheat ol { margin: 0 0 3.5pt; }
.cheat li { margin: 0.5pt 0; }
.cheat table { font-size: 7.9pt; margin: 2pt 0 5pt; }
.cheat th, .cheat td { padding: 1.8pt 4pt; }
.cheat code { font-size: 7.4pt; }

/* Title page */
.title-page { page-break-after: always; padding-top: 55mm; }
.title-page .kicker { font-family: "Noto Sans", sans-serif; color: #5a6475; font-size: 11pt; margin: 0 0 6pt; }
.title-page .title { font-size: 34pt; line-height: 1.1; margin: 0 0 10pt; }
.title-page .title span { background: #f7e27a; padding: 0 4pt; }
.title-page .subtitle { font-size: 13pt; color: #1b2433; max-width: 130mm; }
.title-page .meta { margin-top: 70mm; font-family: "Noto Sans", sans-serif; font-size: 9.5pt; color: #5a6475; }

/* Table of contents with page numbers */
.toc { page: toc; page-break-after: always; }
.toc h1 { page-break-before: avoid; string-set: none; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li { margin: 0; }
.toc li.l1 { margin-top: 5pt; font-weight: 600; }
.toc li.l2 { padding-left: 14pt; font-size: 9.2pt; }
.toc a { color: #1b2433; display: block; }
.toc a::after { content: leader(".") target-counter(attr(href), page); color: #5a6475; }
"""


def render_diagrams(build_dir: Path) -> None:
    """Graphviz .dot -> .svg into <build>/diagrams (so Markdown can reference diagrams/x.svg)."""
    out_dir = build_dir / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)
    for dot in sorted(DIAGRAMS.glob("*.dot")):
        target = out_dir / f"{dot.stem}.svg"
        subprocess.run(["dot", "-Tsvg", str(dot), "-o", str(target)], check=True)  # noqa: S603
        print(f"  diagram {dot.name} -> {target.relative_to(ROOT)}")


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^a-z0-9]+", "-", html.unescape(text).lower()).strip("-")


def to_html(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html"],
        output_format="html5",
    )


def add_heading_ids(body: str, used: set[str]) -> tuple[str, list[tuple[int, str, str]]]:
    """Give every h1/h2 a unique id and collect them for the table of contents."""
    headings: list[tuple[int, str, str]] = []

    def repl(m: re.Match[str]) -> str:
        level, inner = int(m.group(1)), m.group(2)
        base = slugify(inner) or "section"
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        headings.append((level, slug, re.sub(r"<[^>]+>", "", inner)))
        return f'<h{level} id="{slug}">{inner}</h{level}>'

    return re.sub(r"<h([12])>(.*?)</h\1>", repl, body), headings


def build(edition: str, preview_pages: list[int]) -> None:
    src, out, subtitle = EDITIONS[edition]
    build_dir = src / "_build"
    label = "Interview Study Guide" + (" — One-Day Edition" if edition == "short" else "")
    print(f"Building the {edition} edition from {src.relative_to(ROOT)}")
    render_diagrams(build_dir)
    sections = sorted(p for p in src.glob("[0-9][0-9]-*.md"))
    notes = src / "notes.md"
    parts = [p.read_text() for p in sections]
    if notes.exists():
        parts.append("# Appendix: build notes\n\n" + notes.read_text().split("\n", 1)[1])

    used: set[str] = set()
    bodies, toc = [], []
    for md_text in parts:
        body, headings = add_heading_ids(to_html(md_text), used)
        body = body.replace('src="diagrams/', 'class="diagram" src="diagrams/')
        bodies.append(body)
        toc.extend(headings)

    toc_items = "\n".join(
        f'<li class="l{level}"><a href="#{slug}">{html.escape(text)}</a></li>' for level, slug, text in toc
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>DocMind AI — {label}</title><style>{CSS}</style></head><body>
<section class="title-page">
  <p class="kicker">AI Full-Stack Engineer interview preparation</p>
  <p class="title">DocMind <span>AI</span><br>{label.replace(" — ", "<br>")}</p>
  <p class="subtitle">{subtitle}</p>
  <p class="meta">Built from the DocMind AI repository · github.com/hamza0200/qna-assistant-rag</p>
</section>
<nav class="toc"><h1>Contents</h1><ol>{toc_items}</ol></nav>
{"".join(bodies)}
</body></html>"""

    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "study-guide.html").write_text(document)
    HTML(string=document, base_url=str(build_dir)).write_pdf(out)
    print(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")

    for page in preview_pages:
        prefix = build_dir / f"page-{page:03d}"
        cmd = ["pdftoppm", "-png", "-r", "70", "-f", str(page), "-l", str(page)]
        subprocess.run([*cmd, "-singlefile", str(out), str(prefix)], check=True)  # noqa: S603
        print(f"  preview {prefix.relative_to(ROOT)}.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--edition", choices=["full", "short", "all"], default="all")
    parser.add_argument("--preview", default="", help="comma-separated page numbers to render as PNG")
    args = parser.parse_args()
    pages = [int(p) for p in args.preview.split(",") if p.strip()]
    for edition in EDITIONS if args.edition == "all" else [args.edition]:
        build(edition, pages)
