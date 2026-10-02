"""Tests for scripts/letter_text.py, the shared letter normalizer.

The unit tests pin down individual cleanup rules on small inputs. The corpus
tests run every stored letter through clean_letter_text() and check for the
artifacts LETTER_REVIEW.md describes, so a scraper or cleanup change that
reintroduces one shows up here.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from letter_text import clean_letter_text, normalized_letter_blocks  # noqa: E402

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
LETTER_FILES = sorted(LETTERS_DIR.glob("PGR_*_Letter.txt"))


def _kinds(text: str) -> list[str]:
    return [kind for kind, _ in normalized_letter_blocks(text)]


# ── Unit tests ────────────────────────────────────────────────────────────────

def test_strips_leading_sec_exhibit_header():
    text = (
        "EX-99\n"
        "2\n"
        "pgr-20260630xex99.htm\n"
        "EX-99\n"
        "Letter to Shareholders\n"
        "Second Quarter 2026\n"
        "Growth was strong this quarter.\n"
    )
    assert clean_letter_text(text) == "Growth was strong this quarter.\n"


def test_drops_bare_page_numbers():
    text = "First paragraph ends here.\n2\nSecond paragraph.\n"
    assert clean_letter_text(text) == "First paragraph ends here.\n\nSecond paragraph.\n"


def test_rejoins_lines_split_mid_sentence():
    text = "The combined ratio for the quarter\nwas 86.4.\n"
    assert clean_letter_text(text) == "The combined ratio for the quarter was 86.4.\n"


def test_rule_line_marks_preceding_line_as_heading():
    text = (
        "Closing paragraph of the section.\n"
        "Understanding (by the numbers)\n"
        "-----\n"
        "What we thought would transpire happened.\n"
    )
    blocks = normalized_letter_blocks(text)
    assert ("heading", "Understanding (by the numbers)") in blocks
    assert blocks[-1] == ("paragraph", "What we thought would transpire happened.")


def test_inline_signature_is_split_into_name_and_title():
    text = (
        "Thank you for your interest.\n"
        "Tricia Griffith, President and Chief Executive Officer\n"
    )
    assert normalized_letter_blocks(text)[-1] == (
        "signature",
        "Tricia Griffith\nPresident and Chief Executive Officer",
    )


def test_valediction_is_its_own_paragraph():
    text = (
        "We look forward to the year ahead.\n"
        "Stay well and be kind to others,\n"
        "Tricia Griffith\n"
        "President and Chief Executive Officer\n"
    )
    blocks = normalized_letter_blocks(text)
    assert ("paragraph", "Stay well and be kind to others,") in blocks
    assert blocks[-1][0] == "signature"


def test_dropped_trademark_leaves_no_space_before_punctuation():
    text = "We grew Snapshot , our usage-based program, and Name Your Price ” offers.\n"
    assert clean_letter_text(text) == (
        "We grew Snapshot, our usage-based program, and Name Your Price” offers.\n"
    )


def test_line_breaks_inside_curly_quotes_leave_no_padding():
    text = "“\nWhile I was fortunate, I volunteered at the drive-through,\n” Jill shares.\n"
    assert clean_letter_text(text) == (
        "“While I was fortunate, I volunteered at the drive-through,” Jill shares.\n"
    )


def test_split_contraction_is_rejoined():
    assert clean_letter_text("We ’ re excited about it.\n") == "We’re excited about it.\n"


def test_story_quote_ends_after_fully_quoted_passage():
    text = (
        "Our own employee, Terri, shared her experience saying:\n"
        "“When you volunteer you actually see the difference you are making "
        "in the lives of these families every single time.”\n"
        "I concur with her completely.\n"
    )
    assert _kinds(text) == ["paragraph", "quote", "paragraph"]


def test_attributed_quote_does_not_style_following_paragraphs():
    text = (
        "“While I was incredibly fortunate to experience only minimal damage, "
        "it got me thinking about how I could help,” Jill shares.\n"
        "After volunteering, Jill kept collecting donations.\n"
    )
    assert _kinds(text) == ["quote", "paragraph"]


def test_short_quoted_line_continues_previous_quote():
    text = (
        "“You see some misty eyes from the volunteers when they start thinking "
        "about the kids,” shares Heather.\n"
        "“It breaks my heart, but the work is so rewarding.”\n"
        "The group volunteers every month.\n"
    )
    assert _kinds(text) == ["quote", "quote", "paragraph"]


def test_glyph_repairs_in_plain_text():
    text = "Eﬀective results from our in‑house team.\n"
    assert clean_letter_text(text) == "Effective results from our in-house team.\n"


# ── Corpus checks ─────────────────────────────────────────────────────────────

# Letters whose signature count is legitimately not one.
#   2013 Q4 — signed by Glenn Renwick; Exhibit B, reprinted from Peter Lewis,
#             carries his own signature.
#   2016 Q2 — Glenn Renwick's last letter closes "Cheers, Glenn / /s/ Glenn"
#             with no typed name or title.
_SIGNATURE_EXCEPTIONS = {"PGR_2013_Q4_Letter.txt": 2, "PGR_2016_Q2_Letter.txt": 0}

_SEC_REMNANT_RE = re.compile(
    r"(?im)^\s*(?:<PAGE>|EX-99(?:\.1)?|Exhibit 99(?:\.1)?|Page \d+ of \d+|-?\s*\d{1,3}\s*-?)\s*$"
)
# A superscript ordinal dropped by the extraction: "its 56 campaign",
# "my 35 Progressive anniversary". See "Lost ordinals" in LETTER_REVIEW.md.
_LOST_ORDINAL_RE = re.compile(
    r"\b(?:its|our|my|the|his|her|their)\s+\d{1,3}(?:,\d{3})?\s+"
    r"(?:anniversary|campaign|consecutive|percentile|state|birthday|home makeover|vehicle)\b"
)
_LEFTOVER_RE = re.compile(r"[\x00-\x08\x0b-\x1f-ﬀ-ﬄ‑]")


def test_corpus_is_present():
    assert len(LETTER_FILES) >= 100


@pytest.mark.parametrize("path", LETTER_FILES, ids=lambda p: p.stem)
def test_clean_letter_has_no_known_artifacts(path):
    raw = path.read_text(encoding="utf-8")
    text = clean_letter_text(raw)

    assert len(text) > 1000, "letter text is suspiciously short"
    assert not _SEC_REMNANT_RE.search(text), "SEC header or page-number line survived"
    assert not _LOST_ORDINAL_RE.search(text), "number reads like a lost ordinal suffix"
    assert not re.search("“[  ]|[  ]”", text), "space inside curly quotes"
    assert not re.search(r"\S {2,}\S", text), "run of spaces inside a paragraph"
    assert not _LEFTOVER_RE.search(text), "control, private-use, or ligature glyph survived"

    signatures = sum(1 for kind, _ in normalized_letter_blocks(raw) if kind == "signature")
    assert signatures == _SIGNATURE_EXCEPTIONS.get(path.name, 1)
