import json
import anthropic

SYSTEM_PROMPT = (
    "You are a concise research assistant. Your job is to read a YouTube video "
    "transcript and produce a structured summary. You always respond with valid JSON "
    "matching the schema provided. You are accurate, specific, and never pad summaries "
    "with filler phrases."
)


def build_prompt(video: dict, transcript_text: str, channel_instructions: str) -> str:
    description_preview = (video.get("description") or "")[:500]
    return f"""## Video Metadata
Title: {video['title']}
URL: {video['url']}
Description: {description_preview}

## Channel-Specific Instructions
{channel_instructions.strip()}

## Transcript (with timestamps)
{transcript_text}

## Task
Summarize this video according to the channel-specific instructions above.

Respond ONLY with a JSON object matching this exact schema:
{{
  "headline": "One sentence capturing the core topic (max 120 chars)",
  "key_points": [
    {{
      "point": "Concise bullet point text (max 150 chars)",
      "timestamp": "MM:SS of where this point is discussed, or null"
    }}
  ],
  "skip_reason": null
}}

Rules:
- key_points: between 3 and 7 items. Quality over quantity.
- If the channel instructions say to filter out content and the ENTIRE video is filtered \
content (e.g. pure small talk), set key_points to [] and set skip_reason to a one-sentence explanation.
- Timestamps must reference the [MM:SS] markers in the transcript above.
- Do not invent timestamps. Use null if you are not confident.
- Do not include sponsor segments, calls to subscribe, or pleasantries."""


def summarize_video(video: dict, transcript_text: str, channel_instructions: str, api_key: str) -> dict:
    """
    Call Claude to summarize a video. Returns parsed JSON dict with keys:
    headline, key_points, skip_reason.
    """
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(video, transcript_text, channel_instructions)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if model wraps output
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)
