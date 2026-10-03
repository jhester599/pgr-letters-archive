#!/usr/bin/env python3
"""
summarizer.py — Generate 10-bullet summaries for each PGR shareholder letter.

Uses the Gemini API's free tier through its OpenAI-compatible endpoint, so the
existing `openai` client is the only dependency. (GitHub Models was used until
mid-2026; it stopped working for this pipeline — see NEXT_STEPS.md.)

For each filing in the ledger where letter_scraped=True and summary_generated=False,
this script:
  1. Reads the letter text from data/letters/.
  2. Calls Gemini to generate a ranked JSON summary (up to 10 bullets).
  3. Saves the summary to data/summaries/{id}_Summary.json.
  4. Updates the ledger: summary_generated=True, page_built=False (triggers HTML rebuild).

Usage:
    python scripts/summarizer.py              # process only new/missing summaries
    python scripts/summarizer.py --rebuild    # regenerate all summaries
    python scripts/summarizer.py --id PGR_2026_Q1 --dry-run
                                              # print one summary; write nothing

Environment variables:
    GEMINI_API_KEY — Gemini API key from Google AI Studio
                     (https://aistudio.google.com/apikey). Create it in a Google
                     Cloud project with no billing account linked so it stays on
                     the free tier: over-quota requests are then rejected rather
                     than billed. In Actions it comes from the GEMINI_API_KEY
                     repository secret.
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
from letter_text import clean_letter_text

SUMMARIES_DIR = BASE_DIR / "data" / "summaries"

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL    = "gemini-3.8-flash"   # on the Gemini API free tier
# Gemini 3 always thinks, and thinking tokens come out of the output budget; keep
# the effort low and leave headroom so the JSON is never truncated.
GEMINI_REASONING_EFFORT = "low"
MAX_OUTPUT_TOKENS       = 8000
# Free-tier requests-per-minute limits are low; this pause only matters for
# --rebuild over the whole archive (a routine run summarizes one letter).
REQUEST_PAUSE_SECONDS   = 7

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

FACTUAL RULES (critical — the summary is read as a record of what the letter says):
- Use only facts and figures stated in this letter. Do not add outside knowledge,
  industry context, or initiatives the letter does not mention.
- Do not attribute a cause, driver or motive the letter does not give. If the
  letter reports a change without a reason, report the change alone.
- Do not add superlatives ("record", "best ever", "historic") unless the letter
  uses them, and keep the letter's own hedges ("may have been", "approximately").
- Do not merge separate statements into a claim the letter does not make.

FEW-SHOT EXAMPLE (PGR_2024_Q4 annual letter):
[
  {{"topic": "Profitability & Underwriting Performance",
    "text": "Full-year CR 88.8 — possibly one of the best years in company history; PL CR 88.6; CL CR 89.4; property CR 98.3, profitable but short of its target margin."}},
  {{"topic": "Premium Growth",
    "text": "Companywide NPW +21% YOY to $74B, from an 18% PIF increase and higher average written premiums; PL NPW +23%; CL NPW +8%, influenced by the macroeconomic environment."}},
  {{"topic": "Policies in Force & Customer Growth",
    "text": "Added 5M+ PIFs in 2024 (+18% YOY); personal auto PIFs +22% led growth; claims and call-center staff hired well in advance of need to support it."}},
  {{"topic": "Capital Management & Financial Position",
    "text": "$4.50/share annual-variable dividend; $500M preferred shares redeemed; debt-to-capital 21.2%, near the low end of its historical range; portfolio returned 4.6% (fixed income 3.8%, equity 22.9%)."}},
  {{"topic": "Brand Building & Marketing Strategy",
    "text": "Companywide media spend up 150% YOY to drive growth; #2 U.S. personal auto insurer for a third straight year; Superstore and Dr. Rick continued; new NFL 'Back Up' campaign launched."}},
  {{"topic": "Operating Efficiency & Expense Ratio",
    "text": "PL vehicle NAER -0.4 pts and LAE ratio -0.5 pts in 2024 (-2.8 and -2.1 pts over a decade); PL expense ratio +3.0 pts, mainly from higher advertising."}},
  {{"topic": "Rate Adequacy & Pricing Strategy",
    "text": "Adequate rates in most markets let 2023 underwriting restrictions be rolled back to fuel growth; nearly 40% of personal auto premium on the latest product model; next model mid-2025."}},
  {{"topic": "Employee Engagement & Culture",
    "text": "Gallup Exceptional Workplace for a fourth consecutive year; ERG event attendance rose to 26% of employees from 19%; pay equity maintained; nearly $10M in employee disaster relief."}},
  {{"topic": "Product Innovation & Expansion",
    "text": "BOP available in 46 states (~80% of the commercial multi-peril market); HomeQuote Explorer offers online homeowners purchase in 46 states plus DC, with eight partner carriers integrated."}},
  {{"topic": "Strategic Vision & Company Philosophy",
    "text": "Annual theme of empathy frames the letter; customer and employee stories illustrate claims care, and customer obsession is named the core focus going forward."}}
]

OUTPUT FORMAT — return ONLY a JSON array in exactly the same structure, nothing else.

LETTER TEXT:
{letter_text}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────


def _summary_path(filing_id: str) -> Path:
    return SUMMARIES_DIR / f"{filing_id}_Summary.json"


def parse_bullets(raw: str) -> list[dict]:
    """Parse and validate the model's reply into a list of {topic, text} dicts.

    Raises ValueError on anything that is not a summary, so a service that
    answers with something else fails loudly instead of being saved.
    """
    raw = raw.strip()
    # Strip markdown code fences if the model adds them despite instructions.
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        bullets = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reply is not JSON: {raw[:120]!r}") from exc
    if not isinstance(bullets, list) or not bullets:
        raise ValueError(f"Expected a non-empty JSON array, got {type(bullets).__name__}")
    if len(bullets) > 10:
        raise ValueError(f"Expected at most 10 bullets, got {len(bullets)}")
    for item in bullets:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("topic"), str) and item["topic"].strip()
            and isinstance(item.get("text"), str) and item["text"].strip()
        ):
            raise ValueError(f"Malformed bullet: {item!r}")
    return [{"topic": b["topic"].strip(), "text": b["text"].strip()} for b in bullets]


def generate_summary(client: OpenAI, filing: dict, letter_text: str) -> list[dict]:
    """Call Gemini and return a list of {topic, text} bullet dicts."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        filing_id=filing["id"],
        letter_text=letter_text[:30_000],  # cap at ~30k chars; no letter is longer
    )
    response = client.chat.completions.create(
        model=GEMINI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        reasoning_effort=GEMINI_REASONING_EFFORT,
    )
    # A proxy or retired endpoint can answer 200 with a bare string (GitHub
    # Models did in 2026), which the client returns as-is.
    choices = getattr(response, "choices", None)
    if not choices:
        raise ValueError(f"Not a chat completion: {str(response)[:120]!r}")
    choice = choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ValueError("Reply was cut off at the output token limit")
    return parse_bullets(choice.message.content or "")


def save_summary(filing: dict, bullets: list[dict]) -> None:
    data = {
        "id":             filing["id"],
        "year":           filing["year"],
        "quarter":        filing["quarter"],
        "generated_date": datetime.now(timezone.utc).isoformat(),
        "generated_by":   f"{GEMINI_MODEL} (Gemini API)",
        "bullets":        bullets,
    }
    path = _summary_path(filing["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

# ── Main ──────────────────────────────────────────────────────────────────────


def _warn(title: str, message: str) -> None:
    """Log a warning and surface it as an annotation on the Actions run."""
    log.warning(message)
    print(f"::warning title={title}::{message}")


def main(rebuild: bool = False, filing_id: str | None = None, dry_run: bool = False) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Not fatal: letters, pages and the feed must still publish.
        _warn(
            "Summaries skipped",
            "GEMINI_API_KEY is not set, so no summaries were generated. Create a "
            "free-tier key at https://aistudio.google.com/apikey and add it as the "
            "GEMINI_API_KEY repository secret.",
        )
        return

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(base_url=GEMINI_ENDPOINT, api_key=api_key)
    ledger = load_ledger()

    candidates = [
        f for f in ledger["filings"]
        if f.get("letter_scraped") and f.get("letter_file")
        and (
            f["id"] == filing_id if filing_id
            else rebuild or not f.get("summary_generated")
        )
    ]
    if filing_id and not candidates:
        log.error("No scraped letter with id %s in the ledger.", filing_id)
        sys.exit(1)

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

        letter_text = clean_letter_text(letter_path.read_text(encoding="utf-8"))
        log.info("Summarizing %s…", filing["id"])

        try:
            bullets = generate_summary(client, filing, letter_text)
        except Exception as exc:
            log.error("  Failed to summarize %s: %s", filing["id"], exc, exc_info=True)
            continue

        if dry_run:
            print(json.dumps(bullets, indent=2, ensure_ascii=False))
            success += 1
            continue

        save_summary(filing, bullets)
        filing["summary_generated"] = True
        filing["page_built"] = False   # force HTML rebuild to include new summary
        save_ledger(ledger)
        success += 1
        log.info("  → %d bullets saved to %s_Summary.json", len(bullets), filing["id"])

        time.sleep(REQUEST_PAUSE_SECONDS)

    log.info("Done. %d/%d summaries generated.", success, len(candidates))
    if success < len(candidates):
        # The step still succeeds so pages and the feed publish, but a failed
        # summary must not pass unnoticed the way the Q2 2026 one did.
        _warn("Summaries failed", f"{len(candidates) - success} of {len(candidates)} "
              "letter summaries failed; see the summarizer log.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate bullet-point summaries for PGR shareholder letters."
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate summaries for all letters, not just new/missing ones.",
    )
    parser.add_argument(
        "--id", dest="filing_id",
        help="Summarize only this filing (e.g. PGR_2026_Q1), even if it already has one.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the bullets instead of saving them or touching the ledger.",
    )
    args = parser.parse_args()
    main(rebuild=args.rebuild, filing_id=args.filing_id, dry_run=args.dry_run)
