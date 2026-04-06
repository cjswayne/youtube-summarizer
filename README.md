# YouTube Video Summarizer

A daily digest pipeline that monitors YouTube channels, fetches transcripts, summarizes them with Claude (Anthropic), and emails you a digest. Runs as a GitHub Action on a self-hosted runner so your residential IP handles YouTube requests without getting blocked.

## How It Works

1. Checks configured YouTube channels via RSS for new videos
2. Fetches transcripts using `youtube-transcript-api`
3. Summarizes each transcript with Anthropic Claude using per-channel instructions
4. Emails an HTML digest with all summaries
5. Tracks processed videos in `processed_videos.json` to avoid duplicates

## Prerequisites

- **Python 3.12+** installed on your machine
- **Git for Windows** (includes Git Bash, required by the GitHub Actions runner)
- A **GitHub account** with a repo for this project
- An **Anthropic API key** ([console.anthropic.com](https://console.anthropic.com))
- A **Gmail App Password** (not your regular password)

### Getting a Gmail App Password

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already on
3. Go to **App Passwords** (search "App Passwords" in account settings)
4. Generate one for "Mail" — save the 16-character password

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/cjswayne/youtube-summarizer.git
cd youtube-summarizer
pip install -r requirements.txt
```

### 2. Configure channels and email

Edit `config.yaml` to add the YouTube channels you want to monitor:

```yaml
channels:
  - handle: "@SomeChannel"
    channel_id: "UCxxxxxxxxxxxxxxxxxxxxxxxxx"
    name: "Channel Display Name"
    instructions: |
      Focus on key updates and announcements.
      Ignore small talk, sponsor reads, and intro/outro.

email:
  to: "you@example.com"
  from: "you@example.com"
  subject_prefix: "[VideoDigest]"

settings:
  lookback_days: 14
  max_videos_per_channel: 5
  transcript_language: "en"
```

To find a channel's `channel_id`, go to the channel page on YouTube, view page source, and search for `channelId` or `externalId`.

### 3. Add GitHub Secrets

Go to your repo on GitHub: **Settings > Secrets and variables > Actions > New repository secret**

Add these two secrets:

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (starts with `sk-ant-`) |
| `GMAIL_APP_PASSWORD` | Your 16-character Gmail app password |

### 4. Run locally (optional test)

Create a `.env` file from the example and fill in your keys:

```bash
cp .env.example .env
# Edit .env with your real values
```

Run it:

```bash
python main.py
```

You can also use the test script to verify transcript fetching works:

```bash
# Validate config without fetching
python test_transcript.py --dry-run

# Fetch a real transcript
python test_transcript.py --video-id dQw4w9WgXcQ
```

## Self-Hosted GitHub Actions Runner

YouTube blocks transcript requests from cloud provider IPs (AWS, Azure, GitHub Actions, etc.). The solution is to run the GitHub Action on your own machine using a **self-hosted runner**. Your residential IP won't be blocked.

### Why self-hosted?

- GitHub-hosted runners use cloud IPs that YouTube blocks
- Datacenter proxies are also blocked
- Residential rotating proxies cost money
- Your home IP works — the self-hosted runner uses it for free

### Install the runner (Windows)

These steps set up the runner at `C:\actions-runner` and register it as a Windows service that starts automatically on boot.

#### Step 1: Download and extract

Open **PowerShell as Administrator** and run:

```powershell
mkdir C:\actions-runner; cd C:\actions-runner

# Download the runner package
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.333.1/actions-runner-win-x64-2.333.1.zip -OutFile actions-runner-win-x64-2.333.1.zip

# Validate the download
if((Get-FileHash -Path actions-runner-win-x64-2.333.1.zip -Algorithm SHA256).Hash.ToUpper() -ne 'd0c4fcb91f8f0754d478db5d61db533bba14cad6c4676a9b93c0b7c2a3969aa0'.ToUpper()){ throw 'Computed checksum did not match' }

# Extract
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD\actions-runner-win-x64-2.333.1.zip", "$PWD")
```

> Check [actions/runner releases](https://github.com/actions/runner/releases) for the latest version. The hash above is for v2.333.1.

#### Step 2: Configure and install as service

Get a registration token from GitHub: go to your repo **Settings > Actions > Runners > New self-hosted runner**. Copy the token from the `config` command shown on that page.

Still in the **Admin PowerShell**:

```powershell
cd C:\actions-runner

.\config.cmd --url https://github.com/YOUR_USER/youtube-summarizer --token YOUR_TOKEN --name youtube-summarizer-runner --work _work --runasservice
```

When prompted:
- **Runner group**: press Enter (Default)
- **Runner name**: press Enter (keeps the name from `--name`)
- **Additional labels**: press Enter (skip)
- **Run as service? (Y/N)**: Y
- **Service account**: press Enter (uses default `NT AUTHORITY\NETWORK SERVICE`)

The service will start automatically.

#### Step 3: Verify

```powershell
# Check the service is running
Get-Service "actions.runner.*" | Select-Object Name, Status, StartType
```

You should see `Status: Running` and `StartType: AutomaticDelayedStart`.

Also check on GitHub: **repo > Settings > Actions > Runners** — your runner should show a green "Idle" status.

### Managing the service

```powershell
# Check status
Get-Service "actions.runner.*"

# Stop the runner
Stop-Service "actions.runner.*"

# Start the runner
Start-Service "actions.runner.*"

# Uninstall (run from C:\actions-runner in Admin PowerShell)
cd C:\actions-runner
.\svc.cmd uninstall
```

### Trigger a test run

Go to your repo on GitHub: **Actions > Daily Video Summarizer > Run workflow**

Select the `main` branch and click "Run workflow". The job should be picked up by your self-hosted runner within seconds.

## Workflow Schedule

The action runs daily at **3:00 PM UTC** (7:00 AM PST / 8:00 AM PDT). Edit the cron expression in `.github/workflows/daily.yml` to change the schedule:

```yaml
schedule:
  - cron: '0 15 * * *'
```

> Your computer must be on and connected to the internet at the scheduled time for the job to run. Missed jobs do not queue — they are skipped.

## Project Structure

```
youtube-summarizer/
  main.py              # Entry point — orchestrates the pipeline
  fetcher.py           # RSS video discovery + transcript fetching
  summarizer.py        # Anthropic Claude summarization
  emailer.py           # Gmail SMTP HTML digest
  state.py             # processed_videos.json read/write
  config.yaml          # Channels, email, and settings
  requirements.txt     # Python dependencies
  test_transcript.py   # Diagnostic script for transcript fetching
  processed_videos.json  # Tracks which videos have been processed
  .env.example         # Template for local environment variables
  .github/workflows/
    daily.yml           # GitHub Actions workflow
```

## Troubleshooting

### "Request blocked" or "IP blocked" errors

This means YouTube is blocking the IP making the request. If you're running on a self-hosted runner with a residential IP, this is unusual. Try:

1. Run `python test_transcript.py --dry-run` to check connectivity
2. Run `python test_transcript.py` to attempt a real fetch
3. If your home IP is blocked, wait 24 hours — YouTube rate limits are temporary

### Runner shows "Offline" on GitHub

- Check the service is running: `Get-Service "actions.runner.*"`
- Restart it: `Restart-Service "actions.runner.*"`
- If the token expired, re-register the runner with a new token

### Workflow fails at "Commit updated state"

Make sure the repo has **Settings > Actions > General > Workflow permissions** set to "Read and write permissions".

### No email received

- Verify `GMAIL_APP_PASSWORD` secret is set correctly (16-char app password, not your Gmail password)
- Check the `email.to` and `email.from` fields in `config.yaml`
- Check your spam folder
