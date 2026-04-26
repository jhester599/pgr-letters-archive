#!/usr/bin/env python3
"""
scraper.py — SEC EDGAR scraper for Progressive Corporation (PGR) shareholder letters.

Queries the EDGAR submissions API for 10-Q and 10-K filings, locates Exhibit 99
(the CEO's quarterly letter to shareholders), extracts and cleans the text,
and saves each letter as a .txt file in /data/letters/.

State is tracked in docs/ledger.json so already-processed filings are skipped
on subsequent runs.

Usage:
    python scripts/scraper.py

Environment variables:
    None required — SEC EDGAR is a public API.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Constants ─────────────────────────────────────────────────────────────────

PGR_CIK = "0000080661"          # Progressive Corporation CIK on SEC EDGAR
CIK_PLAIN = str(int(PGR_CIK))  # "80661" — no leading zeros, used in URLs

EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# SEC requires a descriptive User-Agent; using project name + contact
HEADERS = {
    "User-Agent": "PGR-Letters-Archive jeffrey.r.hester@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/html, */*",
}

BASE_DIR    = Path(__file__).resolve().parent.parent
LETTERS_DIR = BASE_DIR / "data" / "letters"
LEDGER_PATH = BASE_DIR / "docs" / "ledger.json"

REQUEST_DELAY = 0.15   # seconds — keeps us well under EDGAR's 10 req/s limit
MAX_RETRIES   = 3

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Ledger helpers ────────────────────────────────────────────────────────────

def load_ledger() -> dict:
    if LEDGER_PATH.exists():
        with open(LEDGER_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {"meta": {}, "filings": []}


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    ledger["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    ledger["meta"]["total_letters"] = sum(
        1 for f in ledger["filings"] if f.get("letter_scraped")
    )
    ledger["meta"]["total_audio"] = sum(
        1 for f in ledger["filings"] if f.get("audio_compressed")
    )
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, default=str)


def already_processed(ledger: dict, accession_number: str) -> bool:
    return any(
        f.get("accession_number") == accession_number
        for f in ledger.get("filings", [])
    )

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(url: str) -> Optional[requests.Response]:
    """GET with retry/backoff; returns None on permanent failure."""
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code == 429:
                wait = 5 * (2 ** attempt)
                log.warning("Rate limited (429). Backing off %ds…", wait)
                time.sleep(wait)
            else:
                log.error("HTTP %d for %s", code, url)
                return None
        except requests.RequestException as exc:
            log.warning("Request error (%s): %s", type(exc).__name__, exc)
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(2 ** attempt)
    return None

# ── EDGAR API calls ───────────────────────────────────────────────────────────

def fetch_submissions() -> dict:
    url = f"{EDGAR_SUBMISSIONS}/CIK{PGR_CIK}.json"
    resp = get(url)
    if not resp:
        raise RuntimeError(f"Failed to fetch EDGAR submissions for CIK {PGR_CIK}")
    return resp.json()


def fetch_filing_documents(accession_number: str) -> Optional[list[dict]]:
    """Return the list of document dicts from the filing's HTML index page."""
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{CIK_PLAIN}/{acc}/{accession_number}-index.htm"
    resp = get(url)
    if not resp:
        return None
    try:
        soup = BeautifulSoup(resp.text, "lxml")
        documents = []
        for row in soup.select("table tr"):
            cells = row.find_all("td")
            # Index page table columns: seq, description, filename, type, size
            # cells[3] is the short exhibit code (e.g. "EX-99") in all EDGAR eras;
            # cells[1] is a long description in older filings but equals the code
            # in modern ones. Always prefer cells[3] when present.
            if len(cells) < 3:
                continue
            doc_type = (
                cells[3].get_text(strip=True)
                if len(cells) >= 4 and cells[3].get_text(strip=True)
                else cells[1].get_text(strip=True)
            )
            link = cells[2].find("a")
            if link and doc_type:
                href = link["href"]
                # Strip iXBRL viewer prefix: /ix?doc=/Archives/...
                if "?doc=" in href:
                    href = href.split("?doc=", 1)[1]
                filename = href.split("/")[-1]
                documents.append({"type": doc_type, "filename": filename})
        return documents
    except Exception as exc:
        log.error("Failed to parse filing index HTML: %s", exc)
        return None

# ── Document extraction ───────────────────────────────────────────────────────

def find_exhibit_99(documents: list[dict]) -> Optional[str]:
    """Return filename of the first EX-99 document in the filing."""
    for doc in documents:
        dtype = doc.get("type", "").upper()
        if dtype.startswith("EX-99"):
            return doc.get("filename")
    return None


def fetch_and_clean(accession_number: str, filename: str) -> Optional[str]:
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{CIK_PLAIN}/{acc}/{filename}"
    resp = get(url)
    if not resp:
        return None

    content = resp.text
    content_type = resp.headers.get("Content-Type", "")

    # Parse HTML when present; fall back to treating content as plain text
    if "html" in content_type.lower() or content.lstrip().startswith("<"):
        soup = BeautifulSoup(content, "lxml")
        for tag in soup(["script", "style", "head", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    else:
        text = content

    # Normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    # Collapse runs of 3+ blank lines down to 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

# ── Quarter / year helpers ────────────────────────────────────────────────────

def period_to_quarter(report_date: str, form_type: str) -> tuple[int, str]:
    """Map a filing's period-of-report date to (year, 'QN')."""
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    if form_type == "10-K":
        return dt.year, "Q4"
    # 10-Q: derive quarter from fiscal period-end month
    if dt.month <= 3:
        return dt.year, "Q1"
    if dt.month <= 6:
        return dt.year, "Q2"
    return dt.year, "Q3"

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    LETTERS_DIR.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()

    log.info("Fetching PGR (CIK %s) submission history from SEC EDGAR…", PGR_CIK)
    submissions = fetch_submissions()

    recent    = submissions.get("filings", {}).get("recent", {})
    forms     = recent.get("form", [])
    acc_nums  = recent.get("accessionNumber", [])
    rep_dates = recent.get("reportDate", [])

    target_forms = {"10-Q", "10-K"}
    new_count = 0

    for form, acc, date in zip(forms, acc_nums, rep_dates):
        if form not in target_forms:
            continue
        if already_processed(ledger, acc):
            log.debug("Skipping already-processed filing %s (%s %s)", acc, form, date)
            continue
        if not date:
            log.warning("No reportDate for accession %s — skipping", acc)
            continue

        year, quarter = period_to_quarter(date, form)
        filing_id = f"PGR_{year}_{quarter}"
        log.info("Processing %s  %s  →  %s", form, date, filing_id)

        # Fetch the filing's document index
        documents = fetch_filing_documents(acc)
        if not documents:
            log.warning("Could not retrieve filing index for %s", acc)
            continue

        # Locate Exhibit 99
        ex99_filename = find_exhibit_99(documents)
        if not ex99_filename:
            log.info("No Exhibit 99 in %s — recording skip and continuing", acc)
            ledger["filings"].append({
                "id": filing_id,
                "year": year,
                "quarter": quarter,
                "form_type": form,
                "accession_number": acc,
                "report_date": date,
                "letter_file": None,
                "audio_file": None,
                "letter_scraped": False,
                "audio_generated": False,
                "audio_compressed": False,
                "processed_date": datetime.now(timezone.utc).isoformat(),
                "skip_reason": "no_exhibit_99",
            })
            save_ledger(ledger)
            continue

        # Download and clean the letter text
        text = fetch_and_clean(acc, ex99_filename)
        if not text:
            log.error("Failed to retrieve/clean letter for %s — will retry next run", filing_id)
            continue

        letter_filename = f"{filing_id}_Letter.txt"
        letter_path = LETTERS_DIR / letter_filename
        letter_path.write_text(text, encoding="utf-8")
        log.info("Saved %s  (%d chars)", letter_filename, len(text))

        audio_filename = f"{filing_id}_Letter.mp3"
        ledger["filings"].append({
            "id": filing_id,
            "year": year,
            "quarter": quarter,
            "form_type": form,
            "accession_number": acc,
            "report_date": date,
            "letter_file": f"data/letters/{letter_filename}",
            "audio_file": f"docs/audio/{audio_filename}",
            "letter_scraped": True,
            "audio_generated": False,
            "audio_compressed": False,
            "processed_date": datetime.now(timezone.utc).isoformat(),
        })
        save_ledger(ledger)
        new_count += 1

    log.info("Scraping complete. %d new letter(s) extracted.", new_count)


if __name__ == "__main__":
    main()
