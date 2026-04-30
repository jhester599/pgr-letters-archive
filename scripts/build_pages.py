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


_MOJIBAKE_REPLACEMENTS = {
    "\x91": "\u2018",
    "\x92": "\u2019",
    "\x93": "\u201c",
    "\x94": "\u201d",
    "\x96": "\u2013",
    "\x97": "\u2014",
    "\xa0": " ",
    "\u00e2\u20ac\u02dc": "\u2018",
    "\u00e2\u20ac\u2122": "\u2019",
    "\u00e2\u20ac\u0153": "\u201c",
    "\u00e2\u20ac\u009d": "\u201d",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u00a6": "\u2026",
    "\u00e2\u20ac\u2018": "\u2011",
    "\u00e2\u20ac\u00af": "\u202f",
    "\u00c2\u00ae": "\u00ae",
    "\u00c2\u00b7": "\u00b7",
}

_SEC_NOISE_LINES = {
    "EX-99",
    "DOCUMENT",
    "EXHIBIT 99",
    "LETTER TO SHAREHOLDERS",
}

_SECTION_HEADINGS = {
    "Broad Needs of Customers",
    "Broad Needs of Our Customers",
    "Claims",
    "Constancy of Purpose",
    "Competitive Prices",
    "Investments and Capital Management",
    "Leading Brand",
    "Marketing",
    "Market Conditions",
    "Maximum Preparedness",
    "People and Culture",
    "Retention and Customer Service",
    "Technology",
    "Use of Gainshare to Align Shareholder and Employee Interests",
}

_ORDINAL_SUFFIXES = {"st", "nd", "rd", "th"}
_TRADEMARK_LINES = {"\u00ae", "\u2122"}
_SIGNATURE_TITLE = "President and Chief Executive Officer"

# Bullet list patterns
# Pattern 1: standalone bullet character on its own line (modern letters)
_BULLET_CHAR_RE = re.compile(r"^[\u2022\u25cf\u25aa]\s*$")
# Pattern 2: "bullet HEADING -- body" from older SGML/PDF extracts
_BULLET_WORD_RE = re.compile(r"^bullet\s+(.+?)\s*--\s*(.+)$", re.IGNORECASE | re.DOTALL)

_KNOWN_FIGURES = {
    "Private Passenger Auto Combined Ratios 1976-2005": {
        "src": "../assets/figures/PGR_2005_Q4_private_passenger_auto_combined_ratios.png",
        "caption": "Private Passenger Auto Combined Ratios, 1976-2005",
        "alt": "Line chart of private passenger auto combined ratios from 1976 through 2005.",
    },
    "Storm Tracking \u2014 2005 Season": {
        "src": "../assets/figures/PGR_2005_Q4_storm_tracking_2005_season.png",
        "caption": "Storm Tracking \u2014 2005 Season",
        "alt": "Map showing the 2005 storm season tracking graphic from Progressive's annual report.",
    },
}

_GAINSHARE_FORMULA_TEXT = (
    "Gainshare (GS) Employee GS Employee paid Employee GS factor x targets x eligible earnings = payout "
    "Gainshare (GS) Shareholder GS Annual after-tax Shareholder GS factor x target x underwriting income = payout"
)


def _repair_text_encoding(text: str) -> str:
    """Repair common mojibake left behind by SEC HTML extraction."""
    repaired = text
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(bad, good)
    return repaired


def _is_sec_noise(line: str) -> bool:
    upper_line = line.upper()
    lower_line = line.lower()
    if upper_line in _SEC_NOISE_LINES:
        return True
    if re.fullmatch(r"EX-99(?:\([A-Z]\)|\.[A-Z])?", upper_line):
        return True
    if re.fullmatch(r"EX-99(?:\([A-Z]\)|\.[A-Z])?\s+LETTER TO SHAREHOLDERS", upper_line):
        return True
    if re.fullmatch(r"EXHIBIT\s+NO\.\s+99(?:\([A-Z]\))?", upper_line):
        return True
    if "letter to shareholders" == lower_line:
        return True
    return bool(re.fullmatch(r"(?:pgr-\d+.*exhibit99.*|l\d+aexv99\w*)\.html?", lower_line))


def _is_page_number(line: str, next_line: str | None) -> bool:
    if re.fullmatch(r"-\s*\d{1,3}\s*-", line):
        return True
    if not line.isdigit():
        return False
    if next_line in _ORDINAL_SUFFIXES:
        return False
    return 1 <= int(line) <= 200


_CAPS_SEP_PATTERNS = [
    # "ALL CAPS HEADING. Body text" — heading ends with terminal punct
    (re.compile(r"^([A-Z0-9][A-Z0-9\s,;:’’’#&%()\-]+[.!?])\s+(.{10,})$"), 8),
    # "ALL CAPS HEADING  Body text" — two or more spaces (SGML/PDF column layout)
    (re.compile(r"^([A-Z][A-Z0-9\s,;:’’’#&%()\-]+?)\s{2,}(.{15,})$"), 5),
    # "ALL CAPS HEADING – Body" or "— Body" (en/em dash separator)
    # Require whitespace before dash to avoid matching phone numbers ("CALL 1-800").
    (re.compile(r"^([A-Z][A-Z0-9\s,;:’’’#&%()\-]+?)\s+[–—\-]{1,2}\s*(.{10,})$"), 5),
]


def _split_leading_all_caps_heading(line: str) -> tuple[str, str] | None:
    for pattern, min_letters in _CAPS_SEP_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        heading, rest = match.groups()
        heading = heading.strip()
        # Q/A answer markers are never section headings.
        if heading.startswith("A - ") or heading.startswith("Q - "):
            continue
        # Heading must be all-uppercase alpha and at most 60 chars long.
        letters = [c for c in heading if c.isalpha()]
        if len(letters) < min_letters or len(heading) > 60:
            continue
        if all(not c.isalpha() or c.isupper() for c in heading):
            return heading, rest.strip()
    return None


def _is_heading(line: str) -> bool:
    if line in _SECTION_HEADINGS:
        return True
    # Q/A answer lines are prose, not section headings.
    if line.startswith("A - "):
        return False
    letters = [char for char in line if char.isalpha()]
    if len(letters) < 6 or line.endswith((".", ",", ";", ":")):
        return False
    return all(not char.isalpha() or char.isupper() for char in line)


def _is_signature_marker(line: str) -> bool:
    return line.lower().startswith("/s/")


def _signature_name_from_marker(line: str) -> str:
    return re.sub(r"^/s/\s*", "", line, flags=re.IGNORECASE).strip()


def _is_signature_title(line: str) -> bool:
    return line == _SIGNATURE_TITLE


def _is_story_quote_intro(line: str) -> bool:
    lower_line = line.lower()
    if lower_line.endswith(":") and (" wrote" in lower_line or " shared" in lower_line):
        return True
    return any(
        phrase in lower_line
        for phrase in (
            "this letter comes to you",
            "this letter hits all of those sentiments",
            "the story below is from",
            "i'd like to share a powerful story",
            "i\u2019d like to share a powerful story",
            "below is a great example",
            "in their own words",
            "he shared a peek",
            "she recently shared",
        )
    )


def _is_story_quote_reset(line: str) -> bool:
    lower_line = line.lower()
    return lower_line.startswith((
        "also relevant",
        "at the heart",
        "below are some highlights",
        "broad needs",
        "competitive prices",
        "heading into",
        "i hope those",
        "in addition to",
        "lastly,",
        "looking ahead",
        "never resting",
        "our employee resource groups",
        "our people and culture",
        "leading brand",
        "stay well",
        "spreading kindness",
        "take care",
        "thanks for",
        "through the discipline",
        "times like this",
        "to our employees",
        "we ended",
        "we truly came",
    ))


def _has_terminal_punctuation(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "\u201d", '"', ":", ";"))


def _is_direct_block_quote_start(line: str) -> bool:
    """True when a line opens a real block quote from another person.

    Distinguishes genuine testimonials from CEO sentences that merely begin
    with a quoted term (e.g. '"Re-engineering" is what we have been doing\u2026').

    Rules:
      - Must start with an opening double-quote (straight or curly).
      - Must be >= 80 chars (short lines are inline quoted terms, not stories).
      - Reject if the first closing quote appears within the first 40 chars of
        the inner text \u2014 that pattern is a CEO-quoting-a-concept construction
        like '"Gainshare" is our way\u2026' or '"Move forward" means\u2026'.
      - Reject if the closing quote is followed by a dash attribution marker
        (' \u2014 is where', ' - is where') indicating CEO self-reference.
    """
    if not (line.startswith('"') or line.startswith("\u201c")):
        return False
    if len(line) < 80:
        return False
    inner = line[1:]
    for q in ('"', "\u201d"):
        pos = inner.find(q)
        if 0 <= pos <= 40:
            return False  # early-close \u2192 quoted term, not a block quote
        if pos > 40:
            after = inner[pos + 1 : pos + 20]
            if re.match(r"\s*[-\u2013\u2014]\s*is where", after):
                return False  # CEO self-attribution: "\u2026" - is where I left off
    return True


def _should_join_lines(previous: str, current: str) -> bool:
    if not previous:
        return False
    if current[:1].islower():
        return True
    return not _has_terminal_punctuation(previous)


def _append_inline_marker(paragraph: str, marker: str) -> str:
    if marker in _TRADEMARK_LINES or marker in _ORDINAL_SUFFIXES:
        return f"{paragraph}{marker}"
    return f"{paragraph} {marker}"


def _is_omitted_graphic_note(text: str) -> bool:
    return text.startswith("[") and text.endswith("]") and "graphic intentionally omitted" in text.lower()


def _is_artwork_placeholder(text: str) -> bool:
    return text.strip().upper() == "[ARTWORK]"


def _figure_key_from_note(text: str) -> str | None:
    if not _is_omitted_graphic_note(text):
        return None
    return re.sub(r"\s+graphic intentionally omitted\s*", "", text.strip("[] "), flags=re.IGNORECASE)


def _is_gainshare_formula(text: str) -> bool:
    normalized = " ".join(text.split())
    return normalized == _GAINSHARE_FORMULA_TEXT


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


def _normalized_letter_blocks(text: str) -> list[tuple[str, str]]:
    """Normalize extracted filing text into display-ready paragraph/heading blocks."""
    text = _repair_text_encoding(text)
    raw_lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]

    filtered_lines: list[str | None] = []
    for index, line in enumerate(raw_lines):
        if not line:
            filtered_lines.append(None)
            continue

        next_line = next(
            (candidate.strip() for candidate in raw_lines[index + 1:] if candidate.strip()),
            None,
        )
        if _is_sec_noise(line) or _is_page_number(line, next_line):
            continue
        filtered_lines.append(line)

    blocks: list[tuple[str, str]] = []
    paragraph = ""
    paragraph_kind = "paragraph"
    quote_mode = False
    quote_mode_direct = False  # True when quote_mode set by _is_direct_block_quote_start
    next_is_list_item = False      # set when a standalone • precedes the next paragraph
    next_list_item_strict = False  # whether that next list_item uses strict (•-style) joining
    list_item_strict = False       # True for current paragraph if it's a •-style list item

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_kind, quote_mode, quote_mode_direct, list_item_strict
        if paragraph:
            stripped = paragraph.strip()
            # Post-assembly upgrade: if the fully-joined block starts with a
            # block-quote marker but wasn't caught at line-scan time (e.g. the
            # opening " was on a very short line that got joined), promote it.
            if paragraph_kind == "paragraph" and _is_direct_block_quote_start(stripped):
                paragraph_kind = "quote"
                quote_mode = True
                quote_mode_direct = True
            figure_key = _figure_key_from_note(stripped)
            if figure_key in _KNOWN_FIGURES:
                blocks.append(("figure", figure_key))
            elif figure_key:
                pass
            elif _is_gainshare_formula(stripped):
                blocks.append(("formula", stripped))
            else:
                blocks.append((paragraph_kind, stripped))
            # Auto-reset for direct block quotes: once the paragraph ends with a
            # closing quotation mark the testimonial is complete.
            if quote_mode_direct and paragraph_kind == "quote":
                if stripped.endswith(('"', '”')):
                    quote_mode = False
                    quote_mode_direct = False
            paragraph = ""
            paragraph_kind = "paragraph"
            list_item_strict = False

    index = 0
    while index < len(filtered_lines):
        line = filtered_lines[index]
        index += 1

        if line is None:
            flush_paragraph()
            continue

        # ── Bullet list detection ─────────────────────────────────────────────
        # Pattern 1: standalone bullet char (•) on its own line — flag the next
        # paragraph as a list item.
        if _BULLET_CHAR_RE.match(line):
            flush_paragraph()
            next_is_list_item = True
            next_list_item_strict = True  # • items: uppercase = new paragraph
            continue

        # Pattern 2: "bullet HEADING -- body text" from SGML/PDF extracts.
        # Strip the word "bullet", bold the heading, and start a list_item block.
        m_bullet = _BULLET_WORD_RE.match(line)
        if m_bullet:
            flush_paragraph()
            heading = m_bullet.group(1).strip()
            body = m_bullet.group(2).strip()
            paragraph_kind = "list_item"
            list_item_strict = False  # PDF-wrapped text may have uppercase continuations
            paragraph = f"{heading}\x00{body}"
            next_is_list_item = False
            next_list_item_strict = False
            continue

        if _is_artwork_placeholder(line):
            flush_paragraph()
            quote_mode = False
            quote_mode_direct = False
            continue

        if _is_signature_marker(line):
            flush_paragraph()
            name = _signature_name_from_marker(line)
            while index < len(filtered_lines) and filtered_lines[index] is None:
                index += 1
            if index < len(filtered_lines) and filtered_lines[index]:
                name = filtered_lines[index] or name
                index += 1
            while index < len(filtered_lines) and filtered_lines[index] is None:
                index += 1
            if index < len(filtered_lines) and _is_signature_title(filtered_lines[index] or ""):
                blocks.append(("signature", f"{name}\n{filtered_lines[index]}"))
                index += 1
            elif index < len(filtered_lines):
                lookahead_index = index
                title_lines: list[str] = []
                while lookahead_index < len(filtered_lines) and len(title_lines) < 3:
                    candidate = filtered_lines[lookahead_index]
                    if candidate is None:
                        break
                    title_lines.append(candidate)
                    lookahead_index += 1
                    if "chief executive officer" in " ".join(title_lines).lower():
                        index = lookahead_index
                        blocks.append(("signature", f"{name}\n{_SIGNATURE_TITLE}"))
                        break
                else:
                    blocks.append(("signature", f"{name}\n{_SIGNATURE_TITLE}"))
            else:
                blocks.append(("signature", f"{name}\n{_SIGNATURE_TITLE}"))
            quote_mode = False
            quote_mode_direct = False
            continue

        if (
            index < len(filtered_lines)
            and filtered_lines[index] == _SIGNATURE_TITLE
            and line not in _TRADEMARK_LINES
        ):
            flush_paragraph()
            blocks.append(("signature", f"{line}\n{filtered_lines[index]}"))
            index += 1
            quote_mode = False
            quote_mode_direct = False
            continue

        if line in _TRADEMARK_LINES or line == "SM":
            paragraph = _append_inline_marker(paragraph, line)
            continue
        if line in _ORDINAL_SUFFIXES and paragraph and paragraph[-1:].isdigit():
            paragraph = _append_inline_marker(paragraph, line)
            continue
        if paragraph and line[:1] in {".", ",", ";", ":", ")", "%"}:
            paragraph = f"{paragraph}{line}"
            continue

        figure_key = _figure_key_from_note(paragraph)
        if figure_key and (line is not None):
            flush_paragraph()

        if _is_gainshare_formula(paragraph):
            flush_paragraph()

        if _is_omitted_graphic_note(paragraph) and _is_heading(line):
            flush_paragraph()
            blocks.append(("heading", line))
            quote_mode = False
            quote_mode_direct = False
            next_is_list_item = False
            continue

        if _is_heading(line):
            flush_paragraph()
            blocks.append(("heading", line))
            quote_mode = False
            quote_mode_direct = False
            next_is_list_item = False
            continue

        split_heading = _split_leading_all_caps_heading(line)
        if split_heading:
            flush_paragraph()
            heading, rest = split_heading
            blocks.append(("heading", heading))
            line = rest

        line_starts_new_paragraph = not paragraph or not _should_join_lines(paragraph, line)
        if line_starts_new_paragraph and quote_mode and _is_story_quote_reset(line):
            quote_mode = False
            quote_mode_direct = False

        # Direct block-quote detection: a long line starting with " that isn't
        # a CEO-quoting-a-term construction activates quote_mode immediately.
        if line_starts_new_paragraph and not quote_mode and _is_direct_block_quote_start(line):
            quote_mode = True
            quote_mode_direct = True

        current_kind = "quote" if quote_mode else "paragraph"
        if paragraph and _should_join_lines(paragraph, line):
            # Pattern 1 (strict) list items: an uppercase-starting line is always
            # a paragraph break, not a continuation of the bullet text.
            if paragraph_kind == "list_item" and list_item_strict and line[:1].isupper():
                flush_paragraph()
                current_kind = "quote" if quote_mode else "paragraph"
                next_is_list_item = False
                next_list_item_strict = False
                paragraph_kind = current_kind
                paragraph = line
            else:
                paragraph = f"{paragraph} {line}"
        else:
            flush_paragraph()
            # Recompute after flush: flush_paragraph may have reset quote_mode
            # (e.g. a direct block quote that ended with a closing ").
            current_kind = "quote" if quote_mode else "paragraph"
            if next_is_list_item:
                current_kind = "list_item"
                list_item_strict = next_list_item_strict
                next_list_item_strict = False
            next_is_list_item = False
            paragraph_kind = current_kind
            paragraph = line

        if line_starts_new_paragraph and _is_story_quote_intro(line):
            paragraph_kind = "paragraph"
            quote_mode = True
            quote_mode_direct = False

    flush_paragraph()
    return blocks


def render_letter_html(text: str) -> str:
    """Convert extracted plain letter text to polished, escaped HTML blocks."""
    blocks = _normalized_letter_blocks(text)
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
            name, title = block_text.split("\n", 1)
            rendered.append(
                '<div class="signature-block">\n'
                f'  <p class="signature-name">{html.escape(name)}</p>\n'
                f'  <p class="signature-title">{html.escape(title)}</p>\n'
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
        summary_section=_render_summary_html(filing["id"], filing["year"], filing["quarter"]),
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

    log.info("Done. %d page(s) built.", built)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-letter HTML reading pages.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild all pages, not just new ones.")
    args = parser.parse_args()
    main(rebuild=args.rebuild)
