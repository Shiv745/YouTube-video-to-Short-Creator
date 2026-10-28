import os
import subprocess
import threading
import cv2
import numpy as np

from core.cancellation import PipelineCancelledError
from core.ffmpeg import find_ffmpeg
from core.constants import MAX_SHORT_DURATION_SECONDS


class VideoEngine4K:
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
        layout_mode: str = "Blurred Cinema Canvas (9:16)",
        resolution_preset: str = "4K UHD (2160x3840)",
        log_callback=None,
        cancel_event: threading.Event = None,
    ):
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")

        duration = min(
            float(MAX_SHORT_DURATION_SECONDS),
            max(1.0, end_sec - start_sec),
        )
        target_w, target_h = (2160, 3840) if "4K" in resolution_preset else (1080, 1920)

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

        if layout_mode == "Blurred Cinema Canvas (9:16)":
            # Creates a 4K vertical Gaussian-blurred background with crisp foreground centered + sharpening
            vf_complex = (
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},boxblur=45:12,eq=brightness=-0.12:saturation=1.15[bg];"
                f"[0:v]scale={target_w}:-2:force_original_aspect_ratio=decrease,"
                f"unsharp=5:5:0.8:3:3:0.4[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2{sub_filter}[outv]"
            )
            cmd = [
                find_ffmpeg(), "-y",
                "-ss", f"{start_sec:.2f}",
                "-i", source_video,
                "-t", f"{duration:.2f}",
                "-filter_complex", vf_complex,
                "-map", "[outv]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "256k",
                "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                output_file
            ]
        else:
            # Smart Face Crop 9:16 + Lanczos 4K Upscaling + Unsharp Mask + Studio Color Grade
            crop_x_expr = f"max(0,min(iw-ih*9/16,(iw*{center_ratio:.3f})-(ih*9/32)))"
            vf_chain = (
                f"crop=ih*9/16:ih:'{crop_x_expr}':0,"
                f"scale={target_w}:{target_h}:flags=lanczos,"
                f"unsharp=5:5:0.85:3:3:0.4,"
                f"eq=contrast=1.04:saturation=1.08"
                f"{sub_filter}"
            )
            cmd = [
                find_ffmpeg(), "-y",
                "-ss", f"{start_sec:.2f}",
                "-i", source_video,
                "-t", f"{duration:.2f}",
                "-vf", vf_chain,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "256k",
                "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                output_file
            ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            while True:
                try:
                    _, stderr = proc.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_event and cancel_event.is_set():
                        proc.terminate()
                        try:
                            proc.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.communicate()
                        if os.path.exists(output_file):
                            try:
                                os.remove(output_file)
                            except OSError as exc:
                                raise RuntimeError(
                                    f"Unable to remove incomplete render '{output_file}': {exc}"
                                ) from exc
                        raise PipelineCancelledError("Processing stopped by user.")
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
            raise

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg Render Error: {stderr[-400:]}")
        return output_file
