#!/usr/bin/env python3
"""
build_pages.py — Generate standalone HTML reading pages for each PGR shareholder letter.

Iterates docs/ledger.json and renders a dedicated HTML page for each filing with
letter_scraped=True. Letter text is embedded directly so pages work on GitHub Pages
(data/letters/ is outside docs/ and is not served).

Usage:
    python scripts/build_pages.py              # build only new/missing pages
    python scripts/build_pages.py --rebuild    # rebuild all pages

Environment variables:
    None required.
"""
import argparse
import html
import json
import logging
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR
from letter_text import (
    _KNOWN_FIGURES,
    clean_letter_text,
    normalized_letter_blocks,
)

DOCS_DIR  = BASE_DIR / "docs"
PAGES_DIR = DOCS_DIR / "letters"


def _text_dir() -> Path:
    """Directory for plain-text letter copies published inside the Pages root.

    `data/letters/` sits above `docs/` and is not part of the Pages artifact, so
    the front-end cannot fetch letters from there — they are mirrored here.

    Resolved at call time rather than as a module-level constant: tests
    monkeypatch `BASE_DIR` to redirect writes into a tmp directory, and a
    constant computed at import time would ignore that and write into the real
    repository. `PAGES_DIR` avoids this only because the fixture patches it
    explicitly by name.
    """
    return BASE_DIR / "docs" / "letters_txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _quarter_sort_key(filing: dict) -> int:
    return filing["year"] * 10 + {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(filing["quarter"], 0)


def _gainshare_formula_html() -> str:
    return """\
<div class="formula-block">
  <div class="formula-row">
    <span class="formula-label">Employee GS payout</span>
    <span class="formula-expression">Employee GS factor &times; Employee paid targets &times; eligible earnings = payout</span>
  </div>
  <div class="formula-row">
    <span class="formula-label">Shareholder GS payout</span>
    <span class="formula-expression">Shareholder GS factor &times; Annual after-tax target &times; underwriting income = payout</span>
  </div>
</div>"""


def render_letter_html(text: str) -> str:
    """Convert extracted plain letter text to polished, escaped HTML blocks."""
    blocks = normalized_letter_blocks(text)
    rendered = []
    i = 0
    while i < len(blocks):
        block_type, block_text = blocks[i]

        if block_type == "list_item":
            # Collect all consecutive list_item blocks into one <ul>.
            items: list[str] = []
            while i < len(blocks) and blocks[i][0] == "list_item":
                _, item_text = blocks[i]
                if "\x00" in item_text:
                    heading, body = item_text.split("\x00", 1)
                    items.append(
                        f'  <li><strong>{html.escape(heading)}</strong>'
                        f' — {html.escape(body)}</li>'
                    )
                else:
                    items.append(f"  <li>{html.escape(item_text)}</li>")
                i += 1
            rendered.append('<ul class="letter-list">\n' + "\n".join(items) + "\n</ul>")
            continue

        if block_type == "signature":
            name, _, title = block_text.partition("\n")
            title_html = f'  <p class="signature-title">{html.escape(title)}</p>\n' if title else ""
            rendered.append(
                '<div class="signature-block">\n'
                f'  <p class="signature-name">{html.escape(name)}</p>\n'
                f"{title_html}"
                "</div>"
            )
        elif block_type == "heading":
            rendered.append(f"<h2>{html.escape(block_text)}</h2>")
        elif block_type == "quote":
            rendered.append(f'<p class="quoted-story"><em>{html.escape(block_text)}</em></p>')
        elif block_type == "figure":
            figure = _KNOWN_FIGURES[block_text]
            rendered.append(
                '<figure class="letter-figure">\n'
                f'  <img src="{html.escape(figure["src"])}" alt="{html.escape(figure["alt"])}" loading="lazy" />\n'
                f'  <figcaption>{html.escape(figure["caption"])}</figcaption>\n'
                "</figure>"
            )
        elif block_type == "formula":
            rendered.append(_gainshare_formula_html())
        else:
            rendered.append(f"<p>{html.escape(block_text)}</p>")
        i += 1
    return "\n".join(rendered)




SUMMARIES_DIR = BASE_DIR / "data" / "summaries"


def _render_summary_html(filing_id: str, year: int, quarter: str) -> str:
    """Return an HTML <section> for the letter summary, or '' if none exists."""
    summary_path = SUMMARIES_DIR / f"{filing_id}_Summary.json"
    if not summary_path.exists():
        return ""
    try:
        with open(summary_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return ""
    bullets = data.get("bullets", [])
    if not bullets:
        return ""
    items = "\n".join(
        f'    <li><strong>{html.escape(b["topic"])}</strong>'
        f' — {html.escape(b["text"])}</li>'
        for b in bullets
    )
    heading = html.escape(f"{year} {quarter} Letter — Key Points Summary")
    return (
        '<section class="letter-summary">\n'
        f'  <h2 class="summary-heading">{heading}</h2>\n'
        '  <ol class="summary-list">\n'
        f'{items}\n'
        '  </ol>\n'
        '</section>'
    )


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PGR {year} {quarter} — Shareholder Letter</title>
  <link rel="stylesheet" href="../assets/reading.css" />
</head>
<body>
  <div id="progress-bar"></div>

  <header class="reading-header">
    <nav class="reading-nav">
      <a href="../index.html" class="nav-back">← Archive</a>
      <div class="nav-episodes">
        {prev_link}
        {next_link}
      </div>
      <button id="theme-toggle" aria-label="Toggle dark mode">\U0001f319</button>
    </nav>
  </header>

  <main class="reading-main">
    <article class="letter-article">
      <header class="letter-header">
        <div class="letter-meta">
          <span class="meta-quarter">{year} {quarter}</span>
          <span class="meta-form">{form_type}</span>
          <span class="meta-date">Period ending {report_date}</span>
        </div>
        <h1>CEO Shareholder Letter</h1>
        {audio_section}
      </header>
      {summary_section}
      <div class="letter-body">
        {letter_paragraphs}
      </div>
    </article>
  </main>

  <script>
    // Dark mode — restore saved preference before first paint
    (function () {{
      const saved = localStorage.getItem("pgr-theme");
      if (saved) document.documentElement.setAttribute("data-theme", saved);
    }})();

    document.getElementById("theme-toggle").addEventListener("click", function () {{
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("pgr-theme", next);
      this.textContent = next === "dark" ? "☀️" : "\U0001f319";
    }});

    // Scroll progress bar
    const bar = document.getElementById("progress-bar");
    window.addEventListener("scroll", function () {{
      const doc = document.documentElement;
      const scrolled = doc.scrollTop || document.body.scrollTop;
      const total = doc.scrollHeight - doc.clientHeight;
      bar.style.width = total > 0 ? (scrolled / total * 100) + "%" : "0%";
    }}, {{ passive: true }});

    // Audio toggles — one handler covers both NotebookLM and TTS players
    document.querySelectorAll(".audio-toggle").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        const wrap = this.nextElementSibling;
        wrap.classList.toggle("open");
        this.textContent = wrap.classList.contains("open")
          ? this.dataset.hide
          : this.dataset.show;
      }});
    }});
  </script>
</body>
</html>"""


def build_page(
    filing: dict,
    letter_text: str,
    prev_filing: dict | None,
    next_filing: dict | None,
) -> str:
    """Render a complete HTML reading page for one filing."""
    prev_link = (
        f'<a href="{prev_filing["id"]}.html" class="nav-ep-link">'
        f'← {prev_filing["year"]} {prev_filing["quarter"]}</a>'
        if prev_filing else ""
    )
    next_link = (
        f'<a href="{next_filing["id"]}.html" class="nav-ep-link">'
        f'{next_filing["year"]} {next_filing["quarter"]} →</a>'
        if next_filing else ""
    )

    audio_items: list[str] = []

    if filing.get("audio_compressed") and filing.get("audio_file"):
        audio_filename = filing["audio_file"].split("/")[-1]
        audio_src = filing.get("audio_url") or f"../audio/{audio_filename}"
        audio_items.append(f"""\
  <div class="audio-item">
    <button class="audio-toggle" data-show="\U0001f399 AI Podcast Overview" data-hide="▲ Hide Podcast">\U0001f399 AI Podcast Overview</button>
    <div class="audio-player-wrap">
      <p class="audio-label">AI-generated podcast discussion via NotebookLM</p>
      <audio controls preload="none">
        <source src="{audio_src}" type="audio/mpeg" />
        Your browser does not support the audio element.
      </audio>
    </div>
  </div>""")

    if filing.get("tts_generated") and filing.get("tts_file"):
        tts_filename = filing["tts_file"].split("/")[-1]
        tts_src = filing.get("tts_url") or f"../audio_tts/{tts_filename}"
        audio_items.append(f"""\
  <div class="audio-item">
    <button class="audio-toggle" data-show="🔊 Read-Through Audio" data-hide="▲ Hide Read-Through">🔊 Read-Through Audio</button>
    <div class="audio-player-wrap">
      <p class="audio-label">Full letter read aloud by AI voice (Kokoro TTS)</p>
      <audio controls preload="none">
        <source src="{tts_src}" type="audio/mpeg" />
        Your browser does not support the audio element.
      </audio>
    </div>
  </div>""")

    if audio_items:
        audio_section = '<div class="audio-section">\n' + "\n".join(audio_items) + "\n</div>"
    else:
        audio_section = ""

    return _HTML_TEMPLATE.format(
        year=filing["year"],
        quarter=filing["quarter"],
        form_type=filing["form_type"],
        report_date=filing.get("report_date", "unknown"),
        prev_link=prev_link,
        next_link=next_link,
        audio_section=audio_section,
        summary_section=_render_summary_html(filing["id"], filing["year"], filing["quarter"]),
        letter_paragraphs=render_letter_html(letter_text),
    )


def sync_letter_text(scrapeable: list[dict]) -> int:
    """Mirror each scraped letter's plain text into docs/letters_txt/.

    Runs over every scraped letter on each invocation — not just the ones whose
    HTML page is rebuilt — so a letter added before this directory existed still
    gets published. Files are only rewritten when the content actually changes,
    keeping the workflow's `git add` a no-op on unchanged runs.
    """
    text_dir = _text_dir()
    text_dir.mkdir(parents=True, exist_ok=True)

    synced = 0
    for filing in scrapeable:
        letter_file = filing.get("letter_file")
        if not letter_file:
            continue
        source = BASE_DIR / letter_file
        if not source.exists():
            log.warning("Letter file not found: %s — not publishing text for %s",
                        source, filing["id"])
            continue

        # The stored file is the raw scrape; publish the normalized reading text
        # (no SEC headers or page numbers, headings and paragraphs rejoined).
        text = clean_letter_text(source.read_text(encoding="utf-8"))
        target = text_dir / source.name
        if target.exists() and target.read_text(encoding="utf-8") == text:
            continue

        target.write_text(text, encoding="utf-8")
        synced += 1
        log.info("Published text for %s", filing["id"])

    return synced


def main(rebuild: bool = False) -> None:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    scrapeable = [f for f in ledger["filings"] if f.get("letter_scraped")]
    scrapeable.sort(key=_quarter_sort_key)

    synced = sync_letter_text(scrapeable)

    built = 0
    for i, filing in enumerate(scrapeable):
        if not rebuild and filing.get("page_built"):
            log.debug("Skipping already-built page for %s", filing["id"])
            continue

        letter_file = filing.get("letter_file")
        if not letter_file:
            log.warning("No letter_file for %s — skipping", filing["id"])
            continue
        letter_path = BASE_DIR / letter_file
        if not letter_path.exists():
            log.warning("Letter file not found: %s — skipping %s", letter_path, filing["id"])
            continue

        letter_text  = letter_path.read_text(encoding="utf-8")
        prev_filing  = scrapeable[i - 1] if i > 0 else None
        next_filing  = scrapeable[i + 1] if i < len(scrapeable) - 1 else None
        html_content = build_page(filing, letter_text, prev_filing, next_filing)
        page_filename = f"{filing['id']}.html"

        (PAGES_DIR / page_filename).write_text(html_content, encoding="utf-8")
        filing["page_url"]   = f"letters/{page_filename}"
        filing["page_built"] = True
        save_ledger(ledger)
        built += 1
        log.info("Built %s", page_filename)

    log.info("Done. %d page(s) built, %d letter text file(s) published.", built, synced)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-letter HTML reading pages.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild all pages, not just new ones.")
    args = parser.parse_args()
    main(rebuild=args.rebuild)
