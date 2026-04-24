#!/usr/bin/env python3
"""
generator.py — NotebookLM audio overview generator for PGR shareholder letters.

Iterates through letters in docs/ledger.json that have been scraped but not yet
converted to audio. For each, it uploads the letter text to Google NotebookLM,
triggers Audio Overview generation, waits for completion, and downloads the
resulting audio file to /data/audio_raw/.

Authentication in CI uses a pre-captured browser session stored as JSON:
  export NOTEBOOKLM_AUTH_JSON="$(cat ~/.notebooklm/profiles/default/storage_state.json)"
This avoids the need for interactive Google login in a headless runner.

Usage:
    python scripts/generator.py [--max-new N]

Environment variables (required):
    NOTEBOOKLM_AUTH_JSON — Full contents of the Playwright storage_state.json,
                           as a single JSON string (store as a GitHub Secret).

One-time local setup:
    1. pip install -r requirements.txt
    2. playwright install chromium
    3. notebooklm login          # opens a real browser for Google sign-in
    4. export NOTEBOOKLM_AUTH_JSON="$(cat ~/.notebooklm/profiles/default/storage_state.json)"

Notes:
    • NotebookLM generates audio asynchronously; each notebook can take 3–10 minutes.
    • The script processes letters sequentially and deletes each notebook after download.
    • Failed generations are logged but do not abort the batch; re-running picks them up.
    • Raw audio is downloaded as MP4 (AAC); compressor.py converts to 64 kbps MP3.
"""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).resolve().parent.parent
LETTERS_DIR    = BASE_DIR / "data" / "letters"
AUDIO_RAW_DIR  = BASE_DIR / "data" / "audio_raw"
LEDGER_PATH    = BASE_DIR / "docs" / "ledger.json"

# Pause between notebook submissions to respect NotebookLM's rate limits
INTER_REQUEST_DELAY = 10   # seconds

# How long to wait for audio generation (NotebookLM typically takes 3–8 minutes)
AUDIO_TIMEOUT   = 900      # seconds (15 minutes; generous to handle slow runs)
POLL_INTERVAL   = 15       # seconds between status checks

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Ledger helpers ────────────────────────────────────────────────────────────

def load_ledger() -> dict:
    with open(LEDGER_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def save_ledger(ledger: dict) -> None:
    ledger["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, default=str)


def pending_letters(ledger: dict) -> list[dict]:
    """Return filings that have a scraped letter but no generated audio yet."""
    return [
        f for f in ledger["filings"]
        if f.get("letter_scraped") and not f.get("audio_generated")
        and f.get("letter_file")
        and not f.get("skip_reason")
    ]

# ── NotebookLM audio generation ───────────────────────────────────────────────

async def generate_audio_for_letter(filing: dict) -> Optional[Path]:
    """
    Upload a letter to a new NotebookLM notebook, generate audio, download it.

    Returns the local Path of the downloaded raw audio file (.mp4) on success,
    or None on any failure. Deletes the notebook after downloading.

    Requires notebooklm-py and NOTEBOOKLM_AUTH_JSON to be set in the environment.
    """
    try:
        from notebooklm import NotebookLMClient  # type: ignore[import]
    except ImportError:
        log.error(
            "notebooklm-py is not installed. Run: pip install notebooklm-py && playwright install chromium"
        )
        return None

    letter_path = BASE_DIR / filing["letter_file"]
    if not letter_path.exists():
        log.error("Letter file not found: %s", letter_path)
        return None

    letter_text    = letter_path.read_text(encoding="utf-8")
    notebook_title = f"PGR {filing['year']} {filing['quarter']} — CEO Shareholder Letter"

    # Output filename uses .mp4 because NotebookLM downloads in MP4/AAC container;
    # compressor.py converts it to .mp3.
    raw_filename = f"{filing['id']}_Letter.mp4"
    raw_path     = AUDIO_RAW_DIR / raw_filename

    log.info("Starting NotebookLM session for %s…", filing["id"])
    notebook_id = None

    try:
        # NotebookLMClient.from_storage() reads NOTEBOOKLM_AUTH_JSON from env automatically
        client = await NotebookLMClient.from_storage()

        # Create a fresh notebook for this letter
        notebook_id = await client.notebooks.create(title=notebook_title)
        log.info("  Created notebook '%s' (id: %s)", notebook_title, notebook_id)

        # Add the letter text as the sole source (use add_text to avoid known
        # issues with add_file returning None for plain text uploads)
        await client.sources.add_text(
            notebook_id=notebook_id,
            title=notebook_title,
            content=letter_text,
        )
        log.info("  Uploaded letter text (%d chars)", len(letter_text))

        # Brief pause to let NotebookLM process the source before requesting audio
        await asyncio.sleep(3)

        # Request audio overview generation
        log.info("  Requesting Audio Overview (timeout: %ds)…", AUDIO_TIMEOUT)
        task_id = await client.artifacts.generate_audio(
            notebook_id=notebook_id,
            instructions=(
                "Create an engaging, podcast-style audio overview of this CEO shareholder "
                "letter. Explain the key business results, strategic priorities, and outlook "
                "in a conversational tone accessible to a general investor audience."
            ),
        )

        # Poll until the generation completes
        await client.artifacts.wait_for_completion(
            notebook_id=notebook_id,
            task_id=task_id,
            timeout=AUDIO_TIMEOUT,
            poll_interval=POLL_INTERVAL,
        )
        log.info("  Audio generation complete.")

        # Download the raw audio to data/audio_raw/
        await client.artifacts.download_audio(
            notebook_id=notebook_id,
            path=str(raw_path),
        )
        log.info("  Downloaded raw audio → %s", raw_path.name)

    except asyncio.TimeoutError:
        log.error("  Audio generation timed out after %ds for %s", AUDIO_TIMEOUT, filing["id"])
        return None
    except Exception as exc:
        log.error("  NotebookLM error for %s: %s — %s", filing["id"], type(exc).__name__, exc)
        return None
    finally:
        # Always clean up the notebook to avoid cluttering the Google account
        if notebook_id:
            try:
                await client.notebooks.delete(notebook_id)
                log.info("  Deleted notebook %s", notebook_id)
            except Exception as cleanup_exc:
                log.warning("  Failed to delete notebook %s: %s", notebook_id, cleanup_exc)

    return raw_path if raw_path.exists() else None

# ── Main ──────────────────────────────────────────────────────────────────────

async def main(max_new: int) -> None:
    AUDIO_RAW_DIR.mkdir(parents=True, exist_ok=True)

    auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON", "").strip()
    if not auth_json:
        log.error(
            "NOTEBOOKLM_AUTH_JSON is not set.\n"
            "Run 'notebooklm login' locally, then:\n"
            "  export NOTEBOOKLM_AUTH_JSON=\"$(cat ~/.notebooklm/profiles/default/storage_state.json)\""
        )
        raise SystemExit(1)

    ledger  = load_ledger()
    pending = pending_letters(ledger)

    if not pending:
        log.info("No letters pending audio generation.")
        return

    if max_new > 0:
        pending = pending[:max_new]

    log.info("%d letter(s) queued for audio generation (max-new=%d).", len(pending), max_new)
    success_count = 0

    for i, filing in enumerate(pending):
        log.info("[%d/%d] Generating audio for %s", i + 1, len(pending), filing["id"])

        raw_path = await generate_audio_for_letter(filing)

        if raw_path:
            # compressor.py expects .mp3 filenames in audio_file; store the raw .mp4 path
            # as a separate field so the compressor knows what to find in audio_raw/
            filing["audio_generated"]      = True
            filing["audio_raw_file"]       = f"data/audio_raw/{raw_path.name}"
            filing["audio_generated_date"] = datetime.now(timezone.utc).isoformat()
            save_ledger(ledger)
            success_count += 1
            log.info("  ✓  %s", filing["id"])
        else:
            log.warning("  ✗  %s — will retry on next run", filing["id"])

        if i < len(pending) - 1:
            log.info("  Waiting %ds before next submission…", INTER_REQUEST_DELAY)
            await asyncio.sleep(INTER_REQUEST_DELAY)

    log.info(
        "Audio generation complete. %d/%d succeeded.", success_count, len(pending)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate NotebookLM audio overviews for PGR letters.")
    parser.add_argument(
        "--max-new",
        type=int,
        default=1,
        help="Maximum number of new letters to process per run (default: 1; 0 = unlimited).",
    )
    args = parser.parse_args()
    asyncio.run(main(max_new=args.max_new))
