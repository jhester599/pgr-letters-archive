# Implementation Plan — PGR Letters Archive

## Overview

An automated, serverless pipeline that transforms Progressive Corporation (NYSE: PGR)
CEO Tricia Griffith's quarterly shareholder letters into a publicly accessible podcast
archive, hosted on GitHub Pages.

---

## Architecture

```
SEC EDGAR (public API)
        │
        ▼
  [scraper.py]
  Fetches 10-Q / 10-K filings, extracts Exhibit 99, saves cleaned .txt files
        │
        ▼  data/letters/PGR_YYYY_QN_Letter.txt
  [generator.py]
  Uploads text to Google NotebookLM (via Playwright browser automation),
  triggers Audio Overview generation, downloads raw MP3
        │
        ▼  data/audio_raw/PGR_YYYY_QN_Letter.mp3
  [compressor.py]
  FFmpeg re-encodes to 64 kbps, saves to docs/audio/, deletes raw file,
  regenerates docs/feed.xml RSS feed
        │
        ▼  docs/audio/ + docs/feed.xml + docs/ledger.json
  [GitHub Pages]
  Serves docs/ as a static web app (index.html + embedded audio player)
        │
        ▼
  [GitHub Actions]
  Cron job (every Friday) runs the full pipeline and commits new files to main
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
- [x] `docs/ledger.json` (initial empty state)
- [x] `scripts/__init__.py`

### Phase 3 — Python Pipeline ✅
- [x] `scripts/scraper.py`
- [x] `scripts/generator.py`
- [x] `scripts/compressor.py`

### Phase 4 — Web Front-End ✅
- [x] `docs/index.html` (self-contained SPA, no external CDN deps)
- [ ] `docs/cover.png` (podcast cover art for RSS feed — to be added manually)

### Phase 5 — Automation ✅
- [x] `.github/workflows/quarterly_podcast.yml`

### Phase 6 — Documentation ✅
- [x] `PLAN.md` (this file)
- [x] `CLAUDE.md` (developer reference)
- [x] `README.md` (user-facing overview)

### Phase 7 — First Run & Backfill ⬜
- [ ] Configure GitHub repository secrets (see below)
- [ ] Enable GitHub Pages (`Settings → Pages → Source: /docs on main`)
- [ ] Run scraper manually to backfill historical letters
- [ ] Run generator + compressor manually for historical backfill
- [ ] Verify feed.xml validates against a podcast validator

---

## Data Model — `docs/ledger.json`

The ledger is the single source of truth for pipeline state and is also
read by `index.html` at runtime for the episode list.

```json
{
  "meta": {
    "last_updated": "2025-04-24T00:00:00Z",
    "total_letters": 12,
    "total_audio": 10,
    "description": "..."
  },
  "filings": [
    {
      "id":                  "PGR_2025_Q1",
      "year":                2025,
      "quarter":             "Q1",
      "form_type":           "10-Q",
      "accession_number":    "0000080661-25-000006",
      "report_date":         "2025-03-31",
      "letter_file":         "data/letters/PGR_2025_Q1_Letter.txt",
      "audio_file":          "docs/audio/PGR_2025_Q1_Letter.mp3",
      "letter_scraped":      true,
      "audio_generated":     true,
      "audio_compressed":    true,
      "processed_date":      "2025-04-15T12:00:00Z",
      "audio_generated_date":"2025-04-15T13:00:00Z",
      "audio_compressed_date":"2025-04-15T13:30:00Z"
    }
  ]
}
```

**Lifecycle flags per filing:**

| Flag                | Set by          | Meaning                                     |
|---------------------|-----------------|---------------------------------------------|
| `letter_scraped`    | scraper.py      | .txt file exists in data/letters/           |
| `audio_generated`   | generator.py    | Raw MP3 exists in data/audio_raw/           |
| `audio_compressed`  | compressor.py   | Compressed MP3 in docs/audio/; raw deleted  |

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
- Uses `notebooklm-py` library with Playwright for browser automation.
- Each letter gets its own fresh notebook (created + deleted per run) to avoid
  source accumulation in the Google account.
- Audio generation timeout: 10 minutes per notebook. 
- Rate limit guard: 10-second pause between submissions.
- Credentials never stored in the repo — always from env vars / GitHub Secrets.

### Audio Compression
- FFmpeg: `-codec:a libmp3lame -b:a 64k` (good voice quality at minimal file size).
- At 64 kbps, a 20-minute overview ≈ 9.6 MB per episode.
- Raw files in `data/audio_raw/` are deleted after successful compression.
- `data/audio_raw/` contents are in `.gitignore` — never committed.

### GitHub Pages
- Source: `/docs` folder on `main` branch.
- `index.html` fetches `ledger.json` at runtime — no build step required.
- `feed.xml` is regenerated on every pipeline run.
- Letter `.txt` files live in `data/letters/` (repo root, not `docs/`).
  The web front-end fetches them with `../data/letters/` relative paths,
  which works when served from `docs/` under GitHub Pages.

### Repository Size
- At 64 kbps × 20 min/episode × 40 quarters ≈ 380 MB — within GitHub's 1 GB repo
  limit. If the archive grows significantly (20+ years of backfill), consider
  GitHub LFS for MP3 files (add `*.mp3 filter=lfs diff=lfs merge=lfs -text` to
  `.gitattributes`).

---

## GitHub Actions Secrets Required

Configure these in `Settings → Secrets and variables → Actions`:

| Secret name            | Value                                               |
|------------------------|-----------------------------------------------------|
| `NOTEBOOKLM_EMAIL`     | Google account email (must have NotebookLM access)  |
| `NOTEBOOKLM_PASSWORD`  | Google account password                             |

The `GITHUB_TOKEN` secret is automatically provided by Actions — no setup needed.
Ensure the workflow has `contents: write` permission (already set in the YAML).

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| NotebookLM UI changes break Playwright automation | Pin `notebooklm-py` version; monitor library releases |
| Google 2FA blocks headless login | Use an app password or a dedicated account with 2FA disabled |
| EDGAR changes Exhibit 99 labeling | The scraper falls back gracefully and logs a skip; manual review triggered |
| GitHub Pages 1 GB limit reached | Switch to GitHub LFS for MP3 files |
| Audio generation timeout (>10 min) | Increase `AUDIO_TIMEOUT` in generator.py; re-run handles gracefully |
| Rate limiting from EDGAR | Exponential backoff already implemented; further increase `REQUEST_DELAY` if needed |

---

## Manual Testing Checklist

```bash
# 1. Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 2. Test the scraper (no credentials needed)
python scripts/scraper.py

# 3. Inspect the ledger
cat docs/ledger.json | python -m json.tool

# 4. Check extracted letters
ls -la data/letters/

# 5. Test audio generation (requires Google credentials)
export NOTEBOOKLM_EMAIL="your@email.com"
export NOTEBOOKLM_PASSWORD="yourpassword"
python scripts/generator.py

# 6. Test compression (requires ffmpeg)
python scripts/compressor.py

# 7. Serve the web front-end locally
cd docs && python -m http.server 8000
# Open http://localhost:8000 in a browser
```
