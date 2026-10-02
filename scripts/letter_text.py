#!/usr/bin/env python3
"""
letter_text.py — Turn raw scraped letter text into clean, readable text.

The files in data/letters/ are the scrape record: whatever EDGAR, the annual
report PDFs, or the Wayback Machine returned, minus HTML. They still carry SEC
exhibit headers, page numbers, PDF line wrapping, and inline markers (®, ordinal
suffixes) split onto their own lines.

Everything downstream reads the letter through this module so readers and
listeners all get the same text:

  - build_pages.py renders the reading pages from normalized_letter_blocks()
  - build_pages.py publishes clean_letter_text() to docs/letters_txt/
  - summarizer.py and generator.py send clean_letter_text() to the models

This module has no third-party dependencies.
"""
import re


_MOJIBAKE_REPLACEMENTS = {
    "\x91": "\u2018",
    "\x92": "\u2019",
    "\x93": "\u201c",
    "\x94": "\u201d",
    "\x96": "\u2013",
    "\x97": "\u2014",
    "\xa0": " ",
    "\u00e2\u20ac\u02dc": "\u2018",
    "\u00e2\u20ac\u2122": "\u2019",
    "\u00e2\u20ac\u0153": "\u201c",
    "\u00e2\u20ac\u009d": "\u201d",
    "\u00e2\u20ac\u201d": "\u2014",
    "\u00e2\u20ac\u201c": "\u2013",
    "\u00e2\u20ac\u00a6": "\u2026",
    "\u00e2\u20ac\u2018": "\u2011",
    "\u00e2\u20ac\u00af": "\u202f",
    "\u00c2\u00ae": "\u00ae",
    "\u00c2\u00b7": "\u00b7",
}

_SEC_NOISE_LINES = {
    "EX-99",
    "DOCUMENT",
    "EXHIBIT 99",
    "LETTER TO SHAREHOLDERS",
}

_SECTION_HEADINGS = {
    "Broad Needs of Customers",
    "Broad Needs of Our Customers",
    "Claims",
    "Constancy of Purpose",
    "Competitive Prices",
    "Investments and Capital Management",
    "Leading Brand",
    "Marketing",
    "Market Conditions",
    "Maximum Preparedness",
    "People and Culture",
    "Retention and Customer Service",
    "Technology",
    "Use of Gainshare to Align Shareholder and Employee Interests",
}

_ORDINAL_SUFFIXES = {"st", "nd", "rd", "th"}
_TRADEMARK_LINES = {"\u00ae", "\u2122"}
# Every signer title used in the archive: Lewis (Chairman, President and CEO;
# Chairman of the Board in 2000), Renwick and Griffith (President and CEO).
_SIGNATURE_TITLE_RE = re.compile(
    r"^(?:(?:Chairman,\s+)?President and Chief Executive Officer(?:-Insurance Operations)?|Chairman of the Board)$"
)

# Bullet list patterns
# Pattern 1: standalone bullet character on its own line (modern letters)
_BULLET_CHAR_RE = re.compile(r"^[\u2022\u25cf\u25aa]\s*$")
# Pattern 2: "bullet HEADING -- body" from older SGML/PDF extracts
_BULLET_WORD_RE = re.compile(r"^bullet\s+(.+?)(?:\s*--\s*|\s+-\s+)(.+)$", re.IGNORECASE | re.DOTALL)

# Closing lines that sit between the last paragraph and the signer's name. Kept
# as their own block so the name line is not run into them.
_VALEDICTION_RE = re.compile(
    r"^(?:Joy,?\s+Love,?\s+and\s+Peace|Best|Cheers|Sincerely|Regards"
    r"|Stay\s+well(?:\s+and\s+be\s+kind(?:\s+to\s+others)?)?"
    r"|Take\s+care(?:\s+of\s+one\s+another)?)(?:,\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?|[,.!])?$",
    re.IGNORECASE,
)

_CORPORATE_SUFFIX_RE = re.compile(r"(?<=Chief Executive Officer)\s+The Progressive Corporation and Subsidiaries$")
_INLINE_SIGNATURE_RE = re.compile(
    r"^(?:/s/\s*\S+(?:\s+\S+){0,2}?\s+)?"
    r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+),?\s+"
    r"(?P<title>(?:Chairman,\s+)?President and Chief Executive Officer)$"
)
_DASHED_HEADING_RE = re.compile(r"^-\s+([A-Z][A-Z0-9 ,&'\u2019]+?)\s+-$")
_DASH_BULLET_RE = re.compile(r"^-\s{2,}(\S.*)$")
# A superscript ®/℠/footnote marker dropped by the HTML extraction leaves a space
# before the following punctuation: "Snapshot , our usage-based…", "Name Your
# Price ” program". Spaced ellipses (". . .") are left alone.
_DROPPED_MARK_SPACE_RE = re.compile(r"(?<=[A-Za-z0-9%])[ \u00a0]+(?=[,.;:\u201d)](?![ \u00a0]?\.))")
# "We ’ re excited" — an apostrophe set as a separate HTML span.
_SPLIT_CONTRACTION_RE = re.compile(r"(?<=\w) \u2019 (re|s|ll|ve|d|t|m)\b")
# A line break inside curly quotes ("“\nWhile", "supplies,\n”") becomes a space
# once lines are joined.
_SPACED_OPEN_QUOTE_RE = re.compile(r"“[ \u00a0]+(?=\S)")
_SPACED_CLOSE_QUOTE_RE = re.compile(r"(?<=[^\s“])[ \u00a0]+”")
_RULE_LINE_RE = re.compile(r"^(?:- )?[-_]{3,}$")  # SGML escapes a leading dash as "- "
_HEADING_MARK = "\x01"  # internal: prefixes a line already known to be a heading

_KNOWN_FIGURES = {
    "Private Passenger Auto Combined Ratios 1976-2005": {
        "src": "../assets/figures/PGR_2005_Q4_private_passenger_auto_combined_ratios.png",
        "caption": "Private Passenger Auto Combined Ratios, 1976-2005",
        "alt": "Line chart of private passenger auto combined ratios from 1976 through 2005.",
    },
    "Storm Tracking \u2014 2005 Season": {
        "src": "../assets/figures/PGR_2005_Q4_storm_tracking_2005_season.png",
        "caption": "Storm Tracking \u2014 2005 Season",
        "alt": "Map showing the 2005 storm season tracking graphic from Progressive's annual report.",
    },
}

_GAINSHARE_FORMULA_TEXT = (
    "Gainshare (GS) Employee GS Employee paid Employee GS factor x targets x eligible earnings = payout "
    "Gainshare (GS) Shareholder GS Annual after-tax Shareholder GS factor x target x underwriting income = payout"
)


def _repair_text_encoding(text: str) -> str:
    """Repair common mojibake left behind by SEC HTML extraction."""
    repaired = text
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        repaired = repaired.replace(bad, good)
    return repaired


def _is_sec_noise(line: str) -> bool:
    upper_line = line.upper()
    lower_line = line.lower()
    if upper_line in _SEC_NOISE_LINES:
        return True
    if re.fullmatch(r"EX-99(?:\([A-Z]\)|\.[A-Z])?", upper_line):
        return True
    if re.fullmatch(r"EX-99(?:\([A-Z]\)|\.[A-Z])?\s+LETTER TO SHAREHOLDERS", upper_line):
        return True
    if re.fullmatch(r"EXHIBIT\s+NO\.\s+99(?:\([A-Z]\))?", upper_line):
        return True
    if "letter to shareholders" == lower_line:
        return True
    return bool(re.fullmatch(r"(?:pgr-\d+.*exhibit99.*|l\d+aexv99\w*)\.html?", lower_line))


# Lines that only ever appear in the block of filing metadata and titles above
# the first sentence of a letter: exhibit codes, document filenames, the
# "Letter to Shareholders" title, and the period label. They are only stripped
# from the top of a letter — "First Quarter" or "2016" mid-letter is content.
_LEADING_HEADER_RE = re.compile(
    r"""^(?:
        EX-\d+(?:\.\w+|\(\w\))?(?:\s+\S+\.html?)?   # EX-99, EX-99.0 exhibit99.htm
        | EXHIBIT(?:\s+(?:NO\.\s+)?\d+(?:\.\d+)?(?:\(\w\))?)?  # EXHIBIT, EXHIBIT 99.0
        | DOCUMENT
        | [\w.-]+\.html?                            # pgr-2026331ex99shareholder.htm
        | -{3,}                                     # rule line
        | (?:\d{4}\s+)?LETTER\s+TO\s+SHAREHOLDERS
        | (?:FIRST|SECOND|THIRD|FOURTH)\s+QUARTER(?:\s+\d{4})?
        | \d{4}\s+(?:1ST|2ND|3RD|4TH|FIRST|SECOND|THIRD|FOURTH)\s+QUARTER(?:\s+PRESIDENT[’']S\s+LETTER)?
        | \d{1,4}                                   # sequence number, page, or year
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

# The same metadata run together on the first line of some 2014–2017 filings:
# "EXHIBIT exhibit 99 Shareholder Letter 6.30.14 Exhibit 99 Letter to
# Shareholders Second Quarter 2014 Our 92.6 combined ratio…"
_INLINE_HEADER_RE = re.compile(
    r"""^(?:(?:EX-99(?:\.\d+)?|EXHIBIT|[Ee]xhibit|99(?:\.0)?|Shareholder\s+Letter
           |[\w-]+\.html?|\d{1,2}\.\d{1,2}\.\d{2}|\d{4})\s+)+
        (?:Letter\s+to\s+Shareholders\s+)?
        (?:(?:First|Second|Third|Fourth)\s+Quarter\s+(?:\d{4}\s+)?)?
        (?:(?:1st|2nd|3rd|4th)\s+Quarter\s+)?""",
    re.VERBOSE,
)


def _strip_leading_header(lines: list[str]) -> list[str]:
    """Drop filing metadata and title lines above the first sentence of the letter."""
    start = 0
    while start < len(lines) and (not lines[start] or _LEADING_HEADER_RE.match(lines[start])):
        start += 1
    lines = lines[start:]
    if lines:
        match = _INLINE_HEADER_RE.match(lines[0])
        rest = lines[0][match.end():] if match else ""
        if match and rest[:1].isupper() and re.search(r"(?i)ex-?99|exhibit|quarter", match.group(0)):
            lines = [rest] + lines[1:]
    return lines


def _is_page_number(line: str, next_line: str | None) -> bool:
    if re.fullmatch(r"-\s*\d{1,3}\s*-", line):
        return True
    if not line.isdigit():
        return False
    if next_line in _ORDINAL_SUFFIXES:
        return False
    return 1 <= int(line) <= 200


_CAPS_SEP_PATTERNS = [
    # "ALL CAPS HEADING. Body text" — heading ends with terminal punct
    (re.compile(r"^([A-Z0-9][A-Z0-9\s,;:’’’#&%()\-]+[.!?])\s+(.{10,})$"), 8),
    # "ALL CAPS HEADING  Body text" — two or more spaces (SGML/PDF column layout)
    (re.compile(r"^([A-Z][A-Z0-9\s,;:’’’#&%()\-]+?)\s{2,}(.{15,})$"), 5),
    # "ALL CAPS HEADING – Body" or "— Body" (en/em dash separator)
    # Require whitespace before dash to avoid matching phone numbers ("CALL 1-800").
    (re.compile(r"^([A-Z][A-Z0-9\s,;:’’’#&%()\-]+?)\s+[–—\-]{1,2}\s*(.{10,})$"), 5),
]


def _split_leading_all_caps_heading(line: str) -> tuple[str, str] | None:
    for pattern, min_letters in _CAPS_SEP_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        heading, rest = match.groups()
        heading = heading.strip()
        # Q/A answer markers are never section headings.
        if heading.startswith("A - ") or heading.startswith("Q - "):
            continue
        # Heading must be all-uppercase alpha and at most 60 chars long.
        letters = [c for c in heading if c.isalpha()]
        if len(letters) < min_letters or len(heading) > 60:
            continue
        if all(not c.isalpha() or c.isupper() for c in heading):
            return heading, rest.strip()
    return None


def _is_heading(line: str) -> bool:
    if line in _SECTION_HEADINGS:
        return True
    # Q/A answer lines are prose, not section headings.
    if line.startswith("A - "):
        return False
    letters = [char for char in line if char.isalpha()]
    if len(letters) < 5 or line.endswith((".", ",", ";", ":")):
        return False
    return all(not char.isalpha() or char.isupper() for char in line)


_MINOR_WORDS = {"a", "an", "and", "as", "at", "for", "in", "of", "on", "or", "the", "to", "with", "our"}


def _is_title_case_heading(line: str, paragraph: str, next_line: str | None) -> bool:
    """A short Title Case line standing between two paragraphs: "Marketing Culture",
    "Customer Retention". Only counts when the text before it finished a
    sentence and the next line starts a new one, so a wrapped line that happens
    to be capitalized is not mistaken for a heading."""
    words = line.split()
    if not 1 <= len(words) <= 7 or len(line) > 60:
        return False
    if paragraph and not _has_terminal_punctuation(paragraph):
        return False
    # The next line must open a real paragraph. HTML extraction sometimes puts
    # each bold span on its own line ("Progressive" / "Direct" / "is the name…"),
    # and those fragments are short.
    if not next_line or not (next_line[:1].isupper() or next_line[:1].isdigit()) or len(next_line) < 40:
        return False
    if line.endswith((".", ",", ";", ":", "?", "!", "\u201d", '"')) or not line[:1].isupper():
        return False
    # Sentence-case subheads are short ("Looking forward"); longer ones must be Title Case.
    if len(words) <= 3:
        return True
    return all(word[:1].isupper() or word.lower() in _MINOR_WORDS or word[:1] in "&\u2014-" for word in words)



def _is_signature_marker(line: str) -> bool:
    return line.lower().startswith("/s/")


def _signature_name_from_marker(line: str) -> str:
    return re.sub(r"^/s/\s*", "", line, flags=re.IGNORECASE).strip()


def _is_story_quote_intro(line: str) -> bool:
    lower_line = line.lower()
    if lower_line.endswith(":") and (" wrote" in lower_line or " shared" in lower_line):
        return True
    return any(
        phrase in lower_line
        for phrase in (
            "this letter comes to you",
            "this letter hits all of those sentiments",
            "the story below is from",
            "below is a great example",
            "in their own words",
            "he shared a peek",
            "she recently shared",
        )
    )


def _is_story_quote_reset(line: str) -> bool:
    lower_line = line.lower()
    return lower_line.startswith((
        "also relevant",
        "at the heart",
        "below are some highlights",
        "broad needs",
        "competitive prices",
        "heading into",
        "i hope those",
        "in addition to",
        "lastly,",
        "looking ahead",
        "never resting",
        "our employee resource groups",
        "our people and culture",
        "leading brand",
        "stay well",
        "spreading kindness",
        "take care",
        "thanks for",
        "through the discipline",
        "times like this",
        "to our employees",
        "we ended",
        "we truly came",
    ))


def _tidy_spacing(block: str) -> str:
    block = re.sub(r"[ \t]{2,}", " ", block)
    block = _DROPPED_MARK_SPACE_RE.sub("", block)
    block = _SPACED_OPEN_QUOTE_RE.sub("\u201c", block)
    block = _SPACED_CLOSE_QUOTE_RE.sub("\u201d", block)
    return _SPLIT_CONTRACTION_RE.sub("\u2019\\1", block)


def _quotation_closes_at_end(text: str) -> bool:
    """True when the passage's last quotation mark closes it near the end:
    '…supplies,” Jill shares.' or '…for me.” – Lisa, agent'."""
    close = max(text.rfind("\u201d"), text.rfind('"'))
    if close < 0 or len(text) - close > 60:
        return False
    return "\u201c" not in text[close:]


def _has_terminal_punctuation(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "\u201d", '"', ":", ";"))


def _is_direct_block_quote_start(line: str) -> bool:
    """True when a line opens a real block quote from another person.

    Distinguishes genuine testimonials from CEO sentences that merely begin
    with a quoted term (e.g. '"Re-engineering" is what we have been doing\u2026').

    Rules:
      - Must start with an opening double-quote (straight or curly).
      - Must be >= 80 chars (short lines are inline quoted terms, not stories).
      - Reject if the first closing quote appears within the first 40 chars of
        the inner text \u2014 that pattern is a CEO-quoting-a-concept construction
        like '"Gainshare" is our way\u2026' or '"Move forward" means\u2026'.
      - Reject if the closing quote is followed by a dash attribution marker
        (' \u2014 is where', ' - is where') indicating CEO self-reference.
    """
    if not (line.startswith('"') or line.startswith("\u201c")):
        return False
    if len(line) < 80:
        return False
    inner = line[1:]
    for q in ('"', "\u201d"):
        pos = inner.find(q)
        if 0 <= pos <= 40:
            return False  # early-close \u2192 quoted term, not a block quote
        if pos > 40:
            after = inner[pos + 1 : pos + 20]
            if re.match(r"\s*[-\u2013\u2014]\s*is where", after):
                return False  # CEO self-attribution: "\u2026" - is where I left off
    return True


def _should_join_lines(previous: str, current: str) -> bool:
    if not previous:
        return False
    if current[:1].islower():
        return True
    return not _has_terminal_punctuation(previous)


def _append_inline_marker(paragraph: str, marker: str) -> str:
    if marker in _TRADEMARK_LINES or marker in _ORDINAL_SUFFIXES:
        return f"{paragraph}{marker}"
    return f"{paragraph} {marker}"


def _is_omitted_graphic_note(text: str) -> bool:
    return text.startswith("[") and text.endswith("]") and "graphic intentionally omitted" in text.lower()


# Where the annual report's art pages sat in the EX-13 text: "[ARTWORK]",
# "[ART]", "ART HERE", "[Art - pages 28 through 31]", "Odd - --- Artwork Here".
_ARTWORK_PLACEHOLDER_RE = re.compile(
    r"^(?:\[ART(?:WORK)?\]|ART\s+HERE|\[Art\s+-\s+pages?\b[^\]]*\]|.*\bArtwork\s+Here)$",
    re.IGNORECASE,
)


def _is_artwork_placeholder(text: str) -> bool:
    return bool(_ARTWORK_PLACEHOLDER_RE.match(text.strip()))


def _figure_key_from_note(text: str) -> str | None:
    if not _is_omitted_graphic_note(text):
        return None
    return re.sub(r"\s+graphic intentionally omitted\s*", "", text.strip("[] "), flags=re.IGNORECASE)


def _is_gainshare_formula(text: str) -> bool:
    normalized = " ".join(text.split())
    return normalized == _GAINSHARE_FORMULA_TEXT


_TITLE_END_RE = re.compile(r"officer|of the board", re.IGNORECASE)
_NAME_PREFIX_RE = re.compile(r"^((?:[A-Z][\w.]*\s+){1,3}[A-Z][\w.]*),\s+(.+)$")


def _read_signature_title(name: str, lines: list[str | None], index: int) -> tuple[str, str, int]:
    """Read the signer's title from the lines after their name.

    Titles wrap over up to three lines in the older annual reports
    ("Peter B. Lewis, Chairman, President" / "and Chief Executive Officer") and
    sometimes repeat the full name in front. The title is kept as written:
    Peter Lewis signed as Chairman, President and CEO, Glenn Renwick and Tricia
    Griffith as President and CEO. Returns (name, title, next index); the title
    is empty when none follows within three lines.
    """
    title_lines: list[str] = []
    lookahead = index
    while lookahead < len(lines) and len(title_lines) < 3:
        candidate = lines[lookahead]
        if candidate is None:
            break
        title_lines.append(candidate)
        lookahead += 1
        if _TITLE_END_RE.search(candidate):
            title = " ".join(title_lines)
            match = _NAME_PREFIX_RE.match(title)
            if match and name and match.group(1).split()[-1] == name.split()[-1]:
                name, title = match.group(1), match.group(2)
            return name, title, lookahead
    return name, "", index


def normalized_letter_blocks(text: str) -> list[tuple[str, str]]:
    """Normalize extracted filing text into display-ready paragraph/heading blocks."""
    text = _repair_text_encoding(text)
    raw_lines = _strip_leading_header(
        [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    )

    filtered_lines: list[str | None] = []
    for index, line in enumerate(raw_lines):
        if not line:
            filtered_lines.append(None)
            continue

        next_line = next(
            (candidate.strip() for candidate in raw_lines[index + 1:] if candidate.strip()),
            None,
        )
        if _is_sec_noise(line) or _is_page_number(line, next_line):
            continue
        # Art placeholders are dropped before paragraphs are assembled: they
        # often sit mid-sentence where a page of art interrupted the text
        # ("economies of" / "ART HERE" / "scale, and reduce…"). Any dash rule
        # under one belongs to the art, not to a section title.
        if _is_artwork_placeholder(line):
            following = index + 1
            while following < len(raw_lines) and (
                _is_artwork_placeholder(raw_lines[following]) or _RULE_LINE_RE.match(raw_lines[following])
            ):
                raw_lines[following] = ""
                following += 1
            continue
        # 1990s EX-13 text underlines section titles with a row of dashes:
        # "Results" / "-----------". Promote the title to a heading; any other
        # dash rule is just a separator.
        # "-        Excellent investment professionals are…" (2000 annual):
        # a dash bullet with tab-stop spacing. Split into the bullet marker the
        # list logic already understands, followed by the item text.
        # Signature blocks flattened onto one line, in the layouts seen in the
        # archive: "Glenn M. Renwick President and Chief Executive Officer",
        # "/s/ Glenn M. Renwick Glenn M. Renwick President and Chief Executive
        # Officer", "/s/ Tricia Tricia Griffith President and…", plus a trailing
        # "The Progressive Corporation and Subsidiaries" on the 2004–2005 letters.
        line = _CORPORATE_SUFFIX_RE.sub("", line)
        inline_signature = _INLINE_SIGNATURE_RE.match(line)
        if inline_signature:
            filtered_lines.extend([inline_signature.group("name"), inline_signature.group("title")])
            continue
        # "- FINANCIAL OBJECTIVES AND POLICIES -" (2003 annual report PDF).
        dashed_heading = _DASHED_HEADING_RE.match(line)
        if dashed_heading:
            filtered_lines.extend([None, _HEADING_MARK + dashed_heading.group(1), None])
            continue
        dash_item = _DASH_BULLET_RE.match(line)
        if dash_item:
            filtered_lines.extend([None, "\u2022", dash_item.group(1)])
            continue
        if _RULE_LINE_RE.match(line):
            previous = next((c for c in reversed(filtered_lines) if c is not None), None)
            if (
                previous is not None
                and filtered_lines[-1] is not None
                and len(previous) <= 80
                and not _has_terminal_punctuation(previous)
            ):
                filtered_lines[-1] = _HEADING_MARK + previous
            filtered_lines.append(None)
            continue
        # A bare year under the signature (1990s annual reports) is a date
        # stamp, not content.
        if next_line is None and re.fullmatch(r"(?:19|20)\d{2}", line):
            continue
        filtered_lines.append(line)

    blocks: list[tuple[str, str]] = []
    paragraph = ""
    paragraph_kind = "paragraph"
    quote_mode = False
    quote_mode_direct = False  # True when quote_mode set by _is_direct_block_quote_start
    story_quote_closed = False  # story-intro quote mode has emitted a fully quoted passage
    next_is_list_item = False      # set when a standalone • precedes the next paragraph
    next_list_item_strict = False  # whether that next list_item uses strict (•-style) joining
    list_item_strict = False       # True for current paragraph if it's a •-style list item

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_kind, quote_mode, quote_mode_direct, list_item_strict
        nonlocal story_quote_closed
        if paragraph:
            stripped = paragraph.strip()
            # Post-assembly upgrade: if the fully-joined block starts with a
            # block-quote marker but wasn't caught at line-scan time (e.g. the
            # opening " was on a very short line that got joined), promote it.
            if paragraph_kind == "paragraph" and _is_direct_block_quote_start(stripped):
                paragraph_kind = "quote"
                quote_mode = True
                quote_mode_direct = True
            # A short fully quoted line continuing the previous quote
            # ("…,” shares Heather. / “It breaks my heart…”").
            if (
                paragraph_kind == "paragraph"
                and blocks
                and blocks[-1][0] == "quote"
                and stripped.startswith("\u201c")
                and stripped.endswith("\u201d")
            ):
                paragraph_kind = "quote"
            figure_key = _figure_key_from_note(stripped)
            if figure_key in _KNOWN_FIGURES:
                blocks.append(("figure", figure_key))
            elif figure_key:
                pass
            elif _is_gainshare_formula(stripped):
                blocks.append(("formula", stripped))
            else:
                blocks.append((paragraph_kind, stripped))
            # Auto-reset for direct block quotes: once the paragraph ends with a
            # closing quotation mark the testimonial is complete.
            if quote_mode_direct and paragraph_kind == "quote":
                if stripped.endswith(('"', '”')) or _quotation_closes_at_end(stripped):
                    quote_mode = False
                    quote_mode_direct = False
            # A story intro ("Terri shared her experience saying:") followed by a
            # passage wrapped in quotation marks: the CEO's own text resumes at
            # the next paragraph that does not open another quotation.
            if quote_mode and not quote_mode_direct and paragraph_kind == "quote":
                if stripped.startswith(('"', '“')) and stripped.endswith(('"', '”')):
                    story_quote_closed = True
            paragraph = ""
            paragraph_kind = "paragraph"
            list_item_strict = False

    index = 0
    while index < len(filtered_lines):
        line = filtered_lines[index]
        index += 1

        if line is None:
            flush_paragraph()
            continue

        if line.startswith(_HEADING_MARK):
            flush_paragraph()
            blocks.append(("heading", line[len(_HEADING_MARK):]))
            quote_mode = False
            quote_mode_direct = False
            next_is_list_item = False
            continue

        # ── Bullet list detection ─────────────────────────────────────────────
        # Pattern 1: standalone bullet char (•) on its own line — flag the next
        # paragraph as a list item.
        if _BULLET_CHAR_RE.match(line):
            flush_paragraph()
            next_is_list_item = True
            next_list_item_strict = True  # • items: uppercase = new paragraph
            continue

        # Pattern 2: "bullet HEADING -- body text" from SGML/PDF extracts.
        # Strip the word "bullet", bold the heading, and start a list_item block.
        m_bullet = _BULLET_WORD_RE.match(line)
        if m_bullet:
            flush_paragraph()
            heading = m_bullet.group(1).strip()
            body = m_bullet.group(2).strip()
            paragraph_kind = "list_item"
            list_item_strict = False  # PDF-wrapped text may have uppercase continuations
            paragraph = f"{heading}\x00{body}"
            next_is_list_item = False
            next_list_item_strict = False
            continue

        if _VALEDICTION_RE.match(line):
            flush_paragraph()
            blocks.append(("paragraph", line))
            quote_mode = False
            quote_mode_direct = False
            continue

        if _is_signature_marker(line):
            flush_paragraph()
            name = _signature_name_from_marker(line)
            # 1990s reports put the sign-off on the /s/ line: "/s/ Joy Love and Peace".
            if _VALEDICTION_RE.match(name):
                blocks.append(("paragraph", name))
                name = ""
            while index < len(filtered_lines) and filtered_lines[index] is None:
                index += 1
            if index < len(filtered_lines) and filtered_lines[index]:
                name = filtered_lines[index] or name
                index += 1
            while index < len(filtered_lines) and filtered_lines[index] is None:
                index += 1
            name, title, index = _read_signature_title(name, filtered_lines, index)
            # "Cheers, Glenn" / "/s/ Glenn": the sign-off already carries the name.
            already_signed = (
                not title and blocks and blocks[-1][0] == "paragraph"
                and _VALEDICTION_RE.match(blocks[-1][1]) and blocks[-1][1].endswith(name)
            )
            if not already_signed:
                blocks.append(("signature", f"{name}\n{title}"))
            quote_mode = False
            quote_mode_direct = False
            continue

        if (
            index < len(filtered_lines)
            and _SIGNATURE_TITLE_RE.match(filtered_lines[index] or "")
            and line not in _TRADEMARK_LINES
        ):
            flush_paragraph()
            blocks.append(("signature", f"{line}\n{filtered_lines[index]}"))
            index += 1
            quote_mode = False
            quote_mode_direct = False
            continue

        if line in _TRADEMARK_LINES or line == "SM":
            paragraph = _append_inline_marker(paragraph, line)
            continue
        if line in _ORDINAL_SUFFIXES and paragraph and paragraph[-1:].isdigit():
            paragraph = _append_inline_marker(paragraph, line)
            continue
        if paragraph and line[:1] in {".", ",", ";", ":", ")", "%"}:
            paragraph = f"{paragraph}{line}"
            continue

        figure_key = _figure_key_from_note(paragraph)
        if figure_key and (line is not None):
            flush_paragraph()

        if _is_gainshare_formula(paragraph):
            flush_paragraph()

        if _is_omitted_graphic_note(paragraph) and _is_heading(line):
            flush_paragraph()
            blocks.append(("heading", line))
            quote_mode = False
            quote_mode_direct = False
            next_is_list_item = False
            continue

        if _is_heading(line) or _is_title_case_heading(
            line,
            paragraph,
            filtered_lines[index] if index < len(filtered_lines) else None,
        ):
            flush_paragraph()
            blocks.append(("heading", line))
            quote_mode = False
            quote_mode_direct = False
            next_is_list_item = False
            continue

        split_heading = _split_leading_all_caps_heading(line)
        if split_heading:
            flush_paragraph()
            heading, rest = split_heading
            blocks.append(("heading", heading))
            line = rest

        line_starts_new_paragraph = not paragraph or not _should_join_lines(paragraph, line)
        if line_starts_new_paragraph and quote_mode and _is_story_quote_reset(line):
            quote_mode = False
            quote_mode_direct = False

        # Direct block-quote detection: a long line starting with " that isn't
        # a CEO-quoting-a-term construction activates quote_mode immediately.
        if line_starts_new_paragraph and not quote_mode and _is_direct_block_quote_start(line):
            quote_mode = True
            quote_mode_direct = True

        current_kind = "quote" if quote_mode else "paragraph"
        if paragraph and _should_join_lines(paragraph, line):
            # Pattern 1 (strict) list items: an uppercase-starting line is always
            # a paragraph break, not a continuation of the bullet text.
            if paragraph_kind == "list_item" and list_item_strict and line[:1].isupper():
                flush_paragraph()
                current_kind = "quote" if quote_mode else "paragraph"
                next_is_list_item = False
                next_list_item_strict = False
                paragraph_kind = current_kind
                paragraph = line
            else:
                paragraph = f"{paragraph} {line}"
        else:
            flush_paragraph()
            if story_quote_closed and not line.startswith(('"', '“')):
                quote_mode = False
            if not quote_mode:
                story_quote_closed = False
            # Recompute after flush: flush_paragraph may have reset quote_mode
            # (e.g. a direct block quote that ended with a closing ").
            current_kind = "quote" if quote_mode else "paragraph"
            if next_is_list_item:
                current_kind = "list_item"
                list_item_strict = next_list_item_strict
                next_list_item_strict = False
            next_is_list_item = False
            paragraph_kind = current_kind
            paragraph = line

        if line_starts_new_paragraph and _is_story_quote_intro(line):
            paragraph_kind = "paragraph"
            quote_mode = True
            quote_mode_direct = False
            story_quote_closed = False

    flush_paragraph()
    # Justified PDF text leaves runs of spaces between words ("a  growing  culture").
    blocks = [(kind, _tidy_spacing(block)) for kind, block in blocks]
    # "Brand and Distribution Momentum -": a run-in heading's trailing dash.
    return [(kind, block.rstrip(" -\u2013\u2014") if kind == "heading" else block) for kind, block in blocks]

# Older PDF extractions: typographic ligatures and Adobe private-use-area glyphs
# that encode plain ASCII (U+F7xx -> xx). fix_letter_text.py applied these to
# the stored files once; repeating them here covers anything scraped since.
_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
_PUA_RE = re.compile("[\uf720-\uf77e]")


def _repair_glyphs(text: str) -> str:
    for bad, good in _LIGATURES.items():
        text = text.replace(bad, good)
    text = text.replace("\uf6e4", "$")
    text = text.replace("\u2011", "-")  # non-breaking hyphen ("in\u2011house")
    return _PUA_RE.sub(lambda m: chr(ord(m.group(0)) - 0xF700), text)


def _formula_plain_text() -> str:
    return (
        "Employee Gainshare payout = Employee Gainshare factor \u00d7 Employee paid targets "
        "\u00d7 eligible earnings.\n\n"
        "Shareholder Gainshare payout = Shareholder Gainshare factor \u00d7 Annual after-tax "
        "target \u00d7 underwriting income."
    )


def clean_letter_text(text: str) -> str:
    """Return the letter as clean plain text: one paragraph per line, blank lines between.

    Headings stay on their own line, list items are prefixed with a bullet, and
    the signature is the signer's name followed by their title. Figures the
    filing omitted are dropped; known figures become a bracketed caption.
    """
    parts: list[str] = []
    for kind, block in normalized_letter_blocks(_repair_glyphs(text)):
        if kind == "list_item":
            if "\x00" in block:
                heading, body = block.split("\x00", 1)
                block = f"{heading} \u2014 {body}"
            parts.append(f"\u2022 {block}")
        elif kind == "figure":
            parts.append(f"[Figure: {_KNOWN_FIGURES[block]['caption']}]")
        elif kind == "formula":
            parts.append(_formula_plain_text())
        elif kind == "signature":
            parts.append(block.rstrip("\n"))
        else:
            parts.append(block)
    return "\n\n".join(parts) + "\n"
