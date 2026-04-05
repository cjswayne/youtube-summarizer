import os
import sys
import yaml
from dotenv import load_dotenv
from youtube_transcript_api import TranscriptsDisabled, NoTranscriptFound

from fetcher import get_recent_videos, get_transcript, format_transcript_with_timestamps
from summarizer import summarize_video
from emailer import send_digest
from state import load_processed_ids, mark_processed


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    load_dotenv()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not gmail_password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    settings = config.get("settings", {})
    lookback_days = settings.get("lookback_days", 2)
    max_per_channel = settings.get("max_videos_per_channel", 5)
    transcript_lang = settings.get("transcript_language", "en")

    processed_ids = load_processed_ids()
    all_summaries = []

    for channel in config["channels"]:
        handle = channel["handle"]
        channel_name = channel["name"]
        instructions = channel.get("instructions", "Summarize all key points.")

        print(f"Checking {channel_name} ({handle})...")
        videos = get_recent_videos(handle, lookback_days, max_per_channel)

        if not videos:
            print(f"  No recent videos found.")
            continue

        new_videos = [v for v in videos if v["id"] not in processed_ids]
        print(f"  Found {len(videos)} recent video(s), {len(new_videos)} new.")

        for video in new_videos:
            print(f"  Processing: {video['title']}")
            try:
                segments = get_transcript(video["id"], transcript_lang)
                transcript_text = format_transcript_with_timestamps(segments)

                summary = summarize_video(
                    video=video,
                    transcript_text=transcript_text,
                    channel_instructions=instructions,
                    api_key=anthropic_key,
                )

                if summary.get("key_points"):
                    all_summaries.append({
                        "channel_name": channel_name,
                        "title": video["title"],
                        "url": video["url"],
                        "headline": summary["headline"],
                        "key_points": summary["key_points"],
                    })
                    print(f"    Summarized: {summary['headline'][:60]}...")
                else:
                    reason = summary.get("skip_reason", "filtered by channel instructions")
                    print(f"    Skipped: {reason}")

                # Mark processed regardless of skip — avoid rechecking tomorrow
                processed_ids = mark_processed(video["id"], processed_ids)

            except (TranscriptsDisabled, NoTranscriptFound):
                print(f"    No transcript available, skipping.")
                processed_ids = mark_processed(video["id"], processed_ids)
            except Exception as e:
                print(f"    Error: {e} — will retry tomorrow.")
                # Do NOT mark processed so it retries on the next run

    if all_summaries:
        print(f"\nSending digest with {len(all_summaries)} summary/summaries...")
        send_digest(all_summaries, config, smtp_password=gmail_password)
        print("Email sent.")
    else:
        print("\nNo new summaries to send — skipping email.")


if __name__ == "__main__":
    main()
