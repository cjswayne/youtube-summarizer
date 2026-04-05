import subprocess
import json
import math
import os
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def _cookies_args() -> list[str]:
    """Return yt-dlp cookie args if cookies.txt exists in the project root."""
    if os.path.exists(COOKIES_FILE):
        return ["--cookies", COOKIES_FILE]
    return []


def get_recent_videos(channel_id: str, handle: str, lookback_days: int, max_count: int) -> list[dict]:
    """
    Fetch recent videos from a YouTube channel via the RSS feed.
    No yt-dlp needed — no bot detection, no format issues.
    Returns list of dicts with keys: id, title, description, url, published_at.
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(rss_url, timeout=30) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"  RSS fetch error for {handle}: {e}")
        return []

    NS = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt":   "http://www.youtube.com/xml/schemas/2015",
        "media":"http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(xml_data)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    videos = []

    for entry in root.findall("atom:entry", NS)[:max_count]:
        video_id  = entry.findtext("yt:videoId", namespaces=NS) or ""
        title     = entry.findtext("atom:title", namespaces=NS) or ""
        published_str = entry.findtext("atom:published", namespaces=NS) or ""
        media_grp = entry.find("media:group", NS)
        description = ""
        if media_grp is not None:
            description = media_grp.findtext("media:description", namespaces=NS) or ""

        if not published_str:
            continue
        published = datetime.fromisoformat(published_str)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        print(f"  Found: {title!r} published {published.date()}")

        if published >= cutoff:
            videos.append({
                "id": video_id,
                "title": title,
                "description": description,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published.isoformat(),
            })
        else:
            print(f"  Skipping (older than {lookback_days} days: {published.date()})")

    return videos


def get_transcript(video_id: str, language: str = "en") -> list[dict]:
    """
    Fetch transcript using youtube-transcript-api with a cookie-authenticated
    requests.Session, avoiding yt-dlp bot detection on cloud IPs.
    Returns list of dicts with keys: text, start, duration.
    Raises RuntimeError if no transcript is available.
    """
    import requests
    from http.cookiejar import MozillaCookieJar
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, IpBlocked

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    if os.path.exists(COOKIES_FILE):
        cj = MozillaCookieJar()
        try:
            cj.load(COOKIES_FILE, ignore_discard=True, ignore_expires=True)
            session.cookies = cj
        except Exception as e:
            print(f"  Warning: could not load cookies file: {e}")

    try:
        api = YouTubeTranscriptApi(http_client=session)
        fetched = api.fetch(video_id, languages=[language])
        return [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        # Permanent — no transcript exists for this video
        raise RuntimeError(f"No transcript for {video_id}: {e}") from e
    except IpBlocked as e:
        # Transient — let it propagate so main.py retries tomorrow
        raise


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
