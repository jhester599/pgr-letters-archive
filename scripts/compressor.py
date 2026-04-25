#!/usr/bin/env python3
"""
compressor.py — FFmpeg audio compression and RSS feed publisher.

For each filing in the ledger where audio has been generated but not yet
compressed, this script:
  1. Re-encodes the raw MP3 from /data/audio_raw/ to 64 kbps using FFmpeg.
  2. Saves the compressed file to /docs/audio/ (served by GitHub Pages).
  3. Deletes the raw file to keep the repo lean.
  4. Updates the ledger entry to mark audio_compressed=True.
  5. Regenerates /docs/feed.xml (podcast RSS feed) from the full ledger.

Usage:
    python scripts/compressor.py

Dependencies:
    ffmpeg must be installed and on the system PATH.
    (Ubuntu: sudo apt-get install ffmpeg)

Environment variables:
    PAGES_BASE_URL  — Base URL for GitHub Pages (default: https://jhester599.github.io/pgr-letters-archive)
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
    })
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text        = PODCAST_TITLE
    SubElement(channel, "description").text  = PODCAST_DESC
    SubElement(channel, "link").text         = base_url
    SubElement(channel, "language").text     = "en-us"
    SubElement(channel, "author").text       = PODCAST_AUTHOR
    SubElement(channel, "lastBuildDate").text = formatdate(
        datetime.now(timezone.utc).timestamp(), usegmt=True
    )
    SubElement(channel, "itunes:author").text    = PODCAST_AUTHOR
    SubElement(channel, "itunes:type").text      = "episodic"
    SubElement(channel, "itunes:category", text="Business")
    SubElement(channel, "itunes:image", href=f"{base_url}/cover.png")

    for filing in published:
        audio_url  = f"{base_url}/audio/{Path(filing['audio_file']).name}"
        audio_path = BASE_DIR / filing["audio_file"]
        file_size  = audio_path.stat().st_size if audio_path.exists() else 0
        duration   = get_audio_duration_seconds(audio_path) if audio_path.exists() else None

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
        SubElement(item, "itunes:author").text  = PODCAST_AUTHOR
        if duration:
            SubElement(item, "itunes:duration").text = str(duration)

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
        save_ledger(ledger)
        success_count += 1

    if pending:
        log.info("Compression complete. %d/%d succeeded.", success_count, len(pending))

    # Always regenerate the RSS feed to reflect current state
    generate_rss(ledger, base_url)


if __name__ == "__main__":
    main()
