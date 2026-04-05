import subprocess
import json
import math
import os
import tempfile
from datetime import datetime, timezone, timedelta

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def _cookies_args() -> list[str]:
    """Return yt-dlp cookie args if cookies.txt exists in the project root."""
    if os.path.exists(COOKIES_FILE):
        return ["--cookies", COOKIES_FILE]
    return []


def get_recent_videos(handle: str, lookback_days: int, max_count: int) -> list[dict]:
    """
    Fetch recent videos from a YouTube channel using yt-dlp.
    Returns list of dicts with keys: id, title, description, url, published_at.
    """
    url = f"https://www.youtube.com/{handle}/videos"
    cmd = [
        "yt-dlp",
        "--playlist-end", str(max_count),
        "--dump-json",
        "--no-warnings",
        "--quiet",
        *_cookies_args(),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  yt-dlp error for {handle}: {result.stderr.strip()}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    videos = []

    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"  Failed to parse yt-dlp JSON line: {e}")
            continue

        upload_date = data.get("upload_date", "")
        print(f"  Found: {data.get('title', '?')!r} uploaded {upload_date}")

        if not upload_date or len(upload_date) != 8:
            print(f"  Skipping (no upload_date)")
            continue
        try:
            published = datetime(
                int(upload_date[:4]),
                int(upload_date[4:6]),
                int(upload_date[6:8]),
                tzinfo=timezone.utc,
            )
        except ValueError:
            print(f"  Skipping (bad upload_date format: {upload_date!r})")
            continue

        if published >= cutoff:
            videos.append({
                "id": data["id"],
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "url": f"https://www.youtube.com/watch?v={data['id']}",
                "published_at": published.isoformat(),
            })
        else:
            print(f"  Skipping (older than {lookback_days} days: {published.date()})")

    return videos


def get_transcript(video_id: str, language: str = "en") -> list[dict]:
    """
    Fetch transcript for a video using yt-dlp (auto-generated or manual captions).
    Returns list of dicts with keys: text, start, duration.
    Raises RuntimeError if no transcript is available.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "%(id)s")
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", language,
            "--sub-format", "json3",
            "--no-warnings",
            "--quiet",
            *_cookies_args(),
            "--output", output_template,
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        sub_file = None
        for fname in os.listdir(tmpdir):
            if fname.endswith(".json3"):
                sub_file = os.path.join(tmpdir, fname)
                break

        if not sub_file:
            raise RuntimeError(f"No transcript available for {video_id}")

        with open(sub_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    segments = []
    for event in data.get("events", []):
        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        segs = event.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if text:
            segments.append({
                "text": text,
                "start": start_ms / 1000.0,
                "duration": duration_ms / 1000.0,
            })

    return segments


def format_transcript_with_timestamps(segments: list[dict]) -> str:
    """
    Group transcript segments into ~60-second blocks, each prefixed with [MM:SS].
    Returns a single string for Claude consumption.
    """
    if not segments:
        return ""

    blocks = []
    current_block_start = None
    current_lines = []
    block_duration = 60  # seconds per block

    for seg in segments:
        start = seg["start"]
        text = seg["text"]

        block_index = math.floor(start / block_duration)
        block_start = block_index * block_duration

        if current_block_start is None:
            current_block_start = block_start

        if block_start != current_block_start:
            mm = int(current_block_start) // 60
            ss = int(current_block_start) % 60
            blocks.append(f"[{mm:02d}:{ss:02d}] {' '.join(current_lines)}")
            current_block_start = block_start
            current_lines = []

        current_lines.append(text.strip())

    if current_lines:
        mm = int(current_block_start) // 60
        ss = int(current_block_start) % 60
        blocks.append(f"[{mm:02d}:{ss:02d}] {' '.join(current_lines)}")

    return "\n".join(blocks)
