#!/usr/bin/env python3
"""
tts.py — Generate verbatim TTS audio for PGR shareholder letters via Kokoro.

For each filing with letter_scraped=True and tts_generated=False, synthesizes
the full letter text locally using the Kokoro 82M model and encodes the result
to a 64 kbps MP3 via FFmpeg.

No API key required. Model weights (~350 MB) are downloaded from HuggingFace
automatically on first use and cached at ~/.cache/huggingface/hub/.

Prerequisites:
    pip install kokoro>=0.9.4 soundfile
    # Windows only — download and install espeak-ng for correct pronunciation
    # of unusual words: https://github.com/espeak-ng/espeak-ng/releases/latest

Usage:
    python scripts/tts.py                            # process 1 pending letter
    python scripts/tts.py --max-new 5               # process up to 5
    python scripts/tts.py --id PGR_2025_Q4          # one specific filing
    python scripts/tts.py --voice am_michael        # choose voice (default)
    python scripts/tts.py --id PGR_2025_Q4 \\
        --sample-voices am_michael am_liam bm_daniel af_heart
        # generate one MP3 per voice for audition; does not update the ledger

Available English voices (lang_code='a' = American, 'b' = British):
    American male:   am_adam  am_echo  am_eric  am_fenrir  am_liam
                     am_michael  am_onyx  am_puck
    American female: af_heart  af_bella  af_jessica  af_nicole
                     af_nova  af_sarah  af_sky
    British male:    bm_daniel  bm_fable  bm_george  bm_lewis
    British female:  bf_alice  bf_emma  bf_isabella  bf_lily
"""

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR

# ── Constants ─────────────────────────────────────────────────────────────────

AUDIO_TTS_DIR = BASE_DIR / "docs" / "audio_tts"
SAMPLE_RATE   = 24000     # Kokoro output sample rate
TARGET_BITRATE = "64k"    # MP3 output bitrate (matches NotebookLM compressed files)
DEFAULT_VOICE  = "am_michael"

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Audio helpers ─────────────────────────────────────────────────────────────

def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Encode a WAV file to MP3 at TARGET_BITRATE using FFmpeg."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(wav_path),
                "-b:a", TARGET_BITRATE,
                str(mp3_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFmpeg encoding failed: {exc.stderr.decode(errors='replace')}"
        ) from exc


def _synthesize(pipeline, text: str, voice: str, out_mp3: Path) -> None:
    """
    Synthesize text with Kokoro, write to a WAV, then encode to MP3.

    Kokoro's pipeline handles all internal chunking automatically for English
    (splits at sentence/clause boundaries). Audio chunks are concatenated in
    memory before writing to disk.
    """
    log.info("  Synthesizing with voice '%s'…", voice)
    chunks = []
    for gs, ps, audio in pipeline(text, voice=voice, speed=1.0):
        if audio is not None:
            chunks.append(audio if isinstance(audio, np.ndarray) else audio.numpy())

    if not chunks:
        raise RuntimeError("Kokoro returned no audio — check that the letter text is non-empty")

    audio = np.concatenate(chunks)
    duration_sec = len(audio) / SAMPLE_RATE
    log.info(
        "  Synthesis complete: %.1f min of audio (%d samples)",
        duration_sec / 60,
        len(audio),
    )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        sf.write(str(wav_path), audio, SAMPLE_RATE)
        _wav_to_mp3(wav_path, out_mp3)
    finally:
        wav_path.unlink(missing_ok=True)

    size_kb = out_mp3.stat().st_size // 1024
    log.info("  Saved → %s (%d KB)", out_mp3.name, size_kb)


# ── Ledger helpers ────────────────────────────────────────────────────────────

def pending_letters(ledger: dict, filing_id: str | None = None) -> list[dict]:
    """Return filings that need TTS generation."""
    if filing_id:
        matches = [f for f in ledger["filings"] if f["id"] == filing_id]
        if not matches:
            log.error("Filing ID not found in ledger: %s", filing_id)
        return matches
    return [
        f for f in ledger["filings"]
        if f.get("letter_scraped")
        and f.get("letter_file")
        and not f.get("tts_generated")
        and not f.get("skip_reason")
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def main(
    max_new: int,
    filing_id: str | None,
    voice: str,
    sample_voices: list[str] | None,
) -> None:
    AUDIO_TTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from kokoro import KPipeline
    except ImportError:
        log.error(
            "kokoro is not installed. Run:\n"
            "  pip install kokoro>=0.9.4 soundfile\n"
            "  # Windows: also install espeak-ng from\n"
            "  # https://github.com/espeak-ng/espeak-ng/releases/latest"
        )
        raise SystemExit(1)

    # Determine which voices to use and whether this is a ledger-updating run
    if sample_voices:
        if not filing_id:
            log.error("--sample-voices requires --id <FILING_ID>")
            raise SystemExit(1)
        voices_to_run = sample_voices
        update_ledger_flag = False
        log.info(
            "Voice sampling mode: will generate one MP3 per voice for %s "
            "(ledger will NOT be updated)",
            filing_id,
        )
    else:
        voices_to_run = [voice]
        update_ledger_flag = True

    ledger  = load_ledger()
    pending = pending_letters(ledger, filing_id)

    if not pending:
        log.info("No letters pending TTS generation.")
        return

    if max_new > 0 and not filing_id and not sample_voices:
        pending = pending[:max_new]

    log.info("Initializing Kokoro pipeline (lang_code='a', device='cpu')…")
    pipeline = KPipeline(lang_code="a", device="cpu")
    log.info("Pipeline ready.")

    success_count = 0

    for i, filing in enumerate(pending):
        log.info("[%d/%d] %s", i + 1, len(pending), filing["id"])

        letter_path = BASE_DIR / filing["letter_file"]
        if not letter_path.exists():
            log.error("  Letter file not found: %s", letter_path)
            continue

        letter_text = letter_path.read_text(encoding="utf-8").strip()
        log.info(
            "  Letter: %d chars, %d paragraphs",
            len(letter_text),
            letter_text.count("\n\n") + 1,
        )

        filing_ok = True

        for v in voices_to_run:
            # Sample files get a voice suffix; production files don't
            if sample_voices:
                out_mp3 = AUDIO_TTS_DIR / f"{filing['id']}_{v}.mp3"
            else:
                out_mp3 = AUDIO_TTS_DIR / f"{filing['id']}_Letter.mp3"

            try:
                _synthesize(pipeline, letter_text, v, out_mp3)
            except Exception as exc:
                log.error("  TTS error (voice=%s): %s", v, exc)
                filing_ok = False
                continue

            if sample_voices:
                log.info("  ✓  %s  [%s]", filing["id"], v)

        if update_ledger_flag and filing_ok:
            out_mp3 = AUDIO_TTS_DIR / f"{filing['id']}_Letter.mp3"
            filing["tts_generated"]      = True
            filing["tts_file"]           = f"docs/audio_tts/{out_mp3.name}"
            filing["tts_voice"]          = voice
            filing["tts_generated_date"] = datetime.now(timezone.utc).isoformat()
            save_ledger(ledger)
            success_count += 1
            log.info("  ✓  %s  (ledger updated)", filing["id"])
        elif update_ledger_flag and not filing_ok:
            log.warning("  ✗  %s — will retry on next run", filing["id"])

    if update_ledger_flag:
        log.info("Done. %d/%d succeeded.", success_count, len(pending))
    else:
        log.info(
            "Voice sampling complete. Files in docs/audio_tts/:\n%s",
            "\n".join(
                f"  {filing['id']}_{v}.mp3"
                for filing in pending
                for v in voices_to_run
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Kokoro TTS verbatim audio for PGR shareholder letters."
    )
    parser.add_argument(
        "--max-new", type=int, default=1,
        help="Max letters to process per run (default: 1; 0 = unlimited).",
    )
    parser.add_argument(
        "--id", dest="filing_id", metavar="FILING_ID",
        help="Process a specific filing by ID (e.g. PGR_2025_Q4). Overrides --max-new.",
    )
    parser.add_argument(
        "--voice", default=DEFAULT_VOICE,
        help=f"Kokoro voice ID for production runs (default: {DEFAULT_VOICE}).",
    )
    parser.add_argument(
        "--sample-voices", nargs="+", metavar="VOICE",
        help=(
            "Generate one MP3 per voice for audition. Requires --id. "
            "Files are named {id}_{voice}.mp3 and the ledger is NOT updated. "
            "Example: --sample-voices am_michael am_liam bm_daniel af_heart"
        ),
    )
    args = parser.parse_args()
    main(
        max_new=args.max_new,
        filing_id=args.filing_id,
        voice=args.voice,
        sample_voices=args.sample_voices,
    )
