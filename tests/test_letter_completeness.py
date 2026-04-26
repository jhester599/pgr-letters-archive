import re
from pathlib import Path


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?", text))


def test_annual_letters_are_not_extreme_length_outliers():
    """Catch stale or partial annual-report extractions before they reach the site."""
    repo_root = Path(__file__).resolve().parents[1]
    failures = []

    for letter_path in sorted((repo_root / "data" / "letters").glob("PGR_*_Q4_Letter.txt")):
        text = letter_path.read_text(encoding="utf-8")
        words = _word_count(text)
        if words < 2_500:
            failures.append(f"{letter_path.name}: {words} words")

    assert not failures, "Suspiciously short annual letters: " + ", ".join(failures)
