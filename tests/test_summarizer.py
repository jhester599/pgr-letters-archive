"""Tests for scripts/summarizer.py that need no network or API key.

The summarizer once "succeeded" for two months while writing nothing: the
model endpoint answered 401, and later HTTP 200 with a bare string. These tests
pin down that anything other than a real summary is rejected, and that a
missing key warns without stopping the pipeline.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import summarizer  # noqa: E402

FILING = {"id": "PGR_2026_Q2", "year": 2026, "quarter": "Q2"}
GOOD_REPLY = (
    '```json\n[{"topic": "Premium Growth", "text": "NPW +5% YOY."},'
    ' {"topic": "Profitability & Underwriting Performance", "text": "CR 87.3."}]\n```'
)


def _completion(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_parse_bullets_accepts_fenced_json_array():
    assert summarizer.parse_bullets(GOOD_REPLY) == [
        {"topic": "Premium Growth", "text": "NPW +5% YOY."},
        {"topic": "Profitability & Underwriting Performance", "text": "CR 87.3."},
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "OK",                                         # the 2026 GitHub Models reply
        "",
        '{"topic": "Premium Growth", "text": "x"}',   # object, not array
        "[]",
        '[{"topic": "Premium Growth"}]',               # no text
        '[{"topic": "", "text": "x"}]',
        "[" + ",".join(['{"topic": "t", "text": "x"}'] * 11) + "]",
    ],
)
def test_parse_bullets_rejects_anything_but_a_summary(raw):
    with pytest.raises(ValueError):
        summarizer.parse_bullets(raw)


def test_generate_summary_calls_gemini_and_parses_reply():
    client = _FakeClient(_completion(GOOD_REPLY))
    bullets = summarizer.generate_summary(client, FILING, "Letter text.")
    assert len(bullets) == 2
    call = client.calls[0]
    assert call["model"] == summarizer.GEMINI_MODEL
    assert call["reasoning_effort"] == summarizer.GEMINI_REASONING_EFFORT
    assert "Letter text." in call["messages"][1]["content"]


def test_generate_summary_rejects_a_bare_string_response():
    with pytest.raises(ValueError, match="Not a chat completion"):
        summarizer.generate_summary(_FakeClient("OK"), FILING, "Letter text.")


def test_generate_summary_rejects_a_truncated_reply():
    client = _FakeClient(_completion('[{"topic": "Premium', finish_reason="length"))
    with pytest.raises(ValueError, match="cut off"):
        summarizer.generate_summary(client, FILING, "Letter text.")


def test_missing_key_warns_without_failing(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(summarizer, "load_ledger", lambda: pytest.fail("ledger was read"))
    summarizer.main()  # must return normally, not sys.exit
    assert "::warning title=Summaries skipped::" in capsys.readouterr().out


def test_prompt_example_is_a_valid_summary():
    """The few-shot example is what the model imitates; it must obey the rules it teaches."""
    prompt = summarizer._USER_PROMPT_TEMPLATE.format(filing_id="PGR_X", letter_text="L")
    example = prompt[prompt.index("FEW-SHOT EXAMPLE"):prompt.index("OUTPUT FORMAT")]
    bullets = summarizer.parse_bullets(example[example.index("["):example.rindex("]") + 1])
    assert len(bullets) == 10
    for bullet in bullets:
        assert 20 <= len(bullet["text"].split()) <= 35, bullet
    assert "FACTUAL RULES" in prompt
