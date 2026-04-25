# Pre-2005 Shareholder Letter Extractor — Design

**Date:** 2026-04-25
**Branch:** feature/pre-2005-scraper

---

## Goal

Extract PGR CEO shareholder letters from pre-2005 SEC EDGAR 10-K filings, where the letter is embedded inside Exhibit 13 (Annual Report to Shareholders) rather than attached as a standalone Exhibit 99.

---

## Background

- The existing scraper (`scraper.py`) and backfill script (`backfill.py`) look for `EX-99` attachments in 10-Q and 10-K filings. PGR began attaching the CEO letter as a standalone EX-99 around 2005.
- For 1993–2004 (10 annual 10-K filings), the CEO letter exists inside the Annual Report filed as **Exhibit 13**. These 10 entries are already in `docs/ledger.json` with `skip_reason: "no_exhibit_99"`.
- Pre-2005 10-Q filings contain no shareholder letter (EX-99 in that era was a financial computation table). No 10-Q letters are recoverable.

---

## Scope

- **Target filings**: 10 entries in the ledger where `form_type == "10-K"` and `year < 2005` and `skip_reason == "no_exhibit_99"` (years 1993–2004, all Q4)
- **Output**: `data/letters/PGR_{year}_Q4_Letter.txt` per filing
- **Ledger**: Update existing entries in place (do not add duplicates)

---

## Architecture

### New file: `scripts/backfill_ex13.py`

Standalone script following the same pattern as `backfill.py`. Imports shared helpers from `scraper.py`. Fully idempotent — skips filings already marked `letter_scraped: True`.

**CLI:**
```
python scripts/backfill_ex13.py              # process all eligible filings
python scripts/backfill_ex13.py --dry-run    # preview without writing files
```

---

## Two EX-13 Fetch Paths

EDGAR's filing format changed around 2001. Both paths produce cleaned plain text of the full Annual Report, then pass it to the same letter extraction function.

### Path A — HTML format (2001–2004)

The filing index lists EX-13 as a separate `.htm` file (e.g., `l99510aexv13.htm`). Fetch directly with `get()`, parse with BeautifulSoup, extract text — identical to `fetch_and_clean()` in `scraper.py`.

**Detection:** `find_ex13(documents)` returns a non-empty filename from the filing document list.

### Path B — SGML bundled format (1993–2000)

The filing index lists no individual filenames. Everything is in one `{accession}.txt` file. Steps:

1. Fetch `{EDGAR_ARCHIVES}/{CIK}/{acc_plain}/{acc}.txt`
2. Extract the `<TYPE>EX-13` … `</DOCUMENT>` block using regex
3. Strip SGML markup: `<PAGE>`, `<TABLE>`, `<CAPTION>`, `<S>`, `<C>`, `<FN>`, `<TEXT>`, `</TEXT>` tags
4. Normalize whitespace (same as `fetch_and_clean()`)

**Detection:** `find_ex13(documents)` returns an empty filename — signals bundled format.

---

## Letter Extraction

`extract_letter(annual_report_text: str) -> tuple[str, str]`

Returns `(letter_text, extraction_method)` where `extraction_method` is one of:
- `"letter_section"` — letter boundaries found and extracted
- `"full_ex13_fallback"` — no heading match; full Annual Report text returned

### Algorithm

1. Search case-insensitively for a start heading matching any of:
   - `"letter to shareholders"`
   - `"letter to shareowners"`
   - `"letter to our shareholders"`

2. Take all text after the heading match.

3. Stop at the first subsequent section heading matching any of:
   - `"financial review"`
   - `"financial highlights"`
   - `"management's discussion"`
   - `"consolidated statements"`
   - `"selected financial"`
   - `"report of independent"`

4. If no start heading found → return full text with `extraction_method = "full_ex13_fallback"`.

---

## Ledger Updates (in place)

For each successfully processed filing, update the existing ledger entry:

```json
{
  "letter_file":        "data/letters/PGR_1996_Q4_Letter.txt",
  "letter_scraped":     true,
  "extraction_method":  "letter_section",
  "processed_date":     "<ISO timestamp>",
  "skip_reason":        null
}
```

Fields removed: `skip_reason` is set to `null` (not deleted, to preserve JSON structure).
`audio_file`, `audio_generated`, `audio_compressed`, `page_built`, `page_url` are added with their default values so the entry is compatible with the full pipeline.

---

## Functions

| Function | Purpose |
|----------|---------|
| `find_ex13(documents)` | Return filename of first EX-13 doc (empty string if bundled) |
| `fetch_ex13_html(acc, filename)` | Fetch and clean HTML EX-13 (Path A) |
| `fetch_ex13_bundled(acc)` | Fetch bundled `.txt`, extract and clean EX-13 block (Path B) |
| `extract_letter(text)` | Extract letter section; return `(text, method)` |
| `process_filing(filing, ledger, dry_run)` | Orchestrate one filing end-to-end |
| `main(dry_run)` | Filter ledger, iterate, summarize |

---

## Tests: `tests/test_backfill_ex13.py`

### Unit — SGML extraction
- `test_fetch_ex13_bundled_extracts_correct_block` — synthetic bundled text with `<TYPE>EX-13` block; verify correct text extracted, SGML tags stripped
- `test_fetch_ex13_bundled_missing_block_returns_none` — no `<TYPE>EX-13` in text; verify `None` returned

### Unit — Letter extraction
- `test_extract_letter_finds_section` — text with "Letter to Shareholders" heading followed by "Financial Review"; verify only letter content returned and method is `"letter_section"`
- `test_extract_letter_fallback` — text with no heading match; verify full text returned and method is `"full_ex13_fallback"`
- `test_extract_letter_case_insensitive` — heading in all-caps; verify match still works
- `test_extract_letter_strips_header_line` — the heading line itself is not included in the returned text

### Integration — `main()`
- `test_main_updates_ledger_in_place` — fake ledger with one pre-2005 10-K entry (`skip_reason: "no_exhibit_99"`), monkeypatched `get()` returning canned HTML fixture; verify `.txt` file written, ledger entry updated in place (`letter_scraped: True`, `extraction_method` set, `skip_reason: null`), no duplicate entry added
- `test_main_dry_run_writes_nothing` — same setup with `dry_run=True`; verify no file written, ledger unchanged

---

## Error Handling

- Filing index fetch fails → log warning, skip filing (not retried; will be retried on next run)
- EX-13 document fetch fails → log warning, skip
- SGML bundled fetch succeeds but `<TYPE>EX-13` block not found → log warning, skip
- Extraction falls back to full text → log info noting fallback, set `extraction_method: "full_ex13_fallback"`, proceed

---

## What This Does Not Do

- Does not process 10-Q filings (no letter exists in them pre-2005)
- Does not modify `scraper.py` or `backfill.py`
- Does not generate audio or reading pages (those run from the existing pipeline after letters are scraped)
