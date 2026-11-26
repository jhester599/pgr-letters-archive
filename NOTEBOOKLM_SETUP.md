# NotebookLM Authentication Setup

How to capture your Google session credentials and store them as the
`NOTEBOOKLM_AUTH_JSON` GitHub Actions secret.

This needs to be done once initially, then repeated every **2–4 weeks** when
the session cookies expire. You'll know it's time when the
**Generate podcast audio** step fails and the run summary says
"NotebookLM audio generation did not complete".

---

## Quick refresh (Windows PowerShell)

Run these from the repo root. Each block is one step.

**1. Activate the venv**

```powershell
cd C:\path\to\pgr-letters-archive
.venv\Scripts\Activate.ps1
```

If PowerShell refuses to run the activation script, allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**2. Sign in again** — a browser opens; sign in to Google (including 2FA) and
wait until the NotebookLM home page loads.

```powershell
notebooklm login
```

If the bundled Chromium crashes or Google blocks the sign-in, use your
installed Chrome or Edge instead:

```powershell
notebooklm login --browser chrome
```

**3. Confirm the new session works**

```powershell
notebooklm auth check --test
```

**4. Copy the session JSON to the clipboard**

```powershell
$auth = "$env:USERPROFILE\.notebooklm\profiles\default\storage_state.json"
if (-not (Test-Path $auth)) { $auth = "$env:USERPROFILE\.notebooklm\storage_state.json" }
Get-Content $auth -Raw | Set-Clipboard
```

Recent notebooklm-py versions save to `profiles\default\`; older ones saved to
`~\.notebooklm\storage_state.json`. The two lines above pick whichever exists.

**5. Update the GitHub secret**

1. Open <https://github.com/jhester599/pgr-letters-archive/settings/secrets/actions>
2. Click the pencil next to **`NOTEBOOKLM_AUTH_JSON`** (or **New repository
   secret** if it doesn't exist yet)
3. Paste the clipboard contents and click **Update secret**

Or, if you have the GitHub CLI (`gh`) installed and signed in, skip the
clipboard and set it directly:

```powershell
Get-Content $auth -Raw | gh secret set NOTEBOOKLM_AUTH_JSON --repo jhester599/pgr-letters-archive
```

**6. Re-run the audio**

Either re-run the failed workflow from the Actions tab, or generate it locally
right away (the local run reads the session file directly, no env var needed):

```powershell
python scripts/generator.py --max-new 1
python scripts/compressor.py
```

`scripts/setup_notebooklm.ps1` does steps 2 and 4 for you (and installs the
packages first) if you'd rather run one script.

---

## First-time setup

### Prerequisites

```bash
pip install -r requirements.txt
playwright install chromium
```

### macOS / Linux

```bash
notebooklm login
notebooklm auth check --test
cat ~/.notebooklm/profiles/default/storage_state.json | pbcopy                       # macOS
cat ~/.notebooklm/profiles/default/storage_state.json | xclip -selection clipboard   # Linux
```

Then add the clipboard contents as the `NOTEBOOKLM_AUTH_JSON` repository secret
(**Settings → Secrets and variables → Actions → New repository secret**).

On Windows, follow the Quick refresh steps above. They are the same for a
first-time setup.

---

## Notes

- The JSON contains your Google session cookies. Treat it like a password and
  never commit it to the repository.
- 2-Step Verification is fine: you complete it interactively during
  `notebooklm login`. The saved cookie persists for the rest of the session
  lifetime.
- If `notebooklm` or `playwright` is "not recognized", the venv is not active.
  Activate it and try again.
- Sessions can't be renewed unattended, which is why the workflow's audio step
  is `continue-on-error`: letters, summaries, pages and the RSS feed still
  publish while the cookie is stale.
