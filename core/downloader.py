import hashlib
import os
import threading
from yt_dlp import YoutubeDL

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg


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
        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()
        output_path = os.path.join(cache_dir, f"youtube_{url_hash}.mp4")

        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            if progress_callback:
                progress_callback(f"Using previously downloaded video: {output_path}")
            return {
                "title": "Previously downloaded video",
                "duration": 0,
                "resolution": "Saved locally",
                "filepath": output_path,
                "cached": True,
            }

        def hook(d):
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelledError("Processing stopped by user.")
            if progress_callback and d.get('status') == 'downloading':
                percent_str = d.get('_percent_str', '').strip()
                speed_str = d.get('_speed_str', 'N/A').strip()
                progress_callback(f"Downloading source video: {percent_str} (Speed: {speed_str})")

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
