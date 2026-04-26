#!/usr/bin/env python3
"""
backfill.py — One-time historical scraper for all available PGR filings on SEC EDGAR.

The regular scraper.py only reads the most recent ~40 filings from the EDGAR
submissions API. This script also paginates through the older filing index files
referenced in filings.files[], giving access to the complete SEC history for PGR.

It writes to the same docs/ledger.json and data/letters/ as scraper.py and is
fully idempotent — already-processed filings are skipped on subsequent runs.

Usage:
    # Scrape everything available (may be 100+ filings, takes several minutes)
    python scripts/backfill.py

    # Preview what would be fetched without downloading anything
    python scripts/backfill.py --dry-run

    # Only backfill filings from 2000 onward
    python scripts/backfill.py --from-year 2000

    # Combine flags
    python scripts/backfill.py --from-year 2010 --dry-run

Environment variables:
    None required — SEC EDGAR is a public API.

After backfill, run generator.py to generate audio for all new letters:
    python scripts/generator.py --max-new 0    # 0 = no limit (process all)
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

# Import shared helpers from scraper.py (same package)
from scraper import (
    already_processed,
    fetch_and_clean,
    fetch_filing_documents,
    find_exhibit_99,
    get,
    load_ledger,
    period_to_quarter,
    save_ledger,
    BASE_DIR,
    CIK_PLAIN,
    EDGAR_SUBMISSIONS,
    LETTERS_DIR,
    LEDGER_PATH,
    PGR_CIK,
    REQUEST_DELAY,
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── EDGAR pagination ──────────────────────────────────────────────────────────

def iter_all_filings(from_year: Optional[int]) -> Iterator[tuple[str, str, str]]:
    """
    Yield (form_type, accession_number, report_date) for every 10-Q and 10-K
    filing in PGR's full EDGAR history, newest first.

    Covers both filings.recent (~40 most recent) and all older pages listed
    in filings.files[].
    """
    target_forms = {"10-Q", "10-K", "10-K405"}

    log.info("Fetching root submissions JSON for CIK %s…", PGR_CIK)
    resp = get(f"{EDGAR_SUBMISSIONS}/CIK{PGR_CIK}.json")
    if not resp:
        raise RuntimeError("Failed to fetch EDGAR submissions — check network / User-Agent header")
    root = resp.json()

    # Collect all filing pages: the inline recent block + any older paginated files
    pages: list[dict] = [root["filings"]["recent"]]

    older_files = root.get("filings", {}).get("files", [])
    if older_files:
        log.info("Found %d additional historical filing page(s) to fetch.", len(older_files))
    for file_entry in older_files:
        name = file_entry.get("name", "")
        filing_from = file_entry.get("filingFrom", "")
        filing_to   = file_entry.get("filingTo", "")
        log.info("  Fetching page: %s  (%s → %s)", name, filing_from, filing_to)
        page_resp = get(f"{EDGAR_SUBMISSIONS}/{name}")
        if page_resp:
            pages.append(page_resp.json())
        else:
            log.warning("  Could not fetch %s — some historical filings may be missing", name)

    log.info("Total filing pages collected: %d", len(pages))

    # Yield qualifying filings across all pages
    for page in pages:
        forms     = page.get("form", [])
        acc_nums  = page.get("accessionNumber", [])
        rep_dates = page.get("reportDate", [])

        for form, acc, date in zip(forms, acc_nums, rep_dates):
            if form not in target_forms:
                continue
            if not date:
                continue
            if from_year:
                try:
                    if int(date[:4]) < from_year:
                        continue
                except (ValueError, IndexError):
                    continue
            yield form, acc, date

# ── Filing processing ─────────────────────────────────────────────────────────

def process_filing(
    form: str,
    acc: str,
    date: str,
    ledger: dict,
    dry_run: bool,
) -> str:
    """
    Download and save one filing's Exhibit 99. Returns a status string:
      'saved'     — letter downloaded and saved
      'skipped'   — already in ledger
      'no_ex99'   — filing has no Exhibit 99
      'failed'    — download or parse error
      'dry_run'   — would have been processed but dry_run=True
    """
    if already_processed(ledger, acc):
        return "skipped"

    year, quarter = period_to_quarter(date, form)
    filing_id = f"PGR_{year}_{quarter}"

    if dry_run:
        log.info("[DRY RUN]  Would process %s  %s  →  %s", form, date, filing_id)
        return "dry_run"

    log.info("Processing  %s  %s  →  %s", form, date, filing_id)

    documents = fetch_filing_documents(acc)
    if not documents:
        log.warning("  Could not retrieve filing index — skipping %s", acc)
        return "failed"

    ex99_filename = find_exhibit_99(documents)
    if not ex99_filename:
        log.info("  No Exhibit 99 found in %s — recording skip", acc)
        ledger["filings"].append({
            "id": filing_id,
            "year": year,
            "quarter": quarter,
            "form_type": form,
            "accession_number": acc,
            "report_date": date,
            "letter_file": None,
            "audio_raw_file": None,
            "audio_file": None,
            "letter_scraped": False,
            "audio_generated": False,
            "audio_compressed": False,
            "processed_date": datetime.now(timezone.utc).isoformat(),
            "skip_reason": "no_exhibit_99",
        })
        save_ledger(ledger)
        return "no_ex99"

    text = fetch_and_clean(acc, ex99_filename)
    if not text:
        log.error("  Failed to download/clean letter for %s", filing_id)
        return "failed"

    letter_filename = f"{filing_id}_Letter.txt"
    letter_path = LETTERS_DIR / letter_filename
    letter_path.write_text(text, encoding="utf-8")
    log.info("  Saved %s  (%d chars)", letter_filename, len(text))

    audio_filename = f"{filing_id}_Letter.mp3"
    ledger["filings"].append({
        "id": filing_id,
        "year": year,
        "quarter": quarter,
        "form_type": form,
        "accession_number": acc,
        "report_date": date,
        "letter_file": f"data/letters/{letter_filename}",
        "audio_raw_file": None,
        "audio_file": f"docs/audio/{audio_filename}",
        "letter_scraped": True,
        "audio_generated": False,
        "audio_compressed": False,
        "processed_date": datetime.now(timezone.utc).isoformat(),
    })
    save_ledger(ledger)
    return "saved"

# ── Main ──────────────────────────────────────────────────────────────────────

def main(from_year: Optional[int], dry_run: bool) -> None:
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    if dry_run:
        log.info("=== DRY RUN MODE — no files will be written ===")
    if from_year:
        log.info("Limiting backfill to filings from %d onward.", from_year)

    counts = {"saved": 0, "skipped": 0, "no_ex99": 0, "failed": 0, "dry_run": 0}

    for form, acc, date in iter_all_filings(from_year):
        status = process_filing(form, acc, date, ledger, dry_run)
        counts[status] += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    total = sum(counts.values())
    log.info("")
    log.info("══════════════════════════════════")
    log.info("  Backfill complete.  %d filing(s) examined.", total)
    log.info("  %-12s %d", "New letters:", counts["saved"])
    log.info("  %-12s %d", "Already done:", counts["skipped"])
    log.info("  %-12s %d", "No Exhibit 99:", counts["no_ex99"])
    log.info("  %-12s %d", "Errors:", counts["failed"])
    if dry_run:
        log.info("  %-12s %d", "Would process:", counts["dry_run"])
    log.info("══════════════════════════════════")

    if counts["saved"] and not dry_run:
        log.info("")
        log.info("Next step — generate audio for all new letters:")
        log.info("  python scripts/generator.py --max-new 0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill all historical PGR shareholder letters from SEC EDGAR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        metavar="YYYY",
        help="Only process filings from this year onward (e.g. --from-year 2010).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be downloaded without writing any files.",
    )
    args = parser.parse_args()
    main(from_year=args.from_year, dry_run=args.dry_run)
