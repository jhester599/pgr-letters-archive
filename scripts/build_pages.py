#!/usr/bin/env python3
"""
build_pages.py — Generate standalone HTML reading pages for each PGR shareholder letter.

Iterates docs/ledger.json and renders a dedicated HTML page for each filing with
letter_scraped=True. Letter text is embedded directly so pages work on GitHub Pages
(data/letters/ is outside docs/ and is not served).

Usage:
    python scripts/build_pages.py              # build only new/missing pages
    python scripts/build_pages.py --rebuild    # rebuild all pages

Environment variables:
    None required.
"""
import argparse
import html
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import load_ledger, save_ledger, BASE_DIR

DOCS_DIR  = BASE_DIR / "docs"
PAGES_DIR = DOCS_DIR / "letters"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _quarter_sort_key(filing: dict) -> int:
    return filing["year"] * 10 + {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(filing["quarter"], 0)


def render_letter_html(text: str) -> str:
    """Convert plain letter text to HTML paragraphs, escaping special characters."""
    pass  # implemented in Task 3


def build_page(
    filing: dict,
    letter_text: str,
    prev_filing: "dict | None",
    next_filing: "dict | None",
) -> str:
    """Render a complete HTML reading page for one filing."""
    pass  # implemented in Task 3


def main(rebuild: bool = False) -> None:
    pass  # implemented in Task 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build per-letter HTML reading pages.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild all pages, not just new ones.")
    args = parser.parse_args()
    main(rebuild=args.rebuild)
