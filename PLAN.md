# Implementation Plan — PGR Letters Archive

## Overview

An automated, serverless pipeline that transforms Progressive Corporation (NYSE: PGR)
CEO Tricia Griffith's quarterly shareholder letters into a publicly accessible archive
with two audio tracks per letter — a NotebookLM AI podcast and a Kokoro TTS read-through —
hosted on GitHub Pages.

---

## Architecture

```
SEC EDGAR (public API)
        │
        ▼
  [scraper.py]
  Fetches 10-Q / 10-K filings, extracts Exhibit 99, saves cleaned .txt files
        │
        ├─────────────────────────────────────────┐
        ▼                                         ▼
  [generator.py]                            [tts.py]
  Uploads text to Google NotebookLM         Synthesizes full letter text locally
  (via notebooklm-py Playwright client),    using Kokoro 82M model (CPU inference,
  triggers Audio Overview generation,       no API key). Encodes to 64 kbps MP3
  downloads raw MP4/AAC audio               via FFmpeg.
        │                                         │
        ▼  data/audio_raw/*.mp4                   ▼  docs/audio_tts/*.mp3
  [compressor.py]
  FFmpeg re-encodes NotebookLM MP4 to
  64 kbps MP3, saves to docs/audio/,
  regenerates docs/feed.xml RSS feed
        │
        ▼  docs/audio/*.mp3 + docs/feed.xml + docs/ledger.json
  [build_pages.py]
  Generates per-letter HTML reading pages with dual audio players
        │
        ▼  docs/letters/*.html
  [GitHub Pages]
  Serves docs/ as a static web app (index.html + audio players + reading pages)
        │
        ▼
  [GitHub Actions]
  Triggered by Gmail alert or weekly cron; runs full pipeline, commits to main
```

---

## Implementation Phases

### Phase 1 — Foundation ✅
- [x] Repository created on GitHub (`jhester599/pgr-letters-archive`)
- [x] `plan-v0.md` initial prompt committed
- [x] `README.md` architecture overview
- [x] Feature branch `claude/initial-project-planning-2c6Yn` created

### Phase 2 — Directory Scaffold ✅
- [x] `.gitignore`
- [x] `requirements.txt`
- [x] `data/letters/.gitkeep`
- [x] `data/audio_raw/.gitkeep`
- [x] `docs/audio/.gitkeep`
- [x] `docs/audio_tts/.gitkeep`
- [x] `docs/ledger.json` (initial empty state)
- [x] `scripts/__init__.py`

### Phase 3 — Python Pipeline ✅
- [x] `scripts/scraper.py` — SEC EDGAR downloader
- [x] `scripts/generator.py` — NotebookLM audio (notebooklm-py v0.3.4 async API)
- [x] `scripts/compressor.py` — FFmpeg compression + RSS generation
- [x] `scripts/tts.py` — Kokoro TTS verbatim read-through (with --sample-voices mode)
- [x] `scripts/build_pages.py` — per-letter HTML pages with dual audio players
- [x] `scripts/setup_notebooklm.ps1` — one-time Windows auth setup helper

### Phase 4 — Web Front-End ✅
- [x] `docs/index.html` (self-contained SPA, no external CDN deps)
- [x] `docs/letters/` — per-letter reading pages with dual audio players
- [x] `docs/assets/reading.css`
- [ ] `docs/cover.png` (podcast cover art for RSS feed — to be added manually)

### Phase 5 — Automation ✅
- [x] `.github/workflows/quarterly_podcast.yml`
- [x] Gmail Apps Script trigger (`scripts/gmail_trigger.js`)

### Phase 6 — Documentation ✅
- [x] `PLAN.md` (this file)
- [x] `CLAUDE.md` (developer reference)
- [x] `README.md` (user-facing overview)

### Phase 7 — First Run & Validation 🔄
- [x] GitHub Pages enabled (`Settings → Pages → /docs on main`)
- [x] `NOTEBOOKLM_AUTH_JSON` secret configured
- [x] PGR_2025_Q4 NotebookLM podcast generated and live
- [x] PGR_2025_Q4 reading page deployed with dual audio players (podcast + TTS)
- [x] TTS voice selected for Tricia Griffith era (Q3 2016–present): `af_heart`
- [x] TTS production run complete for PGR_2025_Q4 (`af_heart`)
- [x] PDF artifact cleanup across all 99 letters (page numbers, ®/SM symbols, superscripts, hard-wrapped paragraphs)
- [ ] Voice sampling in progress: Glenn Renwick era (2001–Q2 2016) — run `--sample-voices` on PGR_2010_Q4
- [ ] Voice sampling in progress: Peter Lewis era (1993–2000) — run `--sample-voices` on PGR_1998_Q4
- [ ] Select final voices for Glenn and Peter eras; update `tts.py` author-aware voice logic
- [ ] Verify `feed.xml` validates against a podcast validator

### Phase 8 — Historical Audio Backfill ⬜

Prerequisites must be completed in order before running the batch.

#### Step 1 — Complete text review (manual)
- [ ] Work through `audit_report.txt` (620 short orphan lines across 70 files, 1 repeated word, 1 duplicate line)
- [ ] Report findings; apply programmatic fixes to affected `.txt` files
- [ ] Manual spot-check of financial table data in PGR_2003_Q4 and PGR_2004_Q4 (table rows merged into prose will sound wrong in TTS)

#### Step 2 — Finalize TTS voice configuration
- [ ] Listen to Glenn Renwick sample voices (PGR_2010_Q4); choose preferred voice
- [ ] Listen to Peter Lewis sample voices (PGR_1998_Q4); choose preferred voice
- [ ] Update `tts.py` to auto-select voice by author era:
  - Peter Lewis (1993–2000): `<chosen>`
  - Glenn Renwick (2001–Q2 2016): `<chosen>`
  - Tricia Griffith (Q3 2016–present): `af_heart`

#### Step 3 — Consider GitHub LFS before batch run
- [ ] Evaluate repo size: 99 NotebookLM MP3s (~950 MB) + 99 TTS MP3s (~1.4 GB) ≈ 2.2 GB total
- [ ] Enable GitHub LFS for `*.mp3` if approaching 1 GB limit:
  ```
  git lfs track "*.mp3"
  git add .gitattributes
  ```

#### Step 4 — NotebookLM batch
- [ ] `python scripts/generator.py --max-new 0`  (processes all letters without `audio_generated: true`)

#### Step 5 — TTS batch
- [ ] `python scripts/tts.py --max-new 0`  (processes all letters without `tts_generated: true`, uses author-aware voice)

#### Step 6 — Rebuild and deploy
- [ ] `python scripts/build_pages.py --rebuild`
- [ ] `python scripts/compressor.py`  (regenerates `feed.xml` with all episodes)
- [ ] Commit and push; verify GitHub Pages deploys cleanly
- [ ] Validate `feed.xml` at a podcast validator (e.g., podba.se/validate)

#### Step 7 — Polish
- [ ] Add `docs/cover.png` (3000×3000 px) for podcast cover art in RSS feed

---

## Data Model — `docs/ledger.json`

The ledger is the single source of truth for pipeline state and is also
read by `index.html` at runtime for the episode list.

```json
{
  "meta": {
    "last_updated": "2025-04-24T00:00:00Z",
    "total_letters": 99,
    "total_audio": 1
  },
  "filings": [
    {
      "id":                    "PGR_2025_Q4",
      "year":                  2025,
      "quarter":               "Q4",
      "form_type":             "10-K",
      "accession_number":      "0000080661-26-000086",
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
      "processed_date":        "2026-04-25T20:07:00Z",
      "audio_generated_date":  "2026-05-02T13:14:48Z",
      "audio_compressed_date": "2026-05-02T13:54:25Z",
      "tts_generated_date":    "2026-05-02T15:00:00Z"
    }
  ]
}
```

**Lifecycle flags per filing:**

| Flag                | Set by          | Meaning                                          |
|---------------------|-----------------|--------------------------------------------------|
| `letter_scraped`    | scraper.py      | `.txt` file exists in `data/letters/`            |
| `audio_generated`   | generator.py    | Raw `.mp4` exists in `data/audio_raw/`           |
| `audio_compressed`  | compressor.py   | Compressed `.mp3` in `docs/audio/`               |
| `tts_generated`     | tts.py          | TTS `.mp3` in `docs/audio_tts/`                  |
| `page_built`        | build_pages.py  | HTML reading page in `docs/letters/`             |

---

## Technical Decisions

### SEC EDGAR API
- Uses `data.sec.gov/submissions/CIK{cik}.json` (JSON, no scraping required).
- Progressive Corporation CIK: `0000080661`.
- Required `User-Agent` header: `PGR-Letters-Archive jhester599@github.com`.
- Rate limit: 10 req/s. Script uses 0.15 s delay between requests.
- Exhibit 99 is the CEO's letter; located in the filing document index as type `EX-99` or `EX-99.1`.
- Quarter mapping: 10-Q with period end ≤ March = Q1, ≤ June = Q2, otherwise Q3; 10-K = Q4.

### NotebookLM Integration
- Uses `notebooklm-py` (v0.3.4+) with Playwright for browser automation.
- Client requires async context manager: `async with await NotebookLMClient.from_storage() as client`.
- Auth stored at `~/.notebooklm/storage_state.json` by `notebooklm login`.
- Auth resolution order: `NOTEBOOKLM_AUTH_JSON` env var → `NOTEBOOKLM_AUTH_FILE` env var → default file.
- Each letter gets its own fresh notebook (created + deleted per run) to avoid
  source accumulation in the Google account.
- Audio generation timeout: 15 minutes per notebook.
- Rate limit guard: 10-second pause between submissions.
- Credentials never stored in the repo — always from env vars / GitHub Secrets.
- Session cookies expire every few weeks; re-run `notebooklm login` to refresh.

### Kokoro TTS Integration
- Uses `kokoro` (v0.9.x) for local speech synthesis — no API key or cost.
- **Python 3.12 required**: kokoro 0.9.x depends on spacy/misaki which have no Python 3.13+ wheels.
- Model: Kokoro-82M (~350 MB), auto-downloaded from HuggingFace on first use.
- Device: CPU (no GPU required). Synthesis speed: ~real-time on modern hardware.
- Output: 24 kHz mono WAV → FFmpeg → 64 kbps MP3.
- `--sample-voices` mode generates one MP3 per voice for audition without updating the ledger.
- Default voice: `am_michael` (American English male).
- Windows prerequisite: espeak-ng MSI installer for correct pronunciation of OOD words.

### Audio Compression
- FFmpeg: `-codec:a libmp3lame -b:a 64k` (good voice quality at minimal file size).
- At 64 kbps, a 20-minute overview ≈ 9.6 MB per episode.
- Raw NotebookLM files in `data/audio_raw/` are deleted after successful compression.
- `data/audio_raw/` contents are in `.gitignore` — never committed.
- TTS files are encoded directly to MP3 by `tts.py` via FFmpeg; no intermediate raw files.

### GitHub Pages
- Source: `/docs` folder on `main` branch.
- `index.html` fetches `ledger.json` at runtime — no build step required.
- `feed.xml` is regenerated on every pipeline run.
- Each letter has a reading page at `docs/letters/{id}.html` with two audio players:
  - **AI Podcast Overview** — NotebookLM MP3 from `docs/audio/`
  - **Read-Through Audio** — Kokoro TTS MP3 from `docs/audio_tts/`

### Repository Size
- NotebookLM MP3 at 64 kbps × 20 min/episode × 99 letters ≈ 950 MB.
- TTS MP3 at 64 kbps × 30 min/letter × 99 letters ≈ 1.4 GB.
- Combined archive will exceed GitHub's 1 GB soft limit once both tracks are complete.
- Plan: enable GitHub LFS for `*.mp3` files before the full backfill batch:
  ```
  git lfs track "*.mp3"
  git add .gitattributes
  ```

---

## GitHub Actions Secrets Required

Configure these in `Settings → Secrets and variables → Actions`:

| Secret name            | Value                                                              |
|------------------------|--------------------------------------------------------------------|
| `NOTEBOOKLM_AUTH_JSON` | Full contents of `~/.notebooklm/storage_state.json` from `notebooklm login` |

`GITHUB_TOKEN` is automatically provided by Actions — no setup needed.
No `OPENAI_API_KEY` is required; TTS uses local Kokoro inference in CI.

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| NotebookLM UI changes break Playwright automation | Pin `notebooklm-py` version; monitor library releases |
| notebooklm-py API changes between versions | Use async context manager pattern; read library source before upgrading |
| Google session expiry blocks CI | Refresh `notebooklm login` locally and update `NOTEBOOKLM_AUTH_JSON` secret |
| EDGAR changes Exhibit 99 labeling | Scraper falls back gracefully and logs a skip; manual review triggered |
| kokoro Python version cap | Requires Python 3.12; 3.13/3.14 breaks spacy dependency chain |
| Repository size limit (1 GB) | Enable GitHub LFS for `*.mp3` before running full 99-letter audio backfill |
| TTS synthesis time in CI | Kokoro CPU synthesis ~30 min/letter; acceptable at `--max-new 1` per scheduled run |
| Rate limiting from EDGAR | Exponential backoff already implemented |

---

## Manual Testing Checklist

```cmd
# 1. Set up Python 3.12 environment (3.13/3.14 not compatible with kokoro)
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
playwright install chromium

# 2. Install system dependencies (Windows, one-time)
# FFmpeg: add bin/ folder to System PATH
# espeak-ng: run MSI installer

# 3. Test the scraper (no credentials needed)
python scripts/scraper.py

# 4. Inspect the ledger
python -m json.tool docs\ledger.json

# 5. Test NotebookLM audio generation (requires notebooklm login)
notebooklm login
python scripts/generator.py --id PGR_2025_Q4

# 6. Test TTS audio (no credentials; downloads model ~350 MB on first run)
python scripts/tts.py --id PGR_2025_Q4 --sample-voices am_michael bm_daniel
python scripts/tts.py --id PGR_2025_Q4 --voice am_michael

# 7. Test compression
python scripts/compressor.py

# 8. Build reading pages
python scripts/build_pages.py --rebuild

# 9. Serve the web front-end locally
cd docs && python -m http.server 8000
# Open http://localhost:8000
```
