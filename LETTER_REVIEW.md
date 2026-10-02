# Letter Review — EDGAR / PDF / Wayback Extraction Audit

Started 2026-10-01. Every letter in `data/letters/` read end to end, looking for
damage done by extraction rather than anything Progressive wrote.

## How fixes are split

**Cleanup code (`scripts/letter_text.py`)** handles formatting artifacts that
recur across many letters — exhibit headers, page numbers, PDF line wrapping,
split `®` and ordinal markers, bullet syntax, sign-off layout. These are fixed
once in code, so the stored files stay a faithful record of the extraction and
newly scraped letters get the same treatment automatically.

**Stored text (`data/letters/*.txt`)** is edited only where extraction lost or
corrupted *content*: dropped characters, words run together, text that belongs
to another part of the report, sidebars spliced into the middle of a sentence.
Each edit is listed below.

**Flagged only** — things that look wrong but can't be settled without the
original document (EDGAR and the Wayback Machine were not reachable from the
review environment). These need a check against the source.

## Open questions — check against the original filing

Lost content the text cannot recover:

- **2013 Q2** — "best website for the th time": the count is missing.
- **2021 Q2** — "22 states … that represented % of the commercial
  multi-peril market": the percentage is missing.

Possible extraction damage, lower confidence:

- **1998 Q4** — "notwithstanding the aggressive competition in auto
  insurance history" may be missing "most".
- **1999 Q4** — the first three paragraphs read like the report's opening
  pull-quotes, not the start of the letter.
- **2000 Q4** — "Our objective is to achieve market returns…" may be the
  tail of the previous bullet carried over a page break.
- **2012 Q4** — "More to follow Over the next few years…" may have lost a
  period.

Everything else marked "flagged" below is wording that looks like the
published text (typos, awkward grammar) and is left as is.

## Findings by letter

### PGR_1993_Q4 (annual, EX-13 SGML)
- Fixed in text: sidebar Q&A "What service levels can customers expect" was
  spliced into the middle of the sentence "…by responding / immediately on all
  claims…"; moved after the sentence and rejoined it.
- Fixed in text: sidebar answer "A - It sure has…" was ~60 lines away from its
  question "Has Progressive's productivity increased…"; moved under it.
- Fixed in text: `com-munication` → `communication`; the TEAMWORK bullet was
  split mid-item by a line wrap.
- Fixed by cleanup: `bullet UNPREDICTABLE UNDERWRITING MARGIN… - Margins…` used
  a single dash and was merged into the previous bullet; `RISKS` heading was
  run into its paragraph; sign-off, name, and stray `1993` were run together.
- Note: the Q&A callouts are annual-report pull-quote sidebars, not letter
  prose. They are kept (they are Lewis's text) but read as asides.

### PGR_1994_Q4 (annual, EX-13 SGML)
- Fixed in text: removed four artwork captions extracted from the report's art
  pages and spliced between paragraphs — "An opportunity to see and solve
  problems…", "Adapt to the changes in the industry…", "The diversity of
  humanity…", "Diverse skills and ideas create tension…". Each followed an
  `[ARTWORK]` marker and was set one to three words per line.
- Fixed by cleanup: section titles underlined with dashes ("Results",
  "Progressive's Core Business", "1994 Initiatives", "Risks", "The Future")
  were run into the following paragraph along with the dash rule.
- Fixed by cleanup: signature rendered as "Peter Lewis / President and Chief
  Executive Officer"; Lewis signed as Chairman, President and CEO, and the
  "Joy Love and Peace" sign-off was dropped. Both restored for every letter.

### PGR_1995_Q4 (annual, EX-13 SGML)
- Fixed in text: removed the report's art-spread titles and captions ("sending
  signals", "stepping up to the mark", "jumping through hoops", "meeting the
  challenge", "shaping the future", "working together", "moving moutains" [sic])
  and their caption paragraphs. Three captions duplicated sentences that also
  appear in the letter body; the body copies are kept.
- Fixed in text: the opening title "Progressive--Auto Insurer for All People"
  was run into the first paragraph.
- Flagged (source typos, left as published): "PERFORMACE-BASED", "Chief
  Excutive Officer", "tax initiaitives", "compliment the facility".

### PGR_1996_Q4 (annual, EX-13 SGML)
- Fixed in text: removed art titles and placeholders ("Impulse of Life / To Be
  20", "Changing Globe", "Absolute-Relative", "Lunation / RE: / NEW",
  "Projection", "Odd"). "Impulse of Life" split the sentence "We eliminated the
  Chief Operating Officer … role and created a 'Policy Team'".
- Fixed in text: page numbers fused onto two section titles ("Progressive's
  Core Business 23", "Investments and Capital Management 25").
- Fixed in text: `93/8% Serial Preferred Shares` → `9 3/8%` (the 1995 letter
  shows the same series as "9 3/8 %").
- Fixed by cleanup: SGML-escaped title underlines (`- -------`) left "Results -
  -------", "Risks - -----", "The Future - ----------" fused into paragraphs.

### PGR_1997_Q4 (annual, EX-13 SGML)
- Fixed in text: removed 87 lines after Lewis's signature — the report's
  illustrated customer stories "NO. 6" through "NO. 11" ("Bad News Is Good
  News", "Long Distance Tickle", "Impressing a Trooper", "Honesty Is the Best
  Policy", "All You Need Is Love", "Travels with Progressive") with their
  artist credits. They are not part of the letter, and stories 1–5 were never
  captured, so the set was partial anyway. `backfill_ex13.py` is meant to stop
  at the signature (there is a test for it); this letter predates or escaped
  that rule.
- Fixed in text: the "Process Management" and "24 hours a day, 7 days a week
  service" list items were run into the end of the preceding paragraphs.
- Flagged (source wording, left as published): "would be come an increasingly
  important vehicle for commerce communication"; "total return to
  shareholders' in 1997, was 78.4%".

### PGR_1998_Q4 (annual, EX-13 SGML)
- Fixed by cleanup: `ART HERE` placeholders were shown as text, and four of
  them sat on top of a dash rule so they became section headings; one split
  the sentence "obtain economies of / scale".
- Fixed in text: signature title read "Chief Executive OfficerInsurance
  Operations" — the dash was lost (the letter itself writes
  "CEO-Insurance Operations").
- Flagged (possible dropped word, verify against source): "notwithstanding
  the aggressive competition in auto insurance history" reads as if "most" is
  missing. "we plan to test offer a homeowners product" is probably the
  original wording.
- Note: em dashes in this file were flattened to hyphens at extraction ("buy-in
  person from Independent Agents", "WILL do for them-no matter"). Readable, left
  as is.

### PGR_1999_Q4 (annual, EX-13 SGML)
- Fixed in text: "4th largest U.S.auto insurer" → "U.S. auto".
- Fixed by cleanup: "[Art - pages 28 through 31]" placeholder after the
  signature; section titles underlined with dashes.
- Flagged (verify against source): the first three paragraphs ("Progressive's
  strategy is to become the number one choice…", "If past is prologue…", "A
  key part of the improved customer experience…") read like pull-quotes from
  the report's opening pages rather than the start of the letter, which seems
  to begin "The theme for this annual report is 'not what you'd expect.'" The
  paragraph "It is possible that the many changes implemented in 1999…" sits
  oddly after STOCK PRICE and may be a sidebar too. Left in place.

### PGR_2000_Q4 (annual, EX-13 SGML)
- Clean extraction overall.
- Fixed in text: "wellrationalized" → "well-rationalized". The 2026-era
  `fix_letter_text.py` joined every word split at a line end, which deletes
  real hyphens that happened to fall at a line break. A corpus scan found the
  same damage in 2004 Q4 ("longerterm") and 2005 Q1 ("indepth"), fixed there.
- Fixed by cleanup: the nine "lessons learned" bullets ("-        Excellent
  investment professionals…") rendered as paragraphs starting with a dash.
- Flagged: "Our objective is to achieve market returns on the high-grade…"
  sits between two bullets; it is probably the tail of the "Occasionally,
  extraordinary investors…" bullet carried over a page break.

### PGR_2001_Q4 (annual, EX-13 HTML)
- Fixed in text: the report's two-column layout put seven margin headings
  inside sentences — "became Focus increasingly clearer", "the Customer Value
  Value Proposition… provides a Proposition litmus test", "Our Evolving a
  dramatic change… Business Model", and so on. Each label now sits as a
  heading above its paragraph ("Focus", "Customer Value Proposition", "Open
  Disclosure", "Our Evolving Business Model", "Insurance Operations",
  "Commitment to Service", "Capital Management and Investments").
- Fixed in text: the "Progressive's Financial Policies" chart had collapsed
  into one run-on paragraph ("*UNDERWRITING Risk-Failure to grow… Policies-A.
  Pursue… B. Use…"). Rebuilt as three sections (Underwriting, Investing,
  Financing), each with its risk and lettered policies. Word-for-word
  identical apart from the `[CHART HERE]` placeholder.

### PGR_2002_Q4 (annual, progressive.com PDF)
- Fixed in text: a US map graphic ("WA OR ID MT WY… Growth in 49 Markets > 40%
  25% – 40% < 25% non active") and a garbled ROE formula ("> > > > ROE = {[
  UNDERWRITING MARGIN * ( NPE SHE > )]…") with its footnotes were dumped into
  the letter after the fourth paragraph. Removed; the readable
  "Progressive's Financial Goals and Policies" sidebar beside them was kept and
  rebuilt as four lines. The formula itself cannot be recovered from the text.
- Fixed in text: eight section headings were run into their paragraphs
  ("Objectives and Policies Focus on our goals…", "More Disclosure After…",
  "Market Conditions and Our View of the Future Throughout…", "Segway In
  2002…", "Some Other Notable Actions Our year…", "Capital and Investment
  Management Progressive chooses…", "Corporate Governance Progressive's
  Board…"); "work hard Insurance Operations" carried a stray piece of art text.
- Fixed in text: 10 missing spaces after punctuation ("margin.This",
  "financing.These", "2003.This", "10.1%.We", "pride.Thanks", "trainees;we",
  "meeting,Tom", "in1972", "Impairments'during", "Segway™Human").
- Fixed in text: small caps had come through as lowercase — "u.s.personal",
  "Segway llc", "(ht)", "cfo", "nyse", "no.1" → U.S., LLC, HT, CFO, NYSE,
  No. 1.
- Fixed in text: signature "Glenn M.Renwick President and Chief Executive
  Officer" on one line.
- Fixed by cleanup: double spaces from justified PDF text.

### PGR_2003_Q4 (annual, progressive.com PDF) — heaviest damage in the archive
- Fixed in text: removed 757 words of annual-report front matter that came
  before the letter — table of contents, "About Progressive", the Carlos Vega
  artist statement, the five-year financial-highlights table (flattened into
  number soup), its footnotes, and the Vision / Core Values / Customer Value
  Proposition pages. The letter now starts at "Financial Objectives and
  Policies", which its later sections refer back to.
- Fixed in text: the Investing / Financing / Underwriting policy chart
  ("I N V E S T I N G Maintain… > Manage…") and the Objectives and Policies
  Scorecard table (targets and 2001–2003 actuals run together as one line of
  numbers) rebuilt as readable lines. Every figure was matched to its row and
  year; the table's column order made the mapping unambiguous.
- Fixed in text: removed a loss-adjustment-expense chart ("TACTICAL AGENDA…
  E A L + S T S O C S S O L L A T O T…") and moved the "MARKET CONDITIONS"
  heading, which the chart had pulled away, back above its section.
- Fixed in text: the two market-share ranking charts rebuilt as two sentences
  listing the top ten.
- Fixed in text: 65 missing spaces ("in1937,we", "purchased100 shares",
  "April15,1971", "in2004to", "is57%", "#1writer", "theme,a work in
  progress"…), "premiums-tosurplus", and small caps that came through
  lowercase (s&p500, nwp, gaap, u.s., ceo).
- Fixed by cleanup: section headings written as "- WHAT WORKED -".
- Not changed: run-in subheads ("Profitability Progressive's most important
  goal…", "Improved Claims Quality Claims represent…") — the bold styling is
  lost but the sentences still read.

### PGR_2004_Q1, PGR_2004_Q2, PGR_2004_Q3 (quarterly, Wayback HTML)
- Clean and complete. Q1 (578 words) and Q2 (686 words) are short but have a
  full opening, results discussion, and close — these early quarterly letters
  were simply brief.
- Fixed by cleanup: signature "Glenn M. Renwick President and Chief Executive
  Officer The Progressive Corporation and Subsidiaries" ran together on one
  line (also 2005 Q1–Q3, and the "/s/ Glenn M. Renwick Glenn M. Renwick
  President…" one-liners in 2014–2015 and "/s/ Tricia Tricia Griffith…" in
  2017).

### PGR_2004_Q4 (annual, progressive.com PDF)
- Fixed in text: three charts flattened into the prose and removed — a
  "Relative Frequency 2000–2004" line chart (with its axis label reversed into
  "s e r u t a e F w e N"), a competitor growth/combined-ratio bubble chart
  with its note, and an organization chart ("The Progressive Corporation and
  Subsidiaries Drive Insurance from Progressive Human Resources Claims…") that
  sat in the middle of the sentence "…difficult to measure except in overall
  results."
- Fixed in text: removed five employee quotes about office art (the report's
  theme) that were set as sidebars between paragraphs — "The artwork makes
  the atmosphere very pleasant…", "Even if someone doesn't like a certain
  piece…", "I have always enjoyed the art…", "It encourages you to try and
  understand…", and "Walking into my first training class… Andy Warhol's 10
  faces of Mao…".
- Fixed in text: nine headings run into their paragraphs (Market Conditions,
  Brand, Claims, Technology, New Horizons, Customer Retention, Investments and
  Capital Management, Company Communication, The Progressive Culture);
  "consumer.(On a personal note… renewals.)The", "October15th", "No.1";
  "ProgressiveSM" / "DirectSM" service marks fused to the word → ℠.
- Fixed in text (lost hyphen, see 2000 Q4): "longerterm" → "longer-term".

### PGR_2005_Q1, PGR_2005_Q2, PGR_2005_Q3 (quarterly, Wayback QSR PDF)
- Clean and complete; the letter-section extraction from the quarterly
  shareholder report PDFs worked well.
- Fixed in text: "Progressive DirectSM" (Q2, Q3) → "Progressive Direct℠";
  "indepth" → "in-depth" (Q1, lost hyphen).

### PGR_2005_Q4 (annual, EX-99)
- Clean. The two figures the filing omitted ("Private Passenger Auto Combined
  Ratios 1976-2005", "Storm Tracking — 2005 Season") are rendered from saved
  images on the reading page and as bracketed captions in plain text.
- Fixed in text: "Progressive Direct , is" — the ℠ mark was dropped, leaving a
  stray space.
- Fixed by cleanup: the EX-99.A header block (now stripped generically) and
  the five "- 1 -" page markers that split sentences.

### PGR_2006_Q1 (quarterly, Wayback HTML), PGR_2006_Q2, PGR_2006_Q3 (EX-99)
- Q1 fixed in text: Wayback navigation text after the signature ("CONTINUE TO
  Objectives, Policies and Operations Summary See Archived Version: Letter to
  Shareholders, 2005 Annual Report"); "Progressive Direct , but" dropped ℠.
- Q1 fixed by cleanup: "2006 1st Quarter" header run into the first sentence.
- Q2 fixed in text: page marker "-1-" fused into a word — "increased
  -1competition in both our light local and truck segments".
- Q3: clean. Footnote "(1) As detailed in The Ultimate Question by Fred
  Reichheld" after the signature is the letter's own footnote, kept.
- Q3 fixed by cleanup: "2006 Third Quarter President's Letter" header.

### PGR_2006_Q4 (annual, EX-99)
- Clean text. Fixed by cleanup: the "Marketing Culture" and "Retention"
  subheads were run into their paragraphs, and bold product names that the
  HTML split onto their own lines ("Progressive / Direct / is the name…") are
  rejoined. A general rule now recognizes short Title Case subheads between
  paragraphs; it was checked against every letter and picks up ~45 real
  headings in the 2007–2024 annual letters ("Our People and Culture",
  "Competitive Dynamics", "Strategic Pillars"…).

### Lost ordinal suffixes (EDGAR HTML, 2007–2024) — fixed across 14 letters
The EDGAR filings set ordinal suffixes as superscripts, and the extraction
dropped them: "the 15 quarter in a row", "its 85 anniversary", "the 96
percentile", "October 1 .", "May 3 .". A search for numbers followed by words
that need an ordinal, plus dates followed by a space and punctuation, found
26; each was checked in context and restored (2007 Q3, 2008 Q2, 2008 Q3,
2013 Q3, 2016 Q1, 2017 Q2, 2018 Q1, 2019 Q2, 2019 Q3, 2020 Q2, 2020 Q3,
2021 Q4, 2022 Q1, 2022 Q2, 2022 Q4, 2023 Q4, 2024 Q1). Plural uses such as
"in the 43 states" and "the 18 months" were left alone.

### PGR_2007_Q1, PGR_2007_Q2, PGR_2007_Q3 (quarterly, EX-99)
- Clean and complete apart from the Q3 ordinals above ("October 1st",
  "October 5th", "August 31st").
- Q2 ends with "Net Promoter is a registered trademark of Satmetrix Systems,
  Inc." after the signature — the letter's own footnote, kept.

### PGR_2007_Q4 (annual, EX-99)
- Clean and complete. Fixed by cleanup: "Growth", "Competitive Dynamics",
  "Capital Management and Investing" and "Looking forward" subheads were run
  into their paragraphs ("Capital Management and Investing 2007 was an active
  year…").

### PGR_2008_Q1, PGR_2008_Q2, PGR_2008_Q3 (quarterly, EX-99)
- Clean and complete apart from the lost ordinals listed above ("May 1st",
  "the 3rd quarter 2006").

### PGR_2008_Q4 (annual, EX-99)
- Fixed in text: the five subheads Renwick explicitly reuses from the prior
  year's closing list ("Building a stronger brand and communicating it well",
  "Building on our retention gains…", "Maintaining a focus on operating at a
  lower cost…", "Creating more responsive product and service offerings…",
  "Continuing to be innovative in all we do") were run into their paragraphs
  ("…communicating it well We let 'Flo' loose…"); now headings. "AN / UPDATE"
  heading split over two lines.
- Fixed in text: "May 1 ." → "May 1st." (a non-breaking space had hidden it
  from the first ordinal search; re-ran the search tolerant of that and found
  no others); "MyRate / sm" → "MyRate℠"; "Name Your Price , which" stray space
  from a dropped mark.
- Note: "The graph makes the point better than my words" refers to a frequency
  chart that is not in the filing text.

### Dropped trademark / footnote superscripts (EDGAR HTML, 2009–2023)
The same superscript loss that removed ordinals also dropped ® / ℠ marks and
footnote numbers, leaving a space before the next punctuation: "Snapshot ,
our usage-based…", "“Name Your Price ” program", "Progressive Home Advantage
.", "HomeQuote Explorer .", "Snapshot ProView ,". 41 occurrences across 22
letters. Fixed by cleanup (the space is removed; the mark itself is not
re-inserted because which mark each product carried in a given year isn't
recoverable from the text). One was a lost ordinal instead: 2021 Q4 "Sunday
Jan 9 ." → "Jan 9th." (fixed in text).

### PGR_2009_Q1, PGR_2009_Q2, PGR_2009_Q3 (quarterly, EX-99)
- Clean and complete apart from the dropped "Name Your Price" marks above.

### PGR_2009_Q4 (annual, EX-99)
- Clean text. Fixed in text: the styled lead-in words of two sections were
  split onto their own lines ("Commenting on the" / "94.6% combined…",
  "Nothing we have" / "achieved…"), which kept the "Underwriting Results" and
  "Our Culture and Credits" subheads from being recognized. Same fix in
  2010 Q4 ("Product Development") and 2012 Q4 (three sections).

### PGR_2010_Q1, PGR_2010_Q2, PGR_2010_Q3 (quarterly, EX-99)
- Clean and complete. Q1 is the shortest quarterly letter in the archive
  (585 words) but has a full open, results discussion and close.

### PGR_2010_Q4 (annual, EX-99)
- Clean and complete. Subheads (Underwriting Results, A Destination Company,
  Brand Strategy, Product Development, Operational Skills, Investments and
  Capital, Our People and Culture) now render as headings.

### PGR_2011_Q1, PGR_2011_Q2, PGR_2011_Q3 (quarterly, EX-99)
- Clean and complete. Q1's "First", "Second", "Third" growth-initiative
  labels render as subheads, as laid out in the filing.
- Q3 fixed in text: "Our rd quarter combined ratio was 95.2" — the reverse of
  the usual superscript loss: the suffix survived and the digit did not.
  Restored as "3rd". A search for other orphaned suffixes found one more, in
  2013 Q2, where the number cannot be inferred (flagged there).

### PGR_2011_Q4 (annual, EX-99)
- Fixed in text: an industry growth / combined-ratio table (2006–2010)
  flattened into "Industrywide Premium Growth Combined Ratio 2006 0.4% 94.2
  2007 (0.7)% 97.7…"; rebuilt as one readable sentence.
- Fixed in text: "double-digit growth in the 3 and 4 quarters" → "3rd and
  4th" (lost ordinals in a form the first search missed).
- Fixed in text: a quotation's closing mark had slid onto the next paragraph
  ("…will turn positive. / ” This appears…"); "Closing Speed –" and "Product
  Potential -" run-in heads promoted to headings.

### PGR_2012_Q1, PGR_2012_Q2, PGR_2012_Q3 (quarterly, EX-99)
- Clean and complete.

### PGR_2012_Q4 (annual, EX-99)
- Fixed in text: "Figure 1" (1/3/5-year growth in policies in force and
  policy life expectancy) flattened into numbers and fused with the next
  sentence; rebuilt as two sentences.
- Fixed in text: "Our Business Model", "A Snapshot of 2012", "Claims in the
  Spotlight", "Investments and Capital Management" subheads were run into
  their paragraphs (split lead-in words, see 2009 Q4).
- Flagged: "…to even higher levels. More to follow Over the next few years,
  we will provide…" — probably lost punctuation after "More to follow" (the
  2012 Q1 letter ends with the same phrase, also without a period).

### PGR_2013_Q1, PGR_2013_Q2, PGR_2013_Q3 (quarterly, EX-99)
- Q1 fixed in text: "We opened our 55 and 56 Service Centers" → "55th and
  56th".
- **Q2 flagged — needs the source:** "We were delighted to receive the Keynote
  recognition as best website for the th time" — the number before "th" was
  lost and cannot be inferred (the 2010 letter counts 16 of 17 Keynote
  awards; by mid-2013 it is some higher number). Check the EDGAR exhibit.
- Q3 fixed in text: "branding effor / ts" — a word split across lines; a
  corpus search for other split suffixes found none.
- Q3 "3rd quarter last year" is printed correctly here (the ordinal survived).

### PGR_2013_Q4 (annual, EX-99)
- Clean and complete. Exhibit A (Renwick's business-model statement) and
  Exhibit B (excerpts from Peter Lewis's 2000 letter, reprinted after his
  death in November 2013) are part of the letter and kept; this is why the
  letter has two signature blocks.
- Fixed in text: "most of all Peter B. LewisThanks for making Progressive,
  progressive" — the line break between the dedication and the closing line
  was lost; "Exhibit A / Our Business Model" headings set as headings.

### PGR_2014_Q1, PGR_2014_Q2, PGR_2014_Q3 (quarterly, EX-99)
- Clean and complete. Fixed by cleanup: the one-line header "EXHIBIT exhibit
  99 Shareholder Letter 6.30.14 Exhibit 99 Letter to Shareholders Second
  Quarter 2014" run into the first sentence, and the one-line signature.
- Q2 fixed in text: "Snap shot en rollment" → "Snapshot enrollment". A corpus
  search for words split by a space (adjacent fragments whose join appears
  elsewhere as a word) found no other extraction splits.

### PGR_2014_Q4 (annual, EX-99)
- Fixed in text: the opening dictionary entry for "era" was broken into
  fragments ("1.", "2a." alone on lines; "the Reagan era . b .") and its last
  line was fused with the first sentence of the letter ("…bronze coin.]
  Viewing Progressive as a series of interconnected eras…"). Rebuilt as one
  entry followed by the letter; word-for-word identical.
- Fixed in text: "débuted its 100 commercial" → "100th"; "No.1"; four run-in
  section heads (Looking back, Business Update, Destination Era, Our People
  and Culture).

### PGR_2015_Q1, PGR_2015_Q2, PGR_2015_Q3 (quarterly, EX-99)
- Clean and complete.

### PGR_2015_Q4 (annual, EX-99)
- Clean and complete. Em dashes were flattened to unspaced hyphens at
  extraction ("top $20 billion in 2015-a 10% growth rate", "ASI-the
  controlling interest"); readable, left as is.

### PGR_2016_Q1, PGR_2016_Q2, PGR_2016_Q3 (quarterly, EX-99)
- Clean and complete. Q2 is Renwick's last letter, signed informally
  ("Cheers, Glenn" / "/s/ Glenn"); Q3 is Griffith's first ("Best, / Tricia").
  Neither has a printed title, which is accurate to the filings.
- Fixed by cleanup: Q2's name was repeated after the sign-off ("Cheers, Glenn
  / Glenn"); the "/s/" stamp is now dropped when the sign-off already names
  the signer.
- Q1 lost ordinal fixed ("the 1st quarter", listed above).

### PGR_2016_Q4 (annual, EX-99)
- Clean and complete. Fixed by cleanup: the "EX-99.0 exhibit990123116.htm /
  EXHIBIT 99.0 / Exhibit / Exhibit 99 / LETTER TO SHAREHOLDERS" header block.

### PGR_2017_Q1, PGR_2017_Q2, PGR_2017_Q3 (quarterly, EX-99)
- Clean and complete. Fixed by cleanup: the 2017 Q1/Q2 header lines and the
  "/s/ Tricia Tricia Griffith President and…" one-line signature.
- Q3 fixed in text: "T / he Federal Open Market Committee" — a drop cap split
  from its word. The same search found "M / arket conditions" in 2021 Q3
  (fixed there).
- Q2 "talk to an licensed expert" is in the filing; left as published.

### PGR_2017_Q4 (annual, EX-99)
- Clean and complete.

### PGR_2018_Q1, PGR_2018_Q2, PGR_2018_Q3 (quarterly, EX-99)
- Clean and complete apart from the Q1 dates listed under lost ordinals
  ("March 1st", "May 3rd", "March 9th").

### PGR_2018_Q4 (annual, EX-99)
- Clean and complete.

### PGR_2019_Q1, PGR_2019_Q2, PGR_2019_Q3 (quarterly, EX-99)
- Clean and complete apart from the lost ordinals listed above ("the 10th
  quarter in a row", "the 96th percentile", "90th birthday", "the 15th
  quarter", "October 1st").
- Q3: the four Business Roundtable stakeholder subheads ("Delivering value
  to our customers", "Investing in our employees", "Dealing fairly and
  ethically with our suppliers", "Supporting the communities in which we
  work") set as headings — they were run into their paragraphs.

### PGR_2019_Q4 (annual, EX-99)
- Clean and complete. "Back to the 'Broad' Future" subhead set as a heading.
- Note: the expense and claims-quality passages refer to "the imbedded charts"
  and "this graph"; the charts are images and not part of the filing text.

### PGR_2020_Q1, PGR_2020_Q2, PGR_2020_Q3 (quarterly, EX-99)
- Q1 (the first COVID-19 letter): clean and complete.
- Q2: clean; "Reflecting on our world" subhead set as a heading; "our 45th
  state" (lost ordinal, listed above).
- Q3 fixed in text: "Hurricane Delta… marked the 26 named storm this year" →
  "26th"; seven section heads run into their first sentences ("Property
  While our Property business…", "Investments The third quarter…"); the four
  numbered Diversity and Inclusion objectives had their "1." "2." "3." "4."
  markers split from the item text.

### PGR_2020_Q4 (annual, EX-99)
- Fixed in text: the "Charitable Contributions" table (18 recipients) was
  flattened into one run of names and dollar amounts and fused with the next
  section ("…Together We Rise 250,000 $ 21,574,000 Leading Brand: The year
  2020…"). Rebuilt as one line per recipient; the amounts sum to the printed
  $21,574,000 total.
- Fixed in text: the four Diversity and Inclusion commitments, set as
  bullets, were run into one paragraph ("• maintaining… • contributing… •
  reflecting… • having our leadership reflect the people they lead We know
  that…"); "Details of the Year", "Our Strategic Pillars", "Let's wrap up
  2020" subheads split from their paragraphs.
- Not changed: the letter signs "Best, Tricia Griffith" and then carries the
  signature block with her name again; that is how the filing reads.

### PGR_2021_Q1, PGR_2021_Q2, PGR_2021_Q3 (quarterly, EX-99)
- Q1: clean and complete.
- **Q2 flagged — needs the source:** "bringing the state footprint to 22
  states at the end of the quarter that represented % of the commercial
  multi-peril market" — the percentage figure was lost. (Q1 gives 19 states =
  37%; Q3 gives 29 states = about 55%; the Q2 number is between them but
  cannot be recovered from the text.) A search for other orphaned "%" signs
  found none.
- Q3 fixed in text: "M / arket conditions remain encouraging" (drop-cap
  split).

### PGR_2021_Q4 (annual, EX-99)
- Clean and complete. Lost ordinals restored ("the 7th consecutive year",
  "the 97th percentile", "Sunday Jan 9th", and "In 1988, we ranked 37th" —
  the last is the most judgment-dependent; the filing drops every
  superscript ordinal, and "ranked 37 when we compared ourselves against the
  entire property-casualty market" reads as a rank, not a count).
- "The year of adapting to volatile trends" and "Flexing into the new year"
  subheads set as headings.

### PGR_2022_Q1, PGR_2022_Q2, PGR_2022_Q3 (quarterly, EX-99)
- Clean and complete apart from lost ordinals listed above ("its 85th
  anniversary", "our 37th state", "Progressive's 85th anniversary").
- Q3: a story ending "#ProgressiveStrong" ran into the introduction of the
  next story ("…#ProgressiveStrong Alan is a Progressive employee…"); split.

### PGR_2022_Q4 (annual, EX-99)
- Clean and complete. Lost ordinals restored: "our 85th anniversary", "the
  10th anniversary of our Keys to Progress…", "marked by our 200th campaign
  ad".

### PGR_2023_Q1, PGR_2023_Q2, PGR_2023_Q3 (quarterly, EX-99)
- Clean and complete. Fixed by cleanup: "We ’ re excited" (Q3), an
  apostrophe extracted as a separate span.

### PGR_2023_Q4 (annual, EX-99)
- Lost ordinals restored: "on its 56th campaign", "the gifting of our
  1,000th vehicle", "its 200th home makeover", "my 35th Progressive
  anniversary".
- The "NO AMBIGUITY" heading had its subtitle "(at least of what we needed
  to do)" on a separate line, which ran into the next paragraph; joined
  into one heading.
- "…to execute our plan / – / enter uncertainty" had the dash on its own
  line; rejoined.
- Fixed by cleanup: after a story introduced by "…shared her experience
  saying:", every later paragraph in the letter was styled as a quote,
  including the closing section. Story quote mode now ends at the first
  paragraph after a fully quoted passage that does not open another
  quotation. The same fix corrects closing paragraphs in 2025 Q3, 2025 Q4
  and 2026 Q2.

### PGR_2024_Q1, PGR_2024_Q2, PGR_2024_Q3 (quarterly, EX-99)
- Clean and complete. The employee stories in Q1 (introduced by "…wrote:"
  and "The story below is from…") are reproduced without quotation marks
  and are styled as quotes through "I hope those two stories…".
- Q1, flagged only: "this is further evidence that our efforts to promote
  the well-being of our employees, prioritize communication and listening
  strategies, and integrate engagement into every stage of our employee
  and manager lifecycle." The sentence has no main verb ("…are working"?).
  This looks like the published wording, not a scrape loss.
- Q2 and Q3 close with a handwritten "Tricia" above the typed name; kept.

### PGR_2024_Q4 (annual, EX-99)
- "Understanding" and its subtitle "(by the numbers with some stories)"
  sat on two lines, and the subtitle ran into the first paragraph of the
  section ("…stories) What we thought would transpire…"); joined into one
  heading.
- Fixed by cleanup: line breaks inside curly quotes left "“ While I was…"
  and "…supplies, ” Jill shares" (the same artifact in 2020 Q2, 2022 Q4
  and 2009). Also, a quotation closed by an attribution ("…” Jill shares.")
  left quote styling on the following paragraphs.
- The three DEI subheads ("Our people reflect the customers we serve…",
  "We maintain a fair and inclusive work environment.", "We contribute to
  our communities.") are full sentences and stay as paragraphs.

### PGR_2025_Q1, PGR_2025_Q2, PGR_2025_Q3 (quarterly, EX-99)
- Q1: the sign-off of Courtney's customer note ("Tired mom of two 16yr
  olds, a 15yr old, and 14yr old / Courtney") ran into the closing
  paragraph ("…Courtney We head into the second quarter…"); separated.
- Q2 and Q3 clean and complete. Fixed by cleanup: short fully quoted
  follow-on lines in Q2 ("“It breaks my heart, but the work is so
  rewarding.”") now keep the quote styling of the quote they continue, and
  Q3's closing paragraphs are no longer styled as a quote.

### PGR_2025_Q4 (annual, EX-99)
- Clean and complete.
- Flagged only: "We know that is it very easy to shop for insurance and
  switch carriers" — transposed "it is"; probably as published.
- Fixed by cleanup: the "Adina and Chris…" paragraph is the CEO's own
  narration, not a quote (removed the "I'd like to share a powerful story"
  story trigger, which matched only this letter). Non-breaking hyphens
  ("in‑house", "side‑by‑side") are normalized in the plain-text output.

### PGR_2026_Q1, PGR_2026_Q2 (quarterly, EX-99)
- Q1: "Alexzandrea's story", "Michelle's story" and "Kim's story" are
  subheads; the first ran into its story ("Alexzandrea's story “I grew
  up…"). All three set as headings.
- Q2 clean and complete.
