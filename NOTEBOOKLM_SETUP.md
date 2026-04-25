# NotebookLM Authentication Setup

How to capture your Google session credentials and store them as the
`NOTEBOOKLM_AUTH_JSON` GitHub Actions secret.

This needs to be done once initially, then repeated every **2–4 weeks** when
the session cookies expire.

---

## Prerequisites

```bash
pip install notebooklm-py
playwright install chromium
```

---

## Steps

### 1. Run the login command

```bash
notebooklm login
```

A Chromium browser window will open. Sign in to your Google account normally,
including any 2FA prompts. Once you land on the NotebookLM home page, the
script saves your session cookies automatically and exits.

Cookies are saved to:
```
~/.notebooklm/profiles/default/storage_state.json
```

### 2. Copy the JSON to your clipboard

**macOS:**
```bash
cat ~/.notebooklm/profiles/default/storage_state.json | pbcopy
```

**Linux:**
```bash
cat ~/.notebooklm/profiles/default/storage_state.json | xclip -selection clipboard
```

Or print it to the terminal and copy manually:
```bash
cat ~/.notebooklm/profiles/default/storage_state.json
```

### 3. Add the secret to GitHub

1. Go to your repository on GitHub
2. **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. **Name:** `NOTEBOOKLM_AUTH_JSON`
5. **Value:** paste the full JSON from step 2
6. Click **Add secret**

---

## When to repeat this

Re-run steps 1–3 whenever `generator.py` fails with an authentication error
(typically every 2–4 weeks as Google session cookies expire).

---

## Notes

- The JSON contains your Google session cookies — treat it like a password.
  Never commit it to the repository.
- 2-Step Verification is fine: you complete it interactively during
  `notebooklm login`. The saved cookie persists for the rest of the session
  lifetime.
- If `playwright: command not found`, ensure you are inside the same Python
  virtual environment where `notebooklm-py` is installed.
- The `--max-new 1` flag in the GitHub Actions workflow means only one new
  letter is processed per weekly run, keeping runner time under control.
  Increase this for a manual backfill run.
