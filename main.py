import os
import sys
import yaml
from dotenv import load_dotenv

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
    errors = []

    for channel in config["channels"]:
        handle = channel["handle"]
        channel_name = channel["name"]
        instructions = channel.get("instructions", "Summarize all key points.")
        channel_id = channel.get("channel_id", "")

        if not channel_id:
            errors.append(f"{channel_name}: missing channel_id in config.yaml")
            continue

        print(f"Checking {channel_name} ({handle})...")
        try:
            videos = get_recent_videos(channel_id, handle, lookback_days, max_per_channel)
        except Exception as e:
            errors.append(f"{channel_name}: failed to fetch videos — {e}")
            continue

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

                processed_ids = mark_processed(video["id"], processed_ids)

            except RuntimeError as e:
                # No transcript available — don't mark processed, retry next run
                print(f"    No transcript available ({e}), skipping.")
            except Exception as e:
                # Transient error — don't mark processed, report as error
                msg = f"{channel_name} / {video['title']}: {e}"
                print(f"    ERROR: {msg}")
                errors.append(msg)

    if all_summaries:
        print(f"\nSending digest with {len(all_summaries)} summary/summaries...")
        try:
            send_digest(all_summaries, config, smtp_password=gmail_password)
            print("Email sent.")
        except Exception as e:
            errors.append(f"Failed to send email: {e}")

    else:
        print("\nNo new summaries to send — skipping email.")

    if errors:
        print(f"\n{len(errors)} error(s) occurred:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
