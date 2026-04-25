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
scripts/
  scraper.py        — SEC EDGAR downloader
  generator.py      — NotebookLM audio generation
  compressor.py     — FFmpeg compression + RSS generation
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
    "letter_scraped":        true,
    "audio_generated":       true,
    "audio_compressed":      true,
    "processed_date":        "2025-04-15T12:00:00Z",
    "audio_generated_date":  "2025-04-15T13:00:00Z",
    "audio_compressed_date": "2025-04-15T13:30:00Z"
  }]
}
```

Flag lifecycle: `letter_scraped` → `audio_generated` → `audio_compressed`

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

**Add a podcast cover image:**
Place a `cover.png` (3000×3000 px recommended) in `docs/`. The RSS feed references it at
`{base_url}/cover.png`.

## GitHub Pages setup

1. Repo Settings → Pages → Source: **Deploy from a branch**
2. Branch: `main`, Folder: `/docs`
3. Save. The site deploys at `https://jhester599.github.io/pgr-letters-archive/`
