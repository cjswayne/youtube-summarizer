import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "processed_videos.json")


def load_processed_ids() -> set:
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
    return set(data.get("processed_ids", []))


def save_processed_ids(ids: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump({"processed_ids": sorted(ids)}, f, indent=2)


def mark_processed(video_id: str, current_ids: set) -> set:
    current_ids.add(video_id)
    save_processed_ids(current_ids)
    return current_ids
