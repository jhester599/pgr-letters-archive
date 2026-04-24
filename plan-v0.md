System Role: You are an expert Python developer, data engineer, and web architect.

Objective: I need a complete Python-based automation pipeline that scrapes historical SEC filings for The Progressive Corporation (NYSE: PGR), extracts the CEO's quarterly letters, generates podcast-style audio overviews using NotebookLM, compresses the audio, and organizes everything into a GitHub repository with a web front-end. I also need a GitHub Actions workflow to fully automate this going forward.

Technical Requirements & Step-by-Step Instructions:

1. SEC Filing Scraper (scraper.py)

Target the ticker PGR.

Search the SEC EDGAR database for historical 10-Q and 10-K filings.

The CEO's quarterly letter to shareholders (written by Tricia Griffith) is typically included as Exhibit 99. Write logic to parse the filings, locate Exhibit 99, extract the raw text, and clean up the HTML/formatting.

Save each cleaned letter as a .txt file in a /data/letters/ directory, named by Year and Quarter (e.g., PGR_2025_Q4_Letter.txt).

Include a state-check mechanism (e.g., a processed_filings.json ledger) so the script skips filings it has already downloaded.

2. Audio Generation (generator.py)

Use the notebooklm-py library to automate the podcast generation.

The script should iterate through the /data/letters/ directory, checking against the ledger for any letters that don't have corresponding audio yet.

Upload the new text to NotebookLM, trigger the audio generation, and download the resulting MP3s into a /data/audio_raw/ directory.

Include rate-limiting (e.g., asyncio.sleep()) and robust error handling so temporary API failures don't crash the entire batch.

3. Audio Compression (compressor.py)

To keep the GitHub repository lean and adhere to file size limits, use FFmpeg via Python's subprocess module.

Re-encode the files from /data/audio_raw/ to 64kbps MP3s (using -codec:a libmp3lame -b:a 64k), outputting them to /docs/audio/. Once compressed successfully, delete the raw files to save runner space.

4. GitHub Repository & Web Front-End (/docs/)

Provide a lightweight HTML/CSS/JS front-end inside a /docs/ folder so it can be hosted seamlessly on GitHub Pages.

The web page should dynamically read the ledger or a generated JSON index, display the text of the letters, and include an embedded HTML5 <audio> player for the corresponding podcast.

Include the metadata tags necessary to eventually turn this into a standard RSS podcast feed, setting the author to Jeff Hester.

5. GitHub Actions Automation (.github/workflows/quarterly_podcast.yml)

Write a workflow that triggers on a cron schedule (e.g., every Friday at midnight) to catch the mid-April, mid-July, mid-October, and late-February/early-March filing windows.

The workflow must:

Set up Python and install requirements.

Install ffmpeg on the runner.

Run scraper.py, generator.py, and compressor.py.

If new files were generated, automatically commit the changes back to the main branch.

Trigger a GitHub Pages deployment.

Provide instructions on which repository secrets need to be configured (e.g., Google account credentials for notebooklm-py and GITHUB_TOKEN permissions).

Output: Please provide the requirements.txt, the directory structure, and the complete, well-commented Python code and YAML configurations for each module.
