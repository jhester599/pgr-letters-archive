# Next Agent Handoff

Last updated: 2026-04-26

Repo: `C:\Users\Jeff\Documents\github\pgr-letters-archive`

GitHub: `https://github.com/jhester599/pgr-letters-archive`

GitHub Pages: `https://jhester599.github.io/pgr-letters-archive/`

## Current State

This project is an automated Progressive Corporation shareholder-letter archive:
SEC EDGAR extraction, static reading pages, optional NotebookLM audio generation,
RSS publishing, and GitHub Pages deployment.

The current local checkout is `main` at `8a3af43`, matching `origin/main`.
The only untracked file seen during handoff was `AGENTS.md`.

PR #2 / `codex/letter-length-audit` has effectively been merged into `main`:

- `c2267bf` merged PR #2.
- `4ddb09a` recovered 39 post-2005 letters skipped by the old EDGAR column parser.
- `8a3af43` recovered 1995 Q4 and 2001 Q4 letters and added `10-K405` support.

The archive currently has:

- 129 ledger filings.
- 92 scraped letters.
- 92 built reading pages.
- 0 compressed audio files.
- 37 `no_exhibit_99` skips.
- Letter coverage from 1993 through 2025.
- One expected-looking missing quarter in the checked set: `2006 Q1`.

## Recently Completed Work

The following work from the previous Codex thread has landed in `main`:

- Improved shareholder letter page formatting.
- Removed SEC header noise and page-number artifacts.
- Added paragraph spacing and line-wrap cleanup.
- Split signatures into clean name/title blocks.
- Italicized identified employee/customer story quotes.
- Added chronological left-menu tree with expandable years.
- Improved legacy heading cleanup for older letters.
- Added handling for known figures/formulas in `2005_Q4`.
- Rebuilt reading pages.
- Refreshed stale partial `PGR_1994_Q4`.
- Added annual-letter completeness and rendering regression tests.
- Added `scripts/backfill_ex99.py`.

Important audit finding:

- `PGR_2013_Q2` is short, about 6,082 characters / 969 words, but matches the SEC
  exhibit and appears complete.
- `PGR_1994_Q4` was the true stale outlier and is now refreshed to about 20,208
  characters / 3,115 words.

## Immediate Priorities

### 1. Fix the current test regression

Run:

```powershell
python -m pytest -q
```

Observed result during handoff:

```text
1 failed, 49 passed
```

Failing test:

- `tests/test_backfill_ex13.py::test_main_updates_ledger_in_place`

Likely cause:

- `scripts/scraper.py::fetch_filing_documents()` now prefers `cells[3]` as the
  EDGAR document type column. That fixed modern EX-99 discovery, but the EX-13
  integration fixture/path still reflects an older table shape where the useful
  type string is in another column.

Goal:

- Preserve the modern EX-99 fix.
- Restore EX-13 compatibility.
- Keep the test meaningful rather than blindly rewriting it around the current bug.

Suggested approach:

- Add/adjust parser logic to handle both EDGAR table shapes robustly, or adjust
  the fixture only if it is demonstrably not representative.
- Add a focused parser test for modern EX-99 and older EX-13 table layouts.
- Re-run `python -m pytest -q`.

### 2. Create or intentionally suppress `docs/feed.xml`

Public site links to `feed.xml`, but the URL currently returns 404 because there
is no committed feed and there are no compressed audio files yet.

Options:

- Preferred short-term: run `python scripts/compressor.py` to generate an empty
  valid RSS feed from the current ledger, then commit `docs/feed.xml`.
- Alternative: hide RSS links until at least one audio file exists.

Relevant files:

- `docs/index.html`
- `scripts/compressor.py`
- `docs/feed.xml`

### 3. Ignore raw NotebookLM `.mp4` files

`scripts/generator.py` writes raw NotebookLM audio to:

```text
data/audio_raw/<filing>_Letter.mp4
```

But `.gitignore` currently ignores only:

```text
data/audio_raw/*.mp3
data/audio_raw/*.wav
data/audio_raw/*.m4a
data/audio_raw/*.aac
```

Add:

```text
data/audio_raw/*.mp4
```

### 4. Update stale docs

Several docs still describe old project state or old NotebookLM auth details.
Update after the test fix so docs can cite verified behavior.

Known stale items:

- `PLAN.md` still references `NOTEBOOKLM_EMAIL` and `NOTEBOOKLM_PASSWORD`.
- Current workflow and generator use `NOTEBOOKLM_AUTH_JSON`.
- Roadmap still describes reading pages as future work, but they are implemented.
- Docs should mention `backfill_ex13.py`, `backfill_ex99.py`, page generation,
  known figure/formula rendering, and the current archive status.

### 5. Continue legacy formatting cleanup

After tests are green, prioritize older annual report page artifacts:

- Dashed headings like `Results -----------`.
- Source placeholders like `ART HERE`.
- Any remaining raw SEC/annual-report layout debris.

Relevant files:

- `scripts/build_pages.py`
- `tests/test_build_pages.py`
- `docs/assets/reading.css`
- generated `docs/letters/*.html`

Use tests first for each cleanup rule, then rebuild pages:

```powershell
python -m pytest tests\test_build_pages.py -q
python scripts\build_pages.py --rebuild
python -m pytest -q
```

## Parallel-Agent Coordination

Avoid concurrent edits to these files unless explicitly coordinated:

- `docs/ledger.json`
- `scripts/build_pages.py`
- generated `docs/letters/*.html`
- `scripts/scraper.py`
- `scripts/backfill_ex13.py`
- `scripts/backfill_ex99.py`

Suggested split:

- Agent A: scraper/backfill/parser tests, especially the current EX-13 regression.
- Agent B: docs/RSS/audio setup, `.gitignore`, and public-site sanity checks.

If only one agent is available, do the work in this order:

1. Fix failing tests.
2. Add `.mp4` ignore rule.
3. Generate or intentionally remove the missing RSS link.
4. Update stale docs.
5. Continue legacy formatting cleanup with tests.

## Useful Commands

```powershell
git status --short --branch
python -m pytest -q
python -m pytest tests\test_build_pages.py -q
python scripts\build_pages.py --rebuild
python scripts\compressor.py
```

To inspect the ledger:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
import json
from pathlib import Path
ledger = json.loads(Path("docs/ledger.json").read_text(encoding="utf-8"))
filings = ledger["filings"]
print("filings", len(filings))
print("letters", sum(1 for f in filings if f.get("letter_scraped")))
print("audio", sum(1 for f in filings if f.get("audio_compressed")))
print("pages", sum(1 for f in filings if f.get("page_built")))
print("skips", sum(1 for f in filings if f.get("skip_reason")))
'@ | python -
```
