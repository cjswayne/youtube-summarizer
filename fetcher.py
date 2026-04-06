import math
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from youtube_transcript_api.proxies import GenericProxyConfig

MAX_TRANSCRIPT_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds; retry delays: 2s, 4s


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


class _RotatingProxyConfig(GenericProxyConfig):
    """GenericProxyConfig with connection-close for rotating proxies.
    Retries are handled in get_transcript, not here, to avoid double-retry slowdowns."""

    @property
    def prevent_keeping_connections_alive(self) -> bool:
        return True


def _build_proxy_config():
    """Build a ProxyConfig from YOUTUBE_PROXY_URL env var, or None if unset."""
    proxy_url = os.environ.get("YOUTUBE_PROXY_URL", "").strip().rstrip("/")
    if not proxy_url:
        return None
    print("  Using proxy for transcript fetch.")
    return _RotatingProxyConfig(https_url=proxy_url)


def get_transcript(video_id: str, language: str = "en") -> list[dict]:
    """
    Fetch transcript using youtube-transcript-api with the library's native
    proxy_config support. Retries on RequestBlocked / 429 RetryError with
    exponential backoff.
    Returns list of dicts with keys: text, start, duration.
    Raises RuntimeError if no transcript is available (permanent).
    Raises the last caught error if all retries exhausted (transient).
    """
    from requests.exceptions import RetryError, ConnectionError as ReqConnectionError
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled, NoTranscriptFound, RequestBlocked,
    )

    proxy_config = _build_proxy_config()
    last_error = None

    for attempt in range(1, MAX_TRANSCRIPT_RETRIES + 1):
        try:
            api = YouTubeTranscriptApi(proxy_config=proxy_config)
            fetched = api.fetch(video_id, languages=[language])
            return [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            raise RuntimeError(f"No transcript for {video_id}: {e}") from e
        except (RequestBlocked, RetryError, ReqConnectionError) as e:
            last_error = e
            if attempt < MAX_TRANSCRIPT_RETRIES:
                delay = RETRY_BACKOFF_BASE ** attempt
                print(f"    Blocked/429 (attempt {attempt}/{MAX_TRANSCRIPT_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"    Blocked after {MAX_TRANSCRIPT_RETRIES} attempts: {type(e).__name__}")

    raise last_error


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
