# Roadmap — PGR Letters Archive

Future enhancements planned for the project. Items are grouped by feature area
and roughly ordered by implementation priority within each section.

---

## Feature 1 — Per-Letter Reading Pages

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
- [ ] Write `scripts/build_pages.py` with a Jinja2 (or string-template) HTML renderer
- [ ] Create `docs/letters/` output directory
- [ ] Design and extract a shared `docs/assets/reading.css` stylesheet
- [ ] Add `page_built` flag to the ledger schema
- [ ] Update `docs/index.html` sidebar links to point to per-letter pages
- [ ] Add `build_pages.py` step to `.github/workflows/quarterly_podcast.yml`
- [ ] Add `docs/letters/` to the git-committed output paths in the workflow commit step

---

## Feature 2 — Text-to-Speech Letter Audio

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
5. Saves the output to `docs/audio/PGR_YYYY_QN_Letter_Reading.mp3`
6. Updates the ledger with `tts_generated`, `tts_file`, and `tts_generated_date`

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
  "tts_file":           "docs/audio/PGR_2025_Q1_Letter_Reading.mp3",
  "tts_generated_date": null
}
```

### Implementation steps
- [ ] Write `scripts/tts.py` with chunk-splitting and FFmpeg concatenation
- [ ] Add `OPENAI_API_KEY` (or chosen provider key) to GitHub Secrets
- [ ] Add `tts_generated` / `tts_file` fields to the ledger schema
- [ ] Generate `docs/feed_readings.xml` from `compressor.py` or a new publisher step
- [ ] Add TTS audio player to per-letter reading pages (Feature 1 dependency)
- [ ] Add `tts.py` step to the GitHub Actions workflow
- [ ] Update `docs/index.html` to surface both audio options per episode

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
- Auto-generate a quarterly cover image (e.g. via DALL·E or a simple template)
  rather than using a static `cover.png`
