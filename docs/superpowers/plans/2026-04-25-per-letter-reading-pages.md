# Per-Letter Reading Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a standalone, polished HTML reading page for each PGR shareholder letter, served from `docs/letters/` on GitHub Pages.

**Architecture:** A new Python script (`build_pages.py`) iterates the ledger, reads each `.txt` letter file, and renders a self-contained HTML page with the letter text embedded at build time (required since `data/letters/` is outside `docs/` and not served by GitHub Pages). Pages include a metadata header, prev/next navigation, collapsed audio player, sticky scroll progress bar, dark mode toggle, and print CSS. `index.html`'s sidebar is updated to navigate to reading pages instead of displaying inline text.

**Tech Stack:** Python 3.11+ (`html.escape`, `pathlib`, `string.format`), vanilla CSS + JS (no frameworks), pytest. No new Python dependencies required.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/build_pages.py` | Create | HTML generation script |
| `docs/assets/reading.css` | Create | Reading page stylesheet |
| `docs/letters/.gitkeep` | Create | Output directory marker |
| `tests/conftest.py` | Create | sys.path fixture for script imports |
| `tests/test_build_pages.py` | Create | Unit + integration tests |
| `docs/index.html` | Modify | Update sidebar to navigate to reading pages |
| `.github/workflows/quarterly_podcast.yml` | Modify | Add build_pages.py step and commit path |
| `CLAUDE.md` | Modify | Document new script, pages, and assets |

---

## Task 1: Scaffold directories and stub files

**Files:**
- Create: `docs/assets/reading.css`
- Create: `docs/letters/.gitkeep`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `scripts/build_pages.py` (stub)

- [ ] **Step 1: Create output directories**

```bash
mkdir -p docs/assets docs/letters tests
touch docs/assets/reading.css
touch docs/letters/.gitkeep
touch tests/__init__.py
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
# tests/conftest.py
import sys
from pathlib import Path

# Make scripts/ importable in tests (mirrors how scripts import each other)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
```

- [ ] **Step 3: Create stub `scripts/build_pages.py`**

```python
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
    pass  # implemented in Task 3


def build_page(
    filing: dict,
    letter_text: str,
    prev_filing: "dict | None",
    next_filing: "dict | None",
) -> str:
    """Render a complete HTML reading page for one filing."""
    pass  # implemented in Task 3


def main(rebuild: bool = False) -> None:
    pass  # implemented in Task 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-letter HTML reading pages.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild all pages, not just new ones.")
    args = parser.parse_args()
    main(rebuild=args.rebuild)
```

- [ ] **Step 4: Verify the stub imports cleanly**

```bash
cd C:/Users/Jeff/Documents/github/pgr-letters-archive
.venv/Scripts/python scripts/build_pages.py
```

Expected: exits silently (no output, no error).

- [ ] **Step 5: Commit**

```bash
git add docs/assets/reading.css docs/letters/.gitkeep tests/ scripts/build_pages.py
git commit -m "feat: scaffold build_pages.py and reading page directories"
```

---

## Task 2: Write reading.css

**Files:**
- Modify: `docs/assets/reading.css`

- [ ] **Step 1: Write the full stylesheet**

```css
/* docs/assets/reading.css — Reading page styles */

/* ── CSS custom properties ─────────────────────────────────────────────── */
:root {
  --brand-blue:   #003087;
  --brand-mid:    #0052cc;
  --bg:           #f7f8fc;
  --surface:      #ffffff;
  --text-primary: #1a1a2e;
  --text-muted:   #555570;
  --border:       #d0d5e8;
  --column-width: 700px;
  --progress-h:   3px;
}

[data-theme="dark"] {
  --bg:           #0f1117;
  --surface:      #1a1d27;
  --text-primary: #e8eaf0;
  --text-muted:   #9da3b4;
  --border:       #2e3248;
  --brand-mid:    #4f7ee8;
}

/* ── Reset ──────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text-primary);
  line-height: 1.6;
  min-height: 100vh;
}

/* ── Progress bar ───────────────────────────────────────────────────────── */
#progress-bar {
  position: fixed;
  top: 0; left: 0;
  height: var(--progress-h);
  width: 0%;
  background: var(--brand-mid);
  z-index: 1000;
  transition: width 0.1s linear;
}

/* ── Sticky nav header ──────────────────────────────────────────────────── */
.reading-header {
  position: sticky;
  top: var(--progress-h);
  z-index: 100;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0.65rem 1.5rem;
}

.reading-nav {
  max-width: calc(var(--column-width) + 4rem);
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.nav-back {
  color: var(--brand-mid);
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
}
.nav-back:hover { text-decoration: underline; }

.nav-episodes {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
  flex-shrink: 0;
}

.nav-ep-link {
  color: var(--brand-mid);
  text-decoration: none;
  font-size: 0.8rem;
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 20px;
  transition: background 0.15s;
  white-space: nowrap;
}
.nav-ep-link:hover { background: var(--border); }

#theme-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 0.2rem 0.6rem;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-muted);
  transition: background 0.15s;
  flex-shrink: 0;
}
#theme-toggle:hover { background: var(--border); }

/* ── Main content column ────────────────────────────────────────────────── */
.reading-main {
  max-width: calc(var(--column-width) + 4rem);
  margin: 0 auto;
  padding: 2.5rem 2rem 4rem;
}

/* ── Letter header ──────────────────────────────────────────────────────── */
.letter-header {
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 2px solid var(--border);
}

.letter-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.meta-quarter {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--brand-mid);
}

.meta-form,
.meta-date {
  font-size: 0.75rem;
  color: var(--text-muted);
}
.meta-form::before,
.meta-date::before { content: "·"; margin-right: 0.5rem; }

.letter-header h1 {
  font-size: 1.6rem;
  font-weight: 700;
  line-height: 1.25;
  margin-bottom: 1rem;
}

/* ── Audio player (collapsed by default) ────────────────────────────────── */
.audio-section { margin-top: 1rem; }

.audio-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.85rem;
  cursor: pointer;
  font-size: 0.82rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  transition: background 0.15s;
}
.audio-toggle:hover { background: var(--border); }

.audio-player-wrap { display: none; margin-top: 0.75rem; }
.audio-player-wrap.open { display: block; }

audio { width: 100%; border-radius: 4px; margin-top: 0.25rem; }

.audio-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.35rem;
}

/* ── Letter body ────────────────────────────────────────────────────────── */
.letter-body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.05rem;
  line-height: 1.85;
  color: var(--text-primary);
}

.letter-body p { margin-bottom: 1.4em; }
.letter-body p:last-child { margin-bottom: 0; }

/* ── Print styles ───────────────────────────────────────────────────────── */
@media print {
  #progress-bar, .reading-header { display: none; }
  body { background: #fff; color: #000; }
  .reading-main { padding: 0; max-width: 100%; }
  .letter-body { font-size: 11pt; line-height: 1.6; }
  .audio-section { display: none; }
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .reading-main { padding: 1.5rem 1rem 3rem; }
  .reading-header { padding: 0.5rem 1rem; }
  .letter-header h1 { font-size: 1.25rem; }
  .letter-body { font-size: 0.97rem; }
}
```

- [ ] **Step 2: Quick smoke test with a temporary HTML file**

Create `docs/letters/_test.html`:

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CSS Smoke Test</title>
  <link rel="stylesheet" href="../assets/reading.css" />
</head>
<body>
  <div id="progress-bar"></div>
  <header class="reading-header">
    <nav class="reading-nav">
      <a href="../index.html" class="nav-back">← Archive</a>
      <div class="nav-episodes">
        <a href="#" class="nav-ep-link">← 2025 Q2</a>
        <a href="#" class="nav-ep-link">2025 Q4 →</a>
      </div>
      <button id="theme-toggle">🌙</button>
    </nav>
  </header>
  <main class="reading-main">
    <article>
      <header class="letter-header">
        <div class="letter-meta">
          <span class="meta-quarter">2025 Q3</span>
          <span class="meta-form">10-Q</span>
          <span class="meta-date">Period ending 2025-09-30</span>
        </div>
        <h1>CEO Shareholder Letter</h1>
        <div class="audio-section">
          <button class="audio-toggle" id="audio-toggle">🎙 AI Audio Overview</button>
          <div class="audio-player-wrap" id="audio-player-wrap">
            <p class="audio-label">AI-generated podcast overview via NotebookLM</p>
            <audio controls preload="none"></audio>
          </div>
        </div>
      </header>
      <div class="letter-body">
        <p>Dear Shareholders — first paragraph. Georgia font, generous line-height.</p>
        <p>Second paragraph. Verify spacing looks right between paragraphs.</p>
        <p>Third paragraph. Verify the column is comfortably narrow.</p>
      </div>
    </article>
  </main>
</body>
</html>
```

Run: `cd docs && python -m http.server 8000`
Open: `http://localhost:8000/letters/_test.html`

Verify:
- Centered reading column (~700px), serif font, generous line-height
- Sticky nav header with ← Archive, prev/next episode links, theme toggle
- Audio section shows as a button (collapsed by default)
- Dark mode toggle switches colours

- [ ] **Step 3: Delete the temp file**

```bash
rm docs/letters/_test.html
```

- [ ] **Step 4: Commit**

```bash
git add docs/assets/reading.css
git commit -m "feat: add reading page stylesheet with dark mode and print support"
```

---

## Task 3: HTML template and letter rendering

**Files:**
- Modify: `scripts/build_pages.py` (implement `render_letter_html` and `build_page`)
- Create: `tests/test_build_pages.py`

- [ ] **Step 1: Install pytest**

```bash
.venv/Scripts/pip install pytest -q
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_build_pages.py`:

```python
# tests/test_build_pages.py
import pytest
from build_pages import render_letter_html, build_page

SAMPLE_FILING = {
    "id":               "PGR_2025_Q3",
    "year":             2025,
    "quarter":          "Q3",
    "form_type":        "10-Q",
    "report_date":      "2025-09-30",
    "letter_scraped":   True,
    "letter_file":      "data/letters/PGR_2025_Q3_Letter.txt",
    "audio_compressed": False,
    "audio_file":       None,
}

SAMPLE_FILING_WITH_AUDIO = {
    **SAMPLE_FILING,
    "audio_compressed": True,
    "audio_file":       "docs/audio/PGR_2025_Q3_Letter.mp3",
}

SAMPLE_TEXT = "First paragraph.\n\nSecond paragraph.\n\nThird <special> & paragraph."


def test_render_letter_html_splits_paragraphs():
    result = render_letter_html("Para one.\n\nPara two.")
    assert "<p>Para one.</p>" in result
    assert "<p>Para two.</p>" in result


def test_render_letter_html_escapes_html():
    result = render_letter_html("Text with <b>tags</b> & ampersands.")
    assert "&lt;b&gt;" in result
    assert "&amp;" in result
    assert "<b>" not in result


def test_build_page_contains_metadata():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "2025 Q3" in page
    assert "10-Q" in page
    assert "2025-09-30" in page


def test_build_page_contains_letter_text():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "First paragraph." in page
    assert "Second paragraph." in page


def test_build_page_escapes_special_chars_in_text():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "&lt;special&gt;" in page
    assert "<special>" not in page
    assert "&amp;" in page


def test_build_page_no_audio_section_when_not_compressed():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "audio-section" not in page


def test_build_page_includes_audio_section_when_compressed():
    page = build_page(SAMPLE_FILING_WITH_AUDIO, SAMPLE_TEXT, None, None)
    assert "audio-section" in page
    assert "PGR_2025_Q3_Letter.mp3" in page


def test_build_page_no_nav_ep_links_when_no_prev_next():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "nav-ep-link" not in page


def test_build_page_includes_prev_next_links():
    prev_f = {**SAMPLE_FILING, "id": "PGR_2025_Q2", "year": 2025, "quarter": "Q2"}
    next_f = {**SAMPLE_FILING, "id": "PGR_2025_Q4", "year": 2025, "quarter": "Q4"}
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, prev_f, next_f)
    assert "PGR_2025_Q2.html" in page
    assert "PGR_2025_Q4.html" in page
    assert "2025 Q2" in page
    assert "2025 Q4" in page


def test_build_page_back_link_present():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "../index.html" in page


def test_build_page_reading_css_linked():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "../assets/reading.css" in page
```

- [ ] **Step 3: Run tests to confirm they all fail**

```bash
cd C:/Users/Jeff/Documents/github/pgr-letters-archive
.venv/Scripts/pytest tests/test_build_pages.py -v 2>&1 | tail -20
```

Expected: 10 FAILED (all return None / TypeError).

- [ ] **Step 4: Implement `render_letter_html`**

In `scripts/build_pages.py`, replace the `render_letter_html` stub:

```python
def render_letter_html(text: str) -> str:
    """Convert plain letter text to HTML paragraphs, escaping special characters."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
```

- [ ] **Step 5: Implement `build_page` — add the template constant and function**

Add this constant above `build_page` in `scripts/build_pages.py`:

```python
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
```

Then replace the `build_page` stub:

```python
def build_page(
    filing: dict,
    letter_text: str,
    prev_filing: "dict | None",
    next_filing: "dict | None",
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
        audio_section = (
            '<div class="audio-section">'
            '<button class="audio-toggle" id="audio-toggle">'
            '\U0001f399 AI Audio Overview</button>'
            '<div class="audio-player-wrap" id="audio-player-wrap">'
            '<p class="audio-label">AI-generated podcast overview via NotebookLM</p>'
            f'<audio controls preload="none">'
            f'<source src="../audio/{audio_filename}" type="audio/mpeg" />'
            "Your browser does not support the audio element."
            "</audio>"
            "</div>"
            "</div>"
        )
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
```

- [ ] **Step 6: Run tests to confirm they all pass**

```bash
.venv/Scripts/pytest tests/test_build_pages.py -v
```

Expected: 10 PASSED.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_pages.py tests/test_build_pages.py
git commit -m "feat: implement build_page HTML template and render_letter_html"
```

---

## Task 4: Build loop, ledger updates, and idempotency

**Files:**
- Modify: `scripts/build_pages.py` (implement `main`)
- Modify: `tests/test_build_pages.py` (add integration tests)

- [ ] **Step 1: Add failing integration tests to `tests/test_build_pages.py`**

Append to the end of the file:

```python
# ── Integration tests ────────────────────────────────────────────────────

import json
import time
import build_pages
import scraper


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """Temp ledger + letter file; PAGES_DIR and BASE_DIR redirected."""
    # Letter file
    letters_dir = tmp_path / "data" / "letters"
    letters_dir.mkdir(parents=True)
    (letters_dir / "PGR_2025_Q3_Letter.txt").write_text(
        "Para one.\n\nPara two.", encoding="utf-8"
    )

    # Pages output dir
    pages_out = tmp_path / "docs" / "letters"
    pages_out.mkdir(parents=True)

    # Ledger
    ledger_data = {
        "meta": {
            "last_updated": None,
            "total_letters": 1,
            "total_audio": 0,
            "description": "",
        },
        "filings": [{
            "id":               "PGR_2025_Q3",
            "year":             2025,
            "quarter":          "Q3",
            "form_type":        "10-Q",
            "report_date":      "2025-09-30",
            "letter_file":      "data/letters/PGR_2025_Q3_Letter.txt",
            "audio_file":       "docs/audio/PGR_2025_Q3_Letter.mp3",
            "letter_scraped":   True,
            "audio_compressed": False,
            "page_built":       False,
        }],
    }
    ledger_file = tmp_path / "docs" / "ledger.json"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

    monkeypatch.setattr(build_pages, "PAGES_DIR", pages_out)
    monkeypatch.setattr(build_pages, "BASE_DIR",  tmp_path)
    monkeypatch.setattr(scraper,     "BASE_DIR",  tmp_path)
    monkeypatch.setattr(scraper,     "LEDGER_PATH", ledger_file)

    return tmp_path, ledger_file, pages_out


def test_main_creates_html_file(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    assert (pages_out / "PGR_2025_Q3.html").exists()


def test_main_sets_page_built_in_ledger(fake_env):
    _, ledger_file, _ = fake_env
    build_pages.main(rebuild=False)
    updated = json.loads(ledger_file.read_text())
    filing = updated["filings"][0]
    assert filing["page_built"] is True
    assert filing["page_url"] == "letters/PGR_2025_Q3.html"


def test_main_is_idempotent(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    mtime1 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime

    build_pages.main(rebuild=False)   # second run — page_built=True in ledger
    mtime2 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime
    assert mtime1 == mtime2  # file not rewritten


def test_main_rebuild_forces_regeneration(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    mtime1 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime

    time.sleep(0.05)
    build_pages.main(rebuild=True)
    mtime2 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime
    assert mtime2 > mtime1
```

- [ ] **Step 2: Run to confirm integration tests fail**

```bash
.venv/Scripts/pytest tests/test_build_pages.py::test_main_creates_html_file -v
```

Expected: FAILED — `main()` is a no-op.

- [ ] **Step 3: Implement `main()` in `scripts/build_pages.py`**

Replace the `main` stub:

```python
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

        letter_text   = letter_path.read_text(encoding="utf-8")
        prev_filing   = scrapeable[i - 1] if i > 0 else None
        next_filing   = scrapeable[i + 1] if i < len(scrapeable) - 1 else None
        html_content  = build_page(filing, letter_text, prev_filing, next_filing)
        page_filename = f"{filing['id']}.html"

        (PAGES_DIR / page_filename).write_text(html_content, encoding="utf-8")
        filing["page_url"]   = f"letters/{page_filename}"
        filing["page_built"] = True
        save_ledger(ledger)
        built += 1
        log.info("Built %s", page_filename)

    log.info("Done. %d page(s) built.", built)
```

- [ ] **Step 4: Run the full test suite**

```bash
.venv/Scripts/pytest tests/test_build_pages.py -v
```

Expected: 14 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_pages.py tests/test_build_pages.py
git commit -m "feat: implement build_pages main loop with idempotency and ledger updates"
```

---

## Task 5: Update index.html sidebar links

**Files:**
- Modify: `docs/index.html`

When a filing has a `page_url`, clicking it in the sidebar should navigate to the reading page. Filings without `page_url` still load inline as before.

- [ ] **Step 1: Update the episode click handler in `renderEpisodeList()`**

Find this line in `docs/index.html`:

```javascript
      li.addEventListener("click", () => selectEpisode(filing.id));
```

Replace with:

```javascript
      if (filing.page_url) {
        li.addEventListener("click", () => { window.location.href = filing.page_url; });
      } else {
        li.addEventListener("click", () => selectEpisode(filing.id));
      }
```

- [ ] **Step 2: Add a "Read →" badge for episodes that have a reading page**

Find this block in `renderEpisodeList()`:

```javascript
      const badge = filing.audio_compressed
        ? '<span class="ep-badge badge-audio">Audio available</span>'
        : filing.letter_scraped
        ? '<span class="ep-badge badge-text">Text only</span>'
        : '<span class="ep-badge badge-none">Pending</span>';
```

Replace with:

```javascript
      const audioBadge = filing.audio_compressed
        ? '<span class="ep-badge badge-audio">Audio available</span>'
        : filing.letter_scraped
        ? '<span class="ep-badge badge-text">Text only</span>'
        : '<span class="ep-badge badge-none">Pending</span>';
      const readBadge = filing.page_url
        ? '<span class="ep-badge badge-read">Read →</span>'
        : '';
      const badge = audioBadge + readBadge;
```

- [ ] **Step 3: Add `.badge-read` to the `<style>` block in index.html**

Find the existing badge CSS (near `.badge-audio`, `.badge-text`, `.badge-none`) and add:

```css
    .badge-read   { background: #e8f0fe; color: #003087; }
```

- [ ] **Step 4: Manual verification**

```bash
cd docs && python -m http.server 8000
```

Open `http://localhost:8000`. Since pages aren't generated yet, `page_url` is absent from the ledger and all episodes should still load inline as before. This is expected — the read badges and navigation appear after Task 7 generates the pages.

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: update index.html sidebar to navigate to reading pages"
```

---

## Task 6: Update GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/quarterly_podcast.yml`

- [ ] **Step 1: Add `build_pages.py` step after the compressor step**

Find:

```yaml
      - name: Compress audio and regenerate RSS feed
        env:
          PAGES_BASE_URL: "https://jhester599.github.io/pgr-letters-archive"
        run: python scripts/compressor.py
```

Add directly after it:

```yaml
      - name: Build reading pages
        run: python scripts/build_pages.py
```

- [ ] **Step 2: Add `docs/letters/` to the git commit step**

Find the `git add` block:

```yaml
          git add \
            data/letters/ \
            docs/audio/ \
            docs/ledger.json \
            docs/feed.xml
```

Replace with:

```yaml
          git add \
            data/letters/ \
            docs/audio/ \
            docs/ledger.json \
            docs/feed.xml \
            docs/letters/
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/quarterly_podcast.yml
git commit -m "feat: add build_pages.py step and docs/letters/ commit path to workflow"
```

---

## Task 7: Generate pages for all 41 existing letters

**Files:**
- Create: `docs/letters/PGR_*.html` (41 files)
- Modify: `docs/ledger.json` (page_url and page_built fields populated)

- [ ] **Step 1: Run the build script**

```bash
cd C:/Users/Jeff/Documents/github/pgr-letters-archive
.venv/Scripts/python scripts/build_pages.py
```

Expected final line: `Done. 41 page(s) built.`

- [ ] **Step 2: Confirm file count**

```bash
ls docs/letters/*.html | wc -l
```

Expected: `41`

- [ ] **Step 3: Spot-check the newest letter**

```bash
cd docs && python -m http.server 8000
```

Open `http://localhost:8000/letters/PGR_2025_Q4.html`. Verify:
- Sticky nav shows `← Archive`, no prev/next links (newest letter has no next)
- Metadata: "2025 Q4", "10-K", "Period ending 2025-12-31"
- Letter body in serif font with paragraph spacing
- No audio section (audio not yet generated)
- Dark mode toggle works and persists on refresh (F5)
- Progress bar moves while scrolling

Open `http://localhost:8000/letters/PGR_2025_Q3.html`. Verify:
- Prev link: `← 2025 Q2`, Next link: `2025 Q4 →`
- Clicking Next navigates to PGR_2025_Q4.html

Open `http://localhost:8000`. Verify:
- Each episode row shows `Read →` badge
- Clicking an episode navigates to its reading page (not inline text)

- [ ] **Step 4: Commit all generated pages and updated ledger**

```bash
git add docs/letters/ docs/ledger.json
git commit -m "feat: generate reading pages for all 41 existing PGR letters"
```

---

## Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add new files to the directory structure section**

In CLAUDE.md, find the directory structure block and extend it:

```
scripts/
  scraper.py        — SEC EDGAR downloader
  generator.py      — NotebookLM audio generation
  compressor.py     — FFmpeg compression + RSS generation
  build_pages.py    — Per-letter HTML reading page generator  ← ADD
docs/
  index.html        — Single-page front-end; reads ledger.json at runtime
  ledger.json       — State ledger; also the front-end's data source
  audio/            — Compressed 64 kbps MP3s (committed)
  feed.xml          — Podcast RSS feed (regenerated each run)
  letters/          — Standalone HTML reading pages (one per letter)  ← ADD
  assets/
    reading.css     — Stylesheet for reading pages  ← ADD
```

- [ ] **Step 2: Add build_pages.py to the Common tasks section**

```markdown
**Rebuild all reading pages (after CSS or template changes):**
```bash
python scripts/build_pages.py --rebuild
```

**Build only new reading pages (standard run):**
```bash
python scripts/build_pages.py
```
```

- [ ] **Step 3: Update Ledger schema section**

Add the two new fields to the ledger schema example:

```json
"page_url":   "letters/PGR_2025_Q1.html",
"page_built": true
```

Flag lifecycle note: add `→ page_built` after `audio_compressed` in the lifecycle description.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for build_pages.py and reading pages"
```
