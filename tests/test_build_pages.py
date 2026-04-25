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


def test_render_letter_html_single_newline_becomes_br():
    result = render_letter_html("Line one.\nLine two.")
    assert "<br />" in result
    assert "<p>Line one.\nLine two.</p>" not in result


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
