import subprocess
import json
import math
from datetime import datetime, timezone, timedelta
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def get_recent_videos(handle: str, lookback_days: int, max_count: int) -> list[dict]:
    """
    Fetch recent videos from a YouTube channel using yt-dlp.
    Returns list of dicts with keys: id, title, description, url, published_at.
    """
    url = f"https://www.youtube.com/{handle}/videos"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", str(max_count),
        "--print", "%(id)s\t%(title)s\t%(description)s\t%(upload_date)s",
        "--no-warnings",
        "--quiet",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"yt-dlp error for {handle}: {result.stderr.strip()}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    videos = []

    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        video_id, title, description, upload_date = parts
        if not upload_date or len(upload_date) != 8:
            continue
        try:
            published = datetime(
                int(upload_date[:4]),
                int(upload_date[4:6]),
                int(upload_date[6:8]),
                tzinfo=timezone.utc,
            )
        except ValueError:
            continue

        if published >= cutoff:
            videos.append({
                "id": video_id,
                "title": title,
                "description": description,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published.isoformat(),
            })

    return videos


def get_transcript(video_id: str, language: str = "en") -> list[dict]:
    """
    Fetch transcript segments for a video.
    Each segment: {text, start, duration}
    Raises TranscriptsDisabled or NoTranscriptFound if unavailable.
    """
    return YouTubeTranscriptApi.get_transcript(video_id, languages=[language])


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

        current_lines.append(seg["text"].strip())

    if current_lines:
        mm = int(current_block_start) // 60
        ss = int(current_block_start) % 60
        blocks.append(f"[{mm:02d}:{ss:02d}] {' '.join(current_lines)}")

    return "\n".join(blocks)
