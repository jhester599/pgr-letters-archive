#!/usr/bin/env python3
"""
summarizer.py — Generate 10-bullet summaries for each PGR shareholder letter.

Uses the GitHub Models API (OpenAI-compatible endpoint) so no separate API account
is required — GitHub Actions already provides GITHUB_TOKEN automatically.

For each filing in the ledger where letter_scraped=True and summary_generated=False,
this script:
  1. Reads the letter text from data/letters/.
  2. Calls GitHub Models to generate a ranked JSON summary (up to 10 bullets).
  3. Saves the summary to data/summaries/{id}_Summary.json.
  4. Updates the ledger: summary_generated=True, page_built=False (triggers HTML rebuild).

Usage:
    python scripts/summarizer.py              # process only new/missing summaries
    python scripts/summarizer.py --rebuild    # regenerate all summaries

Environment variables:
    GITHUB_TOKEN  — GitHub token used to authenticate with GitHub Models.
                    In GitHub Actions this is provided automatically via
                    secrets.GITHUB_TOKEN. For local use, create a free
                    GitHub personal access token at:
                    https://github.com/settings/tokens
                    (no special scopes required for public models)
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

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR

SUMMARIES_DIR = BASE_DIR / "data" / "summaries"

GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com"
GITHUB_MODELS_MODEL    = "gpt-4o"        # free via GitHub Models; better style adherence than mini

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an expert financial analyst generating concise, data-dense bullet-point "
    "summaries of Progressive Corporation (PGR) quarterly and annual shareholder letters "
    "for a long-run archival reference system. "
    "Your summaries are read by investors who want the fastest possible orientation to "
    "each letter before reading the full text. "
    "Output ONLY valid JSON — no markdown, no prose, no code fences."
)

_USER_PROMPT_TEMPLATE = """\
Summarize the following PGR shareholder letter ({filing_id}) as exactly 10 ranked bullet \
points (fewer only if the letter is very short or covers fewer than 10 distinct topics).

TOPIC CATEGORIES — choose from these only, using the exact label shown:
 1. Profitability & Underwriting Performance  (combined ratio, underwriting margin, net income, ROE)
 2. Premium Growth                            (NPW / net premiums written, YOY growth rate)
 3. Policies in Force & Customer Growth       (PIF counts, retention, new applications)
 4. Loss Costs & Severity Trends             (frequency, severity, reserve development)
 5. Rate Adequacy & Pricing Strategy
 6. Capital Management & Financial Position  (investments, leverage, dividends, buybacks)
 7. Operating Efficiency & Expense Ratio
 8. Technology & Digital Transformation
 9. Product Innovation & Expansion
10. Brand Building & Marketing Strategy
11. Distribution Channel Strategy
12. Competitive Position & Market Share
13. Employee Engagement & Culture
14. Industry Cycle & Market Conditions
15. Catastrophe Response & Disaster Management
16. Financial Crisis & Macro Volatility Response
17. Strategic Vision & Company Philosophy

RANKING RULES:
- Bullet 1 is the single most important / most-space-devoted topic in this letter.
- Topics 1–7 are core; include them whenever substantively discussed.
- Topics 8–17 float — include only when meaningfully covered; skip if barely mentioned.
- Never pad with a topic that gets only one passing sentence in the letter.

STYLE RULES (critical — match this style exactly):
- Each bullet: 20–35 words. Hard limit. Count carefully.
- Pack metrics densely using semicolons and em-dashes:
    "CR 94.1; NPW +8% to $16B; net income $902M ($1.48/share); ROE 17.4%."
- Use abbreviations freely: CR, NPW, PIF, YOY, ROE, LAE, UBI, CL, PL, pts.
- Lead with the most specific number available; omit generic filler phrases like
  "the letter discusses" or "management highlighted."
- Do not quote the letter. Synthesize and compress.

FEW-SHOT EXAMPLE (PGR_2024_Q4 annual letter):
[
  {{"topic": "Profitability & Underwriting Performance",
    "text": "Full-year CR 88.8 — best in company history; PL CR 88.6; CL CR 89.4; property CR 98.3 despite elevated cats; personal auto drove outsized underwriting profit."}},
  {{"topic": "Premium Growth",
    "text": "Companywide NPW grew 21% YOY to $74B; PL NPW +23%; personal auto PIF +22% — highest organic growth rate in company history."}},
  {{"topic": "Policies in Force & Customer Growth",
    "text": "Total PIFs grew 18% YOY, adding 5M+ new policyholders in 2024; personal auto PIF growth of 22% — strongest PIF expansion ever recorded."}},
  {{"topic": "Capital Management & Financial Position",
    "text": "$4.50/share annual-variable dividend declared; $500M preferred redeemed; debt-to-capital 21.2%; portfolio returned 4.6% (equity 22.9%, fixed income 3.0%)."}},
  {{"topic": "Brand Building & Marketing Strategy",
    "text": "Advertising spend up ~150% YOY as Progressive leaned into strong unit economics to fuel growth; brand investment was the primary strategic lever in 2024."}},
  {{"topic": "Loss Costs & Severity Trends",
    "text": "Sustained lower personal auto frequency drove profitability; catastrophe activity elevated but manageable; property CR 98.3 reflects cat weather pressure."}},
  {{"topic": "Operating Efficiency & Expense Ratio",
    "text": "PL vehicle non-acquisition expense ratio improved 0.4 pts YOY; LAE ratio down 0.5 pts from lower frequency, higher average premiums, and technology gains."}},
  {{"topic": "Employee Engagement & Culture",
    "text": "Gallup Exceptional Workplace designation for 4th consecutive year; culture cited as key differentiator enabling historic simultaneous growth and profitability."}},
  {{"topic": "Industry Cycle & Market Conditions",
    "text": "Personal auto industry broadly reached rate adequacy in 2024; Progressive's early return to profit in 2023 gave it a meaningful head start on growth."}},
  {{"topic": "Product Innovation & Expansion",
    "text": "Pricing model 8.9 rollout continued; AutoQuote Explorer and Progressive Vehicle Protection expanded; Snapshot telematics program growing alongside new commercial products."}}
]

OUTPUT FORMAT — return ONLY a JSON array in exactly the same structure, nothing else.

LETTER TEXT:
{letter_text}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────


def _summary_path(filing_id: str) -> Path:
    return SUMMARIES_DIR / f"{filing_id}_Summary.json"


def generate_summary(client: OpenAI, filing: dict, letter_text: str) -> list[dict]:
    """Call GitHub Models and return a list of {topic, text} bullet dicts."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        filing_id=filing["id"],
        letter_text=letter_text[:30_000],  # cap at ~30k chars; no letter is longer
    )
    response = client.chat.completions.create(
        model=GITHUB_MODELS_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=1500,
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()
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
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log.error(
            "GITHUB_TOKEN environment variable is not set.\n"
            "  • In GitHub Actions this is provided automatically.\n"
            "  • Locally: create a free PAT at https://github.com/settings/tokens\n"
            "    and set: $env:GITHUB_TOKEN = 'github_pat_...'"
        )
        sys.exit(1)

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(base_url=GITHUB_MODELS_ENDPOINT, api_key=token)
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

        time.sleep(0.3)   # polite pause to stay within rate limits

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
