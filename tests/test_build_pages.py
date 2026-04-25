# tests/test_build_pages.py
import pytest
from build_pages import render_letter_html, build_page

SAMPLE_FILING = {
    "id":               "PGR_2025_Q3",
    "year":             2025,
    "quarter":          "Q3",
    "form_type":        "10-Q",
    "report_date":      "2025-09-30",
    "letter_scraped":   True,
    "letter_file":      "data/letters/PGR_2025_Q3_Letter.txt",
    "audio_compressed": False,
    "audio_file":       None,
}

SAMPLE_FILING_WITH_AUDIO = {
    **SAMPLE_FILING,
    "audio_compressed": True,
    "audio_file":       "docs/audio/PGR_2025_Q3_Letter.mp3",
}

SAMPLE_TEXT = "First paragraph.\n\nSecond paragraph.\n\nThird <special> & paragraph."


def test_render_letter_html_splits_paragraphs():
    result = render_letter_html("Para one.\n\nPara two.")
    assert "<p>Para one.</p>" in result
    assert "<p>Para two.</p>" in result


def test_render_letter_html_escapes_html():
    result = render_letter_html("Text with <b>tags</b> & ampersands.")
    assert "&lt;b&gt;" in result
    assert "&amp;" in result
    assert "<b>" not in result


def test_render_letter_html_single_newline_starts_new_paragraph_when_complete():
    result = render_letter_html("Line one.\nLine two.")
    assert "<p>Line one.</p>" in result
    assert "<p>Line two.</p>" in result
    assert "<br />" not in result


def test_render_letter_html_removes_sec_header_noise():
    text = "\n".join([
        "EX-99",
        "13",
        "pgr-20251231exhibit99.htm",
        "EX-99",
        "Document",
        "Exhibit 99",
        "LETTER TO SHAREHOLDERS",
        "The best part of customer-focused growth is that every customer increases share.",
    ])

    result = render_letter_html(text)

    assert "EX-99" not in result
    assert "pgr-20251231exhibit99.htm" not in result
    assert "Document" not in result
    assert "LETTER TO SHAREHOLDERS" not in result
    assert "The best part of customer-focused growth" in result


def test_render_letter_html_removes_older_exhibit_header_variants():
    text = "\n".join([
        "EX-99.A",
        "24",
        "l17994aexv99wa.htm",
        "EX-99(A) LETTER TO SHAREHOLDERS",
        "Exhibit\xa0No.\xa099(A)",
        "LETTER TO SHAREHOLDERS",
        "MEASUREMENT IS CENTRAL TO PROGRESSIVE\x92S BUSINESS DISCIPLINE.",
    ])

    result = render_letter_html(text)

    assert "EX-99" not in result
    assert "l17994aexv99wa.htm" not in result
    assert "LETTER TO SHAREHOLDERS" not in result
    assert "Exhibit" not in result
    assert "PROGRESSIVE’S BUSINESS DISCIPLINE" in result


def test_render_letter_html_removes_page_numbers_and_repairs_wrapped_lines():
    text = "Every customer increases share of the\n1\nmarket. We serve them."

    result = render_letter_html(text)

    assert "<p>Every customer increases share of the market. We serve them.</p>" in result
    assert ">1<" not in result


def test_render_letter_html_repairs_split_trademark_markers():
    text = "Keys to Progress\nÂ®\nwhere customers participate in the survey.\n99\nth\npercentile."

    result = render_letter_html(text)

    assert "Keys to Progress® where customers participate" in result
    assert "99th percentile." in result


def test_render_letter_html_repairs_common_mojibake():
    result = render_letter_html("Iâ€™m proud of Progressiveâ€™s results.")
    assert "I’m proud of Progressive’s results." in result


def test_build_page_contains_metadata():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "2025 Q3" in page
    assert "10-Q" in page
    assert "2025-09-30" in page


def test_build_page_contains_letter_text():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "First paragraph." in page
    assert "Second paragraph." in page


def test_build_page_escapes_special_chars_in_text():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "&lt;special&gt;" in page
    assert "<special>" not in page
    assert "&amp;" in page


def test_build_page_no_audio_section_when_not_compressed():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "audio-section" not in page


def test_build_page_includes_audio_section_when_compressed():
    page = build_page(SAMPLE_FILING_WITH_AUDIO, SAMPLE_TEXT, None, None)
    assert "audio-section" in page
    assert "PGR_2025_Q3_Letter.mp3" in page


def test_build_page_no_nav_ep_links_when_no_prev_next():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "nav-ep-link" not in page


def test_build_page_includes_prev_next_links():
    prev_f = {**SAMPLE_FILING, "id": "PGR_2025_Q2", "year": 2025, "quarter": "Q2"}
    next_f = {**SAMPLE_FILING, "id": "PGR_2025_Q4", "year": 2025, "quarter": "Q4"}
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, prev_f, next_f)
    assert "PGR_2025_Q2.html" in page
    assert "PGR_2025_Q4.html" in page
    assert "2025 Q2" in page
    assert "2025 Q4" in page


def test_build_page_back_link_present():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "../index.html" in page


def test_build_page_reading_css_linked():
    page = build_page(SAMPLE_FILING, SAMPLE_TEXT, None, None)
    assert "../assets/reading.css" in page


# ── Integration tests ────────────────────────────────────────────────────

import json
import time
import build_pages
import scraper


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """Temp ledger + letter file; PAGES_DIR and BASE_DIR redirected."""
    # Letter file
    letters_dir = tmp_path / "data" / "letters"
    letters_dir.mkdir(parents=True)
    (letters_dir / "PGR_2025_Q3_Letter.txt").write_text(
        "Para one.\n\nPara two.", encoding="utf-8"
    )

    # Pages output dir
    pages_out = tmp_path / "docs" / "letters"
    pages_out.mkdir(parents=True)

    # Ledger
    ledger_data = {
        "meta": {
            "last_updated": None,
            "total_letters": 1,
            "total_audio": 0,
            "description": "",
        },
        "filings": [{
            "id":               "PGR_2025_Q3",
            "year":             2025,
            "quarter":          "Q3",
            "form_type":        "10-Q",
            "report_date":      "2025-09-30",
            "letter_file":      "data/letters/PGR_2025_Q3_Letter.txt",
            "audio_file":       "docs/audio/PGR_2025_Q3_Letter.mp3",
            "letter_scraped":   True,
            "audio_compressed": False,
            "page_built":       False,
        }],
    }
    ledger_file = tmp_path / "docs" / "ledger.json"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

    monkeypatch.setattr(build_pages, "PAGES_DIR", pages_out)
    monkeypatch.setattr(build_pages, "BASE_DIR",  tmp_path)
    monkeypatch.setattr(scraper,     "BASE_DIR",  tmp_path)
    monkeypatch.setattr(scraper,     "LEDGER_PATH", ledger_file)

    return tmp_path, ledger_file, pages_out


def test_main_creates_html_file(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    assert (pages_out / "PGR_2025_Q3.html").exists()


def test_main_sets_page_built_in_ledger(fake_env):
    _, ledger_file, _ = fake_env
    build_pages.main(rebuild=False)
    updated = json.loads(ledger_file.read_text())
    filing = updated["filings"][0]
    assert filing["page_built"] is True
    assert filing["page_url"] == "letters/PGR_2025_Q3.html"


def test_main_is_idempotent(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    mtime1 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime

    build_pages.main(rebuild=False)   # second run — page_built=True in ledger
    mtime2 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime
    assert mtime1 == mtime2  # file not rewritten


def test_main_rebuild_forces_regeneration(fake_env):
    _, _, pages_out = fake_env
    build_pages.main(rebuild=False)
    mtime1 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime

    time.sleep(0.15)
    build_pages.main(rebuild=True)
    mtime2 = (pages_out / "PGR_2025_Q3.html").stat().st_mtime
    assert mtime2 > mtime1
