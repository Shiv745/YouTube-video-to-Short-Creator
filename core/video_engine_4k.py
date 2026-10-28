import os
import subprocess
import threading
import time
from collections import deque
import cv2
import numpy as np

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg, get_audio_stream_index
from core.audio_mixer import build_audio_mix_filter
from core.constants import MAX_SHORT_DURATION_SECONDS


class VideoEngine4K:
    @staticmethod
    def _format_render_error(stderr_lines, return_code: int) -> str:
        lines = list(stderr_lines)
        error_markers = (
            "error",
            "failed",
            "invalid",
            "unable",
            "could not",
            "cannot",
            "no such",
            "not found",
            "resource temporarily unavailable",
        )
        diagnostic_lines = [
            line for line in lines
            if any(marker in line.lower() for marker in error_markers)
        ]
        details = "\n".join(diagnostic_lines[-20:] or lines[-80:])
        if not details:
            details = "FFmpeg did not provide diagnostic output."
        return f"FFmpeg render failed with exit code {return_code}:\n{details[-8000:]}"

    @staticmethod
    def detect_smart_face_center_x(video_path: str, start_sec: float, duration_sec: float) -> float:
        """
        Samples frames across the clip using OpenCV Haar Cascade to locate the active speaker's
        horizontal center ratio (0.0 to 1.0). Defaults to 0.5 (center) if no face is detected.
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return 0.5

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920.0
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)

            centers = []
            sample_points = np.linspace(start_sec, start_sec + max(1.0, duration_sec - 0.5), num=12)
            for t in sample_points:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(60, 60))
                if len(faces) > 0:
                    # Pick largest face
                    largest = max(faces, key=lambda rect: rect[2] * rect[3])
                    fx, fy, fw, fh = largest
                    center_x = (fx + fw / 2.0) / width
                    centers.append(center_x)

            cap.release()
            if centers:
                return float(np.median(centers))
        except Exception:
            pass
        return 0.5

    @classmethod
    def render_4k_short(
        cls,
        source_video: str,
        output_file: str,
        start_sec: float,
        end_sec: float,
        ass_subtitle_file: str = None,
        layout_mode: str = "Blurred Cinema Canvas (fit frame)",
        resolution_preset: str = "4K UHD (2160x3840)",
        orientation_preset: str = "Portrait (9:16)",
        max_duration_sec: int = MAX_SHORT_DURATION_SECONDS,
        background_audio: str = None,
        source_audio_volume: float = 1.0,
        background_audio_volume: float = 0.25,
        log_callback=None,
        cancel_event: threading.Event = None,
        progress_callback=None,
    ):
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")

        duration = min(
            float(max_duration_sec),
            max(1.0, end_sec - start_sec),
        )
        if "4K" in resolution_preset:
            target_w, target_h = (
                (3840, 2160) if orientation_preset.startswith("Landscape")
                else (2160, 3840)
            )
        else:
            target_w, target_h = (
                (1920, 1080) if orientation_preset.startswith("Landscape")
                else (1080, 1920)
            )
        target_ratio = target_w / target_h

        center_ratio = cls.detect_smart_face_center_x(source_video, start_sec, duration)
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")
        if log_callback:
            log_callback(f" -> AI Speaker Face Lock X-Ratio: {center_ratio:.2f} | Target: {target_w}x{target_h}")

        # Escape subtitle path for FFmpeg filter
        sub_filter = ""
        if ass_subtitle_file and os.path.exists(ass_subtitle_file):
            escaped_ass = ass_subtitle_file.replace("\\", "/").replace(":", "\\:")
            sub_filter = f",ass='{escaped_ass}'"

        if layout_mode.startswith("Blurred Cinema Canvas"):
            vf_complex = (
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},boxblur=45:12,eq=brightness=-0.12:saturation=1.15[bg];"
                f"[0:v]scale={target_w}:-2:force_original_aspect_ratio=decrease,"
                f"unsharp=5:5:0.8:3:3:0.4[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2{sub_filter}[outv]"
            )
            video_filter_args = ["-filter_complex", vf_complex]
        else:
            crop_width = f"min(iw,ih*{target_ratio:.8f})"
            crop_height = f"min(ih,iw/{target_ratio:.8f})"
            crop_x_expr = (
                f"max(0,min(iw-{crop_width},"
                f"(iw*{center_ratio:.3f})-({crop_width}/2)))"
            )
            crop_y_expr = f"(ih-{crop_height})/2"
            vf_chain = (
                f"crop=w='{crop_width}':h='{crop_height}':"
                f"x='{crop_x_expr}':y='{crop_y_expr}',"
                f"scale={target_w}:{target_h}:flags=lanczos,"
                f"unsharp=5:5:0.85:3:3:0.4,"
                f"eq=contrast=1.04:saturation=1.08"
                f"{sub_filter}"
            )
            video_filter_args = ["-vf", vf_chain]

        audio_stream_index = get_audio_stream_index(source_video)
        source_audio_volume = min(2.0, max(0.0, source_audio_volume))
        background_audio_volume = min(2.0, max(0.0, background_audio_volume))
        cmd = [
            find_ffmpeg(), "-y",
            "-ss", f"{start_sec:.2f}",
            "-i", source_video,
        ]
        if background_audio:
            cmd.extend(["-stream_loop", "-1", "-i", background_audio])
            if audio_stream_index is None:
                cmd.extend([
                    "-f", "lavfi",
                    "-t", f"{duration:.2f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                ])
                original_audio_input = 2
            else:
                original_audio_input = 0
            audio_filter = build_audio_mix_filter(
                original_audio_input,
                1,
                duration,
                source_audio_volume,
                background_audio_volume,
            )
            if video_filter_args[0] == "-filter_complex":
                video_filter_args[1] = f"{video_filter_args[1]};{audio_filter}"
            else:
                video_filter_args = [
                    "-filter_complex",
                    f"[0:v]{video_filter_args[1]}[outv];{audio_filter}",
                ]
            audio_map = ["-map", "[aout]"]
        else:
            audio_filter = (
                "loudnorm=I=-14:TP=-1.0:LRA=11,"
                f"volume={source_audio_volume:.3f}"
            )
            audio_map = ["-map", "0:a?", "-af", audio_filter]

        cmd.extend([
            "-t", f"{duration:.2f}",
            *video_filter_args,
            "-map", "[outv]" if video_filter_args[0] == "-filter_complex" else "0:v",
            *audio_map,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "256k",
        ])
        cmd.extend([
            "-progress", "pipe:1",
            "-nostats",
            output_file,
        ])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stderr_lines = deque(maxlen=200)

        def read_progress():
            current_time = 0.0
            for line in proc.stdout:
                key, separator, value = line.partition("=")
                if not separator:
                    continue
                if key == "out_time":
                    try:
                        hours, minutes, seconds = value.strip().split(":")
                        current_time = (
                            int(hours) * 3600
                            + int(minutes) * 60
                            + float(seconds)
                        )
                    except ValueError:
                        continue
                elif key == "out_time_ms":
                    try:
                        current_time = int(value.strip()) / 1_000_000
                    except ValueError:
                        continue
                elif key == "progress" and value.strip() == "end":
                    current_time = duration

                if progress_callback:
                    progress_callback(min(1.0, current_time / duration))

        def read_errors():
            for line in proc.stderr:
                stderr_lines.append(line.rstrip())

        progress_thread = threading.Thread(target=read_progress, daemon=True)
        error_thread = threading.Thread(target=read_errors, daemon=True)
        progress_thread.start()
        error_thread.start()
        cancelled = False
        try:
            while proc.poll() is None:
                if cancel_event and cancel_event.wait(0.2):
                    cancelled = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    break
                time.sleep(0.05)
            proc.wait()
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        finally:
            progress_thread.join(timeout=2)
            error_thread.join(timeout=2)

        if cancelled:
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError as exc:
                    raise RuntimeError(
                        f"Unable to remove incomplete render '{output_file}': {exc}"
                    ) from exc
            raise PipelineCancelledError("Processing stopped by user.")

        if proc.returncode != 0:
            error = cls._format_render_error(stderr_lines, proc.returncode)
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError as cleanup_error:
                    raise RuntimeError(
                        f"{error}\nCould not remove incomplete render "
                        f"'{output_file}': {cleanup_error}"
                    ) from cleanup_error
            raise RuntimeError(error)
        return output_file
