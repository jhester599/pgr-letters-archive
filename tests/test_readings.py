"""Tests for scripts/readings.py (Gemini TTS pilot) that need no network or ffmpeg."""

import base64
import io
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import readings  # noqa: E402
from letter_text import clean_letter_text  # noqa: E402

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"


def _wav(frames: int, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b"\x01\x00" * frames * channels)
    return out.getvalue()


def test_reading_paragraphs_drops_figures_and_bullets_and_joins_signature():
    clean = (
        "Opening paragraph.\n\n[Figure: Exhibit 1]\n\n• First item\n\n"
        "Jane Doe\nPresident and Chief Executive Officer\n"
    )
    assert readings.reading_paragraphs(clean) == [
        "Opening paragraph.",
        "First item",
        "Jane Doe, President and Chief Executive Officer",
    ]


def test_chunks_respect_the_limit_and_keep_every_word_in_order():
    paragraphs = [f"Paragraph {n} has a few words in it." for n in range(40)]
    chunks = readings.chunk_paragraphs(paragraphs, max_chars=200)
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(" ".join(paragraphs).split())


def test_overlong_paragraph_is_split_between_sentences():
    paragraph = " ".join(f"Sentence number {n} ends here." for n in range(30))
    chunks = readings.chunk_paragraphs([paragraph], max_chars=150)
    assert len(chunks) > 1
    assert all(len(c) <= 150 and c.endswith(".") for c in chunks)


def test_real_letter_chunks_fit_the_limit():
    raw = (LETTERS_DIR / "PGR_2026_Q2_Letter.txt").read_text(encoding="utf-8")
    chunks = readings.chunk_paragraphs(readings.reading_paragraphs(clean_letter_text(raw)))
    assert len(chunks) >= 2
    assert all(len(c) <= readings.MAX_CHUNK_CHARS for c in chunks)


def test_request_puts_style_in_an_annotation_not_the_transcript():
    body = readings.build_request("Hello.", "Kore", "calm")
    content = body["input"][0]["content"][0]
    assert body["model"] == readings.TTS_MODEL
    assert content["text"] == "Hello."
    assert content["annotations"] == [{"type": "speech_metadata", "style": "calm"}]
    assert body["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    assert body["response_format"] == {"type": "audio"}


def test_extract_audio_returns_the_last_audio_item():
    first, last = _wav(10), _wav(20)
    payload = {"steps": [
        {"type": "thought", "content": []},
        {"type": "model_output", "content": [
            {"type": "audio", "data": base64.b64encode(first).decode()},
            {"type": "audio", "data": base64.b64encode(last).decode()},
        ]},
    ]}
    assert readings.extract_audio(payload) == last


@pytest.mark.parametrize("payload", [{}, {"steps": []}, "OK", {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "hi"}]}]}])
def test_extract_audio_rejects_responses_without_audio(payload):
    with pytest.raises((ValueError, AttributeError)):
        readings.extract_audio(payload if isinstance(payload, dict) else {"steps": payload})


def test_join_wavs_concatenates_with_silence_between_clips():
    joined = readings.join_wavs([_wav(1000), _wav(500)], gap_seconds=0.5)
    with wave.open(io.BytesIO(joined), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 1000 + 12000 + 500


def test_join_wavs_rejects_mismatched_formats():
    with pytest.raises(ValueError):
        readings.join_wavs([_wav(10, rate=24000), _wav(10, rate=16000)])


def test_synthesize_retries_rate_limits_then_returns_audio(monkeypatch):
    monkeypatch.setattr(readings.time, "sleep", lambda s: None)
    ok = {"steps": [{"type": "model_output", "content": [
        {"type": "audio", "data": base64.b64encode(_wav(5)).decode()}]}]}
    responses = iter([
        SimpleNamespace(status_code=429, headers={"Retry-After": "1"}, text="slow down"),
        SimpleNamespace(status_code=200, headers={}, text="", json=lambda: ok),
    ])
    session = SimpleNamespace(post=lambda *a, **k: next(responses))
    assert readings.synthesize(session, "key", "Hi.", "Kore", "calm") == _wav(5)


def test_synthesize_raises_on_a_hard_error(monkeypatch):
    monkeypatch.setattr(readings.time, "sleep", lambda s: None)
    session = SimpleNamespace(post=lambda *a, **k: SimpleNamespace(
        status_code=403, headers={}, text="API_KEY_SERVICE_BLOCKED"))
    with pytest.raises(RuntimeError, match="403"):
        readings.synthesize(session, "key", "Hi.", "Kore", "calm")
