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
# Gemini 3 always thinks, and thinking tokens come out of the output budget.
# Medium effort made better fact-check fixes than low in the 2026-11 tests (low
# twice missed a claim the letter does not make), but occasionally thinks past
# 16k tokens, so the budget is generous and the check is retried once.
GEMINI_REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS       = 32000
CHECK_ATTEMPTS          = 2
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
- Compress, but prefer the letter's own words to a paraphrase. Short phrases from
  the letter are fine; never quote whole sentences.

FACTUAL RULES (critical — the summary is read as a record of what the letter says):
- Use only facts and figures stated in this letter. Do not add outside knowledge,
  industry context, or initiatives the letter does not mention.
- Do not attribute a cause, driver or motive the letter does not give. If the
  letter reports a change without a reason, report the change alone.
- Do not add superlatives ("record", "best ever", "historic") unless the letter
  uses them, and keep the letter's own hedges ("may have been", "approximately").
- Do not merge separate statements into a claim the letter does not make.
- Keep the letter's strength. "A significant contributor" is not "drove" or
  "led"; "more than fivefold" is not "fivefold"; keep "over", "about", "nearly",
  "at least", "estimated", "we believe" and "we expect".
- Linking words are claims. Write "despite", "driven by", "due to", "thanks to",
  "forcing", "as" or "while" only when the letter itself makes that link;
  otherwise give the facts side by side, separated by a semicolon.
- The topic label is a filing category, not content. Do not reuse its words
  ("market share", "innovation", "transformation") unless the letter does, and
  never write a claim to fit the label: "competitors are raising rates" does
  not mean "Progressive gained share".
- Attribute forecasts and beliefs: if the letter says "we believe" or "we
  expect", the bullet says "expects" or "believes", not a fact.

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

_VERIFY_SYSTEM_PROMPT = (
    "You are a meticulous fact-checker. You compare a summary against its source "
    "document and correct anything the source does not support. "
    "Output ONLY valid JSON — no markdown, no prose, no code fences."
)

_VERIFY_PROMPT_TEMPLATE = """\
Below are a PGR shareholder letter ({filing_id}) and a draft summary of it as a JSON \
array of {{"topic", "text"}} bullets. Check every claim in every bullet against the letter.

A claim FAILS if it:
- states a fact or figure the letter does not contain;
- is stronger than the letter ("drove" for "contributed to", "fivefold" for "more
  than fivefold", a fact where the letter says "we believe" or "we expect");
- links facts the letter does not link ("despite", "driven by", "due to", "as",
  "forcing", "thanks to", "while");
- adds a superlative, motive or outcome the letter does not state (for example
  "gained share" when the letter only says competitors raised rates).

Return the summary as a JSON array in the same order with the same topics. Copy \
bullets that pass unchanged. Rewrite bullets that fail so every claim matches the \
letter, keeping the same terse style and 20–35 words; drop the failing claim if \
the letter has nothing to replace it with. Add "fixed": true to each bullet you \
changed. Do not add, remove or reorder bullets.

DRAFT SUMMARY:
{bullets_json}

LETTER TEXT:
{letter_text}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────


def _summary_path(filing_id: str) -> Path:
    return SUMMARIES_DIR / f"{filing_id}_Summary.json"


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if the model adds them despite instructions."""
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    return re.sub(r"\n?```$", "", raw).strip()


def parse_bullets(raw: str) -> list[dict]:
    """Parse and validate the model's reply into a list of {topic, text} dicts.

    Raises ValueError on anything that is not a summary, so a service that
    answers with something else fails loudly instead of being saved.
    """
    raw = _strip_fences(raw)
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


def _complete(client: OpenAI, system: str, prompt: str) -> str:
    """One Gemini chat completion; returns its text, or raises ValueError."""
    response = client.chat.completions.create(
        model=GEMINI_MODEL,
        messages=[
            {"role": "system", "content": system},
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
    return choice.message.content or ""


def generate_summary(client: OpenAI, filing: dict, letter_text: str) -> list[dict]:
    """Call Gemini and return a list of {topic, text} bullet dicts."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        filing_id=filing["id"],
        letter_text=letter_text[:30_000],  # cap at ~30k chars; no letter is longer
    )
    return parse_bullets(_complete(client, _SYSTEM_PROMPT, prompt))


def verify_summary(client: OpenAI, filing: dict, letter_text: str,
                   bullets: list[dict]) -> tuple[list[dict], int]:
    """Second pass: Gemini checks the draft against the letter and rewrites any
    bullet the letter does not support. Returns (bullets, number rewritten).

    Raises ValueError if the reply is not the same bullets in the same order, so
    a confused checker can never drop or reshuffle the draft.
    """
    prompt = _VERIFY_PROMPT_TEMPLATE.format(
        filing_id=filing["id"],
        bullets_json=json.dumps(bullets, indent=2, ensure_ascii=False),
        letter_text=letter_text[:30_000],
    )
    raw = _complete(client, _VERIFY_SYSTEM_PROMPT, prompt)
    checked = parse_bullets(raw)
    if [b["topic"] for b in checked] != [b["topic"] for b in bullets]:
        raise ValueError("Checker changed the bullets' topics or order")
    fixed_flags = [bool(item.get("fixed")) for item in json.loads(_strip_fences(raw))]
    fixed = sum(1 for flag, old, new in zip(fixed_flags, bullets, checked)
                if flag or old["text"] != new["text"])
    return checked, fixed


# A figure: digits with optional decimals or thousands commas. The greedy match
# never backtracks, so "$19.9B" yields 19.9, not 19.
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d.,])\d+(?:[.,]\d+)*")
_SCALE_WORDS = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}


def _canonical(number: str) -> str:
    """'1,234' -> '1234', '96.0' -> '96', '0.50' -> '0.5'."""
    number = number.replace(",", "")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number


def _numbers(text: str, expand_scales: bool = False) -> set[str]:
    """Every figure in text, in canonical form.

    Skips labels where a letter follows the digits (Q3 is excluded by the
    look-behind; 1H, 9M and 2nd here), except the scale suffixes K, M and B.
    With expand_scales (used on the letter), "43 thousand" also yields 43000,
    to match a summary's "43,000".
    """
    found = set()
    for match in _NUMBER_RE.finditer(text):
        after = text[match.end():match.end() + 12]
        if after[:1].isalpha() and not re.match(r"[KMB](?![a-z])", after):
            continue
        number = _canonical(match.group())
        found.add(number)
        scale = re.match(r"\s+(thousand|million|billion)\b", after)
        if expand_scales and scale:
            value = float(number) * _SCALE_WORDS[scale.group(1)]
            if value == int(value):
                found.add(str(int(value)))
            # "$3,180.0 million" may be summarized as "$3.18B" or "$3,180M".
            for unit in (1_000_000, 1_000_000_000):
                found.add(_canonical(f"{value / unit:.4f}"))
    return found


def unsupported_numbers(bullets: list[dict], letter_text: str) -> list[str]:
    """Figures that appear in the summary but nowhere in the letter.

    A cheap guard against invented numbers. "$1.5B" matches "$1.5 billion" and
    "+4%" matches "4%". Skipped: small integers (<= 10), which letters often
    spell out ("two states"); bare years; and the 96 CR target when the letter
    states it as "four cents" of underwriting profit.
    """
    in_letter = _numbers(letter_text, expand_scales=True)
    if re.search(r"\bfour cents\b", letter_text, re.IGNORECASE):
        in_letter.add("96")
    missing = []
    for bullet in bullets:
        for number in sorted(_numbers(bullet["text"])):
            if number in in_letter or (number.isdigit() and
                                       (int(number) <= 10 or 1990 <= int(number) <= 2040)):
                continue
            missing.append(number)
    return sorted(set(missing))


def save_summary(filing: dict, bullets: list[dict], verification: dict | None = None) -> None:
    data = {
        "id":             filing["id"],
        "year":           filing["year"],
        "quarter":        filing["quarter"],
        "generated_date": datetime.now(timezone.utc).isoformat(),
        "generated_by":   f"{GEMINI_MODEL} (Gemini API)",
    }
    if verification:
        data["verification"] = verification
    data["bullets"] = bullets
    path = _summary_path(filing["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

# ── Main ──────────────────────────────────────────────────────────────────────


def _warn(title: str, message: str) -> None:
    """Log a warning and surface it as an annotation on the Actions run."""
    log.warning(message)
    print(f"::warning title={title}::{message}")


def check_summary(client: OpenAI, filing: dict, letter_text: str,
                  draft: list[dict]) -> tuple[list[dict], dict]:
    """Run the fact-check pass and the number check on a draft summary.

    Returns the bullets to save and a record of the checks for the summary
    file. A failed check never loses the summary: the draft is kept, marked
    unverified, and the run gets a warning so someone reads it by hand.
    """
    bullets, verification, error = draft, None, None
    for attempt in range(1, CHECK_ATTEMPTS + 1):
        time.sleep(REQUEST_PAUSE_SECONDS)   # another request; free-tier rate limits
        try:
            bullets, fixed = verify_summary(client, filing, letter_text, draft)
        except Exception as exc:
            error = exc
            log.warning("  Fact-check attempt %d/%d failed: %s", attempt, CHECK_ATTEMPTS, exc)
            continue
        verification = {"checked": True, "bullets_rewritten": fixed}
        if fixed:
            log.info("  Fact-check rewrote %d bullet(s).", fixed)
        break
    if verification is None:
        verification = {"checked": False, "error": str(error)[:200]}
        _warn("Summary not fact-checked",
              f"{filing['id']}: the fact-check pass failed ({error}); the unchecked "
              "draft was saved. Compare it with the letter by hand.")

    missing = unsupported_numbers(bullets, letter_text)
    if missing:
        verification["numbers_not_in_letter"] = missing
        _warn("Summary figures not found in letter",
              f"{filing['id']}: {', '.join(missing)} appear in the summary but not "
              "in the letter. Check them by hand.")
    return bullets, verification


def audit_saved_summaries() -> int:
    """Print every saved summary whose figures are not all in its letter.

    Returns the number of summaries flagged. A flag is a lead, not a verdict:
    the letter may spell a figure out ("one hundred percent").
    """
    flagged = 0
    for filing in load_ledger()["filings"]:
        path = _summary_path(filing["id"])
        if not (path.exists() and filing.get("letter_file")):
            continue
        letter = clean_letter_text((BASE_DIR / filing["letter_file"]).read_text(encoding="utf-8"))
        bullets = json.loads(path.read_text(encoding="utf-8"))["bullets"]
        missing = unsupported_numbers(bullets, letter)
        if missing:
            flagged += 1
            print(f"{filing['id']}: {', '.join(missing)}")
    print(f"{flagged} summary file(s) have figures not found in their letter.")
    return flagged


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
            draft = generate_summary(client, filing, letter_text)
        except Exception as exc:
            log.error("  Failed to summarize %s: %s", filing["id"], exc, exc_info=True)
            continue

        bullets, verification = check_summary(client, filing, letter_text, draft)

        if dry_run:
            print(json.dumps({"draft": draft, "verification": verification,
                              "bullets": bullets}, indent=2, ensure_ascii=False))
            success += 1
            continue

        save_summary(filing, bullets, verification)
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
    parser.add_argument(
        "--check-numbers", action="store_true",
        help="List saved summaries with figures that are not in their letter "
             "(no API calls, writes nothing).",
    )
    args = parser.parse_args()
    if args.check_numbers:
        sys.exit(1 if audit_saved_summaries() else 0)
    main(rebuild=args.rebuild, filing_id=args.filing_id, dry_run=args.dry_run)
