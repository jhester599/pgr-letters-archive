# CLAUDE.md — PGR Letters Archive

Developer reference for the PGR Letters Archive project.
See `PLAN.md` for the full implementation plan and architecture decisions.

## What this project does

Automated pipeline: SEC EDGAR → text extraction → Google NotebookLM audio → GitHub Pages.

Every Friday a GitHub Actions job:
1. Queries SEC EDGAR for new PGR (Progressive Corporation) 10-Q / 10-K filings
2. Extracts and cleans the CEO's shareholder letter (Exhibit 99)
3. Generates a podcast-style audio overview via NotebookLM
4. Compresses audio to 64 kbps MP3 with FFmpeg
5. Commits everything to `main`, which auto-deploys to GitHub Pages

## Directory structure

```
.github/workflows/quarterly_podcast.yml  — GitHub Actions cron job
data/
  letters/          — Cleaned .txt letter files (committed)
  audio_raw/        — Temporary raw audio from NotebookLM (gitignored)
docs/               — GitHub Pages root (served at /pgr-letters-archive/)
  index.html        — Single-page front-end; reads ledger.json at runtime
  ledger.json       — State ledger; also the front-end's data source
  audio/            — Compressed 64 kbps MP3s (committed)
  feed.xml          — Podcast RSS feed (regenerated each run)
  letters/          — Standalone HTML reading pages (one per letter)
  assets/
    reading.css     — Stylesheet for reading pages
scripts/
  scraper.py        — SEC EDGAR downloader
  generator.py      — NotebookLM audio generation
  compressor.py     — FFmpeg compression + RSS generation
  build_pages.py    — Per-letter HTML reading page generator
requirements.txt
PLAN.md             — Architecture, phases, technical decisions
CLAUDE.md           — This file
```

## Local development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# SEC EDGAR scraper (no credentials needed)
python scripts/scraper.py

# Inspect output
cat docs/ledger.json | python -m json.tool
ls data/letters/

# NotebookLM auth (one-time per machine)
notebooklm login                    # opens a real browser; sign in to Google
export NOTEBOOKLM_AUTH_JSON="$(cat ~/.notebooklm/profiles/default/storage_state.json)"

# Audio generation (credentials required)
python scripts/generator.py --max-new 1

# Compression + RSS update (requires ffmpeg)
sudo apt-get install -y ffmpeg     # or: brew install ffmpeg
python scripts/compressor.py

# Serve the web front-end
cd docs && python -m http.server 8000    # → http://localhost:8000
```

## GitHub Secrets required

| Secret | Description |
|--------|-------------|
| `NOTEBOOKLM_AUTH_JSON` | Playwright storage_state.json (see below) |

`GITHUB_TOKEN` is provided automatically by Actions — no setup needed.
Enable `contents: write` in repo Settings → Actions → General.

### Capturing NOTEBOOKLM_AUTH_JSON

```bash
# Run locally once (opens a real browser):
notebooklm login

# Copy the output to your clipboard:
cat ~/.notebooklm/profiles/default/storage_state.json | pbcopy   # macOS
cat ~/.notebooklm/profiles/default/storage_state.json | xclip    # Linux

# In GitHub: Settings → Secrets → New secret → NOTEBOOKLM_AUTH_JSON
# Paste the full JSON as the value.
```

Session cookies expire every few weeks. When `generator.py` fails with an auth
error, re-run `notebooklm login` and update the secret.

## SEC EDGAR details

- **CIK**: `0000080661` (Progressive Corporation)
- **API base**: `https://data.sec.gov/submissions/CIK0000080661.json`
- **Rate limit**: 10 req/s; the scraper uses 0.15 s delays + exponential backoff on 429
- **Required header**: `User-Agent: PGR-Letters-Archive jhester599@github.com`
- **Exhibit 99**: the CEO's quarterly letter, filed as `EX-99` or `EX-99.1` in both 10-Q and 10-K filings
- **Historical filings**: the submissions JSON returns ~40 most recent. Older filings appear in
  `filings.files[]`; `scraper.py` currently only processes `filings.recent`. A one-time backfill
  script may be needed for the full archive.

## Ledger schema

`docs/ledger.json` tracks each filing through the pipeline:

```json
{
  "meta": { "last_updated": "...", "total_letters": 0, "total_audio": 0 },
  "filings": [{
    "id":                    "PGR_2025_Q1",
    "year":                  2025,
    "quarter":               "Q1",
    "form_type":             "10-Q",
    "accession_number":      "0000080661-25-000006",
    "report_date":           "2025-03-31",
    "letter_file":           "data/letters/PGR_2025_Q1_Letter.txt",
    "audio_raw_file":        "data/audio_raw/PGR_2025_Q1_Letter.mp4",
    "audio_file":            "docs/audio/PGR_2025_Q1_Letter.mp3",
    "page_url":              "letters/PGR_2025_Q1.html",
    "letter_scraped":        true,
    "audio_generated":       true,
    "audio_compressed":      true,
    "page_built":            true,
    "processed_date":        "2025-04-15T12:00:00Z",
    "audio_generated_date":  "2025-04-15T13:00:00Z",
    "audio_compressed_date": "2025-04-15T13:30:00Z"
  }]
}
```

Flag lifecycle: `letter_scraped` → `audio_generated` → `audio_compressed` → `page_built`

## Proving the concept — initial run checklist

The recommended approach is to run `scraper.py` first on the recent filing window,
verify the full cycle works end-to-end, and then run the historical backfill.

### Step 1 — Scrape recent filings

```bash
python scripts/scraper.py
```

Expect 8–12 quarterly letters covering roughly the last 3 years (the EDGAR
`filings.recent` window holds ~40 entries across all form types).

**Verify:**
- `data/letters/` contains `.txt` files with readable, clean letter text
- `docs/ledger.json` has entries with `"letter_scraped": true`
- Any entries with `"skip_reason": "no_exhibit_99"` are expected — some filings
  don't include the CEO letter as a standalone exhibit

### Step 2 — Generate one audio overview

```bash
python scripts/generator.py --max-new 1
```

This processes a single letter to confirm the NotebookLM flow works without
committing to a long batch run.

**Verify:**
- `data/audio_raw/` contains a `.mp4` file
- The ledger entry for that quarter now has `"audio_generated": true`

### Step 3 — Compress and publish

```bash
python scripts/compressor.py
```

**Verify:**
- `docs/audio/` contains a `.mp3` file (~4–10 MB at 64 kbps)
- `docs/feed.xml` has been created with one episode entry
- The ledger entry now has `"audio_compressed": true`

### Step 4 — Check the web front-end

```bash
cd docs && python -m http.server 8000
# Open http://localhost:8000 in a browser
```

**Verify:**
- The episode appears in the sidebar list
- The audio player loads and plays the compressed MP3
- The letter text loads in the content panel

### Step 5 — Historical backfill (once concept is proven)

```bash
# Preview everything EDGAR has, without downloading
python scripts/backfill.py --dry-run

# Download the full archive
python scripts/backfill.py

# Generate audio for all backfilled letters
python scripts/generator.py --max-new 0
```

---

## Common tasks

**Re-run scraper without re-downloading existing letters:**
The scraper checks `already_processed()` by accession number, so it's safe to re-run at any time.

**Force re-generation of audio for a specific quarter:**
Set `audio_generated: false` on the filing in `ledger.json` and re-run `generator.py`.

**Backfill all historical letters (one-time):**
```bash
# Preview everything EDGAR has, without downloading
python scripts/backfill.py --dry-run

# Download all available filings (may take several minutes)
python scripts/backfill.py

# Limit to a specific year range
python scripts/backfill.py --from-year 2010

# After backfill, generate audio for everything (no per-run limit)
python scripts/generator.py --max-new 0
```
`backfill.py` paginates through all of EDGAR's historical pages for PGR, not just
the most-recent ~40 filings that `scraper.py` covers. It shares the same ledger and
letter directory, and is fully idempotent — safe to re-run at any time.

**Regenerate the RSS feed without a new audio run:**
```bash
python scripts/compressor.py   # no pending audio → skips compression, still writes feed.xml
```

**Rebuild all reading pages (after CSS or template changes):**
```bash
python scripts/build_pages.py --rebuild
```

**Build only new reading pages (standard run):**
```bash
python scripts/build_pages.py
```

**Add a podcast cover image:**
Place a `cover.png` (3000×3000 px recommended) in `docs/`. The RSS feed references it at
`{base_url}/cover.png`.

## Recovering letters not filed on EDGAR

Some quarters — particularly 2004–2006 — have no `EX-99` attached to their 10-Q. Progressive
published those letters directly on their investor relations site instead of filing them with the SEC.

### Background: why some quarters are missing

`backfill_ex99.py` marks 10-Q filings as `skip_reason: no_exhibit_99` when the SEC filing index
has no EX-99 document. This is correct: the letters genuinely were not filed. For affected quarters,
the Wayback Machine (web.archive.org) is the source of truth.

### How to find the letters using the Wayback Machine

**Step 1 — CDX API: discover archived files**

The CDX API lets you query what the Wayback Machine has crawled without fetching full pages:

```python
import requests, json

HEADERS = {'User-Agent': 'PGR-Letters-Archive jeffrey.r.hester@gmail.com'}

# List all archived files under a quarterly directory
quarter = '06Q1_quarterly'   # format: YYQ#_quarterly
url = (f'http://web.archive.org/cdx/search/cdx'
       f'?url=investors.progressive.com/{quarter}/*'
       f'&output=json&fl=timestamp,original,statuscode,mimetype'
       f'&filter=statuscode:200&collapse=original&limit=50')
rows = requests.get(url, headers=HEADERS, timeout=30).json()
for ts, orig, sc, mt in rows[1:]:
    print(ts, orig.split(quarter + '/')[-1])
```

Progressive's quarterly report directories were named `YYQ#_quarterly`
(e.g., `05Q1_quarterly`, `06Q2_quarterly`) at `investors.progressive.com`.
Each directory held:
- `letter.html` — the standalone CEO letter page (HTML, not Flash)
- `pdf/NQYYqsr.pdf` — the full Quarterly Shareholders Report PDF (e.g., `1Q05QSR.pdf`)
- `pdf/Progressive-letter.pdf` — a standalone letter PDF (seen in annual quarters)
- `flash/` — interactive financial pages (Flash, unextractable)

**Step 2 — Identify the right file**

Priority order for letter content:
1. `letter.html` — cleanest; fetch and strip HTML
2. `pdf/<quarter>QSR.pdf` — full report; use `extract_letter()` from `backfill_ex13.py`
3. `pdf/Progressive-letter.pdf` — annual letter (only in annual-report quarters)

**Step 3 — Fetch the archived file**

```python
# Construct Wayback URL from CDX timestamp + original URL
wb_url = f'http://web.archive.org/web/{timestamp}/{original_url}'
resp = requests.get(wb_url, headers=HEADERS, timeout=90)
```

For HTML letters:
```python
from bs4 import BeautifulSoup
import re
soup = BeautifulSoup(resp.text, 'lxml')
for tag in soup(['script', 'style', 'head', 'meta', 'link']):
    tag.decompose()
text = re.sub(r'\n{3,}', '\n\n', '\n'.join(
    l.strip() for l in soup.get_text('\n').splitlines() if l.strip()
)).strip()
```

For PDF letters:
```python
import io
from pdfminer.high_level import extract_text as pdf_extract_text
from backfill_ex13 import extract_letter

raw = pdf_extract_text(io.BytesIO(resp.content))
lines = [l.strip() for l in raw.splitlines() if l.strip()]
cleaned = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
letter_text, method = extract_letter(cleaned)   # finds 'Letter to Shareholders' heading
```

**Step 4 — Update the ledger**

After saving the `.txt` file to `data/letters/`, update the ledger entry:
```python
filing.update({
    'letter_file':       f'data/letters/{filing_id}_Letter.txt',
    'audio_file':        f'docs/audio/{filing_id}_Letter.mp3',
    'letter_scraped':    True,
    'audio_generated':   False,
    'audio_compressed':  False,
    'page_built':        False,
    'page_url':          None,
    'extraction_method': 'wayback_html',   # or 'pdf_letter_section'
    'processed_date':    datetime.now(timezone.utc).isoformat(),
    'skip_reason':       None,
})
save_ledger(ledger)
```

Then run `python scripts/build_pages.py` to generate the HTML reading page.

### Known letter sources by era

| Era | SEC filing | Letter location | Status |
|-----|-----------|-----------------|--------|
| 2006 Q2+ | EX-99 in 10-Q/10-K | `backfill_ex99.py` / `scraper.py` handle this | ✅ complete |
| 2005 Q1–Q3 | No EX-99 | Wayback: `05Q#_quarterly/pdf/NQ05QSR.pdf` | ✅ recovered |
| 2006 Q1 | No EX-99 | Wayback: `06Q1_quarterly/letter.html` | ✅ recovered |
| 2004 Q1–Q3 | No EX-99 | Wayback: `04Q#_quarterly/noflash/letter.html` | ✅ recovered |
| 2001–2004 annual | EX-13 (HTML) in 10-K | `backfill_ex13.py` handles this | ✅ complete |
| 1993–2000 annual | EX-13 (SGML bundle) in 10-K | `backfill_ex13.py` handles this | ✅ complete |
| 2002–2004 annual | EX-13 only had financials | `backfill_ex13.py` falls back to progressive.com PDF | ✅ complete |
| Pre-2004 quarterly | **Did not exist** | Progressive only published annual letters before 2004 | n/a |
| 2002–2003 Q1–Q3 | No EX-99 | Quarterly letters were not published in this era | confirmed absent |

### Research conclusion: quarterly letters started in 2004

The quarterly shareholder letter program began with Q1 2004. Evidence:
- The `investors.progressive.com` reports archive (as of Dec 2004) explicitly lists `04Q1_quarterly`,
  `04Q2_quarterly`, `04Q3_quarterly` quarterly reports — but only `03_annual`, `02_annual.asp`,
  `01_annual.asp`, `00_annual.asp` for prior years.
- Wayback Machine CDX shows `03Q1_quarterly`, `03Q2_quarterly`, `03Q3_quarterly` were
  **never crawled** (not archived), consistent with those directories not existing.
- 2002 and 2003 EDGAR 10-Q filings contain only the main form and ratio exhibits — no EX-99,
  no shareholder letter of any kind.
- Before 2004, Progressive issued one letter per year in the annual report to shareholders,
  delivered as EX-13 with the 10-K filing (handled by `backfill_ex13.py`).

The `no_exhibit_99` ledger entries for 2002–2003 Q1–Q3 are correct and final — no letters exist.

**Add a podcast cover image:**
Place a `cover.png` (3000×3000 px recommended) in `docs/`. The RSS feed references it at
`{base_url}/cover.png`.

## GitHub Pages setup

1. Repo Settings → Pages → Source: **Deploy from a branch**
2. Branch: `main`, Folder: `/docs`
3. Save. The site deploys at `https://jhester599.github.io/pgr-letters-archive/`
