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


# ── Fact-check pass and number check ──────────────────────────────────────────

DRAFT = [
    {"topic": "Premium Growth", "text": "CL NPW +9%, driven by core commercial auto."},
    {"topic": "Profitability & Underwriting Performance", "text": "CR 88.7."},
]


class _SequenceClient(_FakeClient):
    """Answers each call with the next response in the list."""

    def __init__(self, responses):
        super().__init__(None)
        self.responses = list(responses)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_verify_summary_returns_fixed_bullets_and_counts_them():
    reply = ('[{"topic": "Premium Growth", "text": "CL NPW +9%, core commercial auto a '
             'significant contributor.", "fixed": true},'
             ' {"topic": "Profitability & Underwriting Performance", "text": "CR 88.7."}]')
    client = _FakeClient(_completion(reply))
    bullets, fixed = summarizer.verify_summary(client, FILING, "Letter text.", DRAFT)
    assert fixed == 1
    assert bullets[0]["text"].endswith("significant contributor.")
    assert "fixed" not in bullets[0]
    prompt = client.calls[0]["messages"][1]["content"]
    assert "driven by core commercial auto" in prompt and "Letter text." in prompt


def test_verify_summary_rejects_reordered_or_dropped_bullets():
    reply = '[{"topic": "Profitability & Underwriting Performance", "text": "CR 88.7."}]'
    with pytest.raises(ValueError, match="topics or order"):
        summarizer.verify_summary(_FakeClient(_completion(reply)), FILING, "x", DRAFT)


def test_check_summary_retries_then_keeps_the_draft_with_a_warning(monkeypatch, capsys):
    monkeypatch.setattr(summarizer, "REQUEST_PAUSE_SECONDS", 0)
    cut_off = _completion('[{"topic"', finish_reason="length")
    client = _SequenceClient([cut_off, cut_off])
    bullets, verification = summarizer.check_summary(client, FILING, "CL NPW +9%. CR 88.7.", DRAFT)
    assert bullets == DRAFT and len(client.calls) == summarizer.CHECK_ATTEMPTS
    assert verification["checked"] is False and "cut off" in verification["error"]
    assert "::warning title=Summary not fact-checked::" in capsys.readouterr().out


def test_check_summary_succeeds_on_the_retry(monkeypatch):
    monkeypatch.setattr(summarizer, "REQUEST_PAUSE_SECONDS", 0)
    ok = _completion('[{"topic": "Premium Growth", "text": "CL NPW +9%."},'
                     ' {"topic": "Profitability & Underwriting Performance", "text": "CR 88.7."}]')
    client = _SequenceClient([_completion("", finish_reason="length"), ok])
    bullets, verification = summarizer.check_summary(client, FILING, "CL NPW +9%. CR 88.7.", DRAFT)
    assert verification == {"checked": True, "bullets_rewritten": 1}
    assert bullets[0]["text"] == "CL NPW +9%."


@pytest.mark.parametrize("bullet, letter", [
    ("PL NPW +4% to $19.9B", "NPW of $19.9 billion increased 4%"),
    ("43,000+ employees", "the nearly 43 thousand Progressive people"),
    ("debt-to-capital 21.2%; CR 96.0 target", "21.2% ... four cents of underwriting profit"),
    ("model 8.4 in two states; Q3 and 1H 2026", "our 8.4 model"),
    ("$1,234.50M", "$1,234.5 million"),
    ("investments grew to $3.18B", "portfolio increased to $3,180.0 million"),
    ("TNC NPW reduced ~$110.5M", "TNC polices by about $110.5 million"),
])
def test_unsupported_numbers_accepts_figures_the_letter_states(bullet, letter):
    assert summarizer.unsupported_numbers([{"topic": "t", "text": bullet}], letter) == []


def test_unsupported_numbers_flags_figures_the_letter_lacks():
    bullets = [{"topic": "t", "text": "Industry CR 111.4 for 2024; miles driven ~33% lower; CR 88.7"}]
    assert summarizer.unsupported_numbers(bullets, "Our CR was 88.7.") == ["111.4", "33"]
