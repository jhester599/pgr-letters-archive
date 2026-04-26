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


# ── fetch_ex13_bundled ────────────────────────────────────────────────────────

_BUNDLED_TEXT = """\
-----BEGIN PRIVACY-ENHANCED MESSAGE-----
<IMS-DOCUMENT>
<DOCUMENT>
<TYPE>10-K
<SEQUENCE>1
<TEXT>
Main 10-K content here. Should NOT appear in output.
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-13
<SEQUENCE>8
<DESCRIPTION>EXHIBIT 13
<TEXT>
<PAGE>   1
1996 Annual Report to Shareholders

<TABLE>
<CAPTION>Some table content
</TABLE>

Letter to Shareholders

Dear Shareholders, this is the actual letter content.
We had a wonderful year.

Financial Review
Financial data follows.
</TEXT>
</DOCUMENT>
</IMS-DOCUMENT>
-----END PRIVACY-ENHANCED MESSAGE-----
"""


def test_fetch_ex13_bundled_extracts_correct_block(monkeypatch):
    import backfill_ex13

    class FakeResp:
        text = _BUNDLED_TEXT
        headers = {}
        def raise_for_status(self): pass

    monkeypatch.setattr(backfill_ex13, "get", lambda url: FakeResp())
    result = fetch_ex13_bundled("0000950152-97-002528")
    assert result is not None
    assert "Annual Report" in result
    assert "Letter to Shareholders" in result
    assert "Dear Shareholders" in result
    # SGML tags stripped
    assert "<TYPE>" not in result
    assert "<PAGE>" not in result
    assert "<TABLE>" not in result
    # Main 10-K section not included
    assert "10-K content" not in result


def test_fetch_ex13_bundled_missing_block_returns_none(monkeypatch):
    import backfill_ex13

    class FakeResp:
        text = "<IMS-DOCUMENT><DOCUMENT><TYPE>10-K<TEXT>no ex-13 here</TEXT></DOCUMENT></IMS-DOCUMENT>"
        headers = {}
        def raise_for_status(self): pass

    monkeypatch.setattr(backfill_ex13, "get", lambda url: FakeResp())
    result = fetch_ex13_bundled("0000950152-97-002528")
    assert result is None


# ── extract_letter ────────────────────────────────────────────────────────────

_ANNUAL_REPORT = """\
1996 Annual Report to Shareholders

Financial Highlights
Some financial data.

Letter to Shareholders

Dear Shareholders,

We had a wonderful year. This is the first paragraph.

This is the second paragraph.

Sincerely,
Peter Lewis

Financial Review

Management discussion follows here.
"""


def test_extract_letter_finds_section():
    text, method = extract_letter(_ANNUAL_REPORT)
    assert method == "letter_section"
    assert "Dear Shareholders" in text
    assert "We had a wonderful year" in text
    assert "Peter Lewis" in text
    assert "Financial Review" not in text
    assert "Management discussion" not in text


def test_extract_letter_fallback():
    text, method = extract_letter("Plain text with no headings whatsoever.")
    assert method == "full_ex13_fallback"
    assert "Plain text" in text


def test_extract_letter_case_insensitive():
    upper = _ANNUAL_REPORT.replace("Letter to Shareholders", "LETTER TO SHAREHOLDERS")
    _, method = extract_letter(upper)
    assert method == "letter_section"


def test_extract_letter_strips_header_line():
    text, method = extract_letter(_ANNUAL_REPORT)
    assert method == "letter_section"
    assert "Letter to Shareholders" not in text


# ── Integration tests ─────────────────────────────────────────────────────────

import json
import backfill_ex13
import scraper

_INDEX_HTML = """\
<html><body><table>
<tr><td>1</td><td>10-K</td>
    <td><a href="/Archives/edgar/data/80661/123/form10k.htm">form10k.htm</a></td>
    <td>desc</td><td>size</td></tr>
<tr><td>8</td><td>EX-13 ANNUAL REPORT</td>
    <td><a href="/Archives/edgar/data/80661/123/exhibit13.htm">exhibit13.htm</a></td>
    <td>Annual Report</td><td>size</td></tr>
</table></body></html>
"""

_EX13_HTML = """\
<html><body>
<p>1996 Annual Report to Shareholders</p>
<p>Letter to Shareholders</p>
<p>Dear Shareholders, this is the letter content for 1996.</p>
<p>We had an outstanding year.</p>
<p>Sincerely, Peter Lewis</p>
<p>Financial Review</p>
<p>Financial data follows.</p>
</body></html>
"""


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    letters_dir = tmp_path / "data" / "letters"
    letters_dir.mkdir(parents=True)

    ledger_data = {
        "meta": {"last_updated": None, "total_letters": 0, "total_audio": 0},
        "filings": [{
            "id":               "PGR_1996_Q4",
            "year":             1996,
            "quarter":          "Q4",
            "form_type":        "10-K",
            "accession_number": "0000950152-97-002528",
            "report_date":      "1996-12-31",
            "letter_file":      None,
            "audio_file":       None,
            "letter_scraped":   False,
            "audio_generated":  False,
            "audio_compressed": False,
            "skip_reason":      "no_exhibit_99",
        }],
    }
    ledger_file = tmp_path / "docs" / "ledger.json"
    ledger_file.parent.mkdir(parents=True)
    ledger_file.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

    def fake_get(url):
        class R:
            headers = {"Content-Type": "text/html"}
            def raise_for_status(self): pass
        r = R()
        r.text = _INDEX_HTML if "index.htm" in url else _EX13_HTML
        return r

    monkeypatch.setattr(backfill_ex13, "get",        fake_get)
    monkeypatch.setattr(scraper,       "get",        fake_get)
    monkeypatch.setattr(backfill_ex13, "LETTERS_DIR", letters_dir)
    monkeypatch.setattr(scraper,       "LEDGER_PATH", ledger_file)

    return tmp_path, ledger_file, letters_dir


def test_main_updates_ledger_in_place(fake_env):
    _, ledger_file, letters_dir = fake_env
    backfill_ex13.main(dry_run=False)

    updated = json.loads(ledger_file.read_text())
    assert len(updated["filings"]) == 1          # no duplicate added
    filing = updated["filings"][0]
    assert filing["letter_scraped"] is True
    assert filing["skip_reason"] is None
    assert filing["extraction_method"] in ("letter_section", "full_ex13_fallback")
    assert filing["letter_file"] == "data/letters/PGR_1996_Q4_Letter.txt"
    assert (letters_dir / "PGR_1996_Q4_Letter.txt").exists()
    assert filing["audio_generated"] is False
    assert filing["audio_compressed"] is False


def test_main_dry_run_writes_nothing(fake_env):
    _, ledger_file, letters_dir = fake_env
    original = ledger_file.read_text()

    backfill_ex13.main(dry_run=True)

    assert ledger_file.read_text() == original
    assert not any(letters_dir.glob("*.txt"))
