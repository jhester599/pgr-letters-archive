#!/usr/bin/env python3
"""
backfill_ex99.py — Retry post-2005 filings previously skipped as "no_exhibit_99".

The original scraper read the document description column instead of the exhibit
type column from EDGAR filing index pages. This caused filings where the description
was a long string (e.g. "LETTER TO SHAREHOLDERS FROM GLENN M. RENWICK...") to be
missed, even though cells[3] correctly contained "EX-99".

This script finds all ledger entries with skip_reason "no_exhibit_99" and year >= 2005,
re-fetches their filing document index using the corrected column logic, and downloads
the letter if EX-99 is now found. Updates existing ledger entries in place.

Usage:
    python scripts/backfill_ex99.py              # process all eligible filings
    python scripts/backfill_ex99.py --dry-run    # preview without writing files
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import (
    fetch_and_clean,
    fetch_filing_documents,
    find_exhibit_99,
    load_ledger,
    save_ledger,
    LETTERS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def process_filing(filing: dict, ledger: dict, dry_run: bool) -> str:
    """Returns: 'saved', 'skipped', 'no_ex99', 'failed', or 'dry_run'."""
    if filing.get("letter_scraped"):
        return "skipped"

    filing_id = filing["id"]
    acc = filing["accession_number"]

    if dry_run:
        log.info("[DRY RUN] Would retry %s (%s %s)",
                 filing_id, filing["form_type"], filing.get("report_date", ""))
        return "dry_run"

    log.info("Retrying  %s  %s", filing["form_type"], filing_id)

    documents = fetch_filing_documents(acc)
    if not documents:
        log.warning("  Could not retrieve filing index for %s", acc)
        return "failed"

    ex99_filename = find_exhibit_99(documents)
    if not ex99_filename:
        log.info("  Still no EX-99 in %s — genuinely absent", acc)
        return "no_ex99"

    text = fetch_and_clean(acc, ex99_filename)
    if not text:
        log.warning("  Failed to fetch/clean letter for %s", filing_id)
        return "failed"

    letter_filename = f"{filing_id}_Letter.txt"
    (LETTERS_DIR / letter_filename).write_text(text, encoding="utf-8")
    log.info("  Saved %s  (%d chars)", letter_filename, len(text))

    filing.update({
        "letter_file":       f"data/letters/{letter_filename}",
        "audio_file":        f"docs/audio/{filing_id}_Letter.mp3",
        "letter_scraped":    True,
        "audio_generated":   False,
        "audio_compressed":  False,
        "page_built":        False,
        "page_url":          None,
        "processed_date":    datetime.now(timezone.utc).isoformat(),
        "skip_reason":       None,
    })
    save_ledger(ledger)
    return "saved"


def main(dry_run: bool = False) -> None:
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    targets = [
        f for f in ledger["filings"]
        if f.get("skip_reason") == "no_exhibit_99"
        and f.get("year", 0) >= 2005
    ]

    if not targets:
        log.info("No eligible skipped post-2005 filings found — nothing to do.")
        return

    log.info("Found %d skipped post-2005 filing(s) to retry.", len(targets))
    if dry_run:
        log.info("=== DRY RUN — no files will be written ===")

    counts = {"saved": 0, "skipped": 0, "no_ex99": 0, "failed": 0, "dry_run": 0}
    for filing in sorted(targets, key=lambda f: (f["year"], f["quarter"])):
        status = process_filing(filing, ledger, dry_run)
        counts[status] += 1

    log.info("")
    log.info("══════════════════════════════════════════")
    log.info("  EX-99 backfill complete.")
    log.info("  %-14s %d", "Saved:", counts["saved"])
    log.info("  %-14s %d", "Still absent:", counts["no_ex99"])
    log.info("  %-14s %d", "Failed:", counts["failed"])
    if dry_run:
        log.info("  %-14s %d", "Would retry:", counts["dry_run"])
    log.info("══════════════════════════════════════════")

    if counts["saved"] and not dry_run:
        log.info("")
        log.info("Next step — build reading pages for new letters:")
        log.info("  python scripts/build_pages.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retry post-2005 filings skipped due to column-parsing bug.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
