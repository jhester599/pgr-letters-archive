# Figures and Formulas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw graphic placeholder prose and flattened Gainshare formulas with professional figure/formula rendering, starting with 2005 Q4.

**Architecture:** Keep the existing `render_letter_html()` pipeline as the single source of presentation cleanup. Normalize graphic placeholder blocks into either recovered `figure` blocks or hidden artifacts, and normalize known Gainshare formula lines into semantic formula blocks before HTML rendering.

**Tech Stack:** Python renderer, pytest, static HTML/CSS, optional official PDF-derived image assets.

---

### Task 1: Renderer Policy Tests

**Files:**
- Modify: `tests/test_build_pages.py`

- [ ] Add a test that bracketed `graphic intentionally omitted` placeholders are hidden when no known figure mapping exists.
- [ ] Add a test that the 2005 Q4 private-passenger-auto and storm-tracking placeholders render as `<figure>` blocks when known mappings exist.
- [ ] Add a test that flattened Gainshare employee/shareholder formula text renders as a formula block instead of a single prose paragraph.
- [ ] Run `python -m pytest tests\test_build_pages.py -q` and confirm the new tests fail for the expected missing behavior.

### Task 2: Renderer Implementation

**Files:**
- Modify: `scripts/build_pages.py`
- Modify: `docs/assets/reading.css`

- [ ] Add a known-figure mapping for 2005 Q4 graphic placeholder text to stable image paths under `docs/assets/figures/`.
- [ ] Add block type `figure` in `_normalized_letter_blocks()` and render it as `<figure class="letter-figure">`.
- [ ] Hide unknown omitted-graphic placeholders by dropping those blocks from rendered output.
- [ ] Add block type `formula` for the Gainshare employee/shareholder formulas and render it as a compact equation/table.
- [ ] Add CSS for `.letter-figure` and `.formula-block`.
- [ ] Run `python -m pytest tests\test_build_pages.py -q` and confirm tests pass.

### Task 3: Recover 2005 Q4 Figures

**Files:**
- Create: `docs/assets/figures/PGR_2005_Q4_private_passenger_auto_combined_ratios.png`
- Create: `docs/assets/figures/PGR_2005_Q4_storm_tracking_2005_season.png`

- [ ] Download Progressive’s official 2005 annual report PDF to a temporary location.
- [ ] Extract/crop the two figures from the PDF if image quality is good enough.
- [ ] Save optimized PNG assets under `docs/assets/figures/`.
- [ ] If a figure cannot be recovered cleanly, omit that asset and let the renderer suppress its placeholder.

### Task 4: Rebuild and Verify

**Files:**
- Modify: generated pages under `docs/letters/`

- [ ] Run `python scripts\build_pages.py --rebuild`.
- [ ] Verify `docs/letters/PGR_2005_Q4.html` has no raw `graphic intentionally omitted` text.
- [ ] Verify recovered figure blocks or suppression behavior appears for the two graphics.
- [ ] Verify the Gainshare formula is not a run-on paragraph.
- [ ] Run `python -m pytest -q`.
- [ ] Commit and push.
