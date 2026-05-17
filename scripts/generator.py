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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_DIR        = Path(__file__).resolve().parent.parent
LETTERS_DIR     = BASE_DIR / "data" / "letters"
AUDIO_RAW_DIR   = BASE_DIR / "data" / "audio_raw"
SUMMARIES_DIR   = BASE_DIR / "data" / "summaries"
LEDGER_PATH     = BASE_DIR / "docs" / "ledger.json"

# ── NotebookLM context preamble ───────────────────────────────────────────────
# Prepended to every letter before upload. Gives the AI hosts background
# knowledge so they can speak fluently without stopping to define terms.
# This text is NOT meant to be read aloud or discussed directly — it is
# reference context only.

_CONTEXT_PREAMBLE = """\
=== BACKGROUND CONTEXT FOR HOSTS — NOT PART OF THE LETTER ===

ABOUT PROGRESSIVE CORPORATION
Progressive Corporation (ticker: PGR) is one of the largest auto insurers in the
United States, founded in 1937 and publicly traded since its 1971 IPO. The company
sells personal and commercial auto insurance through two channels: independent
insurance agents (the Agency channel) and directly to consumers online and by phone
(the Direct channel). Progressive is known for industry innovations including
24/7 claims service, real-time online quoting, and usage-based insurance pricing.
By the early 2020s it ranked as the #2 personal auto insurer in the U.S. by
premiums written. Its subsidiary ARX / ASI provides homeowners and property insurance.

ABOUT THESE LETTERS
Progressive's CEO writes a letter to shareholders with every quarterly (10-Q) and
annual (10-K) SEC filing. Quarterly letters began in Q1 2004; annual letters exist
back to the early 1990s. The letters are unusually candid and analytical by corporate
standards — the CEO discusses results honestly, including when targets are missed,
and explains the reasoning behind strategic decisions. Glenn Renwick served as CEO
and letter author from 2001 through mid-2016; Tricia Griffith has written the
letters from Q3 2016 onward.

PROGRESSIVE'S CORE FINANCIAL TARGET
Progressive's most important stated goal is to achieve a combined ratio (CR) at or
below 96 in every calendar year — equivalent to a 4% underwriting profit margin.
This target has been in place since the 1971 IPO and is treated as a cultural
constant, not a variable to optimize. A CR below 100 means underwriting is
profitable; below 96 meets the company's own standard.

ACRONYMS AND SHORTHAND — definitions for host context only, not for discussion:

Financial metrics:
  CR   — Combined Ratio: (losses + expenses) ÷ earned premiums. The primary
          insurance profitability gauge. Below 96 = meets Progressive's target.
          Below 100 = profitable. Above 100 = underwriting loss.
  NPW  — Net Premiums Written: total new and renewal premium committed in a period.
  NPE  — Net Premiums Earned: premium recognized as revenue (lags NPW by ~6 months).
  PIF  — Policies in Force: count of active insurance policies; the unit-growth metric.
  LAE  — Loss Adjustment Expense: cost to investigate and settle claims (inside CR).
  ROE  — Return on Equity.
  CAGR — Compound Annual Growth Rate.
  YOY  — Year-over-Year comparison.
  pts  — Percentage points (e.g., "CR improved 2 pts" = improved by 2 percentage points).

Insurance / industry terms:
  PIP  — Personal Injury Protection: mandatory no-fault medical coverage required
          in certain states; a frequent source of loss cost volatility.
  UBI  — Usage-Based Insurance: pricing based on actual driving behavior data
          collected via a telematics device or smartphone app.
  TNC  — Transportation Network Company: ride-share platforms such as Uber and Lyft.
  BOP  — Business Owners Policy: a bundled commercial property + liability product.
  NPS  — Net Promoter Score: customer loyalty metric based on likelihood to recommend.

Progressive-specific programs and terms:
  Snapshot    — Progressive's UBI telematics program; a plug-in device (later a
                smartphone app) that monitors driving behavior for 30 days and
                applies an individualized discount of 0–30% at renewal.
  Gainshare   — Progressive's internal annual performance score on a 0–2 scale,
                combining growth and profitability results. It determines the
                size of the annual variable dividend paid to shareholders and
                drives employee compensation. A score of 1.0 is baseline; 2.0
                is exceptional.
  Robinson    — Progressive's internal term for a customer who holds both an
                auto policy and a home/renters policy with Progressive (a
                bundled "home + auto" household). Growing the Robinson
                segment is a long-running strategic priority.
  Flo         — Progressive's fictional advertising spokesperson, introduced in
                2008. She works in a stylized insurance "Superstore" and became
                one of the most recognized ad characters in the U.S.
  Platinum    — Progressive's integrated Agency-channel bundle: a single policy
                combining Progressive auto and ASI home coverage, with unified
                billing and policy periods. Launched in select markets ~2015.
  HQX         — HomeQuote Explorer: Progressive's online tool that lets customers
                compare home insurance quotes from multiple carriers alongside
                their Progressive auto quote.
  ASI / ARX   — American Strategic Insurance (ASI) is Progressive's property
                insurance subsidiary, acquired in stages. ARX Holding is the
                parent entity. Progressive acquired a non-controlling stake in
                2012, controlling interest in April 2015, and 100% in April 2020.
  Name Your Price — A quoting tool that lets consumers enter a desired monthly
                budget and see coverage options that fit, rather than starting
                from a coverage selection.

Distribution and business segments:
  Agency / Agent channel — policies sold through independent insurance agents.
  Direct channel         — policies sold by Progressive directly to consumers
                           online, by phone, or via app; no agent involved.
  Personal Lines (PL)    — consumer insurance: auto, motorcycle, RV, boat,
                           snowmobile, and property.
  Commercial Lines (CL)  — commercial auto insurance for fleets, trucks,
                           owner-operators, and business vehicles.
  Special Lines           — Progressive's non-auto consumer segment: motorcycle,
                           boat, RV, and snowmobile insurance.

=== END OF BACKGROUND CONTEXT — THE SHAREHOLDER LETTER FOLLOWS ===

"""

# Pause between notebook submissions to respect NotebookLM's rate limits
INTER_REQUEST_DELAY = 10   # seconds

# How long to wait for audio generation (NotebookLM typically takes 3–8 minutes)
AUDIO_TIMEOUT   = 900      # seconds (15 minutes; covers slow/long letters)
POLL_INTERVAL   = 15       # seconds between status checks

# NotebookLM free-tier audio generation quota (~3 per day per account as of 2026).
# When the quota is exhausted, generate_audio() submits successfully but
# wait_for_completion() never sees a completed status and eventually times out.
# After this many consecutive failures (timeout OR exception), abort the batch
# early and tell the user to wait ~24 hours for the quota to reset.
CONSECUTIVE_FAIL_ABORT = 2

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


def pending_letters(ledger: dict, filing_id: str | None = None) -> list[dict]:
    """Return filings that have a scraped letter but no generated audio yet."""
    if filing_id:
        matches = [f for f in ledger["filings"] if f["id"] == filing_id]
        if not matches:
            log.error("Filing ID not found in ledger: %s", filing_id)
        return matches
    return [
        f for f in ledger["filings"]
        if f.get("letter_scraped") and not f.get("audio_generated")
        and f.get("letter_file")
        and not f.get("skip_reason")
    ]

# ── Summary helpers ───────────────────────────────────────────────────────────

def load_summary_text(filing_id: str) -> Optional[str]:
    """
    Return a formatted text version of the analyst summary for a filing, or None
    if no summary file exists yet. The text is uploaded as a second NotebookLM
    source so the hosts can focus on the highest-priority metrics.
    """
    summary_path = SUMMARIES_DIR / f"{filing_id}_Summary.json"
    if not summary_path.exists():
        return None
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    bullets = data.get("bullets", [])
    if not bullets:
        return None

    lines = [
        "=== KEY METRICS BRIEFING — USE THIS TO GUIDE THE DISCUSSION ===",
        "",
        "The following points are ranked by importance. Prioritize these topics",
        "and make sure they are covered in the audio overview.",
        "",
    ]
    for i, b in enumerate(bullets, 1):
        lines.append(f"{i}. [{b['topic']}]")
        lines.append(f"   {b['text']}")
        lines.append("")
    lines.append("=== END OF KEY METRICS BRIEFING ===")
    return "\n".join(lines)


# ── NotebookLM audio generation ───────────────────────────────────────────────

_QUOTA_KEYWORDS = ("rpc create_artifact", "generation_failed", "quota", "rate limit", "rate_limit")


def _looks_like_quota_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(kw in msg for kw in _QUOTA_KEYWORDS)


async def generate_audio_for_letter(filing: dict) -> tuple[Optional[Path], bool]:
    """
    Upload a letter to a new NotebookLM notebook, generate audio, download it.

    Returns (path, quota_failure):
      • path  — local Path of the downloaded .mp4 on success, or None on failure
      • quota_failure — True when the failure looks like a daily-quota exhaustion
                        (caller should abort the batch rather than retrying)
    """
    try:
        from notebooklm import NotebookLMClient  # type: ignore[import]
    except ImportError:
        log.error(
            "notebooklm-py is not installed. Run: pip install notebooklm-py && playwright install chromium"
        )
        return None, False

    letter_path = BASE_DIR / filing["letter_file"]
    if not letter_path.exists():
        log.error("Letter file not found: %s", letter_path)
        return None, False

    letter_text    = _CONTEXT_PREAMBLE + letter_path.read_text(encoding="utf-8")
    notebook_title = f"PGR {filing['year']} {filing['quarter']} — CEO Shareholder Letter"

    # Output filename uses .mp4 because NotebookLM downloads in MP4/AAC container;
    # compressor.py converts it to .mp3.
    raw_filename = f"{filing['id']}_Letter.mp4"
    raw_path     = AUDIO_RAW_DIR / raw_filename

    log.info("Starting NotebookLM session for %s…", filing["id"])
    t_start = time.monotonic()

    try:
        async with await NotebookLMClient.from_storage() as client:
            # Create a fresh notebook for this letter
            notebook = await client.notebooks.create(title=notebook_title)
            log.info("  Created notebook '%s' (id: %s)", notebook_title, notebook.id)

            try:
                # Add the letter text; wait=True ensures processing is done before audio request
                await client.sources.add_text(
                    notebook_id=notebook.id,
                    title=notebook_title,
                    content=letter_text,
                    wait=True,
                )
                log.info("  Uploaded letter text (%d chars)", len(letter_text))

                # Add the analyst summary as a second source if available so the
                # hosts have ranked key metrics to anchor the discussion around.
                summary_text = load_summary_text(filing["id"])
                if summary_text:
                    await client.sources.add_text(
                        notebook_id=notebook.id,
                        title=f"Key Metrics Briefing — {filing['id']}",
                        content=summary_text,
                        wait=True,
                    )
                    log.info("  Uploaded key metrics briefing (%d chars)", len(summary_text))
                else:
                    log.info("  No summary found for %s — skipping briefing doc", filing["id"])

                # Request audio overview generation
                log.info("  Requesting Audio Overview (timeout: %ds)…", AUDIO_TIMEOUT)
                status = await client.artifacts.generate_audio(
                    notebook_id=notebook.id,
                    instructions=(
                        "Create an engaging, podcast-style audio overview of this CEO shareholder "
                        "letter for an audience of Progressive employees who know the company deeply — "
                        "skip introductions to who Progressive is, what insurance is, or what standard "
                        "metrics like combined ratio mean. Dive straight into what this specific letter "
                        "says: the results, the reasoning, the strategic priorities, and any candid "
                        "admissions or forward-looking signals. Treat the listener as a colleague who "
                        "just wants the substance of what was said and why it matters."
                    ),
                )

                # Poll until generation completes
                final_status = await client.artifacts.wait_for_completion(
                    notebook_id=notebook.id,
                    task_id=status.task_id,
                    timeout=AUDIO_TIMEOUT,
                )

                if final_status.is_failed:
                    elapsed = time.monotonic() - t_start
                    is_quota = _looks_like_quota_error(
                        Exception(getattr(final_status, "error", "") or "")
                    )
                    log.error("  Audio generation failed (%.0fs): %s", elapsed, final_status.error)
                    return None, is_quota

                log.info("  Audio generation complete (%.0fs).", time.monotonic() - t_start)

                # Download the raw audio to data/audio_raw/
                await client.artifacts.download_audio(
                    notebook_id=notebook.id,
                    output_path=str(raw_path),
                )
                log.info("  Downloaded raw audio → %s", raw_path.name)

            finally:
                # Always delete the notebook to keep the Google account clean
                try:
                    await client.notebooks.delete(notebook.id)
                    log.info("  Deleted notebook %s", notebook.id)
                except Exception as cleanup_exc:
                    log.warning("  Failed to delete notebook %s: %s", notebook.id, cleanup_exc)

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t_start
        log.error("  Audio generation timed out after %.0fs for %s", elapsed, filing["id"])
        # A timeout on every letter is a strong signal that today's quota is exhausted.
        return None, True
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        is_quota = _looks_like_quota_error(exc)
        log.error(
            "  NotebookLM error for %s (%.0fs): %s — %s",
            filing["id"], elapsed, type(exc).__name__, exc,
        )
        return None, is_quota

    return (raw_path if raw_path.exists() else None), False

# ── Main ──────────────────────────────────────────────────────────────────────

async def main(max_new: int, filing_id: str | None = None) -> None:
    AUDIO_RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Auth resolution (mirrors notebooklm-py's own precedence):
    #   1. NOTEBOOKLM_AUTH_JSON env var — inline JSON string (used in CI/GitHub Actions)
    #   2. NOTEBOOKLM_AUTH_FILE env var — path to storage_state.json (Windows-friendly)
    #   3. ~/.notebooklm/storage_state.json — written automatically by `notebooklm login`
    #
    # For local runs after `notebooklm login`, option 3 works with no env vars at all.
    # For GitHub Actions, set NOTEBOOKLM_AUTH_JSON as a repository secret.

    auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON", "").strip()
    auth_file = os.environ.get("NOTEBOOKLM_AUTH_FILE", "").strip()
    default_storage = Path.home() / ".notebooklm" / "storage_state.json"

    if not auth_json and auth_file:
        try:
            auth_json = Path(auth_file).read_text(encoding="utf-8").strip()
            os.environ["NOTEBOOKLM_AUTH_JSON"] = auth_json
            log.info("Loaded auth from NOTEBOOKLM_AUTH_FILE: %s", auth_file)
        except OSError as exc:
            log.error("Could not read NOTEBOOKLM_AUTH_FILE %s: %s", auth_file, exc)
            raise SystemExit(1)

    if not auth_json and default_storage.exists():
        # Let notebooklm-py read the file directly — no env var needed.
        log.info("Using auth from %s", default_storage)
    elif not auth_json:
        log.error(
            "No NotebookLM auth found. Options:\n"
            "  Local:  run 'notebooklm login' (writes ~/.notebooklm/storage_state.json)\n"
            "  CI:     set NOTEBOOKLM_AUTH_JSON repository secret\n"
            "  Windows workaround: set NOTEBOOKLM_AUTH_FILE=%%USERPROFILE%%\\.notebooklm\\storage_state.json"
        )
        raise SystemExit(1)

    ledger  = load_ledger()
    pending = pending_letters(ledger, filing_id)

    if not pending:
        log.info("No letters pending audio generation.")
        return

    if max_new > 0 and not filing_id:
        pending = pending[:max_new]

    log.info("%d letter(s) queued for audio generation (max-new=%d).", len(pending), max_new)
    success_count       = 0
    consecutive_failures = 0

    for i, filing in enumerate(pending):
        log.info("[%d/%d] Generating audio for %s", i + 1, len(pending), filing["id"])

        raw_path, quota_failure = await generate_audio_for_letter(filing)

        if raw_path:
            # compressor.py expects .mp3 filenames in audio_file; store the raw .mp4 path
            # as a separate field so the compressor knows what to find in audio_raw/
            filing["audio_generated"]      = True
            filing["audio_raw_file"]       = f"data/audio_raw/{raw_path.name}"
            filing["audio_generated_date"] = datetime.now(timezone.utc).isoformat()
            # v1.1 = letter + summary source; v1.0 = letter only (no summary available)
            summary_exists = (SUMMARIES_DIR / f"{filing['id']}_Summary.json").exists()
            filing["audio_version"]        = "1.1" if summary_exists else "1.0"
            save_ledger(ledger)
            success_count       += 1
            consecutive_failures = 0
            log.info("  ✓  %s", filing["id"])
        else:
            log.warning("  ✗  %s — will retry on next run", filing["id"])
            consecutive_failures += 1

            # Circuit breaker: stop the batch early when every attempt is failing.
            # The most common cause is the free-tier daily quota (~3 audio overviews/day).
            if consecutive_failures >= CONSECUTIVE_FAIL_ABORT or quota_failure:
                log.error(
                    "\n"
                    "  ┌─ Batch aborted after %d consecutive failure(s) ────────────────────┐\n"
                    "  │  NotebookLM is rejecting audio generation requests.                │\n"
                    "  │  Most likely cause: free-tier quota (~3 overviews/day) exhausted.  │\n"
                    "  │                                                                    │\n"
                    "  │  What to do:                                                       │\n"
                    "  │    1. Wait ~24 hours for the daily quota to reset.                 │\n"
                    "  │    2. Re-run:  python scripts/generator.py --max-new 3             │\n"
                    "  │    3. Repeat daily until the backlog is cleared.                   │\n"
                    "  └────────────────────────────────────────────────────────────────────┘",
                    consecutive_failures,
                )
                break

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
        help=(
            "Maximum number of new letters to process per run (default: 1; 0 = unlimited). "
            "NotebookLM free tier allows ~3 audio overviews per day — keep this at 3 or below "
            "to avoid hitting the daily quota."
        ),
    )
    parser.add_argument(
        "--id", dest="filing_id", metavar="FILING_ID",
        help="Process a specific filing by ID (e.g. PGR_2025_Q4). Overrides --max-new.",
    )
    args = parser.parse_args()
    asyncio.run(main(max_new=args.max_new, filing_id=args.filing_id))
