# PGR Shareholder Podcast

An automated pipeline that transforms Progressive Corporation (NYSE: PGR) CEO Tricia
Griffith's quarterly shareholder letters into an accessible podcast archive hosted on
GitHub Pages.

The pipeline polls SEC EDGAR, extracts "Exhibit 99" (the CEO's letter) from 10-Q and
10-K filings, generates a podcast-style audio overview via Google NotebookLM, compresses
it to a lean 64 kbps MP3, and publishes everything to a static web front-end with an
embedded audio player and RSS feed — fully automated via GitHub Actions every Friday.

**Live site:** https://jhester599.github.io/pgr-letters-archive/

---

## Pipeline overview

```
SEC EDGAR (public API)
        │
        ▼
  scraper.py / backfill.py
  Fetches 10-Q & 10-K filings, extracts Exhibit 99, saves cleaned .txt files
        │
        ▼
  generator.py
  Uploads letter text to Google NotebookLM, generates Audio Overview, downloads raw audio
        │
        ▼
  compressor.py
  FFmpeg re-encodes to 64 kbps MP3, regenerates podcast RSS feed
        │
        ▼
  GitHub Pages
  Serves docs/ as a static web app — episode list, audio player, letter text
```

GitHub Actions runs the full pipeline on a **cron schedule every Friday** to catch all
four quarterly filing windows, then commits any new files back to `main`.

---

## Repository structure

```
.github/
  workflows/
    quarterly_podcast.yml     — Weekly cron automation
data/
  letters/                    — Cleaned .txt letter files (committed)
  audio_raw/                  — Temporary raw audio from NotebookLM (gitignored)
docs/                         — GitHub Pages web root
  index.html                  — Single-page front-end
  ledger.json                 — Pipeline state ledger (also read by the front-end)
  audio/                      — Compressed 64 kbps MP3s
  feed.xml                    — Podcast RSS feed (regenerated each run)
scripts/
  scraper.py                  — Recent filings scraper (last ~3 years)
  backfill.py                 — Full historical scraper (all available EDGAR filings)
  generator.py                — NotebookLM audio generation
  compressor.py               — FFmpeg compression + RSS feed generation
requirements.txt
PLAN.md                       — Architecture, data model, risk register
ROADMAP.md                    — Planned future features
CLAUDE.md                     — Developer reference and run checklist
NOTEBOOKLM_SETUP.md           — How to capture and store the auth secret
```

---

## Quick start

### Prerequisites

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo apt-get install -y ffmpeg    # or: brew install ffmpeg
```

### 1. Scrape recent filings (no credentials needed)

```bash
python scripts/scraper.py
```

Fetches the most recent ~40 EDGAR filings and extracts any 10-Q / 10-K Exhibit 99
letters not already in the ledger. Expect 8–12 letters covering roughly the last 3 years.

### 2. Generate one audio overview

```bash
# Authenticate first (one-time — opens a real browser)
notebooklm login
export NOTEBOOKLM_AUTH_JSON="$(cat ~/.notebooklm/profiles/default/storage_state.json)"

python scripts/generator.py --max-new 1
```

### 3. Compress and publish

```bash
python scripts/compressor.py
```

Outputs a 64 kbps MP3 to `docs/audio/` and writes `docs/feed.xml`.

### 4. Preview locally

```bash
cd docs && python -m http.server 8000
# Open http://localhost:8000
```

### Full historical backfill

```bash
# Preview without downloading
python scripts/backfill.py --dry-run

# Download all available PGR filings from EDGAR
python scripts/backfill.py

# Generate audio for everything (no per-run limit)
python scripts/generator.py --max-new 0
```

---

## GitHub Actions setup

The workflow runs automatically. Two things to configure in repo settings:

**1. Allow the workflow to push commits**
`Settings → Actions → General → Workflow permissions → Read and write`

**2. Add the NotebookLM auth secret**
`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Value |
|--------|-------|
| `NOTEBOOKLM_AUTH_JSON` | Full contents of `~/.notebooklm/profiles/default/storage_state.json` |

See `NOTEBOOKLM_SETUP.md` for step-by-step instructions. The `GITHUB_TOKEN` secret
is provided automatically — no setup needed.

**3. Enable GitHub Pages**
`Settings → Pages → Source: Deploy from a branch → Branch: main, Folder: /docs`

---

## Documentation

| File | Contents |
|------|----------|
| `PLAN.md` | Full architecture plan, data model, technical decisions, risk register |
| `ROADMAP.md` | Planned features: per-letter reading pages, verbatim TTS audio |
| `CLAUDE.md` | Developer reference: local setup, run checklist, common tasks |
| `NOTEBOOKLM_SETUP.md` | How to capture Google session credentials for CI |

---

## Roadmap highlights

- **Per-letter reading pages** — Stylized `docs/letters/PGR_YYYY_QN.html` pages with
  long-form reading layout, dark mode, and print/PDF support
- **Verbatim TTS audio** — A second MP3 per letter read word-for-word via a TTS API
  (e.g. OpenAI `tts-1-hd`), published as a separate podcast feed

See `ROADMAP.md` for full details and implementation checklists.
