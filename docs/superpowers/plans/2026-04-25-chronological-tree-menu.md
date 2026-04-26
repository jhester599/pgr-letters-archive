# Chronological Tree Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat archive episode list with a chronological year drilldown that opens each year to reveal Q4, Q3, Q2, and Q1 entries.

**Architecture:** Keep `docs/index.html` as the single static client page. Continue loading `docs/ledger.json` in the browser, then group filings by year client-side and render accessible native `<details>` year sections with quarter links inside.

**Tech Stack:** Static HTML, embedded CSS, vanilla JavaScript, GitHub Pages.

---

### Task 1: Render Year Groups

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Replace flat episode CSS with tree menu CSS**

Update the sidebar styles around `#episodes`, `#episodes li`, `.ep-inner`, `.ep-title`, and `.ep-meta` to support `.year-group`, `.year-summary`, `.quarter-list`, `.quarter-item`, and `.quarter-link`.

- [ ] **Step 2: Replace the flat `renderEpisodeList()` implementation**

Change `renderEpisodeList()` to:

```javascript
function renderEpisodeList() {
  const ul = document.getElementById("episodes");
  ul.innerHTML = "";

  const sorted = [...ledger.filings]
    .filter(f => f.letter_scraped || f.audio_compressed)
    .sort((a, b) => (b.year * 10 + qNum(b.quarter)) - (a.year * 10 + qNum(a.quarter)));

  if (!sorted.length) {
    ul.innerHTML = '<li><div class="ep-inner"><span class="ep-title">No episodes yet</span></div></li>';
    return;
  }

  const filingsByYear = groupFilingsByYear(sorted);
  const latestYear = Math.max(...Object.keys(filingsByYear).map(Number));

  for (const year of Object.keys(filingsByYear).sort((a, b) => Number(b) - Number(a))) {
    ul.appendChild(renderYearGroup(year, filingsByYear[year], Number(year) === latestYear));
  }
}
```

- [ ] **Step 3: Add grouping and renderer helpers**

Add helpers:

```javascript
function groupFilingsByYear(filings) {
  return filings.reduce((groups, filing) => {
    const year = String(filing.year);
    groups[year] = groups[year] || [];
    groups[year].push(filing);
    return groups;
  }, {});
}

function renderYearGroup(year, filings, openByDefault) {
  const li = document.createElement("li");
  li.className = "year-group";

  const details = document.createElement("details");
  details.open = openByDefault;

  const summary = document.createElement("summary");
  summary.className = "year-summary";
  summary.innerHTML = `<span class="year-label">${year}</span><span class="year-count">${filings.length} letters</span>`;
  details.appendChild(summary);

  const quarterList = document.createElement("ul");
  quarterList.className = "quarter-list";

  for (const filing of filings.sort((a, b) => qNum(b.quarter) - qNum(a.quarter))) {
    quarterList.appendChild(renderQuarterItem(filing));
  }

  details.appendChild(quarterList);
  li.appendChild(details);
  return li;
}
```

- [ ] **Step 4: Add quarter item renderer**

Add:

```javascript
function renderQuarterItem(filing) {
  const li = document.createElement("li");
  li.className = "quarter-item";
  li.dataset.id = filing.id;

  const audioBadge = filing.audio_compressed
    ? '<span class="ep-badge badge-audio">Audio</span>'
    : filing.letter_scraped
    ? '<span class="ep-badge badge-text">Text</span>'
    : '<span class="ep-badge badge-none">Pending</span>';
  const readBadge = filing.page_url
    ? '<span class="ep-badge badge-read">Read</span>'
    : "";

  li.innerHTML = `
    <button class="quarter-link" type="button">
      <span class="quarter-main">
        <span class="ep-title">${filing.quarter} — ${filing.form_type}</span>
        <span class="ep-meta">Period ending ${filing.report_date || "unknown"}</span>
      </span>
      <span class="quarter-badges">${audioBadge}${readBadge}</span>
    </button>`;

  li.querySelector(".quarter-link").addEventListener("click", () => {
    if (filing.page_url && filing.page_url.startsWith("letters/")) {
      window.location.href = filing.page_url;
    } else {
      selectEpisode(filing.id);
    }
  });

  return li;
}
```

### Task 2: Keep Selection Logic Compatible

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Update active highlighting selector**

Change `selectEpisode()` from `document.querySelectorAll("#episodes li")` to `document.querySelectorAll(".quarter-item")`.

- [ ] **Step 2: Auto-open selected year for non-page selections**

Inside `selectEpisode()`, after active highlighting, find the active `.quarter-item`, then set its nearest `details.open = true`.

### Task 3: Verify

**Files:**
- Verify: `docs/index.html`

- [ ] **Step 1: Static sanity checks**

Run a script that verifies `docs/index.html` contains `groupFilingsByYear`, `renderYearGroup`, `renderQuarterItem`, `.year-summary`, and `.quarter-item`.

- [ ] **Step 2: Ledger grouping sanity check**

Run a script against `docs/ledger.json` to confirm the latest year is `2025` and its quarters sort as `Q4,Q3,Q2,Q1`.

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add docs/index.html docs/superpowers/plans/2026-04-25-chronological-tree-menu.md
git commit -m "Add chronological archive tree menu"
git push origin main
```
