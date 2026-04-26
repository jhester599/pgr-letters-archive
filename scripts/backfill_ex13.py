#!/usr/bin/env python3
"""
backfill_ex13.py — Extract PGR CEO shareholder letters from pre-2005 10-K filings.

Pre-2005 filings did not attach the CEO letter as a standalone Exhibit 99. Instead,
the letter appears inside Exhibit 13 (the Annual Report to Shareholders). This script
finds those 10 annual letters (1993–2004) and updates the existing ledger entries in
place, making them available to the rest of the pipeline (audio generation, reading
pages, etc.).

EDGAR filed two formats in this era:
  - 2001–2004: EX-13 is a separate .htm file in the filing.
  - 1993–2000: All documents bundled in one {accession}.txt SGML file.

Usage:
    python scripts/backfill_ex13.py             # process all eligible filings
    python scripts/backfill_ex13.py --dry-run   # preview without writing files

Environment variables:
    None required — SEC EDGAR is a public API.
"""

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import (
    fetch_filing_documents,
    get,
    load_ledger,
    save_ledger,
    BASE_DIR,
    CIK_PLAIN,
    EDGAR_ARCHIVES,
    LETTERS_DIR,
)

from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Compiled patterns ─────────────────────────────────────────────────────────

_START_RE = re.compile(
    r"letter to (?:our )?share(?:holder|owner)s?",
    re.IGNORECASE,
)
_END_RE = re.compile(
    r"(?:financial review|financial highlights|management.s discussion"
    r"|consolidated statements|selected financial|report of independent)",
    re.IGNORECASE,
)


def find_ex13(documents: list[dict]) -> str | None:
    """Return EX-13 filename, '' if bundled (no filename), None if not found."""
    for doc in documents:
        dtype = doc.get("type", "").upper()
        if "EX-13" in dtype or "EXHIBIT 13" in dtype:
            return doc.get("filename", "")
    return None


def fetch_ex13_html(accession_number: str, filename: str) -> str | None:
    """Fetch and clean an HTML EX-13 file (2001–2004 format)."""
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{CIK_PLAIN}/{acc}/{filename}"
    resp = get(url)
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def fetch_ex13_bundled(accession_number: str) -> str | None:
    """Fetch and extract EX-13 from an SGML bundled submission file (1993–2000 format)."""
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{CIK_PLAIN}/{acc}/{accession_number}.txt"
    resp = get(url)
    if not resp:
        return None

    raw = resp.text
    m = re.search(r"<TYPE>EX-13.*?</DOCUMENT>", raw, re.DOTALL | re.IGNORECASE)
    if not m:
        log.warning("No <TYPE>EX-13 block found in bundled text for %s", accession_number)
        return None

    block = m.group(0)
    block = re.sub(r"<[^>]+>", " ", block)
    lines = [line.strip() for line in block.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_MIN_LETTER_CHARS = 50  # minimum chars to consider a match the real letter, not a TOC entry


def extract_letter(text: str) -> tuple[str, str]:
    """Extract the 'Letter to Shareholders' section from Annual Report text.

    Returns (letter_text, extraction_method).
    extraction_method is 'letter_section' or 'full_ex13_fallback'.

    Iterates all start-heading matches so that table-of-contents entries (which
    are immediately followed by an end-boundary like 'Financial Review') are
    skipped in favour of the actual letter body further in the document.
    """
    for start_m in _START_RE.finditer(text):
        # Skip past the heading line itself
        line_end = text.find("\n", start_m.end())
        body_start = line_end + 1 if line_end >= 0 else start_m.end()
        tail = text[body_start:]

        # Find end boundary — back up to the start of the matched line
        end_m = _END_RE.search(tail)
        if end_m:
            line_start = tail.rfind("\n", 0, end_m.start())
            end_pos = line_start if line_start >= 0 else end_m.start()
            letter = tail[:end_pos].strip()
        else:
            letter = tail.strip()

        if len(letter) >= _MIN_LETTER_CHARS:
            return letter, "letter_section"

    return text, "full_ex13_fallback"


def process_filing(filing: dict, ledger: dict, dry_run: bool) -> str:
    """Process one filing. Returns: 'saved', 'skipped', 'failed', or 'dry_run'."""
    if filing.get("letter_scraped"):
        return "skipped"

    filing_id  = filing["id"]
    acc        = filing["accession_number"]

    if dry_run:
        log.info("[DRY RUN] Would process %s (%s %s)",
                 filing_id, filing["form_type"], filing.get("report_date", ""))
        return "dry_run"

    log.info("Processing  %s  %s", filing["form_type"], filing_id)

    documents = fetch_filing_documents(acc)
    if not documents:
        log.warning("  Could not retrieve filing index for %s", acc)
        return "failed"

    ex13_filename = find_ex13(documents)
    if ex13_filename is None:
        log.warning("  No EX-13 found in filing index for %s", acc)
        return "failed"

    if ex13_filename:
        annual_report_text = fetch_ex13_html(acc, ex13_filename)
    else:
        annual_report_text = fetch_ex13_bundled(acc)

    if not annual_report_text:
        log.warning("  Failed to fetch/parse EX-13 for %s", filing_id)
        return "failed"

    letter_text, extraction_method = extract_letter(annual_report_text)
    if extraction_method == "full_ex13_fallback":
        log.info("  No letter heading found — saving full EX-13 as fallback for %s", filing_id)

    letter_filename = f"{filing_id}_Letter.txt"
    (LETTERS_DIR / letter_filename).write_text(letter_text, encoding="utf-8")
    log.info("  Saved %s  (%d chars, method=%s)",
             letter_filename, len(letter_text), extraction_method)

    filing.update({
        "letter_file":        f"data/letters/{letter_filename}",
        "audio_raw_file":     None,
        "audio_file":         f"docs/audio/{filing_id}_Letter.mp3",
        "letter_scraped":     True,
        "audio_generated":    False,
        "audio_compressed":   False,
        "page_built":         False,
        "page_url":           None,
        "extraction_method":  extraction_method,
        "processed_date":     datetime.now(timezone.utc).isoformat(),
        "skip_reason":        None,
    })
    save_ledger(ledger)
    return "saved"


def main(dry_run: bool = False) -> None:
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    targets = [
        f for f in ledger["filings"]
        if f.get("form_type") == "10-K"
        and f.get("year", 9999) < 2005
    ]

    if not targets:
        log.info("No eligible pre-2005 10-K filings found — nothing to do.")
        return

    log.info("Found %d eligible pre-2005 10-K filing(s).", len(targets))
    if dry_run:
        log.info("=== DRY RUN — no files will be written ===")

    counts = {"saved": 0, "skipped": 0, "failed": 0, "dry_run": 0}
    for filing in sorted(targets, key=lambda f: f["year"]):
        status = process_filing(filing, ledger, dry_run)
        counts[status] += 1

    log.info("")
    log.info("══════════════════════════════════════════")
    log.info("  Pre-2005 EX-13 backfill complete.")
    log.info("  %-12s %d", "Saved:", counts["saved"])
    log.info("  %-12s %d", "Skipped:", counts["skipped"])
    log.info("  %-12s %d", "Failed:", counts["failed"])
    if dry_run:
        log.info("  %-12s %d", "Would process:", counts["dry_run"])
    log.info("══════════════════════════════════════════")

    if counts["saved"] and not dry_run:
        log.info("")
        log.info("Next step — build reading pages for new letters:")
        log.info("  python scripts/build_pages.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract PGR CEO letters from pre-2005 10-K Exhibit 13 filings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be processed without writing any files.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
