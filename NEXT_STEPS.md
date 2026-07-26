# Next Steps

Working guide to what the project needs, in priority order.

Last verified: **2026-07-26**

For architecture see `PLAN.md`; for long-range feature ideas see `ROADMAP.md`.
This file is the short list of what to actually do next.

---

## Current state

| Area | State |
|---|---|
| Letters scraped | 100 of 100 |
| Summaries | 100 of 100 (`data/summaries/`) |
| NotebookLM audio | 100 of 100 — 64 at v1.1, **36 still at v1.0** |
| Reading pages | 100 of 100 built |
| RSS feed | 100 episodes, Apple-required tags present, artwork in place |
| Audio hosting | `audio-library` release, 107 assets, ~1.06 GB, all URLs verified live |
| Git LFS | **1.062 GB of orphaned objects still billed** — see Priority 3 |
| Pipeline schedules | **Both crons disabled** — nothing runs automatically |
| Kokoro TTS | Paused, 3 of 100 letters — see `TTS.md` |

Everything below assumes you are working from `main` with a clean tree.

---

## Priority 1 — Catch up on Q2 2026

The newest ledger entry is `PGR_2026_Q1` (period 2026-03-31). Progressive files
its Q2 10-Q mid-July to mid-August, so a filing is likely already available and
unprocessed. The pipeline could not have picked it up: `quarterly_podcast.yml`
was invalid YAML from 2026-06-02 until it was repaired, so every run since June
failed at parse time.

Check what EDGAR has:

```cmd
python scripts/scraper.py
python -m json.tool docs\ledger.json > NUL
```

If a new filing appears, run the rest by hand — NotebookLM auth almost certainly
needs refreshing first:

```cmd
notebooklm login
python scripts/summarizer.py
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

## Priority 3 — File the GitHub Support request for the orphaned LFS objects

**This is the item most likely to be misremembered as "already done."** Moving
audio to GitHub Releases stopped *new* MP3s from entering Git LFS. It did not
reclaim what was already there.

Verified on 2026-07-26 by querying the LFS batch API directly, which still
returns a working signed download URL for an object no commit references:

| | |
|---|---|
| Orphaned LFS objects | 107 |
| Total size | 1,062,337,219 bytes (1.062 GB) |
| Free-tier allowance | 1 GB |
| Referenced by `main` | none — `git ls-files '*.mp3'` returns nothing |

**A history rewrite does not fix this.** `git filter-repo` and BFG remove the
pointers from commits but leave the objects in GitHub's store, so the quota is
unchanged. Per
[GitHub's documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/removing-files-from-git-large-file-storage),
the only two ways to purge are deleting and recreating the repository, or asking
GitHub Support.

### What to do

1. Check the real number first at **Settings → Billing → Git LFS Data**. If
   GitHub reports well under 1 GB, there is nothing to do.
2. Otherwise file at <https://support.github.com/request> (category: Git LFS or
   billing). The **full request template is in `AUDIO_STORAGE.md`**, under
   "Reclaiming the Leftover Git LFS Storage" — it states the repository, the
   migration commit (`d411e48`), that nothing on the default branch references
   LFS, and that all objects may be deleted permanently.
3. Attach the OID manifest. Regenerate it with the command in the same
   `AUDIO_STORAGE.md` section:

   ```bash
   git rev-list --objects --all \
     | awk '$2 ~ /\.mp3$/ {print $1}' | sort -u \
     | while read sha; do
         git cat-file -p "$sha" \
           | awk '/^oid/{o=$2} /^size/{s=$2} END{print o "," s}'
       done
   ```

   It should print 107 rows summing to 1,062,337,219 bytes.

### How urgent is this really

Low. Being over the LFS **storage** allowance blocks *pushes* of new LFS
objects, which this project will never do again. It does not block clones,
Actions, GitHub Pages, or release-asset downloads — all verified working. Treat
it as housekeeping, not an outage.

Do **not** delete and recreate the repository to solve this. That would destroy
the issues, pull requests, and the `audio-library` release that now hosts all
107 MP3s, and would require re-uploading ~1 GB from the local backup.

---

## Priority 4 — Submit the podcast to directories

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

## Priority 5 — Regenerate the 36 v1.0 episodes as v1.1

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

# Test suite — 50 tests, no ffmpeg/browser/credentials needed
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```
