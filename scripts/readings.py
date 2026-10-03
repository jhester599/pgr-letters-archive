#!/usr/bin/env python3
"""
readings.py — Verbatim read-through audio of a letter via Gemini TTS (PILOT).

This is the pilot for the planned "readings" feed: it narrates one letter in
one or more voices so the voices and narration quality can be judged by ear
before a feed is built. It writes MP3s to an output directory and touches
nothing else: no ledger, no releases, no feed.

The letter text comes from letter_text.clean_letter_text(), split into
paragraph-aligned chunks (Gemini TTS has no documented per-request length
limit, and short requests fail and retry cheaply). Each chunk is one request
to the Gemini Interactions API; the returned WAV clips are joined and encoded
to 64 kbps MP3 with ffmpeg, matching the podcast episodes.

Usage:
    python scripts/readings.py --id PGR_2026_Q2 --voices Kore,Charon --out-dir readings_out

Environment variables:
    GEMINI_API_KEY — the same free-tier key summarizer.py uses.
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
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import BASE_DIR, load_ledger
from letter_text import clean_letter_text

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
    chunks = chunk_paragraphs(reading_paragraphs(clean_letter_text(raw)))
    log.info("%s: %d chunks, %d characters", filing_id, len(chunks), sum(map(len, chunks)))

    session = requests.Session()
    succeeded = 0
    for voice in voices:
        log.info("Voice %s…", voice)
        try:
            clips = []
            for number, chunk in enumerate(chunks, 1):
                log.info("  chunk %d/%d (%d chars)", number, len(chunks), len(chunk))
                clips.append(synthesize(session, api_key, chunk, voice, style))
                time.sleep(REQUEST_PAUSE_SECONDS)
            out_path = out_dir / f"{filing_id}_reading_{voice}.mp3"
            wav_to_mp3(join_wavs(clips), out_path)
            log.info("  → %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
            succeeded += 1
        except Exception as exc:
            # One voice failing (e.g. a daily quota) must not lose the others.
            log.error("  Voice %s failed: %s", voice, exc)
            print(f"::warning title=Reading failed::{filing_id} in voice {voice}: {exc}")
    return succeeded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pilot: narrate one letter with Gemini TTS.")
    parser.add_argument("--id", dest="filing_id", required=True, help="e.g. PGR_2026_Q2")
    parser.add_argument("--voices", default=",".join(DEFAULT_VOICES),
                        help="Comma-separated Gemini prebuilt voice names.")
    parser.add_argument("--style", default=DEFAULT_STYLE, help="Narration style instruction.")
    parser.add_argument("--out-dir", default="readings_out", type=Path)
    args = parser.parse_args()
    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    if not narrate(args.filing_id, voices, args.style, args.out_dir):
        sys.exit(1)
