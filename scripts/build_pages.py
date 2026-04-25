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
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR

DOCS_DIR  = BASE_DIR / "docs"
PAGES_DIR = DOCS_DIR / "letters"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _quarter_sort_key(filing: dict) -> int:
    return filing["year"] * 10 + {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(filing["quarter"], 0)


def render_letter_html(text: str) -> str:
    """Convert plain letter text to HTML paragraphs, escaping special characters."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    escaped = [html.escape(p).replace("\n", "<br />\n") for p in paragraphs]
    return "\n".join(f"<p>{e}</p>" for e in escaped)


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

    // Audio toggle (only wired up if audio section exists)
    const audioToggle = document.getElementById("audio-toggle");
    if (audioToggle) {{
      audioToggle.addEventListener("click", function () {{
        const wrap = document.getElementById("audio-player-wrap");
        wrap.classList.toggle("open");
        this.textContent = wrap.classList.contains("open")
          ? "▲ Hide AI Audio Overview"
          : "\U0001f399 AI Audio Overview";
      }});
    }}
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

    if filing.get("audio_compressed") and filing.get("audio_file"):
        audio_filename = filing["audio_file"].split("/")[-1]
        audio_section = f"""\
<div class="audio-section">
  <button class="audio-toggle" id="audio-toggle">\U0001f399 AI Audio Overview</button>
  <div class="audio-player-wrap" id="audio-player-wrap">
    <p class="audio-label">AI-generated podcast overview via NotebookLM</p>
    <audio controls preload="none">
      <source src="../audio/{audio_filename}" type="audio/mpeg" />
      Your browser does not support the audio element.
    </audio>
  </div>
</div>"""
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
        letter_paragraphs=render_letter_html(letter_text),
    )


def main(rebuild: bool = False) -> None:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    scrapeable = [f for f in ledger["filings"] if f.get("letter_scraped")]
    scrapeable.sort(key=_quarter_sort_key)

    built = 0
    for i, filing in enumerate(scrapeable):
        if not rebuild and filing.get("page_built"):
            log.debug("Skipping already-built page for %s", filing["id"])
            continue

        letter_path = BASE_DIR / filing["letter_file"]
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

    log.info("Done. %d page(s) built.", built)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-letter HTML reading pages.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild all pages, not just new ones.")
    args = parser.parse_args()
    main(rebuild=args.rebuild)
