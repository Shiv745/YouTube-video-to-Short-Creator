import os
import threading
from yt_dlp import YoutubeDL

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg


class VideoDownloader:
    @staticmethod
    def download_youtube_video(
        url: str,
        output_path: str = "temp_source.mp4",
        progress_callback=None,
        cancel_event: threading.Event = None,
    ) -> dict:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass

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

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return {
                "title": info.get("title", "YouTube_Video"),
                "duration": info.get("duration", 0),
                "resolution": f"{info.get('width', 1920)}x{info.get('height', 1080)}",
                "filepath": output_path
            }
