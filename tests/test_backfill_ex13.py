# tests/test_backfill_ex13.py
import pytest
from backfill_ex13 import (
    find_ex13,
    fetch_ex13_html,
    fetch_ex13_bundled,
    extract_letter,
)


# ── find_ex13 ─────────────────────────────────────────────────────────────────

def test_find_ex13_returns_filename_for_html_filing():
    docs = [
        {"type": "10-K", "filename": "form10k.htm"},
        {"type": "EX-13 ANNUAL REPORT", "filename": "exhibit13.htm"},
        {"type": "EX-21", "filename": "exhibit21.txt"},
    ]
    assert find_ex13(docs) == "exhibit13.htm"


def test_find_ex13_returns_empty_string_for_bundled_filing():
    docs = [
        {"type": "PROGRESSIVE 10-K", "filename": ""},
        {"type": "EX-13", "filename": ""},
        {"type": "EX-21", "filename": ""},
    ]
    assert find_ex13(docs) == ""


def test_find_ex13_returns_none_when_absent():
    docs = [
        {"type": "10-K", "filename": "form10k.htm"},
        {"type": "EX-21", "filename": "exhibit21.txt"},
    ]
    assert find_ex13(docs) is None


# ── fetch_ex13_html ───────────────────────────────────────────────────────────

def test_fetch_ex13_html_strips_tags_and_returns_text(monkeypatch):
    import backfill_ex13

    class FakeResp:
        text = "<html><body><p>Hello shareholder.</p><p>Second paragraph.</p></body></html>"
        headers = {"Content-Type": "text/html"}
        def raise_for_status(self): pass

    monkeypatch.setattr(backfill_ex13, "get", lambda url: FakeResp())
    result = fetch_ex13_html("0000950152-99-002467", "exhibit13.htm")
    assert result is not None
    assert "Hello shareholder." in result
    assert "Second paragraph." in result
    assert "<p>" not in result
