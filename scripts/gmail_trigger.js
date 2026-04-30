/**
 * gmail_trigger.js — Google Apps Script
 *
 * Watches a dedicated Gmail inbox for Progressive Corporation SEC filing
 * alert emails and fires a GitHub Actions workflow via repository_dispatch
 * whenever a 10-Q or 10-K alert arrives.
 *
 * ── SETUP (one-time) ──────────────────────────────────────────────────────────
 *
 * 1. The dedicated Gmail account for this project is:
 *      pgr.letters.archive@gmail.com
 *
 * 2. Subscribe that address to Progressive's investor email alerts at:
 *      https://investors.progressive.com/investor-resources/investor-email-alerts/default.aspx
 *    Select at minimum: "SEC Filings — 10-Q and 10-K"
 *    Send yourself a test email after subscribing and note the exact From address.
 *
 * 3. Open Google Apps Script in that Gmail account:
 *      https://script.google.com → New project → paste this file's contents.
 *
 * 4. Create a GitHub Fine-Grained Personal Access Token (PAT):
 *      https://github.com/settings/tokens?type=beta
 *    Settings:
 *      • Resource owner:   jhester599
 *      • Repository:       pgr-letters-archive
 *      • Permissions:      Actions → Read and Write
 *    Copy the token (shown only once).
 *
 * 5. Store the PAT in Apps Script (never hard-code it):
 *      In the script editor → Project Settings → Script Properties → Add:
 *        Key:   GITHUB_PAT
 *        Value: <your token>
 *
 * 6. Update PROGRESSIVE_SENDER below after verifying the actual From address
 *    of the first alert email you receive. A safe fallback is to leave it as
 *    an empty string ("") to skip sender filtering and rely on subject matching only.
 *
 * 7. Run checkForFilingAlerts() once manually to grant Gmail permissions
 *    (Apps Script will prompt for authorization on first run).
 *
 * 8. Set the script timezone to match Eastern Time so the active-hours
 *    guard works correctly:
 *      Project Settings (gear icon) → Time zone → America/New_York
 *
 * 9. Set up the time-driven trigger:
 *      Triggers (clock icon) → Add Trigger:
 *        Function:         checkForFilingAlerts
 *        Event source:     Time-driven
 *        Type:             Hour timer
 *        Interval:         Every hour
 *    The script itself limits execution to M–F 7 am–7 pm ET, so the
 *    hourly trigger simply exits immediately outside that window.
 *
 * ── HOW IT WORKS ─────────────────────────────────────────────────────────────
 *
 * Every 15 minutes the script searches Gmail for unread messages that look like
 * a Progressive 10-Q or 10-K filing alert. If it finds one it:
 *   1. Calls the GitHub API to fire a repository_dispatch event.
 *   2. Applies a "PGR-Processed" label so the email is never processed twice.
 *   3. Logs the action (visible in Apps Script → Executions).
 *
 * The GitHub workflow's weekly Friday cron remains active as a fallback in case
 * the email never arrives or the Apps Script misses a trigger window.
 */

// ── Configuration ─────────────────────────────────────────────────────────────

const GITHUB_REPO_OWNER = "jhester599";
const GITHUB_REPO_NAME  = "pgr-letters-archive";
const DISPATCH_EVENT    = "sec-filing-alert";

// From address used by Progressive's investor alert service (via Q4 Inc / SendGrid).
// Confirmed from the subscription confirmation email:
//   From:      Progressive <investor_relations@progressive.com>
//   Mailed-by: mail-sendgrid.q4inc.com
//   Signed-by: q4inc.com
// Matching on the envelope domain "q4inc.com" is the most durable filter —
// it survives any display-name or subdomain changes on Progressive's end.
const PROGRESSIVE_SENDER = "q4inc.com";

// Gmail search query — finds unread filing alerts not yet processed.
// Apps Script's GmailApp.search() uses Gmail search syntax.
const GMAIL_SEARCH = buildSearchQuery();

// Label applied to processed emails to prevent re-triggering.
const PROCESSED_LABEL_NAME = "PGR-Processed";

// ── Active-hours guard ────────────────────────────────────────────────────────
// Script timezone must be set to America/New_York in Project Settings so
// getDay() / getHours() reflect Eastern Time.

function isWithinActiveHours() {
  const now  = new Date();
  const day  = now.getDay();    // 0 = Sun … 5 = Fri … 6 = Sat
  const hour = now.getHours();  // 0–23 in script timezone (ET)
  return day >= 1 && day <= 5   // Monday–Friday
      && hour >= 7 && hour < 19; // 7 am up to (not including) 7 pm
}

// ── Main function (called by hourly time-driven trigger) ──────────────────────

function checkForFilingAlerts() {
  if (!isWithinActiveHours()) {
    Logger.log("Outside active window (M–F 7 am–7 pm ET). Skipping.");
    return;
  }

  const threads = GmailApp.search(GMAIL_SEARCH);

  if (threads.length === 0) {
    Logger.log("No unprocessed filing alerts found.");
    return;
  }

  const processedLabel = getOrCreateLabel(PROCESSED_LABEL_NAME);
  let triggered = false;

  for (const thread of threads) {
    for (const message of thread.getMessages()) {
      if (!message.isUnread()) continue;  // already handled in a prior run

      const subject = message.getSubject();
      const from    = message.getFrom();

      // Double-check the message looks like a filing alert (guards against
      // false positives if the search query is broad).
      if (!isFilingAlert(subject, from)) {
        Logger.log(`Skipping non-alert message: "${subject}" from ${from}`);
        continue;
      }

      Logger.log(`Filing alert detected: "${subject}" from ${from}`);

      if (!triggered) {
        // Only fire one dispatch per run regardless of how many emails arrived.
        const success = triggerGitHubWorkflow(subject, from);
        if (success) triggered = true;
      }

      // Mark as read and label so it won't be picked up again.
      message.markRead();
      thread.addLabel(processedLabel);
    }
  }

  if (!triggered && threads.length > 0) {
    Logger.log("Threads found but none qualified as filing alerts.");
  }
}

// ── GitHub dispatch ───────────────────────────────────────────────────────────

function triggerGitHubWorkflow(subject, from) {
  const pat = PropertiesService.getScriptProperties().getProperty("GITHUB_PAT");
  if (!pat) {
    Logger.log("ERROR: GITHUB_PAT not found in Script Properties. See setup instructions.");
    return false;
  }

  const url     = `https://api.github.com/repos/${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}/dispatches`;
  const payload = {
    event_type: DISPATCH_EVENT,
    client_payload: {
      source:  "progressive-investor-email",
      subject: subject,
      from:    from,
      fired_at: new Date().toISOString(),
    },
  };

  const options = {
    method:            "post",
    contentType:       "application/json",
    headers: {
      "Authorization":        `Bearer ${pat}`,
      "Accept":               "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    payload:           JSON.stringify(payload),
    muteHttpExceptions: true,
  };

  const response = UrlFetchApp.fetch(url, options);
  const status   = response.getResponseCode();

  if (status === 204) {
    Logger.log(`✓ GitHub workflow triggered successfully (HTTP ${status}).`);
    return true;
  } else {
    Logger.log(`✗ GitHub API returned HTTP ${status}: ${response.getContentText()}`);
    return false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildSearchQuery() {
  // Base: unread, in inbox, not yet labeled as processed, contains filing keywords.
  let query = `is:unread in:inbox -label:${PROCESSED_LABEL_NAME} ` +
              `subject:(10-Q OR 10-K OR "quarterly report" OR "annual report")`;

  // Narrow by sender if configured.
  if (PROGRESSIVE_SENDER) {
    query += ` from:${PROGRESSIVE_SENDER}`;
  }

  return query;
}

function isFilingAlert(subject, from) {
  const subjectLower = subject.toLowerCase();
  const hasFilingKeyword = (
    subjectLower.includes("10-q") ||
    subjectLower.includes("10-k") ||
    subjectLower.includes("quarterly report") ||
    subjectLower.includes("annual report") ||
    subjectLower.includes("sec filing")
  );

  // If sender filtering is configured, also verify the From field.
  if (PROGRESSIVE_SENDER) {
    return hasFilingKeyword && from.toLowerCase().includes(PROGRESSIVE_SENDER.toLowerCase());
  }

  return hasFilingKeyword;
}

function getOrCreateLabel(name) {
  const existing = GmailApp.getUserLabelByName(name);
  return existing || GmailApp.createLabel(name);
}
