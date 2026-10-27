import json
import re
import time
from google import genai
from google.genai.errors import APIError

from core.constants import MAX_SHORT_DURATION_SECONDS


class InvalidGeminiApiKeyError(ValueError):
    pass


class GeminiServiceUnavailableError(RuntimeError):
    pass


class ViralClipFinder:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def find_best_clips(
        self,
        formatted_transcript: str,
        max_clips: int = 3,
        min_sec: int = 25,
        max_sec: int = MAX_SHORT_DURATION_SECONDS,
        log_callback=None,
    ) -> list:
        prompt = f"""
You are a top-tier viral short-form video producer (like OpusClip & Kixy.ai).
Analyze the timestamped transcript below and extract the {max_clips} highest-retention, most viral segments suitable for 4K YouTube Shorts / Instagram Reels.

Rules:
1. Each clip MUST be between {min_sec} and {max_sec} seconds in duration.
2. Start right on a strong hook and end on a punchy conclusion.
3. Provide a 'virality_score' out of 100 and a short 'hook_reason'.
4. Return ONLY a valid JSON array matching this exact structure (no markdown blocks, no extra commentary):
[
  {{
    "start": 14.5,
    "end": 52.0,
    "title": "Unbelievable_Secret_Hook",
    "virality_score": 96,
    "hook_reason": "Strong curiosity gap in the first 3 seconds"
  }}
]

Transcript:
{formatted_transcript}
"""
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=prompt
                )
                break
            except APIError as error:
                if error.code == 400 and "API_KEY_INVALID" in str(error.details):
                    raise InvalidGeminiApiKeyError(
                        "Gemini rejected the API key. Create or copy a valid Gemini API "
                        "key from Google AI Studio, replace the key in the sidebar, "
                        "and try again."
                    ) from error

                if error.code not in {500, 502, 503, 504}:
                    raise

                if attempt == max_attempts:
                    raise GeminiServiceUnavailableError(
                        "Gemini 3.8 Flash is temporarily unavailable after 5 attempts. "
                        "Please wait a few minutes and retry."
                    ) from error

                delay = min(10 * (2 ** (attempt - 1)), 30)
                if log_callback:
                    log_callback(
                        f"Gemini is temporarily unavailable. Retrying in {delay} "
                        f"seconds (attempt {attempt + 1}/{max_attempts})..."
                    )
                time.sleep(delay)

        raw_text = response.text.strip()
        raw_text = re.sub(r"^```(?:json)?", "", raw_text).strip()
        raw_text = re.sub(r"```$", "", raw_text).strip()
        clips = json.loads(raw_text)
        return clips
