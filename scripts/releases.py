#!/usr/bin/env python3
"""
releases.py — GitHub Releases audio hosting helper.

Uploads MP3 files to the 'audio-library' GitHub Release so they can be
served via GitHub-hosted release asset URLs instead of git or Git LFS.

The release acts as a permanent, append-only audio store. Files that are
already present are not re-uploaded.

Environment variables:
    GITHUB_TOKEN  — Personal access token or Actions GITHUB_TOKEN with
                    contents:write permission. If unset, upload_mp3() returns
                    None and logs a warning so local dev still works.
"""

import logging
import os
from pathlib import Path

import requests

# ── Constants ─────────────────────────────────────────────────────────────────

OWNER = "jhester599"
REPO  = "pgr-letters-archive"
TAG   = "audio-library"

API_BASE    = f"https://api.github.com/repos/{OWNER}/{REPO}"
RELEASE_URL = f"{API_BASE}/releases/tags/{TAG}"
RELEASES_URL = f"{API_BASE}/releases"

# ── Logging ───────────────────────────────────────────────────────────────────

log = logging.getLogger(__name__)

# ── Internal helpers ──────────────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_or_create_release() -> tuple[int, str]:
    """Return (release_id, upload_url_template).

    GETs the existing 'audio-library' release first; if it doesn't exist,
    POSTs to create it with a stable tag and name.
    """
    resp = requests.get(RELEASE_URL, headers=_headers(), timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        return data["id"], data["upload_url"]

    if resp.status_code != 404:
        resp.raise_for_status()

    # Release doesn't exist — create it
    log.info("'%s' release not found — creating it now.", TAG)
    payload = {
        "tag_name":         TAG,
        "name":             "PGR Letters Audio Library",
        "body":             (
            "Permanent audio archive for the PGR Letters Archive project. "
            "MP3 files are uploaded here automatically by the pipeline so "
            "GitHub Pages and the podcast feed can reference release-hosted audio."
        ),
        "draft":            False,
        "prerelease":       False,
        "make_latest":      "false",
    }
    resp = requests.post(RELEASES_URL, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    log.info("Created release '%s' (id=%d).", TAG, data["id"])
    return data["id"], data["upload_url"]


def _list_existing_assets(release_id: int) -> dict[str, str]:
    """Return {filename: download_url} for all assets already on the release."""
    assets: dict[str, str] = {}
    page = 1
    while True:
        url  = f"{API_BASE}/releases/{release_id}/assets"
        resp = requests.get(url, headers=_headers(), params={"per_page": 100, "page": page}, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for asset in batch:
            assets[asset["name"]] = asset["browser_download_url"]
        if len(batch) < 100:
            break
        page += 1
    return assets


# ── Public API ────────────────────────────────────────────────────────────────


def upload_mp3(mp3_path: Path, asset_name: str | None = None) -> str | None:
    """Upload an MP3 to the audio-library release if not already present.

    Returns the public download URL on success, or None if:
      - GITHUB_TOKEN is not set (warns; local dev continues unaffected)
      - The file does not exist on disk

    Raises requests.HTTPError on unexpected API failures.
    """
    if not os.environ.get("GITHUB_TOKEN"):
        log.warning(
            "GITHUB_TOKEN is not set — skipping upload of %s. "
            "Set GITHUB_TOKEN to enable audio uploads to GitHub Releases.",
            mp3_path.name,
        )
        return None

    if not mp3_path.exists():
        log.warning("MP3 file not found, skipping upload: %s", mp3_path)
        return None

    release_id, upload_url_template = _get_or_create_release()
    existing = _list_existing_assets(release_id)

    filename = asset_name or mp3_path.name
    if filename in existing:
        log.info("  Already uploaded: %s → %s", filename, existing[filename])
        return existing[filename]

    # Strip the URI template suffix, e.g. "{?name,label}"
    upload_url = upload_url_template.split("{")[0]
    upload_url = f"{upload_url}?name={filename}"

    log.info("  Uploading %s (%.1f MB)…", filename, mp3_path.stat().st_size / 1e6)
    with mp3_path.open("rb") as fh:
        resp = requests.post(
            upload_url,
            headers={**_headers(), "Content-Type": "audio/mpeg"},
            data=fh,
            timeout=300,
        )
    resp.raise_for_status()
    download_url = resp.json()["browser_download_url"]
    log.info("  Uploaded → %s", download_url)
    return download_url
