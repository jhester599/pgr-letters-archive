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

## Reclaiming the Leftover Git LFS Storage

Moving the audio to Releases stopped *new* MP3s from entering Git LFS, but it did
not reclaim what was already there. As of 2026-07-26:

| | |
|---|---|
| LFS objects still in GitHub's store | 107 |
| Total size | 1,062,337,219 bytes (1.062 GB) |
| Referenced by `main` | none — `git ls-files '*.mp3'` returns nothing |
| Duplicated by | the same 107 files as `audio-library` release assets |

The objects survive because GitHub keeps LFS objects independently of git
history. Verified by querying the LFS batch API directly, which still returns a
working signed download URL for an object no commit references any more:

```bash
curl -X POST \
  -H "Accept: application/vnd.git-lfs+json" \
  -H "Content-Type: application/vnd.git-lfs+json" \
  -d '{"operation":"download","transfers":["basic"],"objects":[{"oid":"<oid>","size":<bytes>}]}' \
  "https://github.com/jhester599/pgr-letters-archive.git/info/lfs/objects/batch"
```

**A history rewrite does not help.** `git filter-repo` / BFG remove the pointers
from commits but leave the objects in GitHub's LFS store, so the quota is
unchanged. Per
[GitHub's documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/removing-files-from-git-large-file-storage),
the only two ways to purge are to delete and recreate the repository, or to ask
GitHub Support.

### Impact of leaving it

Being over the 1 GB free storage allowance blocks *pushes* of new LFS objects.
It does not block clones, Actions, Pages, or release-asset downloads, and this
project never pushes LFS again — so the overage is inert. Fixing it is
housekeeping, not an outage.

### Regenerate the object manifest

Support will ask which objects to purge. This prints every LFS OID still
reachable from history, with size and filename:

```bash
git rev-list --objects --all \
  | awk '$2 ~ /\.mp3$/ {print $1}' | sort -u \
  | while read sha; do
      git cat-file -p "$sha" \
        | awk -v n="$sha" '/^oid/{o=$2} /^size/{s=$2} END{print o "," s}'
    done
```

### Support request template

File at <https://support.github.com/request> (category: Git LFS / billing).

> **Subject:** Purge orphaned Git LFS objects from jhester599/pgr-letters-archive
>
> Repository: `jhester599/pgr-letters-archive` (public)
>
> This repository previously stored 107 podcast MP3s in Git LFS. On 2026-07-04
> (commit `d411e48`) I migrated all of that audio to GitHub Releases — it is now
> served from the `audio-library` release — removed the `*.mp3` rule from
> `.gitattributes`, and stopped committing MP3s. No commit on the default branch
> references any LFS object today; `git ls-files '*.mp3'` returns nothing.
>
> The 107 objects (1,062,337,219 bytes total) still count against my Git LFS
> storage quota. Your documentation on removing files from Git LFS says the
> objects can only be purged by deleting and recreating the repository, or by
> contacting support — I would prefer not to delete the repository, since that
> would also destroy the issues, pull requests, and the `audio-library` release
> that now hosts this same audio.
>
> Could you purge these LFS objects for this repository? I have attached the full
> list of OIDs with sizes and filenames. I have verified independent backups of
> every file and I am happy for all LFS objects in this repository to be deleted
> permanently — there is nothing I need to retain from the LFS store.
>
> Thank you.

Attach the OID manifest generated by the command above.

## Do Not Do This

- Do not recommit `docs/audio/*.mp3` or `docs/audio_tts/*.mp3`.
- Do not re-enable broad `*.mp3` Git LFS tracking without a deliberate storage
  plan.
- Do not delete the local backup or Google Drive backup after the release upload;
  they are protection against accidental release-asset deletion.
- Do not remove `audio_url` or `tts_url` from the ledger unless intentionally
  republishing those assets.
