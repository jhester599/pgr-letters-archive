# Roadmap — PGR Letters Archive

Long-range feature ideas, grouped by area.

For the near-term to-do list — what to actually work on next, with current
state and commands — see `NEXT_STEPS.md`. This file is the idea backlog.

Features 1 and 2 below are **already built**; their design notes are kept for
reference. Everything under "Other Future Enhancements" is still unbuilt.

---

## Feature 1 — Per-Letter Reading Pages ✅ SHIPPED

**Goal:** Generate a stylized, standalone HTML page for each quarterly letter so
readers can engage with the original text in a polished, distraction-free format
rather than reading raw plain text in the current sidebar panel.

### What this involves

A new script (`scripts/build_pages.py`) would iterate the ledger and render a
dedicated HTML page for each letter with full `docs/letters/PGR_YYYY_QN.html`
paths served by GitHub Pages.

### Page design
- Clean long-form reading layout: centered content column, generous line-height,
  serif body font (e.g. Georgia / Palatino)
- Header with filing metadata: quarter, year, form type, period-of-report date
- Sticky progress bar showing read position
- Previous / Next navigation between letters
- Back link to the main archive index
- Embedded audio player (NotebookLM overview) at the top of the page, collapsed by default
- Print-friendly CSS (`@media print`) for clean PDF export
- Dark mode toggle, persisted via `localStorage`

### Integration with the existing pipeline

1. `build_pages.py` runs as the final step in the GitHub Actions workflow, after
   `compressor.py`, so each new letter gets a page on the same commit that adds its audio.
2. `docs/index.html` episode links point to the per-letter pages instead of loading
   text inline.
3. The ledger gains a `page_url` field (`letters/PGR_YYYY_QN.html`) for each entry.

### Implementation steps
- [x] Write `scripts/build_pages.py` with a Jinja2 (or string-template) HTML renderer
- [x] Create `docs/letters/` output directory
- [x] Design and extract a shared `docs/assets/reading.css` stylesheet
- [x] Add `page_built` flag to the ledger schema
- [x] Update `docs/index.html` sidebar links to point to per-letter pages
- [x] Add `build_pages.py` step to `.github/workflows/quarterly_podcast.yml`
- [x] Add `docs/letters/` to the git-committed output paths in the workflow commit step

All 100 letters have pages. `build_pages.py` also publishes plain-text copies to
`docs/letters_txt/` so the index page can fetch them — `data/` is outside the
Pages artifact and is not reachable from the deployed site.

---

## Feature 2 — Text-to-Speech Letter Audio ⏸️ BUILT, THEN PAUSED

> Built with Kokoro (local inference) rather than the hosted providers compared
> below, then removed from the pipeline on 2026-07-26 at 3 of 100 letters.
> **See `TTS.md`** for what still works and how to resume it. The provider
> comparison and design notes below are retained for reference.

**Goal:** Produce an MP3 of each letter read verbatim by a synthetic voice, giving
listeners the full original text as audio — distinct from the NotebookLM podcast
which is an AI-generated overview/summary.

This creates two audio products per quarter:
| Product | Script | Description |
|---------|--------|-------------|
| AI Overview | `generator.py` (existing) | NotebookLM podcast-style summary |
| Verbatim Reading | `tts.py` (new) | Full letter read word-for-word by TTS |

### TTS provider options

| Provider | Quality | Cost | Notes |
|----------|---------|------|-------|
| **OpenAI TTS** (`tts-1-hd`) | High | ~$0.03/1K chars | Simple REST API; `alloy` or `nova` voices work well for business content |
| **Google Cloud TTS** (WaveNet / Neural2) | High | ~$0.016/1K chars | Requires GCP project and service account |
| **Amazon Polly** (Neural) | High | ~$0.016/1K chars | Requires AWS credentials |
| **ElevenLabs** | Very high | $0.30/1K chars | Most natural; higher cost for a full archive |

**Recommended starting point:** OpenAI TTS (`tts-1-hd`, `nova` voice) — straightforward
API, no browser automation, single secret (`OPENAI_API_KEY`), and the quality is
well-suited to spoken business prose.

### What this involves

A new script (`scripts/tts.py`) that:
1. Reads letters from `data/letters/` where `tts_generated` is not yet `true`
2. Splits long letters into chunks ≤ 4,096 characters (OpenAI TTS input limit)
3. Calls the TTS API for each chunk, collecting raw audio segments
4. Concatenates segments with FFmpeg (`concat` filter) into a single MP3
5. Saves the output to `docs/audio_tts/PGR_YYYY_QN_Letter.mp3` as a local staging file
6. Uploads the MP3 to the `audio-library` GitHub Release with a `tts_` filename prefix
7. Updates the ledger with `tts_generated`, `tts_file`, `tts_url`, and `tts_generated_date`

### RSS feed extension

The existing `feed.xml` covers the NotebookLM overviews. TTS readings would either:
- **Option A:** Add a second `<enclosure>` per episode item (not widely supported)
- **Option B:** Generate a second feed `docs/feed_readings.xml` — a separate podcast
  feed subscribers can add alongside the overview feed
- **Option C:** Add the readings as bonus episodes interleaved in the main feed,
  with clear title labeling (`"… — Full Reading"` vs `"… — AI Overview"`)

**Recommended:** Option B (separate feed) — keeps both feeds clean and lets
subscribers choose one or both.

### Ledger schema additions

```json
{
  "tts_generated":      false,
  "tts_file":           "docs/audio_tts/PGR_2025_Q1_Letter.mp3",
  "tts_url":            null,
  "tts_generated_date": null
}
```

### Implementation steps
- [x] Write `scripts/tts.py` with chunk-splitting and FFmpeg concatenation
- [x] Add `tts_generated` / `tts_file` fields to the ledger schema
- [x] Add TTS audio player to per-letter reading pages (Feature 1 dependency)
- [~] Add `tts.py` step to the GitHub Actions workflow — added, then removed
- [ ] Generate `docs/feed_readings.xml` — never built; there is no read-through feed
- [ ] Update `docs/index.html` to surface both audio options per episode — never built
- [n/a] `OPENAI_API_KEY` — not needed; Kokoro runs locally with no API key

---

## Other Future Enhancements

### Search
- Add full-text search across all letters using a pre-built client-side index
  (e.g. [Lunr.js](https://lunrjs.com/) or [Pagefind](https://pagefind.app/))
- Index built by `build_pages.py` at deploy time; no server required

### Letter diff / year-over-year comparison
- Side-by-side view comparing the same quarter across different years
- Highlight added/removed language between consecutive annual letters

### Financial data overlay
- Pull PGR stock price and key metrics (combined ratio, premium growth) from a
  public API and display them alongside each letter for context

### Email / calendar notifications
- GitHub Actions job that sends an email when a new letter is detected
- `.ics` calendar file listing approximate filing dates for the coming year

### Podcast cover art generation
- A static `docs/cover.png` (3000×3000) now ships with the repo and satisfies the
  RSS feed's `itunes:image`. Auto-generating a *per-quarter* cover is still open,
  though RSS channel artwork is per-show rather than per-episode, so this would
  mean per-episode `itunes:image` tags.
