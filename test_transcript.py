"""
Test script: fetch a real YouTube transcript through the proxy.

Usage:
  python test_transcript.py                        # live fetch (requires YOUTUBE_PROXY_URL)
  python test_transcript.py --dry-run              # validate config without fetching
  python test_transcript.py --test                 # alias for --dry-run
  python test_transcript.py --video-id <ID>        # test a specific video
"""
import argparse
import os
import sys
import time

from dotenv import load_dotenv


def check_proxy_connectivity(proxy_url: str) -> bool:
    """Verify the proxy can reach an external host."""
    import requests
    try:
        resp = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=15,
        )
        data = resp.json()
        print(f"  Proxy is reachable. Exit IP: {data.get('origin', 'unknown')}")
        return True
    except Exception as e:
        print(f"  Proxy connectivity check FAILED: {e}")
        return False


def check_proxy_reaches_youtube(proxy_url: str) -> bool:
    """Verify the proxy can reach YouTube specifically."""
    import requests
    try:
        resp = requests.get(
            "https://www.youtube.com/",
            proxies={"http": proxy_url, "https": proxy_url},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
            timeout=15,
        )
        print(f"  YouTube via proxy: HTTP {resp.status_code}, {len(resp.text)} bytes")
        return resp.status_code == 200
    except Exception as e:
        print(f"  YouTube via proxy FAILED: {e}")
        return False


def dry_run():
    """Validate config and proxy connectivity without fetching a transcript."""
    print("=== DRY RUN ===\n")

    proxy_url = os.environ.get("YOUTUBE_PROXY_URL", "").strip().rstrip("/")
    if not proxy_url:
        print("YOUTUBE_PROXY_URL is NOT set. Transcripts will use direct connection.")
        print("(This will fail on cloud IPs like GitHub Actions.)")
        return

    print(f"YOUTUBE_PROXY_URL is set (host: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url})")

    print("\n1. Testing proxy connectivity (httpbin.org)...")
    if not check_proxy_connectivity(proxy_url):
        print("   -> Proxy is unreachable. Check URL, credentials, and firewall.")
        sys.exit(1)

    print("\n2. Testing proxy can reach YouTube...")
    if not check_proxy_reaches_youtube(proxy_url):
        print("   -> Proxy cannot reach YouTube. The proxy may be blocked or misconfigured.")
        sys.exit(1)

    print("\nDry run passed. Proxy appears functional.")


def live_fetch(video_id: str):
    """Attempt a real transcript fetch using the fetcher module."""
    print(f"=== LIVE FETCH: {video_id} ===\n")

    proxy_url = os.environ.get("YOUTUBE_PROXY_URL", "").strip().rstrip("/")
    if proxy_url:
        host_part = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
        print(f"Proxy configured: {host_part}")
    else:
        print("No proxy configured (direct connection).")

    print(f"\nFetching transcript for: https://www.youtube.com/watch?v={video_id}")
    start = time.time()

    try:
        from fetcher import get_transcript, format_transcript_with_timestamps

        segments = get_transcript(video_id, language="en")
        elapsed = time.time() - start

        print(f"\nTranscript fetched in {elapsed:.1f}s")
        print(f"Segments: {len(segments)}")

        if segments:
            formatted = format_transcript_with_timestamps(segments)
            lines = formatted.split("\n")
            print(f"Formatted lines: {len(lines)}")
            print(f"\n--- First 5 lines ---")
            for line in lines[:5]:
                print(f"  {line}")
            print(f"--- Last 2 lines ---")
            for line in lines[-2:]:
                print(f"  {line}")

        print(f"\nSUCCESS: Transcript fetched.")

    except RuntimeError as e:
        elapsed = time.time() - start
        print(f"\nPERMANENT FAILURE ({elapsed:.1f}s): {e}")
        print("This video has no transcript available.")
        sys.exit(1)

    except Exception as e:
        elapsed = time.time() - start
        print(f"\nFAILURE ({elapsed:.1f}s): {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser(description="Test YouTube transcript fetching")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without fetching")
    parser.add_argument("--test", action="store_true", help="Alias for --dry-run")
    parser.add_argument("--video-id", default="buz9z1HqCiQ", help="YouTube video ID to test")
    args = parser.parse_args()

    if args.dry_run or args.test:
        dry_run()
    else:
        live_fetch(args.video_id)
