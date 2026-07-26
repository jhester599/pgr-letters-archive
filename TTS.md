# Kokoro TTS Read-Through Audio — Paused

Status: **paused, not removed** (2026-07-26)

The pipeline used to produce two audio products per letter: a NotebookLM
podcast-style overview, and a verbatim read-through synthesized with Kokoro TTS.
The read-through has been removed from CI. Everything needed to resume it is
still in the repository and still works.

This document exists so picking it back up is a small, well-understood change
rather than an archaeology exercise.

## Why it was paused

TTS stopped being a priority for the project. Left in place it cost real time
and complexity for output nobody was using:

- Roughly 35 minutes of Actions runtime per letter, at approximately real-time
  synthesis speed on a CPU runner.
- A ~1 GB `torch` install on every pipeline run, via kokoro's dependency chain.
- An `espeak-ng` apt install on the runner, which was the entry point for the
  `libcaca0` dependency breakage that plagued the workflow through mid-2026.
- Kokoro pins Python `<3.13` (through its spacy/misaki chain). This is the sole
  reason the project targets Python 3.12.

Coverage never got past the first few letters, so almost nothing is lost by
stopping: **3 of 100 letters** have read-through audio.

## What was actually removed

Only two things:

1. The `Generate TTS read-through audio via Kokoro` step in
   `.github/workflows/quarterly_podcast.yml`.
2. The `espeak-ng` apt install in that workflow's system-dependencies step
   (nothing else needed it).

`kokoro` and `soundfile` also moved out of `requirements.txt` into
`requirements-tts.txt`, so CI no longer installs the TTS stack.

## What is still here and still works

| Asset | State |
|---|---|
| `scripts/tts.py` | Untouched and functional. Run it locally any time. |
| `requirements-tts.txt` | The optional dependency set. |
| Ledger fields `tts_file`, `tts_url`, `tts_voice`, `tts_generated`, `tts_generated_date` | Populated for the 3 completed letters; schema unchanged. |
| `scripts/build_pages.py` TTS player | Still renders a second player when `tts_url` is present, and correctly omits it otherwise. |
| `tts_*.mp3` release assets | 7 assets still published in the `audio-library` release. Nothing was deleted. |
| `docs/audio_tts/` staging dir | Still gitignored, still the local output path. |

Letters with read-through audio today:

| Filing | Voice |
|---|---|
| `PGR_2025_Q4` | `af_heart` |
| `PGR_2025_Q3` | `am_michael` |
| `PGR_2025_Q2` | `am_michael` |

The other 4 `tts_` release assets are voice auditions for `PGR_2025_Q4`
(`af_heart`, `am_liam`, `am_michael`, `bm_daniel`) and are not referenced by the
ledger.

Note that `docs/index.html` never had a TTS player — the read-through only ever
surfaced on the per-letter reading pages. If you resume TTS and want it on the
main archive page too, that front-end work is still outstanding.

## Running it locally today

```cmd
pip install -r requirements.txt -r requirements-tts.txt
```

Plus espeak-ng, which kokoro shells out to for unusual-word pronunciation:

- Linux: `sudo apt-get install -y espeak-ng`
- macOS: `brew install espeak-ng`
- Windows: installer at <https://github.com/espeak-ng/espeak-ng/releases/latest>

Then:

```cmd
REM Audition voices on one letter (files named {id}_{voice}.mp3, no ledger update)
python scripts/tts.py --id PGR_2025_Q4 --sample-voices am_michael am_liam bm_daniel af_heart

REM Production run with the chosen voice (updates the ledger)
python scripts/tts.py --id PGR_2025_Q4 --voice am_michael

REM Work through the backlog
python scripts/tts.py --max-new 1
```

Kokoro model weights (~350 MB) download from HuggingFace on first use and cache
at `%USERPROFILE%\.cache\huggingface\hub\`.

`scripts/tts.py` imports `kokoro`, `numpy`, and `soundfile` lazily, so running it
without the optional dependencies fails with an instructive message rather than
an import traceback.

### Voices

Default: `am_michael` (American English male).

| Prefix | Language | Gender | Examples |
|--------|----------|--------|----------|
| `am_` | American | Male | `am_michael`, `am_liam`, `am_fenrir`, `am_adam`, `am_echo` |
| `af_` | American | Female | `af_heart`, `af_bella`, `af_nova`, `af_sarah`, `af_jessica` |
| `bm_` | British | Male | `bm_daniel`, `bm_george`, `bm_lewis`, `bm_fable` |
| `bf_` | British | Female | `bf_alice`, `bf_emma`, `bf_isabella`, `bf_lily` |

Blend voices with a comma-separated list, e.g. `--voice af_heart,af_bella`.

## Re-enabling it in CI

Three edits.

**1. Restore the workflow step.** In `.github/workflows/quarterly_podcast.yml`,
put this back after the NotebookLM step (there is a `NOTE:` comment marking the
spot):

```yaml
      - name: Generate TTS read-through audio via Kokoro
        id: tts
        if: ${{ inputs.skip_audio != true }}
        continue-on-error: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python scripts/tts.py --max-new 1
```

Then widen the summary step's condition back to
`if: ${{ steps.notebooklm.outcome == 'failure' || steps.tts.outcome == 'failure' }}`
and add a TTS branch to its body.

**2. Restore espeak-ng.** In the same workflow's system-dependencies step, after
the ffmpeg block:

```bash
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends espeak-ng
          espeak-ng --version
```

Keep `--no-install-recommends`. Without it, apt drags in the ffmpeg multimedia
stack and re-triggers the `libcaca0` failure the static ffmpeg build exists to
avoid.

**3. Install the TTS dependencies.** Change the Python install step to:

```yaml
        run: pip install -r requirements.txt -r requirements-tts.txt
```

Also raise `timeout-minutes` back to `180` — it was lowered to `120` when TTS
left, and NotebookLM plus TTS together need the extra headroom.

### Before you re-enable it

Think about whether CI is the right place. At ~35 min per letter, a 97-letter
backlog is roughly 57 hours of runner time. Generating locally and letting
`tts.py` upload to the release (it does this whenever `GITHUB_TOKEN` is set) is
usually the better path for a backfill; CI only makes sense for keeping up with
one new letter per quarter.

## Related documentation

- `AUDIO_STORAGE.md` — how `tts_` release assets are named and hosted, and why
  the `tts_` filename prefix is required.
- `CLAUDE.md` — ledger schema including the `tts_*` fields.
- `ROADMAP.md` — the original TTS feature design.
