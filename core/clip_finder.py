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

    def _generate_content(self, prompt: str, log_callback=None):
        models = [
            ("gemini-3.8-flash", "Gemini 3.8 Flash"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash"),
        ]
        max_attempts_per_model = 2
        for model_index, (model, model_name) in enumerate(models):
            for attempt in range(1, max_attempts_per_model + 1):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )
                    if model_index > 0 and log_callback:
                        log_callback(f"{model_name} fallback succeeded.")
                    return response
                except APIError as error:
                    if error.code == 400 and "API_KEY_INVALID" in str(error.details):
                        raise InvalidGeminiApiKeyError(
                            "Gemini rejected the API key. Create or copy a valid Gemini API "
                            "key from Google AI Studio, replace the key in the sidebar, "
                            "and try again."
                        ) from error

                    if error.code not in {500, 502, 503, 504}:
                        raise

                    if attempt < max_attempts_per_model:
                        delay = 10
                        if log_callback:
                            log_callback(
                                f"{model_name} is temporarily unavailable "
                                f"(HTTP {error.code}). Retrying in {delay} seconds "
                                f"(attempt {attempt + 1}/{max_attempts_per_model})..."
                            )
                        time.sleep(delay)
                        continue

                    if model_index < len(models) - 1:
                        fallback_name = models[model_index + 1][1]
                        if log_callback:
                            log_callback(
                                f"{model_name} remains unavailable (HTTP {error.code}); "
                                f"switching to {fallback_name}."
                            )
                        break

                    raise GeminiServiceUnavailableError(
                        f"Gemini models are unavailable after trying "
                        f"{', '.join(name for _, name in models)}. "
                        f"Last error (HTTP {error.code}): {error}"
                    ) from error

        raise GeminiServiceUnavailableError("Gemini returned no response from either model.")

    @staticmethod
    def _parse_json_response(response):
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
        raw_text = response.text.strip()
        raw_text = re.sub(r"^```(?:json)?", "", raw_text).strip()
        raw_text = re.sub(r"```$", "", raw_text).strip()
        return json.loads(raw_text)

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
        response = self._generate_content(prompt, log_callback)
        clips = self._parse_json_response(response)
        if not isinstance(clips, list):
            raise ValueError("Gemini clip selection response must be a JSON array.")
        return clips

    def create_publishing_plan(
        self,
        clips: list,
        audience: str,
        timezone: str,
        log_callback=None,
    ) -> dict:
        candidates = [
            {
                "clip_number": index,
                "title": clip.get("title", f"Clip {index}"),
                "start_seconds": round(float(clip["start"]), 2),
                "end_seconds": round(float(clip["end"]), 2),
                "virality_score": clip.get("virality_score"),
                "hook_reason": clip.get("hook_reason", ""),
                "transcript": clip.get("transcript_excerpt", ""),
            }
            for index, clip in enumerate(clips, 1)
        ]
        prompt = f"""
You are a cautious YouTube Shorts publishing strategist. Compare the candidate clips
and return a practical, evidence-based publishing package for EVERY clip.
Audience: {audience or "Infer from the clip content"}
Audience timezone: {timezone or "Not specified; state the timezone used"}

Rank clips against each other for likely audience retention and sharing, using the
provided transcript excerpts, hook, and virality score. Scores estimate creative
potential only; never promise views or claim certainty. Do not invent audience
analytics, current trends, copyright status, or exact optimal posting data.
For upload timing, suggest a test window in the requested timezone and explicitly
say it should be checked against the creator's YouTube Analytics.
Write descriptions and tags that accurately match the transcript. Return only JSON
with this shape:
{{
  "comparison_summary": "One concise comparison of the candidates",
  "recommendations": [
    {{
      "clip_number": 1,
      "rank": 1,
      "why_ranked": "Why this clip placed here compared with the others",
      "title_options": ["Title option 1", "Title option 2", "Title option 3"],
      "description": "Copy-ready YouTube Shorts description",
      "tags": ["tag one", "tag two"],
      "target_audience": "Specific audience this clip may appeal to",
      "upload_window": "A test day and time range in the requested timezone",
      "upload_rationale": "Why this is a reasonable time to test"
    }}
  ]
}}

Candidate clips:
{json.dumps(candidates, ensure_ascii=False)}
"""
        response = self._generate_content(prompt, log_callback)
        plan = self._parse_json_response(response)
        if not isinstance(plan, dict) or not isinstance(plan.get("recommendations"), list):
            raise ValueError("Gemini publishing plan is missing its recommendations list.")
        return plan
