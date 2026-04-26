#!/usr/bin/env python3
"""
fix_letter_text.py — Clean up formatting issues in all collected CEO letters.

Issues addressed:
  1. SGML metadata headers in 2005+ ex99 letters (EX-99, exhibit numbers, etc.)
  2. Windows-1252 encoding surrogates (\x91-\x97) → proper Unicode
  3. PDF ligature characters (ﬁ→fi, ﬂ→fl)
  4. Bare page-number-only lines in 1993-2004 annual letters
  5. Trailing nav text in 2004 Q3
  6. Horizontal-rule line in 2021 Q4

Run:
    python scripts/fix_letter_text.py             # apply all fixes
    python scripts/fix_letter_text.py --dry-run   # preview only
"""

import argparse
import io
import re
import sys
from pathlib import Path

# Force UTF-8 output on Windows consoles.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"

# ── Encoding fix maps ─────────────────────────────────────────────────────────

WIN1252_MAP = {
    "\x91": "‘",  # left single quotation mark
    "\x92": "’",  # right single quotation mark / apostrophe
    "\x93": "“",  # left double quotation mark
    "\x94": "”",  # right double quotation mark
    "\x95": "•",  # bullet
    "\x96": "–",  # en dash
    "\x97": "—",  # em dash
}
WIN1252_RE = re.compile("[" + "".join(WIN1252_MAP) + "]")

LIGATURE_MAP = {
    "ﬁ": "fi",   # ﬁ
    "ﬂ": "fl",   # ﬂ
}
LIGATURE_RE = re.compile("[" + "".join(LIGATURE_MAP) + "]")

# ── SGML header detection ─────────────────────────────────────────────────────
# These patterns match lines that are metadata, not letter content.

_HEADER_LINE_RE = re.compile(
    r"""^(?:
        EX-\d+                          # EX-99, EX-13, etc.
        | EXHIBIT\s+.*                  # EXHIBIT 99, EXHIBIT NO. 99
        | exhibit\s+.*                  # exhibit 99 Shareholder Letter ...
        | Exhibit\s+.*                  # Exhibit 99, Exhibit No. 99
        | \d+                           # bare number (sequence / page ref)
        | [a-zA-Z0-9_\-]+\.htm         # HTML filename
        | LETTER\s+TO\s+SHAREHOLDERS.* # all-caps heading
        | Letter\s+to\s+Shareholders.* # mixed-case heading (with or without suffix)
        | Letter\s+to                   # split heading part 1
        | Shareholders                  # split heading part 2
        | SHAREHOLDERS
        | Document
        | The\s+Progressive\s+Corporation.*  # company name header
        | (?:First|Second|Third|Fourth)\s+Quarter.*  # quarter label
        | Q[1-4]\s*                     # Q1 / Q2 alone
        | \d{4}\s*                      # bare 4-digit year
        | \{\s*Letter\s+to\s+Shareholders\s*\}  # { Letter to Shareholders }
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

# A "real content" line: long enough and not a known header pattern.
_MIN_CONTENT_LEN = 20


def _is_header_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True  # blank lines before content are skippable
    return bool(_HEADER_LINE_RE.match(stripped))


def strip_sgml_header(text: str) -> tuple[str, bool]:
    """Remove SGML metadata header from the top of a letter.

    Returns (cleaned_text, was_changed).
    Only acts on letters whose first non-blank line is 'EX-99' or 'EX-13'
    or '{ Letter to Shareholders }' (wayback HTML variant).
    """
    lines = text.splitlines()
    if not lines:
        return text, False

    first_real = next((l.strip() for l in lines if l.strip()), "")
    is_sgml = bool(re.match(r"^EX-\d+$", first_real, re.IGNORECASE))
    is_wayback_html = bool(re.match(r"^\{.+Letter.+\}", first_real, re.IGNORECASE))

    if not (is_sgml or is_wayback_html):
        return text, False

    # Find the first line that looks like real content.
    start_idx = 0
    for i, line in enumerate(lines):
        if not _is_header_line(line):
            start_idx = i
            break

    if start_idx == 0:
        return text, False  # nothing to strip

    remaining = lines[start_idx:]

    # Special case: if the first content line starts lowercase, it may be a
    # fragment from a broken Q1/Q2 header (e.g. "Q1\nwas a very good quarter.").
    # Check if the last skipped line was a quarter token and join it.
    if remaining and remaining[0].strip() and remaining[0].strip()[0].islower():
        last_header = lines[start_idx - 1].strip()
        if re.match(r"^Q[1-4]$", last_header, re.IGNORECASE):
            remaining[0] = last_header + " " + remaining[0].strip()

    cleaned = "\n".join(remaining).strip()
    return cleaned, cleaned != text.strip()


# ── Encoding fixes ─────────────────────────────────────────────────────────────

def fix_encoding(text: str) -> tuple[str, list[str]]:
    """Replace Win-1252 surrogates, PDF ligatures, and join hyphenated line breaks."""
    changes = []
    original = text

    def repl_win(m):
        return WIN1252_MAP[m.group(0)]

    def repl_lig(m):
        return LIGATURE_MAP[m.group(0)]

    text = WIN1252_RE.sub(repl_win, text)
    if text != original:
        changes.append("win1252_surrogates")
        original = text

    text = LIGATURE_RE.sub(repl_lig, text)
    if text != original:
        changes.append("pdf_ligatures")
        original = text

    # Join hyphenated line-breaks from columnar PDF layout (e.g. "high-\nlights").
    dehyphenated = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    if dehyphenated != text:
        text = dehyphenated
        changes.append("dehyphenated_linebreaks")

    # Decode PDF private-use-area (PUA) font encoding.
    # Some PDFs encode characters as U+F7XX where XX is the ASCII code point.
    # E.g. U+F730–U+F739 = '0'–'9', U+F761–U+F77A = 'a'–'z'.
    _PUA_RE = re.compile(r"[-]")

    def _decode_pua(m: re.Match) -> str:
        decoded = chr(ord(m.group(0)) - 0xF700)
        # Only replace if decoded character is printable ASCII.
        if 0x20 <= ord(decoded) <= 0x7E:
            return decoded
        return m.group(0)

    text = text.replace(chr(0xF6E4), "$")  # Adobe dollar.tf glyph
    pua_fixed = _PUA_RE.sub(_decode_pua, text)
    if pua_fixed != text:
        text = pua_fixed
        changes.append("pua_font_decoded")

    return text, changes


# ── Bare page-number lines ────────────────────────────────────────────────────
# In 1993-2004 annual letters extracted from SGML/PDF, pages are delimited by
# lines that contain only a page number (1-3 digits) or a range like "2 - 3".

_PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?\s*$")
_PHOTO_CAPTION_RE = re.compile(r"^Photograph:", re.IGNORECASE)


def strip_page_markers(text: str) -> tuple[str, bool]:
    """Remove isolated page-number lines and photo caption lines."""
    lines = text.splitlines()
    cleaned = [
        l for l in lines
        if not _PAGE_NUM_RE.match(l) and not _PHOTO_CAPTION_RE.match(l)
    ]
    result = "\n".join(cleaned)
    # Collapse runs of 3+ blank lines to double blank.
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result, result != text.strip()


# ── Per-file specific patches ─────────────────────────────────────────────────

def apply_specific_patches(stem: str, text: str) -> tuple[str, list[str]]:
    """Apply known per-file fixes. Returns (text, [change_labels])."""
    changes = []

    if stem == "PGR_2004_Q3_Letter":
        # Last two lines are nav text from the Wayback noflash page.
        lines = text.splitlines()
        while lines and re.match(
            r"^(?:continue to|THIRD QUARTER \d{4} FINANCIAL REVIEW)\s*$",
            lines[-1].strip(),
            re.IGNORECASE,
        ):
            lines.pop()
        new = "\n".join(lines).strip()
        if new != text.strip():
            text = new
            changes.append("removed_nav_text")

    if stem == "PGR_2021_Q4_Letter":
        # A horizontal rule separating employee story excerpts.
        new = re.sub(r"^_{10,}\s*$", "", text, flags=re.MULTILINE)
        new = re.sub(r"\n{3,}", "\n\n", new).strip()
        if new != text.strip():
            text = new
            changes.append("removed_hr_underscores")

    return text, changes


# ── Main processing ───────────────────────────────────────────────────────────

def process_file(path: Path, dry_run: bool) -> dict:
    """Process one letter file. Returns a result dict."""
    stem = path.stem
    original = path.read_text(encoding="utf-8")
    text = original

    applied = []

    # 1. Strip SGML / wayback-HTML header
    text, changed = strip_sgml_header(text)
    if changed:
        applied.append("stripped_sgml_header")

    # 2. Encoding fixes (win1252 + ligatures)
    text, enc_changes = fix_encoding(text)
    applied.extend(enc_changes)

    # 3. Bare page-number / photo-caption lines (pre-2005 annual letters)
    year_str = stem.split("_")[1] if "_" in stem else "9999"
    try:
        year = int(year_str)
    except ValueError:
        year = 9999

    if year < 2005 and path.stat().st_size > 10_000:
        # Only apply to large pre-2005 files (annual reports, not wayback HTML)
        text, changed = strip_page_markers(text)
        if changed:
            applied.append("stripped_page_markers")

    # 4. Per-file patches
    text, patch_changes = apply_specific_patches(stem, text)
    applied.extend(patch_changes)

    text = text.strip() + "\n"
    changed_overall = text != original

    if not dry_run and changed_overall:
        path.write_text(text, encoding="utf-8")

    return {
        "stem": stem,
        "original_len": len(original),
        "new_len": len(text),
        "changed": changed_overall,
        "applied": applied,
    }


# ── Manual review checklist ───────────────────────────────────────────────────

_REVIEW_CHECKS = [
    # (label, pattern, description)
    ("garbled_chars",   re.compile(r"[?]{3,}"),
     "3+ consecutive question marks (OCR garble)"),
    ("pua_chars",       re.compile(r"[-]"),
     "Unicode Private Use Area characters (garbled from PDF font mapping)"),
    ("missing_space",   re.compile(r"Glenn M\.Renwick"),
     "CEO name missing space after period (Glenn M.Renwick)"),
    ("low_content",     None,
     "Unusually short letter (< 2000 chars after cleaning)"),
    ("very_large_pre2005", None,
     "Pre-2005 letter > 35000 chars — may be full annual report rather than CEO letter"),
    ("starts_lowercase", None,
     "First content line starts with lowercase — possible split fragment or false positive"),
    ("hyphenated_words", re.compile(r"\b\w+-\n\w+"),
     "Remaining hyphenated line-breaks from columnar PDF layout (after auto-fix)"),
]


def check_manual_review(path: Path, text: str) -> list[str]:
    """Return a list of manual review flags for this letter."""
    flags = []
    lines = [l for l in text.splitlines() if l.strip()]
    body = text.strip()

    year_str = path.stem.split("_")[1] if "_" in path.stem else "9999"
    try:
        file_year = int(year_str)
    except ValueError:
        file_year = 9999

    for label, pattern, desc in _REVIEW_CHECKS:
        if label == "low_content" and len(body) < 2000:
            flags.append(f"{label}: {desc} ({len(body)} chars)")
        elif label == "very_large_pre2005" and file_year < 2005 and len(body) > 35000:
            flags.append(f"{label}: {desc} ({len(body)} chars)")
        elif label == "starts_lowercase" and lines:
            first_word = lines[0].lstrip()
            if first_word and first_word[0].islower():
                flags.append(f"{label}: {desc} — '{lines[0][:60]}'")
        elif label == "hyphenated_words" and pattern and pattern.search(body):
            n = len(pattern.findall(body))
            flags.append(f"{label}: {desc} — {n} occurrence(s)")
        elif label not in ("low_content", "very_large_pre2005", "starts_lowercase", "hyphenated_words"):
            if pattern and pattern.search(body):
                flags.append(f"{label}: {desc}")

    return flags


# ── Entry point ───────────────────────────────────────────────────────────────

def main(dry_run: bool) -> None:
    if dry_run:
        print("=== DRY RUN — no files will be written ===\n")

    files = sorted(LETTERS_DIR.glob("*.txt"))
    if not files:
        print("No letter files found in", LETTERS_DIR)
        sys.exit(1)

    total_changed = 0
    review_items: list[tuple[str, list[str]]] = []

    for path in files:
        result = process_file(path, dry_run)
        stem = result["stem"]

        if result["changed"]:
            total_changed += 1
            verb = "[DRY RUN] Would change" if dry_run else "Fixed"
            print(f"{verb}  {stem}")
            print(f"   Changes: {', '.join(result['applied'])}")
            print(f"   Size: {result['original_len']} → {result['new_len']} chars")

        # Compute post-fix text for manual review scan.
        if dry_run:
            t = path.read_text(encoding="utf-8")
            t, _ = strip_sgml_header(t)
            t, _ = fix_encoding(t)
            t, _ = apply_specific_patches(stem, t)
            text_for_review = t
        else:
            text_for_review = path.read_text(encoding="utf-8")

        flags = check_manual_review(path, text_for_review)
        if flags:
            review_items.append((stem, flags))

    print(f"\n{'='*60}")
    action = "Would change" if dry_run else "Changed"
    print(f"  {action} {total_changed} / {len(files)} files")
    print(f"{'='*60}")

    if review_items:
        print(f"\n{'='*60}")
        print("  MANUAL REVIEW REQUIRED")
        print(f"  {len(review_items)} letter(s) need human inspection:")
        print(f"{'='*60}")
        for stem, flags in review_items:
            print(f"\n  {stem}:")
            for flag in flags:
                print(f"    • {flag}")
    else:
        print("\n  No manual review items — all letters look clean.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fix formatting issues in collected PGR CEO letters."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview fixes without writing files.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)