# PGR Shareholder Podcast 🎙️📊

An automated pipeline that transforms the Progressive Corporation (NYSE: PGR) CEO's quarterly shareholder letters into an accessible podcast archive. 

This project automatically polls the SEC EDGAR database, extracts "Exhibit 99" (the CEO's letter) from 10-Q and 10-K filings, and uses Google's NotebookLM AI to generate an audio overview. The resulting audio is compressed and published to a static GitHub Pages front-end with an embedded audio player and RSS feed.

## 🏗️ Architecture & Pipeline

The project relies on a 100% serverless, automated pipeline orchestrated via GitHub Actions:

1. **Scraping (`scraper.py`):** Queries the SEC EDGAR API for recent PGR filings, isolates Exhibit 99, and extracts/cleans the text.
2. **Audio Generation (`generator.py`):** Interacts with NotebookLM via `notebooklm-py` to generate the podcast-style "Audio Overview."
3. **Compression (`compressor.py`):** Uses FFmpeg to compress the raw audio down to 64kbps MP3s, adhering to GitHub's file size limits without sacrificing voice quality.
4. **Publishing:** Updates the internal JSON ledger and pushes the new files back to the `main` branch, triggering a GitHub Pages deployment.

## 📂 Repository Structure

```text
├── .github/
│   └── workflows/
│       └── quarterly_podcast.yml   # Cron job automation (runs weekly)
├── data/
│   ├── letters/                    # Raw text of extracted quarterly letters
│   └── audio_raw/                  # Temporary holding for uncompressed audio
├── docs/                           # GitHub Pages web root
│   ├── index.html                  # Front-end UI
│   ├── audio/                      # Compressed 64kbps MP3s
│   └── ledger.json                 # State-tracking of processed quarters
├── scripts/
│   ├── scraper.py
│   ├── generator.py
│   └── compressor.py
├── requirements.txt
└── README.md
