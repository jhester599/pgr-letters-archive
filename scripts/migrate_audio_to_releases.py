#!/usr/bin/env python3
"""
migrate_audio_to_releases.py — One-time migration of MP3 files from Git LFS to
GitHub Releases.

Run this script once LFS bandwidth resets. It pulls all LFS objects for the
audio directories, uploads each MP3 to the 'audio-library' GitHub Release, and
stores the CDN download URL in the ledger. It then rebuilds all reading pages
and regenerates the RSS feed with the new URLs.

Usage:
    python scripts/migrate_audio_to_releases.py
    python scripts/migrate_audio_to_releases.py --dry-run   # preview only

Environment variables:
    GITHUB_TOKEN  — Required for uploads. Set via 'export GITHUB_TOKEN=<token>'
                    or in the GitHub Actions environment.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

# Ensure scripts/ is on the path so we can import sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scraper import BASE_DIR, load_ledger, save_ledger
import releases as _releases

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _pull_lfs_objects() -> None:
    """Pull LFS-tracked audio files so they are available on disk."""
    log.info("Pulling LFS objects for docs/audio/ and docs/audio_tts/…")
    cmd = [
        "git", "lfs", "pull",
        "--",
        "docs/audio/",
        "docs/audio_tts/",
    ]
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        log.error("git lfs pull failed:\n%s", result.stderr)
        raise SystemExit(1)
    log.info("LFS pull complete.")


def _run_script(script: str, extra_args: list[str] | None = None) -> None:
    """Run a pipeline script via subprocess."""
    cmd = [sys.executable, str(BASE_DIR / "scripts" / script)]
    if extra_args:
        cmd.extend(extra_args)
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        log.error("Script '%s' exited with code %d", script, result.returncode)
        raise SystemExit(result.returncode)


# ── Main ──────────────────────────────────────────────────────────────────────


def main(dry_run: bool) -> None:
    if not os.environ.get("GITHUB_TOKEN"):
        log.error(
            "GITHUB_TOKEN is not set. Export it before running this script:\n"
            "  export GITHUB_TOKEN=<your-token>\n"
            "The token needs 'contents: write' permission on this repository."
        )
        raise SystemExit(1)

    # ── Step 1: Pull LFS objects ───────────────────────────────────────────────
    if dry_run:
        log.info("[dry-run] Skipping git lfs pull.")
    else:
        _pull_lfs_objects()

    # ── Step 2: Load ledger ────────────────────────────────────────────────────
    ledger = load_ledger()
    filings = ledger["filings"]

    # Identify filings that need audio_url / tts_url
    need_audio = [
        f for f in filings
        if f.get("audio_compressed") and not f.get("audio_url") and f.get("audio_file")
    ]
    need_tts = [
        f for f in filings
        if f.get("tts_generated") and not f.get("tts_url") and f.get("tts_file")
    ]

    log.info(
        "Found %d filing(s) needing audio_url and %d needing tts_url.",
        len(need_audio),
        len(need_tts),
    )

    if dry_run:
        log.info("[dry-run] Would upload the following NotebookLM audio files:")
        for f in need_audio:
            path = BASE_DIR / f["audio_file"]
            exists = "EXISTS" if path.exists() else "MISSING"
            log.info("  [%s] %s", exists, path)

        log.info("[dry-run] Would upload the following TTS audio files:")
        for f in need_tts:
            path = BASE_DIR / f["tts_file"]
            exists = "EXISTS" if path.exists() else "MISSING"
            log.info("  [%s] %s", exists, path)

        log.info("[dry-run] No changes made.")
        return

    # ── Step 3: Upload NotebookLM audio ───────────────────────────────────────
    audio_ok = 0
    audio_fail = 0
    for filing in need_audio:
        mp3_path = BASE_DIR / filing["audio_file"]
        log.info("[%s] Uploading NotebookLM audio: %s", filing["id"], mp3_path.name)
        try:
            url = _releases.upload_mp3(mp3_path)
            if url:
                filing["audio_url"] = url
                log.info("  Stored audio_url: %s", url)
                audio_ok += 1
            else:
                log.warning("  upload_mp3 returned None for %s", mp3_path.name)
                audio_fail += 1
        except Exception as exc:
            log.error("  Upload failed for %s: %s", mp3_path.name, exc)
            audio_fail += 1

    # ── Step 4: Upload TTS audio ───────────────────────────────────────────────
    tts_ok = 0
    tts_fail = 0
    for filing in need_tts:
        mp3_path = BASE_DIR / filing["tts_file"]
        log.info("[%s] Uploading TTS audio: %s", filing["id"], mp3_path.name)
        try:
            url = _releases.upload_mp3(mp3_path)
            if url:
                filing["tts_url"] = url
                log.info("  Stored tts_url: %s", url)
                tts_ok += 1
            else:
                log.warning("  upload_mp3 returned None for %s", mp3_path.name)
                tts_fail += 1
        except Exception as exc:
            log.error("  Upload failed for %s: %s", mp3_path.name, exc)
            tts_fail += 1

    # ── Step 5: Save ledger ────────────────────────────────────────────────────
    save_ledger(ledger)
    log.info(
        "Ledger saved. NotebookLM uploads: %d ok / %d failed. "
        "TTS uploads: %d ok / %d failed.",
        audio_ok, audio_fail, tts_ok, tts_fail,
    )

    # ── Step 6: Rebuild all reading pages with new URLs ───────────────────────
    log.info("Rebuilding all reading pages with new CDN URLs…")
    _run_script("build_pages.py", ["--rebuild"])

    # ── Step 7: Regenerate RSS feed with new CDN URLs ─────────────────────────
    log.info("Regenerating RSS feed with new CDN URLs…")
    _run_script("compressor.py")

    # ── Done — print next steps ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("Migration complete. Next steps:")
    print()
    print("  1. git rm docs/audio/*.mp3 docs/audio_tts/*.mp3")
    print("  2. git add docs/ledger.json docs/feed.xml docs/letters/")
    print("  3. git commit -m \"chore: migrate audio to GitHub Releases\"")
    print("  4. git push")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "One-time migration: upload all existing MP3s to GitHub Releases "
            "and store CDN URLs in the ledger."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without making any changes.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
