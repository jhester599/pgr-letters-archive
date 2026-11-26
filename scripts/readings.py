#!/usr/bin/env python3
"""
readings.py — Verbatim read-through audio of each letter via Gemini TTS.

Two modes:

  Publish (the readings feed):
      python scripts/readings.py --publish --max-letters 6

      Narrates letters that have a narrator voice assigned (see VOICE_BY_SIGNER)
      and no reading yet, newest first. Each MP3 is uploaded to the
      audio-library release as reading_<id>.mp3, recorded in the ledger
      (reading_* fields), and listed in docs/feed_readings.xml, a podcast feed
      separate from the NotebookLM overviews in docs/feed.xml. The reading page
      is marked for rebuild so build_pages.py adds a player.

  Pilot (listening tests; writes MP3s only):
      python scripts/readings.py --id PGR_2026_Q2 --voices Kore,Charon --out-dir readings_out

The letter text comes from letter_text.clean_letter_text(), with a few
speech-only fixes (speech_text), split into paragraph-aligned chunks. Each chunk
is one request to the Gemini Interactions API; the WAV clips are joined and
encoded to 64 kbps MP3 with ffmpeg, matching the podcast episodes.

Letters whose text has a known hole (a lost figure such as "represented % of")
are held back until the text is fixed; see hold_reason().

Environment variables:
    GEMINI_API_KEY — the same free-tier key summarizer.py uses.
    GITHUB_TOKEN   — uploads to the release (publish mode); provided in Actions.
"""

import argparse
import base64
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import BASE_DIR, load_ledger, save_ledger
from letter_text import clean_letter_text, normalized_letter_blocks

TTS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
TTS_MODEL = "gemini-3.8-flash-tts"   # on the Gemini API free tier
# Female-presenting candidates for the CEO's voice: Warm, Mature, Smooth.
DEFAULT_VOICES = ["Sulafat", "Gacrux", "Despina"]
DEFAULT_STYLE = (
    "A woman executive reading her own letter to shareholders aloud: "
    "professional and composed, but kind and sincere; warm, clear and "
    "unhurried, conversational rather than theatrical or salesy, with "
    "natural pauses between paragraphs."
)
MAX_CHUNK_CHARS = 2500          # roughly three minutes of speech per request
PARAGRAPH_GAP_SECONDS = 0.6     # silence inserted between chunks
REQUEST_PAUSE_SECONDS = 6       # stay under low free-tier requests-per-minute limits
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT = 300

# Narrator voice per letter signer (matched on the start of the signature name).
# Tricia Griffith's letters (2016 Q3 on) use Despina, chosen in the 2026-10 pilot.
# Peter Lewis and Glenn Renwick have no voice yet, so their letters are skipped.
VOICE_BY_SIGNER = {"Tricia": "Despina"}
# Letters signed with a first name only (2016 Q3: "Tricia").
SIGNER_FULL_NAMES = {"Tricia": "Tricia Griffith"}
PUBLISH_STYLE = DEFAULT_STYLE

READINGS_DIR = BASE_DIR / "docs" / "audio_readings"   # local staging; gitignored
READINGS_FEED_PATH = BASE_DIR / "docs" / "feed_readings.xml"
READINGS_TITLE = "PGR Shareholder Letters — Read Aloud"
READINGS_DESC = (
    "The complete text of Progressive Corporation (NYSE: PGR) CEO letters to "
    "shareholders, read aloud by an AI voice. A companion to the PGR Shareholder "
    "Letters — Audio Archive podcast of AI-generated discussions."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Text preparation ──────────────────────────────────────────────────────────

_FIGURE_RE = re.compile(r"^\[Figure: .*\]$")


def reading_paragraphs(clean_text: str) -> list[str]:
    """Turn clean letter text into the paragraphs a narrator would read.

    Figure placeholders are dropped (there is nothing to read aloud) and list
    bullets lose their bullet glyph. Headings stay as their own paragraph.
    """
    paragraphs = []
    for block in clean_text.split("\n\n"):
        block = block.strip()
        if not block or _FIGURE_RE.match(block):
            continue
        if block.startswith("• "):
            block = block[2:]
        # The signature is "Name\nTitle": read it as "Name, Title".
        paragraphs.append(", ".join(line.strip() for line in block.splitlines()))
    return paragraphs


# "(4.1)%" is accounting notation for a negative number; a narrator would read
# it as "four point one percent" and lose the sign.
_ACCOUNTING_NEGATIVE_RE = re.compile(r"\((\d+(?:\.\d+)?)\)\s?%")


def speech_text(clean_text: str) -> str:
    """Speech-only rewrites of the clean text; the published text is unchanged."""
    return _ACCOUNTING_NEGATIVE_RE.sub(r"negative \1 percent", clean_text)


# Text holes left by the extraction that a narrator would read aloud as nonsense:
# a percent sign with its number gone ("represented % of") or an ordinal suffix
# with its number gone ("for the th time"). LETTER_REVIEW.md lists both cases.
_HOLE_PATTERNS = {
    "a percentage is missing": re.compile(r"(?<![\d)\]])\s%"),
    "a number is missing before an ordinal": re.compile(r"\bthe (?:st|nd|rd|th)\b"),
}


def hold_reason(clean_text: str) -> str | None:
    """Why a letter should not be narrated yet, or None if it is ready."""
    for reason, pattern in _HOLE_PATTERNS.items():
        match = pattern.search(clean_text)
        if match:
            context = clean_text[max(0, match.start() - 40):match.end() + 40]
            return f"{reason}: …{' '.join(context.split())}…"
    return None


def letter_signer(raw_letter: str) -> str | None:
    """Name on the letter's last signature block, if any."""
    names = [b.split("\n")[0] for k, b in normalized_letter_blocks(raw_letter) if k == "signature"]
    return names[-1] if names else None


def narrator_voice(signer: str | None) -> str | None:
    if not signer:
        return None
    return next((v for prefix, v in VOICE_BY_SIGNER.items() if signer.startswith(prefix)), None)


def chunk_paragraphs(paragraphs: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Group paragraphs into chunks of at most max_chars, splitting only between
    paragraphs, or between sentences when a single paragraph is too long."""
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
            continue
        sentences = re.split(r"(?<=[.!?”])\s+(?=[A-Z“])", paragraph)
        current = ""
        for sentence in sentences:
            if current and len(current) + 1 + len(sentence) > max_chars:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks

# ── Gemini TTS ────────────────────────────────────────────────────────────────


def build_request(text: str, voice: str, style: str) -> dict:
    """Request body for one chunk, per the Gemini speech-generation docs.

    Gemini 3.8 TTS reads the text verbatim; the style goes in an annotation.
    """
    return {
        "model": TTS_MODEL,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}],
            }],
        }],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }


def extract_audio(payload: dict) -> bytes:
    """Return the WAV bytes from an Interactions API response.

    Follows the documented path: the last audio item in the model_output steps.
    Raises ValueError when the response carries no audio.
    """
    audio = [
        item.get("data")
        for step in payload.get("steps", [])
        if isinstance(step, dict) and step.get("type") == "model_output"
        for item in step.get("content", [])
        if isinstance(item, dict) and item.get("type") == "audio" and item.get("data")
    ]
    if not audio:
        raise ValueError(f"No audio in response: {str(payload)[:200]!r}")
    return base64.b64decode(audio[-1])


def synthesize(session: requests.Session, api_key: str, text: str, voice: str, style: str) -> bytes:
    """Synthesize one chunk, retrying rate limits and transient server errors."""
    body = build_request(text, voice, style)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = session.post(
            TTS_ENDPOINT,
            json=body,
            headers={"x-goog-api-key": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return extract_audio(resp.json())
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            retry_after = resp.headers.get("Retry-After", "")
            wait = int(retry_after) if retry_after.isdigit() else 20 * attempt
            log.warning("  HTTP %d (attempt %d/%d); retrying in %ds…",
                        resp.status_code, attempt, MAX_ATTEMPTS, wait)
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini TTS HTTP {resp.status_code}: {resp.text[:500]}")
    raise RuntimeError("unreachable")

# ── Audio assembly ────────────────────────────────────────────────────────────


def join_wavs(clips: list[bytes], gap_seconds: float = PARAGRAPH_GAP_SECONDS) -> bytes:
    """Concatenate WAV clips with a short silence between them.

    All clips must share channels, sample width and rate (Gemini returns
    24 kHz mono 16-bit for every request).
    """
    if not clips:
        raise ValueError("No audio clips to join")
    params = None
    frames: list[bytes] = []
    for clip in clips:
        with wave.open(io.BytesIO(clip), "rb") as wav:
            clip_params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            if params is None:
                params = clip_params
            elif clip_params != params:
                raise ValueError(f"Clip format {clip_params} differs from {params}")
            if frames:
                channels, width, rate = params
                frames.append(b"\x00" * int(rate * gap_seconds) * channels * width)
            frames.append(wav.readframes(wav.getnframes()))
    channels, width, rate = params
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b"".join(frames))
    return out.getvalue()


def wav_to_mp3(wav_bytes: bytes, out_path: Path) -> None:
    """Encode to 64 kbps MP3, the bitrate the podcast episodes use."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name,
             "-codec:a", "libmp3lame", "-b:a", "64k", str(out_path)],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-1000:]}")

def wav_duration_seconds(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        return round(wav.getnframes() / wav.getframerate())


def synthesize_letter(session, api_key: str, chunks: list[str], voice: str, style: str) -> bytes:
    """Narrate every chunk and return the joined WAV."""
    clips = []
    for number, chunk in enumerate(chunks, 1):
        log.info("  chunk %d/%d (%d chars)", number, len(chunks), len(chunk))
        clips.append(synthesize(session, api_key, chunk, voice, style))
        if number < len(chunks):
            time.sleep(REQUEST_PAUSE_SECONDS)
    return join_wavs(clips)

# ── Publishing ────────────────────────────────────────────────────────────────


def reading_asset_name(filing_id: str) -> str:
    return f"reading_{filing_id}.mp3"


def pending_readings(ledger: dict) -> list[tuple[dict, str, str, list[str]]]:
    """Letters ready to narrate, newest first: (filing, signer, voice, chunks).

    Skips letters already read, letters with no assigned narrator voice, and
    letters held back for a text hole (logged so the hold stays visible).
    """
    ready = []
    for filing in sorted(ledger["filings"], key=lambda f: f["id"], reverse=True):
        if filing.get("reading_generated") or not (filing.get("letter_scraped") and filing.get("letter_file")):
            continue
        path = BASE_DIR / filing["letter_file"]
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        signer = letter_signer(raw)
        signer = SIGNER_FULL_NAMES.get(signer, signer)
        voice = narrator_voice(signer)
        if not voice:
            continue
        clean = clean_letter_text(raw)
        reason = hold_reason(clean)
        if reason:
            log.warning("Holding %s back: %s", filing["id"], reason)
            continue
        ready.append((filing, signer, voice, chunk_paragraphs(reading_paragraphs(speech_text(clean)))))
    return ready


def publish(max_letters: int, synth=synthesize_letter, upload=None) -> int:
    """Narrate up to max_letters pending letters; returns how many were published.

    synth and upload are injectable for tests; upload defaults to
    releases.upload_mp3. The ledger is saved after each letter so a later
    failure (e.g. the daily free-tier quota) keeps the earlier work.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("::warning title=Readings skipped::GEMINI_API_KEY is not set.")
        return 0
    if upload is None:
        from releases import upload_mp3 as upload

    ledger = load_ledger()
    pending = pending_readings(ledger)
    log.info("%d letter(s) waiting for a reading; doing up to %d.", len(pending), max_letters)

    session = requests.Session()
    published = 0
    for filing, signer, voice, chunks in pending[:max_letters]:
        log.info("%s (%s, voice %s): %d chunks", filing["id"], signer, voice, len(chunks))
        try:
            wav = synth(session, api_key, chunks, voice, PUBLISH_STYLE)
            mp3_path = READINGS_DIR / reading_asset_name(filing["id"])
            wav_to_mp3(wav, mp3_path)
            url = upload(mp3_path, reading_asset_name(filing["id"]))
        except Exception as exc:
            log.error("  %s failed: %s", filing["id"], exc)
            print(f"::warning title=Reading failed::{filing['id']}: {exc}")
            if "HTTP 429" in str(exc):
                log.warning("Rate limit or daily quota reached; stopping this run.")
                break
            continue
        if not url:
            log.warning("  %s narrated but not uploaded (no GITHUB_TOKEN); left pending.", filing["id"])
            continue
        filing.update({
            "reading_url": url,
            "reading_bytes": mp3_path.stat().st_size,
            "reading_duration": wav_duration_seconds(wav),
            "reading_voice": voice,
            "reading_model": TTS_MODEL,
            "reading_signer": signer,
            "reading_generated": True,
            "reading_generated_date": datetime.now(timezone.utc).isoformat(),
            "page_built": False,   # rebuild the reading page with a player
        })
        save_ledger(ledger)
        published += 1
        log.info("  → %s (%.1f MB, %d s)", url, filing["reading_bytes"] / 1e6, filing["reading_duration"])
    return published


def write_readings_feed(ledger: dict, base_url: str, feed_path: Path = READINGS_FEED_PATH) -> int:
    """Write the readings podcast feed; returns the number of episodes."""
    from compressor import (PODCAST_AUTHOR, PODCAST_OWNER_EMAIL, _quarter_to_pub_date)

    episodes = sorted(
        (f for f in ledger["filings"] if f.get("reading_generated") and f.get("reading_url")),
        key=lambda f: (f["year"], f["quarter"]),
        reverse=True,
    )
    rss = Element("rss", {
        "version": "2.0",
        "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
    })
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = READINGS_TITLE
    SubElement(channel, "description").text = READINGS_DESC
    SubElement(channel, "link").text = base_url
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "copyright").text = (
        "Letter text is © The Progressive Corporation. The narration is AI-generated "
        "and is not affiliated with or endorsed by Progressive."
    )
    SubElement(channel, "lastBuildDate").text = formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)
    SubElement(channel, "atom:link", {
        "href": f"{base_url}/{feed_path.name}", "rel": "self", "type": "application/rss+xml",
    })
    SubElement(channel, "itunes:author").text = PODCAST_AUTHOR
    SubElement(channel, "itunes:summary").text = READINGS_DESC
    SubElement(channel, "itunes:type").text = "episodic"
    SubElement(channel, "itunes:explicit").text = "false"
    owner = SubElement(channel, "itunes:owner")
    SubElement(owner, "itunes:name").text = PODCAST_AUTHOR
    SubElement(owner, "itunes:email").text = PODCAST_OWNER_EMAIL
    category = SubElement(channel, "itunes:category", text="Business")
    SubElement(category, "itunes:category", text="Investing")
    SubElement(channel, "itunes:image", href=f"{base_url}/cover.png")

    for filing in episodes:
        signer = filing.get("reading_signer") or "the CEO"
        item = SubElement(channel, "item")
        SubElement(item, "title").text = f"PGR {filing['year']} {filing['quarter']} — Letter to Shareholders, Read Aloud"
        SubElement(item, "description").text = (
            f"The full text of {signer}'s {filing['quarter']} {filing['year']} letter to "
            f"Progressive Corporation shareholders, read by an AI voice "
            f"(Gemini TTS, voice {filing.get('reading_voice')})."
        )
        SubElement(item, "pubDate").text = _quarter_to_pub_date(
            filing["year"], filing["quarter"], filing.get("report_date"))
        SubElement(item, "guid", isPermaLink="false").text = f"reading-{filing['id']}"
        SubElement(item, "enclosure", {
            "url": filing["reading_url"],
            "length": str(filing.get("reading_bytes") or 0),
            "type": "audio/mpeg",
        })
        SubElement(item, "itunes:author").text = PODCAST_AUTHOR
        SubElement(item, "itunes:explicit").text = "false"
        if filing.get("reading_duration"):
            SubElement(item, "itunes:duration").text = str(filing["reading_duration"])

    tree = ElementTree(rss)
    indent(tree, space="  ")
    with open(feed_path, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)
    log.info("Readings feed written → %s (%d episode(s))", feed_path.name, len(episodes))
    return len(episodes)

# ── Main ──────────────────────────────────────────────────────────────────────


def narrate(filing_id: str, voices: list[str], style: str, out_dir: Path) -> int:
    """Narrate one letter in each voice. Returns the number of voices that succeeded."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY is not set.")
        return 0

    filing = next((f for f in load_ledger()["filings"] if f["id"] == filing_id), None)
    if not filing or not filing.get("letter_file"):
        log.error("No scraped letter with id %s in the ledger.", filing_id)
        return 0

    raw = (BASE_DIR / filing["letter_file"]).read_text(encoding="utf-8")
    chunks = chunk_paragraphs(reading_paragraphs(speech_text(clean_letter_text(raw))))
    log.info("%s: %d chunks, %d characters", filing_id, len(chunks), sum(map(len, chunks)))

    session = requests.Session()
    succeeded = 0
    for voice in voices:
        log.info("Voice %s…", voice)
        try:
            out_path = out_dir / f"{filing_id}_reading_{voice}.mp3"
            wav_to_mp3(synthesize_letter(session, api_key, chunks, voice, style), out_path)
            log.info("  → %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
            succeeded += 1
        except Exception as exc:
            # One voice failing (e.g. a daily quota) must not lose the others.
            log.error("  Voice %s failed: %s", voice, exc)
            print(f"::warning title=Reading failed::{filing_id} in voice {voice}: {exc}")
    return succeeded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini TTS read-throughs of PGR letters.")
    parser.add_argument("--publish", action="store_true",
                        help="Narrate pending letters, upload them and rewrite the readings feed.")
    parser.add_argument("--max-letters", type=int, default=6,
                        help="Publish mode: most letters to narrate this run (0 = feed only).")
    parser.add_argument("--base-url", default=os.environ.get(
        "PAGES_BASE_URL", "https://jhester599.github.io/pgr-letters-archive"))
    parser.add_argument("--id", dest="filing_id", help="Pilot mode: letter to narrate, e.g. PGR_2026_Q2")
    parser.add_argument("--voices", default=",".join(DEFAULT_VOICES),
                        help="Pilot mode: comma-separated Gemini prebuilt voice names.")
    parser.add_argument("--style", default=DEFAULT_STYLE, help="Pilot mode: narration style instruction.")
    parser.add_argument("--out-dir", default="readings_out", type=Path)
    args = parser.parse_args()

    if args.publish:
        if args.max_letters > 0:
            publish(args.max_letters)
        # Always rewrite the feed so it matches the ledger, even when nothing new
        # was narrated (failures warn rather than fail: pages must still publish).
        write_readings_feed(load_ledger(), args.base_url)
    elif args.filing_id:
        voices = [v.strip() for v in args.voices.split(",") if v.strip()]
        if not narrate(args.filing_id, voices, args.style, args.out_dir):
            sys.exit(1)
    else:
        parser.error("use --publish, or --id for a pilot run")
