import hashlib
import os
import threading
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg


def _cache_key(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    video_id = ""

    if host == "youtu.be" or host.endswith(".youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        if not video_id:
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) > 1 and path_parts[0] in {"shorts", "embed", "live"}:
                video_id = path_parts[1]

    identity = f"youtube:{video_id}" if video_id else url.strip()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class VideoDownloader:
    @staticmethod
    def download_youtube_video(
        url: str,
        progress_callback=None,
        cancel_event: threading.Event = None,
        cookie_browser: str = None,
    ) -> dict:
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")

        cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "downloaded_videos")
        )
        os.makedirs(cache_dir, exist_ok=True)
        url_hash = _cache_key(url)
        output_path = os.path.join(cache_dir, f"youtube_{url_hash}.mp4")
        legacy_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        legacy_path = os.path.join(cache_dir, f"youtube_{legacy_hash}.mp4")

        cached_path = next(
            (
                path for path in (output_path, legacy_path)
                if os.path.isfile(path) and os.path.getsize(path) > 0
            ),
            None,
        )
        if cached_path:
            if progress_callback:
                progress_callback(
                    f"Using previously downloaded video: {cached_path}",
                    1.0,
                )
            return {
                "title": "Previously downloaded video",
                "duration": 0,
                "resolution": "Saved locally",
                "filepath": cached_path,
                "cached": True,
            }

        def hook(d):
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelledError("Processing stopped by user.")
            if progress_callback and d.get('status') == 'downloading':
                percent_str = d.get('_percent_str', '').strip()
                speed_str = d.get('_speed_str', 'N/A').strip()
                eta_str = d.get('_eta_str', 'unknown').strip()
                try:
                    fraction = float(percent_str.rstrip("%")) / 100
                except ValueError:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate')
                    downloaded = d.get('downloaded_bytes')
                    fraction = downloaded / total if total else None
                progress_callback(
                    f"Downloading source video: {percent_str} "
                    f"(Speed: {speed_str}, ETA: {eta_str})",
                    fraction,
                )

        # Prioritize highest resolution up to 4K (2160p) MP4 stream
        ydl_opts = {
            'format': 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': find_ffmpeg(),
            'progress_hooks': [hook]
        }
        if cookie_browser:
            ydl_opts['cookiesfrombrowser'] = (cookie_browser,)

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelledError("Processing stopped by user.")
            return {
                "title": info.get("title", "YouTube_Video"),
                "duration": info.get("duration", 0),
                "resolution": f"{info.get('width', 1920)}x{info.get('height', 1080)}",
                "filepath": output_path,
                "cached": False,
            }
