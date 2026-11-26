# Audio Storage and Backup Policy

Last updated: 2026-07-04

## Current State

Podcast audio is no longer stored in git or Git LFS. The canonical public audio
store is the GitHub Release named `audio-library`:

https://github.com/jhester599/pgr-letters-archive/releases/tag/audio-library

As of the 2026-07-04 migration, the release contains:

- 100 NotebookLM overview MP3s
- 7 Kokoro TTS / voice-sample MP3s
- 107 total MP3 assets
- About 1.0 GB of audio

Letter read-throughs (Gemini TTS, from October 2026) are added to the same
release as `reading_<id>.mp3` (e.g. `reading_PGR_2026_Q2.mp3`) by
`scripts/readings.py`, about 7–8 MB per quarterly letter at 64 kbps.

The website and RSS feed should use `audio_url` and `tts_url` fields in
`docs/ledger.json`. Those URLs point to release assets under:

```text
https://github.com/jhester599/pgr-letters-archive/releases/download/audio-library/
```

## Why Audio Moved Out of Git

The completed NotebookLM archive is about 906 MB, and the early TTS files add
another 107 MB. A full TTS backfill would push the binary archive well past the
comfortable size for a normal GitHub repository and risks recurring Git LFS
storage/bandwidth quota issues.

The project now keeps small, reviewable source files in git:

- `data/letters/*.txt`
- `data/summaries/*.json`
- `docs/ledger.json`
- `docs/feed.xml`
- `docs/letters/*.html`
- scripts, workflows, and documentation

The project does not commit MP3s:

- `docs/audio/*.mp3`
- `docs/audio_tts/*.mp3`
- `data/audio_raw/*`

## Local Backup

A complete local backup was created on 2026-07-04 at:

```text
C:\Users\Jeff\Documents\github\pgr-letters-archive-audio-backup-2026-07-04
```

Expected backup contents:

```text
pgr-letters-archive-audio-backup-2026-07-04/
  notebooklm-overviews/          100 MP3s
  tts-readthroughs/              7 MP3s
  metadata/
    docs__ledger.json
    docs__feed.xml
    AUDIO_PROGRESS.md
    README.md
    PLAN.md
    .gitattributes
    .gitignore
  audio-backup-manifest.csv
  audio-sha256-checksums.csv
  README_BACKUP.txt
```

The backup should contain 107 MP3s totaling about 1013 MB. The local repo may
also have untracked MP3s under `docs/audio/` and `docs/audio_tts/`; that is fine
for local convenience, but git must not track them.

## Google Drive Backup

The Google Drive backup should use this structure:

```text
PGR Letters Archive/
  01_Audio_Backups/
    2026-07-04_full-audio-backup/
      notebooklm-overviews/
      tts-readthroughs/
      metadata/
      audio-backup-manifest.csv
      audio-sha256-checksums.csv
      README_BACKUP.txt
  02_Project_Exports/
  03_Source_PDFs_or_SEC_Artifacts/
  99_Admin/
```

Treat Google Drive as the disaster-recovery copy. Treat GitHub Releases as the
public serving copy. Treat git as code, text, metadata, and generated HTML only.

## Adding New Audio

Normal pipeline behavior:

1. `generator.py` downloads raw NotebookLM audio into `data/audio_raw/`.
2. `compressor.py` compresses it into `docs/audio/` as a local staging file.
3. If `GITHUB_TOKEN` is available, `compressor.py` uploads the MP3 to the
   `audio-library` release using `scripts/releases.py`.
4. `compressor.py` records the release URL in `docs/ledger.json` as `audio_url`.
5. `compressor.py` regenerates `docs/feed.xml`.
6. `build_pages.py` writes reading pages that use the release URL.
7. The workflow commits metadata and pages, not MP3s.

For TTS (paused — no workflow runs this today, see `TTS.md`; the behaviour below
still applies when `tts.py` is run by hand):

1. `tts.py` writes a local staging MP3 under `docs/audio_tts/`.
2. If `GITHUB_TOKEN` is available, it uploads the release asset using the
   filename prefix `tts_`.
3. The ledger stores the public URL in `tts_url`.

The `tts_` prefix is required because TTS files can otherwise have the same
basename as NotebookLM overview files.

The 7 `tts_` assets already in the release stay published. Do not delete them —
3 are referenced by the ledger and 4 are `PGR_2025_Q4` voice auditions.

## Migration and Recovery Commands

Upload missing audio assets to the release and refresh URLs:

```powershell
$env:GITHUB_TOKEN = gh auth token
python scripts\migrate_audio_to_releases.py
python scripts\build_pages.py --rebuild
python scripts\compressor.py
```

Stop tracking any accidentally tracked MP3s while keeping local copies:

```powershell
git rm --cached -- docs/audio/*.mp3 docs/audio_tts/*.mp3
```

Verify release and ledger state:

```powershell
gh release view audio-library --repo jhester599/pgr-letters-archive --json assets,url
git ls-files docs/audio/*.mp3 docs/audio_tts/*.mp3
python -m json.tool docs\ledger.json > $null
```

`git ls-files` should return no MP3s.

## Leftover Git LFS Storage — resolved

Moving the audio to Releases left the 107 old MP3s (1,062,337,219 bytes) in
GitHub's LFS store, over the 1 GB free allowance, as of 2026-07-26. On
2026-10-03, Settings → Billing → Git LFS Data showed 100% of the allowance
available, so the objects have since been purged. Nothing in the project uses
Git LFS, and nothing should again: new audio goes to the `audio-library`
release.

## Do Not Do This

- Do not recommit `docs/audio/*.mp3` or `docs/audio_tts/*.mp3`.
- Do not re-enable broad `*.mp3` Git LFS tracking without a deliberate storage
  plan.
- Do not delete the local backup or Google Drive backup after the release upload;
  they are protection against accidental release-asset deletion.
- Do not remove `audio_url` or `tts_url` from the ledger unless intentionally
  republishing those assets.
