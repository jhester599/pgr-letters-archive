#!/usr/bin/env python3
"""
summarizer.py — Generate 10-bullet summaries for each PGR shareholder letter using Claude API.

For each filing in the ledger where letter_scraped=True and summary_generated=False,
this script:
  1. Reads the letter text from data/letters/.
  2. Calls the Claude API to generate a ranked JSON summary (up to 10 bullets).
  3. Saves the summary to data/summaries/{id}_Summary.json.
  4. Updates the ledger: summary_generated=True, page_built=False (triggers HTML rebuild).

Usage:
    python scripts/summarizer.py              # process only new/missing summaries
    python scripts/summarizer.py --rebuild    # regenerate all summaries

Environment variables:
    ANTHROPIC_API_KEY  — Claude API key (required)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR

SUMMARIES_DIR = BASE_DIR / "data" / "summaries"

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You generate concise, ranked bullet-point summaries of Progressive Corporation (PGR) "
    "shareholder letters for an archival reference system. "
    "Output ONLY valid JSON — no markdown, no prose, no code fences."
)

_USER_PROMPT_TEMPLATE = """\
Summarize the following PGR shareholder letter ({filing_id}) in up to 10 ranked bullet \
points. Select the most relevant topics from the list below, rank them by importance in \
this specific letter, and include specific numbers and metrics where the letter provides \
them. Keep each bullet to 20–35 words. Do not quote the letter directly.

TOPIC CATEGORIES (choose from these only):
 1. Profitability & Underwriting Performance (combined ratio, underwriting margin, ROE)
 2. Premium Growth (net premiums written / NPW growth)
 3. Policies in Force & Customer Growth (PIF growth, retention, new applications)
 4. Rate Adequacy & Pricing Strategy
 5. Loss Costs & Severity Trends (frequency, severity, reserve adequacy)
 6. Operating Efficiency & Expense Ratio
 7. Capital Management & Financial Position (leverage, surplus, investments, share repurchases)
 8. Distribution Channel Strategy
 9. Claims Service & Innovation
10. Technology & Digital Transformation
11. Competitive Position & Market Share
12. Product Innovation & Expansion
13. Brand Building & Marketing Strategy
14. Catastrophe Response & Disaster Management
15. Industry Cycle & Market Conditions
16. Financial Crisis & Macro Volatility Response
17. Strategic Vision & Company Philosophy

RULES:
- Rank bullets from most to least important/prominent in this letter.
- Topics 1–7 are core and likely present in most letters; topics 8–17 appear only when
  meaningfully discussed.
- Include specific metrics (percentages, dollar figures, ratios) whenever available.
- Omit any topic not substantively covered in the letter.
- Return fewer than 10 bullets if warranted.

OUTPUT FORMAT — return ONLY a JSON array, nothing else:
[
  {{"topic": "Topic Name", "text": "Tight summary with numbers."}},
  ...
]

LETTER TEXT:
{letter_text}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────


def _summary_path(filing_id: str) -> Path:
    return SUMMARIES_DIR / f"{filing_id}_Summary.json"


def generate_summary(
    client: anthropic.Anthropic,
    filing: dict,
    letter_text: str,
) -> list[dict]:
    """Call Claude API and return a list of {topic, text} bullet dicts."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        filing_id=filing["id"],
        letter_text=letter_text[:30_000],  # cap at ~30k chars; no letter is longer
    )
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if the model adds them despite instructions.
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    bullets = json.loads(raw)
    if not isinstance(bullets, list):
        raise ValueError(f"Expected JSON array, got {type(bullets).__name__}")
    return bullets


def save_summary(filing: dict, bullets: list[dict]) -> None:
    data = {
        "id":             filing["id"],
        "year":           filing["year"],
        "quarter":        filing["quarter"],
        "generated_date": datetime.now(timezone.utc).isoformat(),
        "bullets":        bullets,
    }
    path = _summary_path(filing["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

# ── Main ──────────────────────────────────────────────────────────────────────


def main(rebuild: bool = False) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=api_key)
    ledger = load_ledger()

    candidates = [
        f for f in ledger["filings"]
        if f.get("letter_scraped") and f.get("letter_file")
        and (rebuild or not f.get("summary_generated"))
    ]

    if not candidates:
        log.info("All letters already summarized — nothing to do.")
        return

    log.info("%d letter(s) to summarize.", len(candidates))
    success = 0

    for filing in candidates:
        letter_path = BASE_DIR / filing["letter_file"]
        if not letter_path.exists():
            log.warning(
                "Letter file not found: %s — skipping %s", letter_path, filing["id"]
            )
            continue

        letter_text = letter_path.read_text(encoding="utf-8")
        log.info("Summarizing %s…", filing["id"])

        try:
            bullets = generate_summary(client, filing, letter_text)
        except Exception as exc:
            log.error("  Failed: %s", exc)
            continue

        save_summary(filing, bullets)
        filing["summary_generated"] = True
        filing["page_built"] = False   # force HTML rebuild to include new summary
        save_ledger(ledger)
        success += 1
        log.info("  → %d bullets saved to %s_Summary.json", len(bullets), filing["id"])

        time.sleep(0.5)   # polite pause to stay within API rate limits

    log.info("Done. %d/%d summaries generated.", success, len(candidates))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate bullet-point summaries for PGR shareholder letters."
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate summaries for all letters, not just new/missing ones.",
    )
    args = parser.parse_args()
    main(rebuild=args.rebuild)
