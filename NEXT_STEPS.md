# Next Steps

Working guide to what the project needs, in priority order.

Last verified: **2026-10-02**

For architecture see `PLAN.md`; for long-range feature ideas see `ROADMAP.md`.
This file is the short list of what to actually do next.

---

## Current state

| Area | State |
|---|---|
| Letters scraped | 101 of 101 (through Q2 2026) |
| Letter text review | All 101 read; fixes and open questions in `LETTER_REVIEW.md` |
| Summaries | 101 of 101 (`data/summaries/`) — Gemini free tier from Q2 2026 on, see Priority 1 |
| NotebookLM audio | 100 of 101 — 64 at v1.1, **36 still at v1.0**, **Q2 2026 missing** |
| Reading pages | 101 of 101 built |
| RSS feed | 100 episodes, Apple-required tags present, artwork in place |
| Audio hosting | `audio-library` release, 107 assets, ~1.06 GB, all URLs verified live |
| Git LFS | Clear — 100% of the free allowance available (checked 2026-10-03); nothing uses LFS |
| Pipeline schedules | **Both crons disabled** — nothing runs automatically |
| Kokoro TTS | Paused, 3 of 100 letters — see `TTS.md` |

Everything below assumes you are working from `main` with a clean tree.

---

## Priority 1 — Finish Q2 2026

`PGR_2026_Q2` was scraped on 2026-08-03 and now has its reading page and summary,
but no audio. Q3 2026 (period 2026-09-30) files in late October or early
November; run `python scripts/scraper.py` again after that.

**Summaries use the Gemini API free tier.** GitHub Models stopped working for
the pipeline in mid-2026: it returned `401`, and then a bare string instead of a
completion. `summarizer.py` now calls `gemini-3.8-flash` with the
`GEMINI_API_KEY` repository secret (added 2026-10-03) and rejects any reply that
is not a valid summary. If the secret is missing or revoked, the summary step
warns and skips; everything else still publishes.

The key worked on 2026-10-03, once its API restrictions allowed the
Generative Language API (a restricted key fails with `403
API_KEY_SERVICE_BLOCKED`). The Q2 2026 summary was regenerated with Gemini under
the prompt's factual rules (only letter-stated facts, no unstated causes or
superlatives) and checked against the letter.

Generate the audio by hand. NotebookLM auth almost certainly needs refreshing
first:

```cmd
notebooklm login
python scripts/generator.py --max-new 1
python scripts/compressor.py
python scripts/build_pages.py
```

Then update the `NOTEBOOKLM_AUTH_JSON` repository secret from the refreshed
session so the next unattended run has a chance of working. `NOTEBOOKLM_SETUP.md`
has the capture steps.

**Verify:** the new filing has `letter_scraped`, `audio_generated`,
`audio_compressed`, and `page_built` all `true`, plus a non-empty `audio_url`,
`audio_bytes`, and `audio_duration`.

---

## Priority 2 — Re-enable the schedules

Both crons are commented out:

- `.github/workflows/quarterly_podcast.yml` — weekly Friday fallback
- `.github/workflows/daily_audio_backfill.yml` — daily backlog burn-down

They were disabled while the workflow was broken. Two things have changed that
make re-enabling safe:

1. The workflow file parses again.
2. NotebookLM generation is now `continue-on-error`. An expired session cookie
   no longer aborts the job, so scraping, summaries, reading pages, the RSS feed,
   and the commit all still run and publish. The run summary carries the
   recovery commands when audio is skipped.

That second point is what makes an unattended schedule worthwhile even though
the NotebookLM credentials cannot be renewed automatically — the archive stays
current on text, and audio becomes a manual catch-up whenever you get to it.

Do a manual `workflow_dispatch` run first and confirm it goes green end to end
before uncommenting either `schedule:` block.

The daily backfill workflow's backlog is clear (0 letters pending), so its
`check` job will exit in seconds on most days. It is only worth re-enabling if
you expect new letters to need audio.

---

## Priority 3 — Submit the podcast to directories

The feed could not have been accepted before 2026-07-26. Two independent
blockers were fixed:

- `docs/cover.png` did not exist, although `feed.xml` had always advertised
  `<itunes:image>` at that path. Artwork that 404s is on its own enough for
  Apple and Spotify to reject a feed.
- The feed had no `itunes:explicit`, no `itunes:owner` with a verifiable email,
  and no `atom:link rel="self"`.

Both are resolved, so submission is now possible:

- Apple Podcasts: <https://podcastsconnect.apple.com>
- Spotify: <https://podcasters.spotify.com>

Feed URL: `https://jhester599.github.io/pgr-letters-archive/feed.xml`

Before submitting, run the feed through a validator such as
<https://podba.se/validate/> or <https://castfeedvalidator.com/>.

Two things a validator may flag, both expected:

- **Content-Type.** GitHub serves release assets as `application/octet-stream`
  rather than `audio/mpeg`. Browsers and podcast clients sniff the bytes and
  play them correctly, and this is not fixable from our side — GitHub controls
  that header.
- **Owner email.** `itunes:owner/itunes:email` is published in a public feed
  because Apple requires a reachable address to verify ownership. Override it
  with the `PODCAST_OWNER_EMAIL` environment variable before running
  `compressor.py` if you would rather use a different address.

To replace the artwork, drop a new file at `docs/cover.png`. Apple requires
1400×1400 to 3000×3000, RGB, PNG or JPEG, under 512 KB. No code change needed.

---

## Priority 4 — Regenerate the 36 v1.0 episodes as v1.1

36 episodes were generated before summary integration was ready, so NotebookLM
only received the letter text and a background preamble — no ranked-metrics
briefing. See the version table in `CLAUDE.md`.

Affected: `PGR_2017_Q1` through `PGR_2025_Q4`.

All 100 summaries already exist in `data/summaries/`, so every one of these is
ready to regenerate — the only cost is NotebookLM quota (~3 per day on the free
tier, so roughly 12 days) and your time refreshing auth.

Per episode:

```cmd
REM set audio_generated: false for the entry in docs/ledger.json, then:
python scripts/generator.py --id PGR_2024_Q1
python scripts/compressor.py
python scripts/build_pages.py
```

This is a quality improvement to existing content, not a gap — every one of
these episodes already has working audio. Do it only if the v1.1 briefing
noticeably improves the output on a sample of two or three.

---

## Letter readings feed (Gemini TTS) — in progress

Verbatim read-throughs of each letter, published as a podcast feed separate
from the NotebookLM overviews: `docs/feed_readings.xml`
(https://jhester599.github.io/pgr-letters-archive/feed_readings.xml). Each
reading page also gets a "Letter Read Aloud" player.

**How it works.** `python scripts/readings.py --publish` narrates every letter
that has a narrator voice and no reading yet, newest first. It uploads
`reading_<id>.mp3` to the `audio-library` release, records `reading_*` fields in
the ledger, and rewrites the feed. The **Letter Readings (Gemini TTS)** workflow
runs it daily (6 letters a run) until the backlog is done. The main pipeline
reads up to 2 new letters per run.

**Voices.** Tricia Griffith's 40 letters (2016 Q3 – 2026 Q2) use **Despina**,
chosen in the October 2026 pilot (`readings_pilot.yml` stays for voice tests).
Peter Lewis (9 letters, 1993–2000) and Glenn Renwick (52 letters, 2001–2016)
have no voice yet and are skipped until `VOICE_BY_SIGNER` in `readings.py` names
one. That needs a male-voice pilot.

**Held back.** `readings.py` refuses to narrate a letter with a text hole a
narrator would read as nonsense. Two letters are held:
- **2021 Q2** (Tricia): "…22 states … that represented % of the commercial
  multi-peril market" (the figure is being looked up in the EDGAR filing);
- **2013 Q2** (Renwick): "best website for the th time".

Fix the text in `data/letters/`, and the next run narrates the letter.

**Speech-only fixes.** Accounting negatives such as "(4.1)%" are read as
"negative 4.1 percent". The published text is unchanged, and the acronyms (CR,
NPW, PIF…) sounded right in the pilot, so no pronunciation list.

**Backlog.** 39 letters ready (328 requests, ~680k characters, ~12 hours of
audio, ~0.35 GB), so about a week of daily runs.

---

## Not planned

**Kokoro TTS read-throughs.** Removed from the pipeline on 2026-07-26. The
script, ledger fields, reading-page player, and published `tts_` release assets
all still work. `TTS.md` documents why it was paused and exactly how to resume
it, including the YAML to paste back.

---

## Known limitations

- **`docs/index.html` has no TTS player.** Read-through audio only ever appeared
  on per-letter reading pages. Moot while TTS is paused; relevant if it resumes.
- **Four orphaned release assets.** `tts_PGR_2025_Q4_{af_heart,am_liam,am_michael,bm_daniel}.mp3`
  are voice auditions (~77 MB) not referenced by the ledger. Release storage is
  free for public repositories, so there is no pressure to remove them.
- **`scraper.py` only reads `filings.recent`.** Older filings in
  `filings.files[]` are handled by the one-off backfill scripts, not the routine
  scraper. Not a problem while the archive is complete back to 1993.

---

## Verifying the state of things

```bash
# Pipeline counts straight from the ledger
python3 -c "
import json, collections
d = json.load(open('docs/ledger.json'))
f = d['filings']
c = collections.Counter()
for x in f:
    for k in ('letter_scraped','audio_generated','audio_compressed','page_built'):
        if x.get(k): c[k] += 1
    if x.get('audio_url'): c['has_audio_url'] += 1
    c['v' + str(x.get('audio_version'))] += 1 if x.get('audio_generated') else 0
print(dict(c))
"

# The feed must never regress to length=0 or lose durations
grep -c 'length="0"' docs/feed.xml        # expect 0
grep -c 'itunes:duration' docs/feed.xml   # expect 100

# No MP3 may ever be tracked in git
git ls-files '*.mp3'                      # expect no output

# Workflows must parse — an invalid file fails silently at trigger time
python3 -c "
import yaml, glob
for p in glob.glob('.github/workflows/*.yml'):
    yaml.safe_load(open(p)); print('OK', p)
"

# Test suite — no ffmpeg/browser/credentials needed
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```
