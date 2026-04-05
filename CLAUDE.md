# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in real values
```

## Running

```bash
python main.py
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `GMAIL_APP_PASSWORD` | Google Account → Security → App Passwords |

## Architecture

Single Python pipeline triggered daily by a Claude Code scheduled remote agent (cron `0 15 * * *` UTC = 7am PST).

**Data flow**: `main.py` → for each channel in `config.yaml`, call `fetcher.py` (yt-dlp for video list, youtube-transcript-api for transcripts) → `summarizer.py` (Claude API → structured JSON) → `emailer.py` (Gmail SMTP, only if summaries exist).

**State**: `processed_videos.json` is committed to git. The remote agent updates and pushes it after each run to persist which videos have been seen.

**Key design decisions**:
- Videos are marked processed even if their transcript is unavailable or their summary is filtered — only hard errors (API failures) leave a video unmarked so it retries the next day.
- `config.yaml` channels use `handle:` (e.g. `@LiquidWeekly`) — yt-dlp resolves these at runtime; no YouTube API key needed.
- Email is only sent when `all_summaries` is non-empty.

## Scheduled Agent

Set up via `/schedule` in Claude Code. The agent prompt contains the actual secret values (embedded in the trigger config server-side, not in this repo). After running `python main.py`, the agent commits and pushes `processed_videos.json` back to main.

## Adding a Channel

Add an entry to `config.yaml`:
```yaml
- handle: "@SomeChannel"
  name: "Display Name"
  instructions: |
    Focus on X. Ignore Y.
```
