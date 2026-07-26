#!/usr/bin/env python3
"""
compressor.py — FFmpeg audio compression and RSS feed publisher.

For each filing in the ledger where audio has been generated but not yet
compressed, this script:
  1. Re-encodes the raw MP3 from /data/audio_raw/ to 64 kbps using FFmpeg.
  2. Saves the compressed file to /docs/audio/ for local staging.
  3. Uploads the compressed MP3 to the GitHub Releases audio-library asset store
     when GITHUB_TOKEN is available, and records the release download URL.
  4. Deletes the raw file to keep the repo lean.
  5. Updates the ledger entry to mark audio_compressed=True.
  6. Regenerates /docs/feed.xml (podcast RSS feed) from the full ledger.

Usage:
    python scripts/compressor.py

Dependencies:
    ffmpeg must be installed and on the system PATH.
    (Ubuntu: sudo apt-get install ffmpeg)

Environment variables:
    PAGES_BASE_URL  — Base URL for GitHub Pages (default: https://jhester599.github.io/pgr-letters-archive)
    GITHUB_TOKEN    — Optional token used to publish MP3s to the audio-library release.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import (
    Element, SubElement, ElementTree, indent
)

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).resolve().parent.parent
AUDIO_RAW_DIR = BASE_DIR / "data" / "audio_raw"
AUDIO_OUT_DIR = BASE_DIR / "docs" / "audio"
LEDGER_PATH   = BASE_DIR / "docs" / "ledger.json"
FEED_PATH     = BASE_DIR / "docs" / "feed.xml"

DEFAULT_BASE_URL = "https://jhester599.github.io/pgr-letters-archive"
PODCAST_AUTHOR   = "Jeff Hester"
PODCAST_TITLE    = "PGR Shareholder Letters — Audio Archive"
PODCAST_DESC     = (
    "AI-generated audio overviews of Progressive Corporation (NYSE: PGR) "
    "CEO Tricia Griffith's quarterly shareholder letters, powered by Google NotebookLM."
)
PODCAST_COPYRIGHT = (
    "Letter text is © The Progressive Corporation. Audio overviews are "
    "AI-generated and are not affiliated with or endorsed by Progressive."
)
# Apple Podcasts requires a reachable owner email to verify feed ownership
# before a show can be submitted. Override with PODCAST_OWNER_EMAIL.
PODCAST_OWNER_EMAIL = os.environ.get("PODCAST_OWNER_EMAIL", "jeffrey.r.hester@gmail.com")

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Ledger helpers ────────────────────────────────────────────────────────────

def load_ledger() -> dict:
    with open(LEDGER_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def save_ledger(ledger: dict) -> None:
    ledger["meta"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    ledger["meta"]["total_audio"] = sum(
        1 for f in ledger["filings"] if f.get("audio_compressed")
    )
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, default=str)

# ── FFmpeg compression ────────────────────────────────────────────────────────

def compress(raw_path: Path, out_path: Path) -> bool:
    """Re-encode raw_path → out_path at 64 kbps. Returns True on success."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",                          # overwrite output without prompting
        "-i", str(raw_path),
        "-codec:a", "libmp3lame",
        "-b:a", "64k",
        "-map_metadata", "0",          # preserve any existing ID3 tags
        str(out_path),
    ]
    log.info("  Compressing %s → %s…", raw_path.name, out_path.name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("  FFmpeg failed:\n%s", result.stderr[-2000:])
        return False
    log.info("  Compressed successfully (%.1f MB)", out_path.stat().st_size / 1e6)
    return True


def get_audio_duration_seconds(path: Path) -> Optional[int]:
    """Use ffprobe to extract audio duration in whole seconds."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        return int(float(data["format"]["duration"]))
    except (KeyError, ValueError, json.JSONDecodeError):
        return None

# ── RSS feed generation ───────────────────────────────────────────────────────

def _quarter_to_pub_date(year: int, quarter: str, report_date: Optional[str]) -> str:
    """Return an RFC 2822 date string for a filing. Use report_date when available."""
    if report_date:
        try:
            dt = datetime.strptime(report_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return formatdate(dt.timestamp(), usegmt=True)
        except ValueError:
            pass
    # Fallback: approximate the filing date from the quarter
    month_map = {"Q1": 5, "Q2": 8, "Q3": 11, "Q4": 3}
    fallback_year = year if quarter != "Q4" else year + 1
    dt = datetime(fallback_year, month_map.get(quarter, 1), 1, tzinfo=timezone.utc)
    return formatdate(dt.timestamp(), usegmt=True)


def _enclosure_metadata(filing: dict) -> tuple[int, Optional[int], bool]:
    """Return (size_bytes, duration_seconds, ledger_was_updated) for a filing.

    Audio is served from GitHub Releases and the docs/audio/ staging copies are
    gitignored, so a fresh CI checkout has no MP3 to stat or probe. The ledger is
    therefore the source of truth; the local file is only a fallback used to
    populate the ledger on the machine that produced the audio. Without this,
    regenerating the feed in Actions emits length="0" and no <itunes:duration>
    for every episode.
    """
    size     = filing.get("audio_bytes") or 0
    duration = filing.get("audio_duration")
    if size and duration is not None:
        return size, duration, False

    audio_path = BASE_DIR / filing["audio_file"]
    if not audio_path.exists():
        if not size:
            log.warning(
                "No audio_bytes in ledger and no local file for %s — "
                "enclosure length will be 0", filing["id"],
            )
        return size, duration, False

    if not size:
        size = audio_path.stat().st_size
        filing["audio_bytes"] = size
    if duration is None:
        duration = get_audio_duration_seconds(audio_path)
        if duration is not None:
            filing["audio_duration"] = duration
    return size, duration, True


def generate_rss(ledger: dict, base_url: str) -> None:
    """Write /docs/feed.xml from the set of compressed audio filings."""

    # Only include quarters with published audio
    published = sorted(
        [f for f in ledger["filings"] if f.get("audio_compressed")],
        key=lambda f: (f["year"], f["quarter"]),
        reverse=True,
    )

    rss = Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
    })
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text        = PODCAST_TITLE
    SubElement(channel, "description").text  = PODCAST_DESC
    SubElement(channel, "link").text         = base_url
    SubElement(channel, "language").text     = "en-us"
    SubElement(channel, "copyright").text    = PODCAST_COPYRIGHT
    SubElement(channel, "author").text       = PODCAST_AUTHOR
    SubElement(channel, "lastBuildDate").text = formatdate(
        datetime.now(timezone.utc).timestamp(), usegmt=True
    )
    # Podcast clients use rel="self" to know the feed's canonical location.
    SubElement(channel, "atom:link", {
        "href": f"{base_url}/feed.xml",
        "rel":  "self",
        "type": "application/rss+xml",
    })
    SubElement(channel, "itunes:author").text    = PODCAST_AUTHOR
    SubElement(channel, "itunes:summary").text   = PODCAST_DESC
    SubElement(channel, "itunes:type").text      = "episodic"
    # Apple rejects feeds without an explicit rating or a verifiable owner.
    SubElement(channel, "itunes:explicit").text  = "false"
    owner = SubElement(channel, "itunes:owner")
    SubElement(owner, "itunes:name").text  = PODCAST_AUTHOR
    SubElement(owner, "itunes:email").text = PODCAST_OWNER_EMAIL
    category = SubElement(channel, "itunes:category", text="Business")
    SubElement(category, "itunes:category", text="Investing")
    SubElement(channel, "itunes:image", href=f"{base_url}/cover.png")

    ledger_updated = False
    for filing in published:
        audio_url = filing.get("audio_url") or f"{base_url}/audio/{Path(filing['audio_file']).name}"
        file_size, duration, touched = _enclosure_metadata(filing)
        ledger_updated = ledger_updated or touched

        item = SubElement(channel, "item")
        SubElement(item, "title").text = (
            f"PGR {filing['year']} {filing['quarter']} — CEO Shareholder Letter Overview"
        )
        SubElement(item, "description").text = (
            f"AI-generated audio overview of Progressive Corporation CEO Tricia Griffith's "
            f"{filing['quarter']} {filing['year']} shareholder letter."
        )
        SubElement(item, "pubDate").text = _quarter_to_pub_date(
            filing["year"], filing["quarter"], filing.get("report_date")
        )
        SubElement(item, "guid", isPermaLink="false").text = filing["id"]
        SubElement(item, "enclosure", {
            "url": audio_url,
            "length": str(file_size),
            "type": "audio/mpeg",
        })
        SubElement(item, "itunes:author").text   = PODCAST_AUTHOR
        SubElement(item, "itunes:explicit").text = "false"
        if duration:
            SubElement(item, "itunes:duration").text = str(duration)

    # Persist anything measured from local staging files so the next run —
    # which may be a fresh CI checkout with no MP3s — still has the numbers.
    if ledger_updated:
        save_ledger(ledger)
        log.info("Ledger updated with enclosure size/duration metadata.")

    tree = ElementTree(rss)
    indent(tree, space="  ")
    with open(FEED_PATH, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)

    log.info("RSS feed written → %s (%d episode(s))", FEED_PATH.name, len(published))

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    AUDIO_OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_url = os.environ.get("PAGES_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    ledger  = load_ledger()
    pending = [
        f for f in ledger["filings"]
        if f.get("audio_generated") and not f.get("audio_compressed")
        and f.get("audio_file") and f.get("audio_raw_file")
    ]

    if not pending:
        log.info("No audio files pending compression.")
    else:
        log.info("%d file(s) pending compression.", len(pending))

    success_count = 0
    for filing in pending:
        # Raw file may be .mp4 (AAC) or .mp3; output is always .mp3
        raw_path = BASE_DIR / filing["audio_raw_file"]
        out_path = AUDIO_OUT_DIR / Path(filing["audio_file"]).name

        if not raw_path.exists():
            log.error("Raw audio not found: %s — skipping", raw_path)
            continue

        ok = compress(raw_path, out_path)
        if not ok:
            continue

        # Delete the uncompressed raw file to save runner/repo space
        raw_path.unlink()
        log.info("  Deleted raw file %s", raw_path.name)

        filing["audio_compressed"] = True
        filing["audio_compressed_date"] = datetime.now(timezone.utc).isoformat()
        filing["page_built"] = False  # force reading page rebuild to add audio player

        # Capture enclosure metadata now, while the MP3 is still on disk. The
        # staging copy is gitignored, so this is the only moment a CI run can
        # measure it — see _enclosure_metadata().
        filing["audio_bytes"] = out_path.stat().st_size
        filing["audio_duration"] = get_audio_duration_seconds(out_path)

        # Upload to GitHub Releases for CDN hosting (avoids LFS on GitHub Pages)
        try:
            import releases as _releases
            url = _releases.upload_mp3(out_path)
            if url:
                filing["audio_url"] = url
                log.info("  Audio URL stored in ledger: %s", url)
        except Exception as exc:
            log.warning("  releases.upload_mp3 failed (non-fatal): %s", exc)

        save_ledger(ledger)
        success_count += 1

    if pending:
        log.info("Compression complete. %d/%d succeeded.", success_count, len(pending))

    # Always regenerate the RSS feed to reflect current state
    generate_rss(ledger, base_url)


if __name__ == "__main__":
    main()
