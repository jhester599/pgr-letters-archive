# CLAUDE.md — PGR Letters Archive

Developer reference for the PGR Letters Archive project.
See `PLAN.md` for the full implementation plan and architecture decisions.

## What this project does

Automated pipeline: SEC EDGAR → text extraction → Google NotebookLM podcast audio +
Kokoro TTS read-through audio → GitHub Pages.

Every Friday a GitHub Actions job:
1. Queries SEC EDGAR for new PGR (Progressive Corporation) 10-Q / 10-K filings
2. Extracts and cleans the CEO's shareholder letter (Exhibit 99)
3. Generates a podcast-style audio overview via NotebookLM
4. Generates a verbatim read-through MP3 via Kokoro TTS (local inference, no API key)
5. Compresses NotebookLM audio to 64 kbps MP3 with FFmpeg
6. Commits everything to `main`, which auto-deploys to GitHub Pages

## Directory structure

```
.github/workflows/quarterly_podcast.yml  — GitHub Actions cron job
data/
  letters/          — Cleaned .txt letter files (committed)
  audio_raw/        — Temporary raw audio from NotebookLM (gitignored)
docs/               — GitHub Pages root (served at /pgr-letters-archive/)
  index.html        — Single-page front-end; reads ledger.json at runtime
  ledger.json       — State ledger; also the front-end's data source
  audio/            — Compressed 64 kbps MP3s from NotebookLM (committed)
  audio_tts/        — Kokoro TTS read-through MP3s (committed)
  feed.xml          — Podcast RSS feed (regenerated each run)
  letters/          — Standalone HTML reading pages (one per letter)
  assets/
    reading.css     — Stylesheet for reading pages
scripts/
  scraper.py        — SEC EDGAR downloader
  generator.py      — NotebookLM audio generation
  compressor.py     — FFmpeg compression + RSS generation
  tts.py            — Kokoro TTS verbatim read-through generation
  build_pages.py    — Per-letter HTML reading page generator
  setup_notebooklm.ps1  — One-time Windows NotebookLM auth setup
requirements.txt
PLAN.md             — Architecture, phases, technical decisions
CLAUDE.md           — This file
```

## Local development setup

### Python version requirement

**Python 3.12 is required.** Kokoro 0.9.x (the TTS engine) requires Python <3.13.
Python 3.13 and 3.14 are not compatible with kokoro's dependency chain (spacy/misaki).

Install Python 3.12 from the Microsoft Store (search "Python 3.12") or from
[python.org/downloads/release/python-31210](https://www.python.org/downloads/release/python-31210/).
Python 3.12 can coexist alongside newer versions on Windows.

Verify available versions with `py --list` and create the venv explicitly:
```cmd
py -3.12 -m venv .venv
```

### Windows system dependencies (one-time installs)

**FFmpeg** (required for audio compression and TTS MP3 encoding):
1. Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) → Windows → gyan.dev → essentials build (`.zip`)
2. Extract and note the `bin/` folder path (e.g. `C:\Program Files\ffmpeg-8.1-essentials_build\bin`)
3. Add that path to **System variables → Path** in Windows environment variables
4. Open a new cmd window and verify: `ffmpeg -version`

**espeak-ng** (required for Kokoro TTS pronunciation of unusual words):
1. Download the `.msi` installer from [github.com/espeak-ng/espeak-ng/releases/latest](https://github.com/espeak-ng/espeak-ng/releases/latest)
2. Run the installer (all defaults are fine)

### Python environment

```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
playwright install chromium
```

### SEC EDGAR scraper (no credentials needed)

```cmd
python scripts/scraper.py
cat docs/ledger.json | python -m json.tool
dir data\letters\
```

### NotebookLM auth (one-time per machine)

Run the setup script (requires PowerShell execution policy allowing scripts):
```powershell
.\scripts\setup_notebooklm.ps1
```

Or manually in cmd.exe:
```cmd
notebooklm login
```
This opens a real browser. Sign in to Google, then close the browser.
Auth is saved automatically to `%USERPROFILE%\.notebooklm\storage_state.json`.

For CI/GitHub Actions, copy the auth JSON to a repository secret:
```powershell
Get-Content "$env:USERPROFILE\.notebooklm\storage_state.json" -Raw | Set-Clipboard
```
Add as secret `NOTEBOOKLM_AUTH_JSON` in GitHub → Settings → Secrets → Actions.

Session cookies expire every few weeks. When `generator.py` fails with an auth
error, re-run `notebooklm login` and update the GitHub secret.

### Audio generation

```cmd
# NotebookLM podcast (requires valid auth session)
python scripts/generator.py --max-new 1

# TTS read-through (no credentials; downloads ~350 MB model on first run)
python scripts/tts.py --max-new 1

# Audition multiple voices on one letter (does not update ledger)
python scripts/tts.py --id PGR_2025_Q4 --sample-voices am_michael am_liam bm_daniel af_heart

# Production run with chosen voice (updates ledger)
python scripts/tts.py --id PGR_2025_Q4 --voice am_michael
```

Kokoro model weights (~350 MB) are downloaded automatically from HuggingFace on
first use and cached at `%USERPROFILE%\.cache\huggingface\hub\`. Synthesis runs at
roughly real-time speed on CPU (~25–35 min for a typical letter).

### Compression + RSS

```cmd
python scripts/compressor.py
```

### Build reading pages

```cmd
python scripts/build_pages.py          # build only new pages
python scripts/build_pages.py --rebuild  # rebuild all (after template/CSS changes)
```

### Serve the web front-end

```cmd
cd docs && python -m http.server 8000
# Open http://localhost:8000
```

## GitHub Secrets required

| Secret | Description |
|--------|-------------|
| `NOTEBOOKLM_AUTH_JSON` | Full contents of `storage_state.json` from `notebooklm login` |

`GITHUB_TOKEN` is provided automatically by Actions — no setup needed.
Enable `contents: write` in repo Settings → Actions → General.

No `OPENAI_API_KEY` is required — TTS uses local Kokoro inference.

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
    "id":                    "PGR_2025_Q4",
    "year":                  2025,
    "quarter":               "Q4",
    "form_type":             "10-K",
    "accession_number":      "0000080661-25-000086",
    "report_date":           "2025-12-31",
    "letter_file":           "data/letters/PGR_2025_Q4_Letter.txt",
    "audio_raw_file":        "data/audio_raw/PGR_2025_Q4_Letter.mp4",
    "audio_file":            "docs/audio/PGR_2025_Q4_Letter.mp3",
    "tts_file":              "docs/audio_tts/PGR_2025_Q4_Letter.mp3",
    "tts_voice":             "am_michael",
    "page_url":              "letters/PGR_2025_Q4.html",
    "letter_scraped":        true,
    "audio_generated":       true,
    "audio_compressed":      true,
    "tts_generated":         true,
    "page_built":            true,
    "processed_date":        "2025-04-15T12:00:00Z",
    "audio_generated_date":  "2025-04-15T13:00:00Z",
    "audio_compressed_date": "2025-04-15T13:30:00Z",
    "tts_generated_date":    "2025-04-15T14:00:00Z"
  }]
}
```

Flag lifecycle: `letter_scraped` → `audio_generated` → `audio_compressed` → `tts_generated` → `page_built`

## Proving the concept — initial run checklist

The recommended approach is to run `scraper.py` first on the recent filing window,
verify the full cycle works end-to-end, and then run the historical backfill.

### Step 1 — Scrape recent filings

```cmd
python scripts/scraper.py
```

Expect 8–12 quarterly letters covering roughly the last 3 years.

**Verify:**
- `data/letters/` contains `.txt` files with readable, clean letter text
- `docs/ledger.json` has entries with `"letter_scraped": true`
- Entries with `"skip_reason": "no_exhibit_99"` are expected — some filings
  don't include the CEO letter as a standalone exhibit

### Step 2 — Generate NotebookLM podcast audio

```cmd
python scripts/generator.py --max-new 1
```

**Verify:**
- `data/audio_raw/` contains a `.mp4` file
- The ledger entry has `"audio_generated": true`

### Step 3 — Generate TTS read-through audio

```cmd
# Audition voices first (files named {id}_{voice}.mp3, no ledger update)
python scripts/tts.py --id PGR_2025_Q4 --sample-voices am_michael am_liam bm_daniel af_heart

# Production run with chosen voice (updates ledger)
python scripts/tts.py --id PGR_2025_Q4 --voice am_michael
```

**Verify:**
- `docs/audio_tts/PGR_2025_Q4_Letter.mp3` exists
- The ledger entry has `"tts_generated": true`

### Step 4 — Compress NotebookLM audio and update RSS

```cmd
python scripts/compressor.py
```

**Verify:**
- `docs/audio/` contains a `.mp3` file (~4–10 MB at 64 kbps)
- `docs/feed.xml` has been created with one episode entry
- The ledger entry has `"audio_compressed": true`

### Step 5 — Check the web front-end

```cmd
cd docs && python -m http.server 8000
```

**Verify:**
- The episode appears in the sidebar list
- Both audio players load (NotebookLM podcast + TTS read-through)
- The letter text loads in the content panel

### Step 6 — Historical backfill (once concept is proven)

```cmd
python scripts/backfill.py --dry-run    # preview what EDGAR has
python scripts/backfill.py              # download full archive
python scripts/generator.py --max-new 0  # generate all NotebookLM audio
python scripts/tts.py --max-new 0        # generate all TTS audio
```

---

## Common tasks

**Re-run scraper without re-downloading existing letters:**
Safe to re-run at any time — checks `already_processed()` by accession number.

**Force re-generation of NotebookLM audio for a specific quarter:**
Set `audio_generated: false` in `ledger.json` and re-run `generator.py`.

**Force re-generation of TTS audio for a specific quarter:**
Set `tts_generated: false` in `ledger.json` and re-run `tts.py`.

**Audition TTS voices without affecting the ledger:**
```cmd
python scripts/tts.py --id PGR_2025_Q4 --sample-voices am_michael bm_daniel af_heart
```
Sample files are named `{id}_{voice}.mp3` in `docs/audio_tts/`.

**Regenerate the RSS feed without a new audio run:**
```cmd
python scripts/compressor.py
```

**Rebuild all reading pages (after CSS or template changes):**
```cmd
python scripts/build_pages.py --rebuild
```

**Add a podcast cover image:**
Place a `cover.png` (3000×3000 px recommended) in `docs/`. The RSS feed references it at
`{base_url}/cover.png`.

## Kokoro TTS voices

Default voice: `am_michael` (American English male). Available English voices:

| Prefix | Language | Gender | Example voices |
|--------|----------|--------|----------------|
| `am_` | American | Male | `am_michael`, `am_liam`, `am_fenrir`, `am_adam`, `am_echo` |
| `af_` | American | Female | `af_heart`, `af_bella`, `af_nova`, `af_sarah`, `af_jessica` |
| `bm_` | British | Male | `bm_daniel`, `bm_george`, `bm_lewis`, `bm_fable` |
| `bf_` | British | Female | `bf_alice`, `bf_emma`, `bf_isabella`, `bf_lily` |

Voice blending: pass a comma-separated list, e.g. `--voice af_heart,af_bella`.

## Recovering letters not filed on EDGAR

Some quarters — particularly 2004–2006 — have no `EX-99` attached to their 10-Q. Progressive
published those letters directly on their investor relations site instead of filing them with the SEC.

### Background: why some quarters are missing

`backfill_ex99.py` marks 10-Q filings as `skip_reason: no_exhibit_99` when the SEC filing index
has no EX-99 document. This is correct: the letters genuinely were not filed. For affected quarters,
the Wayback Machine (web.archive.org) is the source of truth.

### How to find the letters using the Wayback Machine

**Step 1 — CDX API: discover archived files**

```python
import requests, json

HEADERS = {'User-Agent': 'PGR-Letters-Archive jeffrey.r.hester@gmail.com'}

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

Priority order:
1. `letter.html` — cleanest; fetch and strip HTML
2. `pdf/<quarter>QSR.pdf` — full report; use `extract_letter()` from `backfill_ex13.py`
3. `pdf/Progressive-letter.pdf` — annual letter only

**Step 3 — Fetch the archived file**

```python
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
letter_text, method = extract_letter(cleaned)
```

**Step 4 — Update the ledger**

```python
filing.update({
    'letter_file':       f'data/letters/{filing_id}_Letter.txt',
    'audio_file':        f'docs/audio/{filing_id}_Letter.mp3',
    'letter_scraped':    True,
    'audio_generated':   False,
    'audio_compressed':  False,
    'tts_generated':     False,
    'page_built':        False,
    'page_url':          None,
    'extraction_method': 'wayback_html',
    'processed_date':    datetime.now(timezone.utc).isoformat(),
    'skip_reason':       None,
})
save_ledger(ledger)
```

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

The quarterly shareholder letter program began with Q1 2004. The `no_exhibit_99` ledger entries
for 2002–2003 Q1–Q3 are correct and final — no letters exist for those quarters.

## GitHub Pages setup

1. Repo Settings → Pages → Source: **Deploy from a branch**
2. Branch: `main`, Folder: `/docs`
3. Save. The site deploys at `https://jhester599.github.io/pgr-letters-archive/`
