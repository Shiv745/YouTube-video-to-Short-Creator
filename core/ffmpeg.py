import os
import shutil
import subprocess
import time
from pathlib import Path

from core.cancellation import PipelineCancelledError


def find_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates = sorted(
            packages_dir.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"),
            reverse=True,
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

    raise FileNotFoundError(
        "FFmpeg was not found. Install it and add its bin folder to PATH, "
        "then restart the app."
    )


def find_ffplay() -> str:
    executable = shutil.which("ffplay")
    if executable:
        return executable

    ffmpeg_path = Path(find_ffmpeg())
    ffplay_path = ffmpeg_path.with_name(f"ffplay{ffmpeg_path.suffix}")
    if ffplay_path.is_file():
        return str(ffplay_path)

    raise FileNotFoundError(
        "FFplay was not found beside FFmpeg. Install a complete FFmpeg build "
        "to preview audio."
    )


def get_video_duration(video_path: str) -> float:
    ffmpeg_path = Path(find_ffmpeg())
    ffprobe_name = f"ffprobe{ffmpeg_path.suffix}"
    ffprobe_path = shutil.which("ffprobe") or str(
        ffmpeg_path.with_name(ffprobe_name)
    )
    if not os.path.isfile(ffprobe_path):
        raise FileNotFoundError(
            "FFprobe was not found beside FFmpeg; install a complete FFmpeg build."
        )

    result = subprocess.run(
        [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError(
            f"FFprobe returned an invalid duration for '{video_path}'."
        ) from error
    if duration <= 0:
        raise RuntimeError(f"Video has an invalid duration: '{video_path}'.")
    return duration


def get_audio_stream_index(video_path: str) -> int | None:
    ffmpeg_path = Path(find_ffmpeg())
    ffprobe_name = f"ffprobe{ffmpeg_path.suffix}"
    ffprobe_path = shutil.which("ffprobe") or str(
        ffmpeg_path.with_name(ffprobe_name)
    )
    if not os.path.isfile(ffprobe_path):
        raise FileNotFoundError(
            "FFprobe was not found beside FFmpeg; install a complete FFmpeg build."
        )

    result = subprocess.run(
        [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    stream_index = result.stdout.strip()
    if not stream_index:
        return None
    try:
        return int(stream_index)
    except ValueError as error:
        raise RuntimeError(
            f"FFprobe returned an invalid audio stream index for '{video_path}'."
        ) from error


def create_looped_video(
    source_path: str,
    output_path: str,
    duration: float,
    cancel_event=None,
) -> str:
    command = [
        find_ffmpeg(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-stream_loop", "-1",
        "-i", source_path,
        "-t", f"{duration:.3f}",
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        while process.poll() is None:
            if cancel_event and cancel_event.wait(0.2):
                process.terminate()
                try:
                    _, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    _, stderr = process.communicate()
                raise PipelineCancelledError("Processing stopped by user.")
            time.sleep(0.05)

        _, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"FFmpeg could not loop the short source video: {stderr[-1200:]}"
            )
    except BaseException as error:
        if process and process.poll() is None:
            process.kill()
            process.communicate()
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as cleanup_error:
                raise RuntimeError(
                    f"Could not remove incomplete looped video '{output_path}': "
                    f"{cleanup_error}"
                ) from error
        raise

    return output_path


def ensure_ffmpeg_on_path() -> str:
    executable = find_ffmpeg()
    executable_dir = os.path.dirname(executable)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    normalized_dir = os.path.normcase(os.path.normpath(executable_dir))

    if not any(
        os.path.normcase(os.path.normpath(entry)) == normalized_dir
        for entry in path_entries
        if entry
    ):
        os.environ["PATH"] = os.pathsep.join(
            [executable_dir, *[entry for entry in path_entries if entry]]
        )

    return executable
