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


# ── Publish mode ──────────────────────────────────────────────────────────────

import copy  # noqa: E402
import json  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

import build_pages  # noqa: E402

LEDGER = json.loads((Path(__file__).resolve().parent.parent / "docs" / "ledger.json").read_text(encoding="utf-8"))


def _raw(filing_id: str) -> str:
    return (LETTERS_DIR / f"PGR_{filing_id}_Letter.txt").read_text(encoding="utf-8")


def test_accounting_negatives_are_spoken_as_negative():
    assert readings.speech_text("returned (4.1)% in the quarter") == "returned negative 4.1 percent in the quarter"
    assert readings.speech_text("a 4.1% gain (see note)") == "a 4.1% gain (see note)"


@pytest.mark.parametrize("text", [
    "that represented % of the market",
    "best website for the th time",
])
def test_hold_reason_flags_text_holes(text):
    assert readings.hold_reason(text)


def test_hold_reason_passes_normal_percentages_and_ordinals():
    assert readings.hold_reason("NPW grew 5% and (4.1)% fell; the 10th year; up 3 %.") is None


def test_known_hole_letters_are_held_and_a_clean_one_is_not():
    assert readings.hold_reason(clean_letter_text(_raw("2021_Q2")))
    assert readings.hold_reason(clean_letter_text(_raw("2026_Q2"))) is None


@pytest.mark.parametrize("filing_id, voice", [
    ("2026_Q2", "Despina"),   # Tricia Griffith
    ("2016_Q3", "Despina"),   # signed "Tricia"
    ("2010_Q2", None),        # Glenn Renwick: no voice yet
    ("1999_Q4", None),        # Peter Lewis: no voice yet
])
def test_narrator_voice_follows_the_signer(filing_id, voice):
    assert readings.narrator_voice(readings.letter_signer(_raw(filing_id))) == voice


def test_pending_readings_are_tricias_letters_newest_first_minus_holds():
    pending = readings.pending_readings(copy.deepcopy(LEDGER))
    ids = [f["id"] for f, *_ in pending]
    assert ids == sorted(ids, reverse=True)
    assert "PGR_2021_Q2" not in ids and "PGR_2010_Q2" not in ids
    assert {"PGR_2026_Q2", "PGR_2016_Q3"} <= set(ids)
    assert {signer for _, signer, *_ in pending} == {"Tricia Griffith"}
    assert all(len(c) <= readings.MAX_CHUNK_CHARS for *_, chunks in pending for c in chunks)


def _fake_publish_env(monkeypatch, tmp_path, ledger):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(readings, "load_ledger", lambda: ledger)
    saves = []
    monkeypatch.setattr(readings, "save_ledger", lambda l: saves.append(copy.deepcopy(l)))
    monkeypatch.setattr(readings, "READINGS_DIR", tmp_path)
    monkeypatch.setattr(readings, "wav_to_mp3", lambda wav, path: path.write_bytes(b"mp3" * 100))
    return saves


def test_publish_records_reading_fields_and_respects_the_limit(monkeypatch, tmp_path):
    ledger = copy.deepcopy(LEDGER)
    saves = _fake_publish_env(monkeypatch, tmp_path, ledger)
    calls = []
    synth = lambda session, key, chunks, voice, style: (calls.append(voice), _wav(48000))[1]
    upload = lambda path, name: f"https://example.test/{name}"

    assert readings.publish(2, synth=synth, upload=upload) == 2
    assert calls == ["Despina", "Despina"] and len(saves) == 2
    done = [f for f in ledger["filings"] if f.get("reading_generated")]
    assert {f["id"] for f in done} == {"PGR_2026_Q2", "PGR_2026_Q1"}   # the two newest
    q2 = next(f for f in done if f["id"] == "PGR_2026_Q2")
    assert q2["reading_url"] == "https://example.test/reading_PGR_2026_Q2.mp3"
    assert q2["reading_duration"] == 2 and q2["reading_bytes"] == 300
    assert q2["reading_voice"] == "Despina" and q2["reading_signer"] == "Tricia Griffith"
    assert q2["page_built"] is False


def test_publish_stops_on_quota_and_keeps_finished_work(monkeypatch, tmp_path):
    ledger = copy.deepcopy(LEDGER)
    saves = _fake_publish_env(monkeypatch, tmp_path, ledger)
    results = iter([_wav(24000)])

    def synth(*args):
        try:
            return next(results)
        except StopIteration:
            raise RuntimeError("Gemini TTS HTTP 429: quota exhausted")

    calls = []
    upload = lambda path, name: (calls.append(name), f"https://example.test/{name}")[1]
    assert readings.publish(5, synth=synth, upload=upload) == 1
    assert len(calls) == 1 and len(saves) == 1


def test_publish_without_upload_leaves_the_letter_pending(monkeypatch, tmp_path):
    ledger = copy.deepcopy(LEDGER)
    _fake_publish_env(monkeypatch, tmp_path, ledger)
    assert readings.publish(1, synth=lambda *a: _wav(24000), upload=lambda p, n: None) == 0
    assert not any(f.get("reading_generated") for f in ledger["filings"])


def test_readings_feed_lists_only_published_readings(tmp_path):
    ledger = copy.deepcopy(LEDGER)
    for filing in ledger["filings"]:
        if filing["id"] in ("PGR_2026_Q2", "PGR_2025_Q4"):
            filing.update(reading_generated=True, reading_url=f"https://example.test/reading_{filing['id']}.mp3",
                          reading_bytes=1234, reading_duration=960, reading_voice="Despina",
                          reading_signer="Tricia Griffith")
    feed = tmp_path / "feed_readings.xml"
    assert readings.write_readings_feed(ledger, "https://site.test", feed) == 2
    channel = ET.parse(feed).getroot().find("channel")
    items = channel.findall("item")
    assert [i.find("guid").text for i in items] == ["reading-PGR_2026_Q2", "reading-PGR_2025_Q4"]
    enclosure = items[0].find("enclosure")
    assert enclosure.get("url") == "https://example.test/reading_PGR_2026_Q2.mp3"
    assert enclosure.get("length") == "1234"
    assert "Tricia Griffith" in items[0].find("description").text


def test_reading_page_shows_the_read_aloud_player():
    filing = next(f for f in LEDGER["filings"] if f["id"] == "PGR_2026_Q2")
    filing = dict(filing, reading_generated=True, reading_voice="Despina",
                  reading_url="https://example.test/reading_PGR_2026_Q2.mp3")
    page = build_pages.build_page(filing, "Para one.", None, None)
    assert "Letter Read Aloud" in page
    assert "https://example.test/reading_PGR_2026_Q2.mp3" in page
    assert "voice Despina" in page
