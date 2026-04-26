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
        if "EX-13" in dtype:
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
    pass  # implemented in Task 3


def extract_letter(text: str) -> tuple[str, str]:
    pass  # implemented in Task 4


def process_filing(filing: dict, ledger: dict, dry_run: bool) -> str:
    pass  # implemented in Task 5


def main(dry_run: bool = False) -> None:
    pass  # implemented in Task 5


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
