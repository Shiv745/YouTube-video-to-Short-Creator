import os
import subprocess
import threading
import time

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg, get_audio_stream_index, get_video_duration


def build_audio_mix_filter(
    source_audio_input: int,
    music_audio_input: int,
    duration: float,
    source_volume: float,
    music_volume: float,
) -> str:
    source_volume = min(2.0, max(0.0, source_volume))
    music_volume = min(2.0, max(0.0, music_volume))
    return (
        f"[{source_audio_input}:a]aresample=48000,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "loudnorm=I=-14:TP=-1.0:LRA=11,"
        f"volume={source_volume:.3f},"
        f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[original];"
        f"[{music_audio_input}:a]aresample=48000,"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "loudnorm=I=-14:TP=-1.0:LRA=11,"
        f"volume={music_volume:.3f},"
        f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[music];"
        f"[original][music]amix=inputs=2:duration=longest:"
        f"dropout_transition=0:normalize=0,"
        f"atrim=duration={duration:.3f},alimiter=limit=0.95[aout]"
    )


def create_audio_preview(
    source_audio_path: str,
    background_audio_path: str,
    output_path: str,
    source_volume: float,
    music_volume: float,
    duration: float = 15.0,
    cancel_event: threading.Event = None,
) -> str:
    if duration <= 0:
        raise ValueError("Audio preview duration must be greater than zero.")
    if cancel_event and cancel_event.is_set():
        raise PipelineCancelledError("Audio preview stopped by user.")

    source_stream_index = get_audio_stream_index(source_audio_path)
    if source_stream_index is None and not background_audio_path:
        raise ValueError(
            "The source video has no audio track. Select background audio to preview."
        )

    command = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    if source_audio_path:
        command.extend(["-i", source_audio_path])
    else:
        raise ValueError("Select a source video or audio track to preview.")

    if background_audio_path:
        command.extend(["-stream_loop", "-1", "-i", background_audio_path])
        if source_stream_index is None:
            command.extend([
                "-f", "lavfi",
                "-t", f"{duration:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            ])
            source_audio_input = 2
        else:
            source_audio_input = 0
        filter_complex = build_audio_mix_filter(
            source_audio_input,
            1,
            duration,
            source_volume,
            music_volume,
        )
    else:
        filter_complex = (
            f"[0:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            "loudnorm=I=-14:TP=-1.0:LRA=11,"
            f"volume={min(2.0, max(0.0, source_volume)):.3f},"
            f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[aout]"
        )

    command.extend([
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-vn",
        "-t", f"{duration:.3f}",
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        output_path,
    ])

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        while process.poll() is None:
            if cancel_event and cancel_event.wait(0.1):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise PipelineCancelledError("Audio preview stopped by user.")
            time.sleep(0.05)
        _, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"FFmpeg could not create the audio preview: {stderr[-2000:]}"
            )
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("FFmpeg completed without creating the audio preview.")
        return output_path
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as cleanup_error:
                raise RuntimeError(
                    f"Could not remove incomplete audio preview '{output_path}': "
                    f"{cleanup_error}"
                )
        raise


def mix_audio_into_video(
    source_video_path: str,
    background_audio_path: str | None,
    output_path: str,
    source_volume: float,
    music_volume: float,
    cancel_event: threading.Event = None,
) -> str:
    if not os.path.isfile(source_video_path):
        raise FileNotFoundError(f"Source video was not found: {source_video_path}")
    if os.path.abspath(source_video_path) == os.path.abspath(output_path):
        raise ValueError("Choose an output path different from the source video.")
    if cancel_event and cancel_event.is_set():
        raise PipelineCancelledError("Audio export stopped by user.")

    duration = get_video_duration(source_video_path)
    source_stream_index = get_audio_stream_index(source_video_path)
    command = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", source_video_path]

    if background_audio_path:
        command.extend(["-stream_loop", "-1", "-i", background_audio_path])
        if source_stream_index is None:
            command.extend([
                "-f", "lavfi",
                "-t", f"{duration:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            ])
            source_audio_input = 2
        else:
            source_audio_input = 0
        filter_complex = build_audio_mix_filter(
            source_audio_input,
            1,
            duration,
            source_volume,
            music_volume,
        )
        command.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
        ])
    elif source_stream_index is not None:
        filter_complex = (
            f"[0:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            "loudnorm=I=-14:TP=-1.0:LRA=11,"
            f"volume={min(2.0, max(0.0, source_volume)):.3f},"
            f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[aout]"
        )
        command.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
        ])
    else:
        command.extend(["-map", "0:v:0", "-an"])

    command.extend([
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        output_path,
    ])

    def run_export(args: list[str]) -> tuple[int, str]:
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            while process.poll() is None:
                if cancel_event and cancel_event.wait(0.1):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise PipelineCancelledError("Audio export stopped by user.")
                time.sleep(0.05)
            _, stderr_text = process.communicate()
            return process.returncode, stderr_text
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise

    try:
        return_code, stderr = run_export(command)
        if return_code != 0:
            if os.path.exists(output_path):
                os.remove(output_path)
            fallback_command = command.copy()
            video_codec_index = fallback_command.index("-c:v")
            fallback_command[video_codec_index:video_codec_index + 2] = [
                "-c:v", "libx264",
            ]
            fallback_command[video_codec_index + 2:video_codec_index + 2] = [
                "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            ]
            return_code, fallback_stderr = run_export(fallback_command)
            if return_code != 0:
                raise RuntimeError(
                    "FFmpeg audio export failed with both video stream copy and "
                    f"H.264 encoding: {fallback_stderr[-4000:] or stderr[-4000:]}"
                )
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("FFmpeg completed without creating the output video.")
        return output_path
    except BaseException as error:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as cleanup_error:
                raise RuntimeError(
                    f"Could not remove incomplete audio export '{output_path}': "
                    f"{cleanup_error}"
                ) from error
        raise
