#!/usr/bin/env python3
"""
register_local_audio.py — One-time helper to register locally-generated MP4 files.

Scans data/audio_raw/ for .mp4 files, matches them against the ledger, and marks
those filings as audio_generated=True so compressor.py can process them.

Run this when NotebookLM generated audio locally but the ledger wasn't updated
(e.g. the script was interrupted before saving). Then run compressor.py.

Usage:
    python scripts/register_local_audio.py
    python scripts/compressor.py
    python scripts/build_pages.py
    python scripts/audio_progress.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR      = Path(__file__).resolve().parent.parent
AUDIO_RAW_DIR = BASE_DIR / "data" / "audio_raw"
LEDGER_PATH   = BASE_DIR / "docs" / "ledger.json"


def main() -> None:
    mp4_files = sorted(AUDIO_RAW_DIR.glob("*_Letter.mp4"))
    if not mp4_files:
        print(f"No .mp4 files found in {AUDIO_RAW_DIR}")
        print("Make sure the MP4 files are in data/audio_raw/ and try again.")
        return

    print(f"Found {len(mp4_files)} MP4 file(s):")
    for f in mp4_files:
        print(f"  {f.name}")

    with open(LEDGER_PATH, encoding="utf-8") as fh:
        ledger = json.load(fh)

    now     = datetime.now(timezone.utc).isoformat()
    updated = []

    for mp4 in mp4_files:
        # Filename pattern: PGR_YYYY_QN_Letter.mp4
        match = re.match(r"(PGR_\d{4}_\w+)_Letter\.mp4", mp4.name)
        if not match:
            print(f"  Skipping unrecognised filename: {mp4.name}")
            continue

        filing_id = match.group(1)
        filing = next((f for f in ledger["filings"] if f["id"] == filing_id), None)

        if filing is None:
            print(f"  {filing_id}: not found in ledger — skipping")
            continue

        if filing.get("audio_generated"):
            print(f"  {filing_id}: already marked audio_generated — skipping")
            continue

        filing["audio_generated"]      = True
        filing["audio_raw_file"]       = f"data/audio_raw/{mp4.name}"
        filing["audio_generated_date"] = now
        updated.append(filing_id)
        print(f"  {filing_id}: marked as audio_generated ✓")

    if not updated:
        print("Nothing to update.")
        return

    ledger["meta"]["last_updated"] = now
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, default=str)

    print(f"\nLedger updated for {len(updated)} filing(s): {', '.join(updated)}")
    print("\nNext steps:")
    print("  python scripts/compressor.py")
    print("  python scripts/build_pages.py")
    print("  python scripts/audio_progress.py")
    print("  git add docs/ledger.json docs/feed.xml docs/letters/ AUDIO_PROGRESS.md")
    print('  git commit -m "chore: add NotebookLM audio for ' + ", ".join(updated) + '"')
    print("  git push origin main")


if __name__ == "__main__":
    main()
