import glob
import hashlib
import os
import threading
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg


def is_supported_audio_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    supported_host = any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("youtube.com", "youtu.be", "instagram.com")
    )
    return parsed.scheme in {"http", "https"} and supported_host


class AudioDownloader:
    @staticmethod
    def download_audio(
        url: str,
        progress_callback=None,
        cancel_event: threading.Event = None,
        cookie_browser: str = None,
    ) -> str:
        if not is_supported_audio_url(url):
            raise ValueError("Use a valid YouTube or Instagram audio/video URL.")
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")

        cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "downloaded_videos", "audio")
        )
        os.makedirs(cache_dir, exist_ok=True)
        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        cached_paths = [
            path
            for path in glob.glob(os.path.join(cache_dir, f"{url_hash}.*"))
            if not path.endswith((".part", ".ytdl"))
            and os.path.isfile(path)
            and os.path.getsize(path) > 0
        ]
        if cached_paths:
            if progress_callback:
                progress_callback("Using previously downloaded background audio.", 1.0)
            return cached_paths[0]

        def hook(data):
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelledError("Processing stopped by user.")
            if progress_callback and data.get("status") == "downloading":
                percent = data.get("_percent_str", "").strip()
                try:
                    fraction = float(percent.rstrip("%")) / 100
                except ValueError:
                    total = data.get("total_bytes") or data.get("total_bytes_estimate")
                    downloaded = data.get("downloaded_bytes")
                    fraction = downloaded / total if total else None
                progress_callback(
                    f"Downloading background audio: {percent or 'progress unavailable'}",
                    fraction,
                )

        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(cache_dir, f"{url_hash}.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": find_ffmpeg(),
            "progress_hooks": [hook],
        }
        if cookie_browser:
            options["cookiesfrombrowser"] = (cookie_browser,)
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelledError("Processing stopped by user.")
            output_path = ydl.prepare_filename(info)
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(
                "The audio downloader completed without producing a usable audio file."
            )
        return output_path
