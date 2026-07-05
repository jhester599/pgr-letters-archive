# PGR Shareholder Podcast

An automated pipeline that transforms Progressive Corporation (NYSE: PGR) CEO Tricia
Griffith's quarterly shareholder letters into an accessible podcast archive hosted on
GitHub Pages.

The pipeline polls SEC EDGAR, extracts "Exhibit 99" (the CEO's letter) from 10-Q and
10-K filings, generates a ranked analyst summary, produces a podcast-style audio overview
via Google NotebookLM (using the letter and summary as sources), generates a verbatim
read-through via Kokoro TTS, and publishes everything to a static web front-end with an
embedded audio player and RSS feed — fully automated via GitHub Actions.

**Live site:** https://jhester599.github.io/pgr-letters-archive/

---

## Pipeline overview

```
SEC EDGAR (public API)
        │
        ▼
  scraper.py / backfill scripts
  Fetches 10-Q & 10-K filings, extracts Exhibit 99, saves cleaned .txt files
        │
        ▼
  summarizer.py
  Calls GitHub Models API to generate a ranked 10-bullet summary JSON for each letter
        │
        ▼
  generator.py
  Uploads letter + summary to Google NotebookLM, generates Audio Overview, downloads raw audio
        │
        ▼
  tts.py
  Synthesizes a verbatim read-through MP3 via Kokoro TTS (local inference, no API key)
        │
        ▼
  compressor.py
  FFmpeg re-encodes NotebookLM audio to 64 kbps MP3, uploads it to GitHub Releases,
  records the release URL in the ledger, and regenerates the podcast RSS feed
        │
        ▼
  build_pages.py
  Generates per-letter HTML reading pages under docs/letters/
        │
        ▼
  GitHub Pages
  Serves docs/ as a static web app — episode list, dual audio players, letter text, summaries
```

Two GitHub Actions workflows drive the automation:

- **`quarterly_podcast.yml`** — Fires on new SEC filings (email trigger or Friday cron).
  Runs the full pipeline: scrape → summarize → NotebookLM → TTS → compress → build → publish.
- **`daily_audio_backfill.yml`** — Runs daily at 10:00 UTC to burn down the historical
  audio backlog at ~3 letters/day (NotebookLM free-tier quota). See `AUDIO_PROGRESS.md`
  for current status.

---

## Repository structure

```
.github/
  workflows/
    quarterly_podcast.yml      — Full pipeline for new filings
    daily_audio_backfill.yml   — Daily NotebookLM backlog runner
data/
  letters/                     — Cleaned .txt letter files (committed)
  summaries/                   — 10-bullet JSON summaries (committed)
  audio_raw/                   — Temporary raw audio from NotebookLM (gitignored)
docs/                          — GitHub Pages web root
  index.html                   — Single-page front-end
  ledger.json                  — Pipeline state ledger (also read by the front-end)
  audio/                       — Local staging for NotebookLM MP3s (gitignored)
  audio_tts/                   — Local staging for Kokoro TTS MP3s (gitignored)
  feed.xml                     — Podcast RSS feed (regenerated each run)
  letters/                     — Per-letter HTML reading pages
scripts/
  scraper.py                   — Recent filings scraper (last ~3 years)
  backfill.py                  — Full historical EDGAR scraper
  backfill_ex13.py             — EX-13 backfill for pre-2004 annual letters
  backfill_ex99.py             — EX-99 backfill for quarterly letters
  summarizer.py                — GitHub Models API summary generator
  generator.py                 — NotebookLM audio generation
  tts.py                       — Kokoro TTS verbatim read-through generation
  compressor.py                — FFmpeg compression + RSS feed generation
  build_pages.py               — Per-letter HTML reading page generator
  audio_progress.py            — Generates AUDIO_PROGRESS.md backfill tracker
  gmail_trigger.js             — Apps Script that fires the Actions workflow on filing alerts
  setup_notebooklm.ps1         — One-time Windows NotebookLM auth setup
requirements.txt
AUDIO_PROGRESS.md              — Live backfill progress tracker (auto-updated by CI)
AUDIO_STORAGE.md               — Audio release hosting, backups, and recovery steps
PLAN.md                        — Architecture, data model, technical decisions
CLAUDE.md                      — Developer reference and run checklist
NOTEBOOKLM_SETUP.md            — How to capture and store the NotebookLM auth secret
```

---

## Quick start

### Prerequisites

```bash
# Python 3.12 required (kokoro is not compatible with 3.13+)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo apt-get install -y ffmpeg espeak-ng   # or: brew install ffmpeg espeak-ng
```

On Windows, use `py -3.12 -m venv .venv` and see `CLAUDE.md` for full setup.

### 1. Scrape recent filings

```bash
python scripts/scraper.py
```

Fetches the most recent ~40 EDGAR filings and extracts any 10-Q / 10-K Exhibit 99
letters not already in the ledger. Expect 8–12 letters covering roughly the last 3 years.

### 2. Generate summaries

```bash
# Requires a GitHub personal access token (free; no special scopes needed)
export GITHUB_TOKEN="your_token_here"
python scripts/summarizer.py
```

Produces `data/summaries/{id}_Summary.json` for each letter — a ranked 10-bullet JSON
used as a second source document in NotebookLM to focus the hosts on key metrics.

### 3. Generate NotebookLM podcast audio

```bash
# Authenticate first (one-time — opens a real browser for Google sign-in)
notebooklm login
export NOTEBOOKLM_AUTH_JSON="$(cat ~/.notebooklm/profiles/default/storage_state.json)"

python scripts/generator.py --max-new 1
```

### 4. Generate TTS read-through audio

```bash
python scripts/tts.py --max-new 1
```

Downloads the Kokoro model (~350 MB, cached after first run) and synthesizes a verbatim
MP3. Default voice: `am_michael`. See `CLAUDE.md` for voice options and audition workflow.

### 5. Compress and publish

```bash
export PAGES_BASE_URL="https://jhester599.github.io/pgr-letters-archive"
export GITHUB_TOKEN="your_token_here"  # optional locally; provided automatically in Actions
python scripts/compressor.py
python scripts/build_pages.py
```

Outputs a local 64 kbps MP3 to `docs/audio/`, uploads public audio to the
`audio-library` GitHub Release when `GITHUB_TOKEN` is available, writes release
URLs into `docs/ledger.json`, builds per-letter HTML pages in `docs/letters/`,
and writes `docs/feed.xml`.

Do not commit MP3 files. `docs/audio/*.mp3` and `docs/audio_tts/*.mp3` are local
staging files; public playback should come from release URLs in the ledger. See
`AUDIO_STORAGE.md` for the storage policy and recovery commands.

### 6. Preview locally

```bash
cd docs && python -m http.server 8000
# Open http://localhost:8000
```

### Full historical backfill

```bash
python scripts/backfill.py --dry-run   # preview without downloading
python scripts/backfill.py             # download all available PGR filings from EDGAR
python scripts/summarizer.py           # summarize all letters
python scripts/generator.py --max-new 0  # generate all NotebookLM audio (respects quota)
python scripts/tts.py --max-new 0        # generate all TTS audio
```

---

## Podcast audio versions

Each ledger entry records an `audio_version` field:

| Version | Description |
|---------|-------------|
| `1.0` | Letter + background context preamble only |
| `1.1` | Letter + background context preamble + ranked summary as a second NotebookLM source |

All letters processed from mid-May 2026 onward are v1.1. See `AUDIO_PROGRESS.md` for
per-letter version tracking.

---

## GitHub Actions setup

### 1. Allow the workflow to push commits

`Settings → Actions → General → Workflow permissions → Read and write`

### 2. Add the NotebookLM auth secret

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Value |
|--------|-------|
| `NOTEBOOKLM_AUTH_JSON` | Full contents of `~/.notebooklm/profiles/default/storage_state.json` |

See `NOTEBOOKLM_SETUP.md` for step-by-step instructions. Session cookies expire every
few weeks — re-run `notebooklm login` and update the secret when `generator.py` logs an
auth error. `GITHUB_TOKEN` is provided automatically.

### 3. Enable GitHub Pages

`Settings → Pages → Source: Deploy from a branch → Branch: main, Folder: /docs`

---

## Documentation

| File | Contents |
|------|----------|
| `CLAUDE.md` | Developer reference: local setup, run checklist, ledger schema, common tasks |
| `PLAN.md` | Full architecture plan, data model, technical decisions |
| `AUDIO_PROGRESS.md` | Live backfill progress — letters done, pending, versions, ETA |
| `AUDIO_STORAGE.md` | GitHub Releases audio hosting, Google Drive/local backups, recovery commands |
| `NOTEBOOKLM_SETUP.md` | How to capture Google session credentials for CI |
| `ROADMAP.md` | Planned future features |
