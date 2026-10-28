import json
import os
import re
import sys
import subprocess
import threading
import tempfile
import time
from tkinter import filedialog
import customtkinter as ctk

from core.cancellation import PipelineCancelledError
from core.downloader import VideoDownloader
from core.transcriber import AudioTranscriber
from core.clip_finder import (
    GeminiServiceUnavailableError,
    InvalidGeminiApiKeyError,
    ViralClipFinder,
)
from core.subtitles import SubtitleGenerator
from core.video_engine_4k import VideoEngine4K
from core.ffmpeg import create_looped_video, get_video_duration
from core.constants import MAX_SHORT_DURATION_SECONDS, MIN_SHORT_DURATION_SECONDS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ShivStudioApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Shiv.Studio 4K — AI Viral Shorts & Reels Creator")
        self.geometry("1120x740")
        self.minsize(1020, 680)
        self.configure(fg_color="#0B0F19")

        self.local_video_path = None
        self._cancel_event = None
        self._progress_indeterminate = False
        self._closing_requested = False
        self.output_dir = os.path.abspath("output_4k_shorts")
        os.makedirs(self.output_dir, exist_ok=True)

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._close_app)

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEFT SIDEBAR NAVIGATION & SETTINGS
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color="#111827")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Brand Logo
        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.pack(fill="x", padx=22, pady=(24, 16))

        logo_badge = ctk.CTkLabel(
            brand_frame, text=" S ", font=("Inter", 20, "bold"),
            fg_color="#FACC15", text_color="#0B0F19", corner_radius=8, width=38, height=38
        )
        logo_badge.pack(side="left")

        title_lbl = ctk.CTkLabel(
            brand_frame, text=" Shiv.Studio 4K", font=("Inter", 21, "bold"), text_color="#F9FAFB"
        )
        title_lbl.pack(side="left", padx=8)

        badge_unlimited = ctk.CTkLabel(
            self.sidebar, text="⚡ UNLIMITED LOCAL 4K ENGINE",
            font=("Inter", 11, "bold"), fg_color="#1E293B", text_color="#38BDF8", corner_radius=12, height=28
        )
        badge_unlimited.pack(fill="x", padx=22, pady=(0, 20))

        # AI & Render Settings Section
        settings_lbl = ctk.CTkLabel(
            self.sidebar, text="4K STUDIO RENDER SETTINGS",
            font=("Inter", 11, "bold"), text_color="#9CA3AF", anchor="w"
        )
        settings_lbl.pack(fill="x", padx=22, pady=(5, 8))

        # Gemini API Key
        ctk.CTkLabel(self.sidebar, text="Gemini API Key:", font=("Inter", 12), text_color="#D1D5DB", anchor="w").pack(fill="x", padx=22)
        self.api_entry = ctk.CTkEntry(
            self.sidebar, placeholder_text="Paste Gemini API Key...",
            show="*", height=36, fg_color="#1F2937", border_color="#374151"
        )
        self.api_entry.pack(fill="x", padx=22, pady=(4, 12))

        ctk.CTkLabel(
            self.sidebar,
            text="YouTube Sign-in Browser (if requested):",
            font=("Inter", 12),
            text_color="#D1D5DB",
            anchor="w",
        ).pack(fill="x", padx=22)
        self.youtube_browser_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=["None (public videos)", "Chrome", "Edge", "Firefox", "Brave"],
            height=36,
            fg_color="#1F2937",
            button_color="#2563EB",
            button_hover_color="#1D4ED8",
        )
        self.youtube_browser_menu.set("None (public videos)")
        self.youtube_browser_menu.pack(fill="x", padx=22, pady=(4, 12))
        ctk.CTkLabel(
            self.sidebar,
            text="Uses your selected browser's local YouTube sign-in.",
            font=("Inter", 10),
            text_color="#9CA3AF",
            anchor="w",
            wraplength=250,
        ).pack(fill="x", padx=22, pady=(0, 8))

        # Resolution Selector
        ctk.CTkLabel(self.sidebar, text="Export Resolution:", font=("Inter", 12), text_color="#D1D5DB", anchor="w").pack(fill="x", padx=22)
        self.res_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["4K UHD (2160x3840)", "1080p Full HD (1080x1920)"],
            height=36, fg_color="#1F2937", button_color="#2563EB", button_hover_color="#1D4ED8"
        )
        self.res_menu.pack(fill="x", padx=22, pady=(4, 12))

        # Framing Mode
        ctk.CTkLabel(self.sidebar, text="Smart Vertical Framing:", font=("Inter", 12), text_color="#D1D5DB", anchor="w").pack(fill="x", padx=22)
        self.layout_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["Smart Face Crop (Full 9:16)", "Blurred Cinema Canvas (9:16)"],
            height=36, fg_color="#1F2937", button_color="#2563EB", button_hover_color="#1D4ED8"
        )
        self.layout_menu.set("Blurred Cinema Canvas (9:16)")
        self.layout_menu.pack(fill="x", padx=22, pady=(4, 12))

        # Caption Theme
        ctk.CTkLabel(self.sidebar, text="Dynamic Caption Style:", font=("Inter", 12), text_color="#D1D5DB", anchor="w").pack(fill="x", padx=22)
        self.caption_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["Hormozi Gold", "Cyber Neon", "Clean Minimal"],
            height=36, fg_color="#1F2937", button_color="#2563EB", button_hover_color="#1D4ED8"
        )
        self.caption_menu.pack(fill="x", padx=22, pady=(4, 12))
        self.captions_enabled = ctk.CTkSwitch(
            self.sidebar,
            text="Burn captions into video",
            font=("Inter", 12),
            text_color="#D1D5DB",
            progress_color="#2563EB",
        )
        self.captions_enabled.select()
        self.captions_enabled.pack(fill="x", padx=22, pady=(0, 12))

        # Whisper Model Size
        ctk.CTkLabel(self.sidebar, text="Whisper AI Accuracy:", font=("Inter", 12), text_color="#D1D5DB", anchor="w").pack(fill="x", padx=22)
        self.whisper_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["base", "small", "medium"],
            height=36, fg_color="#1F2937", button_color="#2563EB", button_hover_color="#1D4ED8"
        )
        self.whisper_menu.pack(fill="x", padx=22, pady=(4, 12))

        # Number of Shorts Slider
        self.clip_count_lbl = ctk.CTkLabel(self.sidebar, text="Max Viral Clips to Generate: 3", font=("Inter", 12), text_color="#D1D5DB", anchor="w")
        self.clip_count_lbl.pack(fill="x", padx=22, pady=(4, 0))
        self.clip_slider = ctk.CTkSlider(self.sidebar, from_=1, to=8, number_of_steps=7, command=self._update_slider_label)
        self.clip_slider.set(3)
        self.clip_slider.pack(fill="x", padx=22, pady=(6, 18))

        # Open Output Folder Button
        self.open_folder_btn = ctk.CTkButton(
            self.sidebar, text="📂 Open 4K Output Folder", height=38,
            fg_color="#1F2937", hover_color="#374151", border_width=1, border_color="#4B5563",
            command=self.open_output_folder
        )
        self.open_folder_btn.pack(fill="x", padx=22, pady=(10, 20), side="bottom")

        # MAIN WORKSPACE AREA
        self.main_area = ctk.CTkFrame(self, fg_color="#0B0F19", corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=28, pady=24)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(3, weight=1)

        # Hero Banner
        hero_frame = ctk.CTkFrame(self.main_area, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1F2937")
        hero_frame.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        hero_frame.grid_columnconfigure(0, weight=1)

        hero_title = ctk.CTkLabel(
            hero_frame, text="Pick a video. Start clipping in 4K.",
            font=("Inter", 26, "bold"), text_color="#FFFFFF"
        )
        hero_title.grid(row=0, column=0, padx=24, pady=(18, 4), sticky="w")

        hero_sub = ctk.CTkLabel(
            hero_frame,
            text="AI Viral Hook Detection • Active Face Tracking • 4K Lanczos Upscaling • Animated Word Captions",
            font=("Inter", 13), text_color="#9CA3AF"
        )
        hero_sub.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        # Source Input Card (YouTube URL or Local Video File)
        input_card = ctk.CTkFrame(self.main_area, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1F2937")
        input_card.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        input_card.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_card, placeholder_text="🔗 Paste YouTube Video Link (supports up to 4K source)... or select a local file",
            height=44, font=("Inter", 13), fg_color="#0B0F19", border_color="#374151"
        )
        self.url_entry.grid(row=0, column=0, padx=(20, 10), pady=18, sticky="ew")

        self.browse_btn = ctk.CTkButton(
            input_card, text="📁 Local File", width=120, height=44,
            fg_color="#1F2937", hover_color="#374151", font=("Inter", 13, "bold"),
            command=self.select_local_file
        )
        self.browse_btn.grid(row=0, column=1, padx=(0, 10), pady=18)

        self.start_btn = ctk.CTkButton(
            input_card, text="✨ Generate 4K Shorts", width=190, height=44,
            fg_color="#2563EB", hover_color="#1D4ED8", font=("Inter", 14, "bold"),
            command=self.start_pipeline
        )
        self.start_btn.grid(row=0, column=2, padx=(0, 10), pady=18)

        self.stop_btn = ctk.CTkButton(
            input_card, text="⏹ Stop", width=100, height=44,
            fg_color="#991B1B", hover_color="#7F1D1D", font=("Inter", 13, "bold"),
            command=self.stop_pipeline, state="disabled"
        )
        self.stop_btn.grid(row=0, column=3, padx=(0, 20), pady=18)

        # Progress Bar & Status Indicator
        status_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        status_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            status_frame, text="Ready — Paste a YouTube link or choose a local video to begin.",
            font=("Inter", 13, "bold"), text_color="#38BDF8", anchor="w"
        )
        self.status_lbl.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.progress_bar = ctk.CTkProgressBar(status_frame, height=10, progress_color="#2563EB")
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.set(0.0)
        self.progress_detail_lbl = ctk.CTkLabel(
            status_frame,
            text="Ready • 0% complete",
            font=("Inter", 11),
            text_color="#9CA3AF",
            anchor="w",
        )
        self.progress_detail_lbl.grid(row=2, column=0, sticky="w", pady=(5, 0))

        # Dual Split View: Left = Generated Viral Clips Cards, Right = Live Studio Telemetry Console
        split_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        split_frame.grid(row=3, column=0, sticky="nsew")
        split_frame.grid_columnconfigure(0, weight=3)
        split_frame.grid_columnconfigure(1, weight=2)
        split_frame.grid_rowconfigure(0, weight=1)

        # Viral Clips Feed
        clips_container = ctk.CTkFrame(split_frame, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1F2937")
        clips_container.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        clips_container.grid_rowconfigure(1, weight=1)
        clips_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            clips_container, text="🎬 GENERATED 4K VIRAL CLIPS",
            font=("Inter", 12, "bold"), text_color="#9CA3AF", anchor="w"
        ).grid(row=0, column=0, padx=18, pady=(14, 6), sticky="w")

        self.results_open_folder_btn = ctk.CTkButton(
            clips_container,
            text="📂 Open Output Folder",
            width=155,
            height=30,
            fg_color="#1F2937",
            hover_color="#374151",
            border_width=1,
            border_color="#4B5563",
            command=self.open_output_folder,
        )
        self.results_open_folder_btn.grid(
            row=0, column=1, padx=(0, 14), pady=(10, 4), sticky="e"
        )

        self.clips_scroll = ctk.CTkScrollableFrame(clips_container, fg_color="transparent")
        self.clips_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self.clips_scroll.grid_columnconfigure(0, weight=1)

        # Live Console Log
        console_container = ctk.CTkFrame(split_frame, fg_color="#111827", corner_radius=16, border_width=1, border_color="#1F2937")
        console_container.grid(row=0, column=1, sticky="nsew")
        console_container.grid_rowconfigure(1, weight=1)
        console_container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_container, text="🖥️ STUDIO ENGINE TELEMETRY",
            font=("Inter", 12, "bold"), text_color="#9CA3AF", anchor="w"
        ).grid(row=0, column=0, padx=18, pady=(14, 6), sticky="ew")

        self.log_box = ctk.CTkTextbox(
            console_container, font=("Consolas", 12), fg_color="#0B0F19", text_color="#E5E7EB", corner_radius=10
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.log("Shiv.Studio 4K Engine Initialized.")
        self.log(f"Output Directory: {self.output_dir}")

    def _close_app(self):
        if self._cancel_event:
            self._closing_requested = True
            self._cancel_event.set()
            self.stop_btn.configure(state="disabled", text="Stopping...")
            self.set_status("Stopping safely before closing...", None)
            self.log("[!] Closing requested; waiting for the current operation to stop.")
            return
        self.destroy()

    def _update_slider_label(self, val):
        self.clip_count_lbl.configure(text=f"Max Viral Clips to Generate: {int(val)}")

    def log(self, message: str):
        self.after(0, lambda: self._append_log(message))

    def _append_log(self, message: str):
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def set_status(self, text: str, progress: float = None):
        def _update():
            self.status_lbl.configure(text=text)
            if progress is not None:
                if self._progress_indeterminate:
                    self.progress_bar.stop()
                    self._progress_indeterminate = False
                self.progress_bar.set(progress)
        self.after(0, _update)

    def set_pipeline_progress(
        self,
        status: str,
        progress: float,
        detail: str,
        indeterminate: bool = False,
    ):
        bounded_progress = min(1.0, max(0.0, progress))

        def _update():
            self.status_lbl.configure(text=status)
            self.progress_detail_lbl.configure(text=detail)
            if indeterminate != self._progress_indeterminate:
                if indeterminate:
                    self.progress_bar.start()
                else:
                    self.progress_bar.stop()
                self._progress_indeterminate = indeterminate
            if not indeterminate:
                self.progress_bar.set(bounded_progress)

        self.after(0, _update)

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        if isinstance(error, json.JSONDecodeError):
            return True
        if isinstance(
            error, (InvalidGeminiApiKeyError, GeminiServiceUnavailableError, PipelineCancelledError),
        ):
            return False
        if isinstance(
            error,
            (TimeoutError, ConnectionError, subprocess.TimeoutExpired),
        ):
            return True

        message = str(error).lower()
        permanent_markers = (
            "sign in to confirm",
            "could not copy",
            "cookie database",
            "database is locked",
            "database locked",
            "api_key_invalid",
            "invalid api key",
            "permission denied",
            "forbidden",
            "no space left",
            "disk full",
            "unsupported",
        )
        if any(marker in message for marker in permanent_markers):
            return False

        transient_markers = (
            "timed out",
            "timeout",
            "temporarily unavailable",
            "temporary failure",
            "connection reset",
            "connection aborted",
            "connection refused",
            "network is unreachable",
            "server disconnected",
            "try again",
            "rate limit",
            "resource_exhausted",
            "429",
            "http error 429",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
            "resource temporarily unavailable",
        )
        return any(marker in message for marker in transient_markers)

    def _run_with_retries(
        self,
        stage_name,
        operation,
        cancel_event,
        overall_progress,
        remaining_detail,
    ):
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            self._check_cancelled(cancel_event)
            try:
                return operation()
            except PipelineCancelledError:
                raise
            except Exception as error:
                if attempt >= max_attempts or not self._is_retryable_error(error):
                    self.log(
                        f"[!] {stage_name} failed ({type(error).__name__}): {error}"
                    )
                    raise

                delay = 2 ** attempt
                self.log(
                    f"[AUTO-RECOVERY] {stage_name} failed temporarily "
                    f"({type(error).__name__}: {error}). Retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_attempts})."
                )
                self.set_pipeline_progress(
                    f"⚠ Recovering {stage_name} after a temporary error...",
                    overall_progress,
                    f"Automatic retry {attempt + 1}/{max_attempts} • "
                    f"waiting {delay}s • {remaining_detail}",
                )
                if cancel_event.wait(delay):
                    raise PipelineCancelledError("Processing stopped by user.")

    def select_local_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Source Video File",
            filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.webm")]
        )
        if filepath:
            self.local_video_path = filepath
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, filepath)
            self.log(f"Selected local source file: {filepath}")

    def open_output_folder(self):
        if sys.platform == "win32":
            os.startfile(self.output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", self.output_dir])
        else:
            subprocess.Popen(["xdg-open", self.output_dir])

    def add_clip_card(self, idx: int, clip_data: dict, output_path: str, resolution_label: str):
        def _render_card():
            card = ctk.CTkFrame(self.clips_scroll, fg_color="#1F2937", corner_radius=12, border_width=1, border_color="#374151")
            card.pack(fill="x", padx=6, pady=6)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=14, pady=(10, 4))

            score = clip_data.get("virality_score")
            badge_text = (
                "♻ LOOPED CLIP"
                if score is None
                else f"🔥 {score}/100 VIRAL SCORE"
            )
            badge = ctk.CTkLabel(
                header, text=badge_text,
                font=("Inter", 11, "bold"), fg_color="#1E3A8A" if score is None else "#065F46",
                text_color="#93C5FD" if score is None else "#34D399",
                corner_radius=6, padx=8, pady=2
            )
            badge.pack(side="left")

            res_tag = ctk.CTkLabel(
                header, text=resolution_label.split()[0],
                font=("Inter", 11, "bold"), fg_color="#1E3A8A", text_color="#93C5FD", corner_radius=6, padx=8, pady=2
            )
            res_tag.pack(side="left", padx=6)

            duration = float(clip_data["end"]) - float(clip_data["start"])
            time_lbl = ctk.CTkLabel(
                header, text=f"⏱ {duration:.1f}s ({clip_data['start']:.1f}s - {clip_data['end']:.1f}s)",
                font=("Inter", 11), text_color="#9CA3AF"
            )
            time_lbl.pack(side="right")

            title_lbl = ctk.CTkLabel(
                card, text=f"#{idx} — {clip_data.get('title', 'Viral_Short')}",
                font=("Inter", 14, "bold"), text_color="#F9FAFB", anchor="w"
            )
            title_lbl.pack(fill="x", padx=14, pady=(2, 2))

            reason_lbl = ctk.CTkLabel(
                card, text=f"💡 {clip_data.get('hook_reason', 'High-retention segment')}",
                font=("Inter", 12), text_color="#D1D5DB", anchor="w", wraplength=420
            )
            reason_lbl.pack(fill="x", padx=14, pady=(0, 10))

        self.after(0, _render_card)

    def start_pipeline(self):
        source_input = self.url_entry.get().strip()
        api_key = self.api_entry.get().strip()

        if not source_input:
            self.log("[!] Please paste a YouTube URL or choose a local video file.")
            return
        if not api_key:
            self.log("[!] Please enter your Gemini API Key in the left sidebar.")
            return

        self.start_btn.configure(state="disabled", text="⏳ Rendering 4K...")
        self._cancel_event = threading.Event()
        self.stop_btn.configure(state="normal", text="⏹ Stop")
        selected_browser = self.youtube_browser_menu.get()
        cookie_browser = (
            None if selected_browser == "None (public videos)"
            else selected_browser.lower()
        )
        options = {
            "max_clips": int(self.clip_slider.get()),
            "resolution": self.res_menu.get(),
            "layout": self.layout_menu.get(),
            "caption_style": self.caption_menu.get(),
            "burn_captions": bool(self.captions_enabled.get()),
            "whisper_model": self.whisper_menu.get(),
        }
        self.progress_bar.set(0.0)
        self.progress_detail_lbl.configure(text="Starting • 0% complete")
        threading.Thread(
            target=self._pipeline_worker,
            args=(source_input, api_key, cookie_browser, options, self._cancel_event),
            daemon=True
        ).start()

    def stop_pipeline(self):
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            self.stop_btn.configure(state="disabled", text="Stopping...")
            self.set_status("Stopping after the current operation...", None)
            self.log("\n[!] Stop requested. Finishing the current operation safely...")

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event):
        if cancel_event.is_set():
            raise PipelineCancelledError("Processing stopped by user.")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def _pipeline_worker(
        self,
        source_input: str,
        api_key: str,
        cookie_browser: str,
        options: dict,
        cancel_event: threading.Event,
    ):
        overall_progress = 0.0
        pipeline_started_at = time.monotonic()
        looped_source_path = None
        try:
            self._check_cancelled(cancel_event)
            max_clips = options["max_clips"]
            res_preset = options["resolution"]
            layout_mode = options["layout"]
            caption_style = options["caption_style"]
            burn_captions = options["burn_captions"]
            whisper_model = options["whisper_model"]

            # Step 1: Acquire Source Video
            if os.path.exists(source_input):
                video_path = source_input
                overall_progress = 0.10
                self.set_pipeline_progress(
                    "Step 1/4: Using local source video...",
                    overall_progress,
                    "Overall estimate: 10% • 1/4 stages complete • 3 stages remaining",
                )
                self.log(f"\n[1/4] Loaded local video: {video_path}")
            else:
                self.set_pipeline_progress(
                    "Step 1/4: Downloading highest-resolution video from YouTube...",
                    0.0,
                    "Overall estimate: 0% • Download progress will update below",
                )
                self.log("\n[1/4] Downloading source video via yt-dlp...")

                def report_download_progress(message, fraction):
                    if fraction is None:
                        fraction = 0.0
                        download_detail = "Download progress unavailable"
                    else:
                        fraction = min(1.0, max(0.0, fraction))
                        eta_text = message.rsplit("ETA: ", 1)[-1]
                        download_detail = (
                            f"Download: {fraction:.0%} • ETA {eta_text}"
                        )
                    progress = 0.10 * fraction
                    self.set_pipeline_progress(
                        f"Step 1/4: {message}",
                        progress,
                        f"Overall estimate: {progress:.0%} • {download_detail}",
                    )

                info = self._run_with_retries(
                    "YouTube download",
                    lambda: VideoDownloader.download_youtube_video(
                        source_input,
                        progress_callback=report_download_progress,
                        cancel_event=cancel_event,
                        cookie_browser=cookie_browser,
                    ),
                    cancel_event,
                    overall_progress,
                    "download remains incomplete",
                )
                video_path = info["filepath"]
                overall_progress = 0.10
                if info["cached"]:
                    self.log(f" -> Reusing saved video: {video_path}")
                else:
                    self.log(
                        f" -> Downloaded '{info['title']}' ({info['resolution']})"
                        f"\n -> Saved locally: {video_path}"
                    )

            source_duration = get_video_duration(video_path)
            short_source = source_duration < MIN_SHORT_DURATION_SECONDS
            if short_source:
                self._check_cancelled(cancel_event)
                file_descriptor, looped_source_path = tempfile.mkstemp(
                    prefix="kixystudio_looped_",
                    suffix=".mp4",
                    dir=self.output_dir,
                )
                os.close(file_descriptor)
                self.set_pipeline_progress(
                    "Step 1/4: Looping short source to the 25-second minimum...",
                    overall_progress,
                    f"Source: {source_duration:.1f}s • Creating a "
                    f"{MIN_SHORT_DURATION_SECONDS}s loop",
                    indeterminate=True,
                )
                self.log(
                    f" -> Source is {source_duration:.1f}s; looping it to "
                    f"{MIN_SHORT_DURATION_SECONDS}s so it can produce a Short."
                )
                create_looped_video(
                    video_path,
                    looped_source_path,
                    MIN_SHORT_DURATION_SECONDS,
                    cancel_event=cancel_event,
                )
                video_path = looped_source_path
                source_duration = get_video_duration(video_path)
                self.log(
                    f" -> Prepared looped source ({source_duration:.1f}s)."
                )

            # Step 2: Whisper Word-Level Transcription
            self._check_cancelled(cancel_event)
            self.set_pipeline_progress(
                "Step 2/4: Transcribing audio with word-level timestamps...",
                overall_progress,
                f"Overall estimate: {overall_progress:.0%} • "
                f"Transcription in progress • AI analysis + up to {max_clips} "
                "renders remain • ETA unavailable",
                indeterminate=True,
            )
            self.log(f"\n[2/4] Running Whisper ({whisper_model}) speech-to-text...")
            transcriber = AudioTranscriber(model_size=whisper_model)
            whisper_result = self._run_with_retries(
                "Whisper transcription",
                lambda: transcriber.transcribe_with_words(
                    video_path,
                    log_callback=self.log,
                ),
                cancel_event,
                overall_progress,
                "transcription and analysis remain",
            )
            self._check_cancelled(cancel_event)
            formatted_transcript = AudioTranscriber.format_for_llm(whisper_result)
            overall_progress = 0.45
            self.set_pipeline_progress(
                "Step 2/4: Transcription complete.",
                overall_progress,
                f"Overall estimate: 45% • 2/4 stages complete • "
                f"{max_clips} clips to analyze and render",
            )
            self.log(f" -> Extracted {len(whisper_result.get('segments', []))} speech segments.")

            # Step 3: Gemini Viral Clip Selection
            self._check_cancelled(cancel_event)
            self.set_pipeline_progress(
                "Step 3/4: Gemini AI analyzing hooks & virality scores...",
                overall_progress,
                f"Overall estimate: 45% • AI analysis in progress • "
                f"{max_clips} clip renders remain • ETA unavailable",
                indeterminate=True,
            )
            if short_source and not formatted_transcript.strip():
                clips = []
                self.log(
                    " -> No speech was detected in the short video. "
                    "Skipping Gemini clip analysis."
                )
            else:
                self.log(f"\n[3/4] Finding top {max_clips} viral hooks with Gemini 3.8 Flash...")
                finder = ViralClipFinder(api_key=api_key)
                try:
                    clips = self._run_with_retries(
                        "Gemini analysis",
                        lambda: finder.find_best_clips(
                            formatted_transcript,
                            max_clips=max_clips,
                            max_sec=MAX_SHORT_DURATION_SECONDS,
                            log_callback=self.log,
                        ),
                        cancel_event,
                        overall_progress,
                        f"{max_clips} clips remain to render",
                    )
                except GeminiServiceUnavailableError:
                    if not short_source:
                        raise
                    clips = []
                    self.log(
                        " -> Gemini is unavailable; using the prepared looped "
                        "video instead of stopping without output."
                    )

            if short_source and not clips:
                clips = [{
                    "start": 0.0,
                    "end": min(source_duration, MAX_SHORT_DURATION_SECONDS),
                    "title": "Looped_Short_Video",
                    "virality_score": None,
                    "hook_reason": (
                        "The short source was looped to meet the minimum duration; "
                        "no AI-selected segment was available."
                    ),
                }]
                self.log(" -> Rendering the full looped short video directly.")
            self._check_cancelled(cancel_event)
            overall_progress = 0.55
            self.log(f" -> Gemini selected {len(clips)} high-retention clips.")

            # Step 4: 4K Smart Render with optional captions
            self.log(f"\n[4/4] Rendering vertical shorts in {res_preset}...")
            render_started_at = time.monotonic()
            for idx, clip in enumerate(clips, 1):
                self._check_cancelled(cancel_event)
                safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", clip.get("title", f"clip_{idx}"))
                clip_started_at = time.monotonic()
                clip_count = max(1, len(clips))

                def report_render_progress(fraction, clip_index=idx):
                    nonlocal overall_progress
                    fraction = min(1.0, max(0.0, fraction))
                    completed_render_units = (clip_index - 1) + fraction
                    render_fraction = completed_render_units / clip_count
                    progress = 0.55 + (0.45 * render_fraction)
                    overall_progress = progress
                    clip_elapsed = time.monotonic() - clip_started_at
                    remaining_units = max(0.0, clip_count - completed_render_units)
                    eta = None
                    if fraction > 0.02 and clip_elapsed > 0:
                        eta = clip_elapsed * remaining_units / completed_render_units
                    eta_text = (
                        f"ETA about {self._format_duration(eta)}"
                        if eta is not None
                        else "ETA estimating"
                    )
                    self.set_pipeline_progress(
                        f"Step 4/4: Rendering 4K Short #{clip_index} "
                        f"({fraction:.0%}) — {safe_title}",
                        progress,
                        f"Overall estimate: {progress:.0%} • "
                        f"Clip {clip_index}/{clip_count} • "
                        f"{clip_index - 1} completed • "
                        f"{clip_count - clip_index + (1 if fraction < 1 else 0)} remaining • "
                        f"{eta_text}",
                    )

                report_render_progress(0.0)

                start_s = float(clip["start"])
                end_s = min(
                    float(clip["end"]),
                    start_s + MAX_SHORT_DURATION_SECONDS,
                )
                clip["end"] = end_s

                ass_path = None
                if burn_captions:
                    ass_path = os.path.join(
                        self.output_dir, f"temp_subs_{idx}.ass"
                    )
                    SubtitleGenerator.generate_4k_ass_subtitles(
                        whisper_result,
                        start_s,
                        end_s,
                        ass_path,
                        style_preset=caption_style,
                    )

                out_file = os.path.join(self.output_dir, f"4K_Short_{idx}_{safe_title}.mp4")
                try:
                    self._run_with_retries(
                        f"Rendering clip {idx}",
                        lambda: VideoEngine4K.render_4k_short(
                            source_video=video_path,
                            output_file=out_file,
                            start_sec=start_s,
                            end_sec=end_s,
                            ass_subtitle_file=ass_path,
                            layout_mode=layout_mode,
                            resolution_preset=res_preset,
                            log_callback=self.log,
                            cancel_event=cancel_event,
                            progress_callback=report_render_progress,
                        ),
                        cancel_event,
                        overall_progress,
                        f"{len(clips) - idx + 1} render(s) remain",
                    )
                finally:
                    if ass_path and os.path.exists(ass_path):
                        try:
                            os.remove(ass_path)
                        except OSError as exc:
                            self.log(f"[!] Could not remove temporary subtitle file '{ass_path}': {exc}")

                overall_progress = 0.55 + (0.45 * (idx / clip_count))
                clip_elapsed = time.monotonic() - render_started_at
                eta = (
                    clip_elapsed * (len(clips) - idx) / idx
                    if idx < len(clips)
                    else 0
                )
                self.set_pipeline_progress(
                    f"Step 4/4: Clip {idx}/{len(clips)} rendered.",
                    overall_progress,
                    f"Overall estimate: {overall_progress:.0%} • "
                    f"{idx} completed • {len(clips) - idx} clips remaining • "
                    f"ETA about {self._format_duration(eta)}",
                )
                self.log(f" -> Saved 4K Short: {out_file}")
                self.add_clip_card(idx, clip, out_file, res_preset)

            self._check_cancelled(cancel_event)
            elapsed = time.monotonic() - pipeline_started_at
            overall_progress = 1.0
            self.set_pipeline_progress(
                "✅ All 4K Viral Shorts Rendered & Ready to Upload!",
                overall_progress,
                f"Complete • {len(clips)} clips rendered • "
                f"total time {self._format_duration(elapsed)} • no work remaining",
            )
            self.log("\n🎉 Render Complete! Click 'Open 4K Output Folder' to view your videos.")

        except PipelineCancelledError:
            self.set_pipeline_progress(
                "⏹ Processing stopped.",
                overall_progress,
                f"Stopped at about {overall_progress:.0%} • completed clips remain saved.",
            )
            self.log("\n⏹ Processing stopped by user.")
        except InvalidGeminiApiKeyError as e:
            self.set_pipeline_progress(
                "❌ Gemini API key rejected. Update it and retry.",
                overall_progress,
                "Stopped • check the API key in the sidebar.",
            )
            self.log(f"\n[!] ERROR: {e}")
        except GeminiServiceUnavailableError as e:
            self.set_pipeline_progress(
                "❌ Gemini is still unavailable after its automatic retries.",
                overall_progress,
                "Stopped • completed work is preserved • retry later.",
            )
            self.log(f"\n[!] ERROR: {e}")
        except Exception as e:
            error_text = str(e)
            lowered_error = error_text.lower()
            if "could not copy" in lowered_error and "cookie" in lowered_error:
                self.set_pipeline_progress(
                    "❌ The selected browser's cookie database is locked.",
                    overall_progress,
                    "Close every window of that browser completely, then retry. "
                    "Or select Edge if you are signed in there.",
                )
                self.log(
                    f"\n[!] ERROR: {error_text}\n"
                    "[!] yt-dlp cannot copy the selected browser's cookie database "
                    "while the browser is using it. Close all browser windows "
                    "(including background processes), or select another browser "
                    "where you are signed in, then retry. This is a local lock error; "
                    "automatic retries cannot unlock it."
                )
            elif "sign in to confirm" in lowered_error:
                self.set_pipeline_progress(
                    "❌ YouTube requires sign-in. Select your browser and retry.",
                    overall_progress,
                    "Stopped • sign-in is required; choose a signed-in browser.",
                )
                self.log(
                    f"\n[!] ERROR: {error_text}\n"
                    "[!] Select the browser where you are signed in to YouTube, "
                    "then retry. Your browser cookies stay on this computer."
                )
            else:
                self.set_pipeline_progress(
                    f"❌ Processing stopped after automatic recovery attempts: {error_text[:100]}",
                    overall_progress,
                    f"Stopped at about {overall_progress:.0%} • "
                    "completed clips are saved • see telemetry for recovery details",
                )
                self.log(
                    f"\n[!] ERROR: {type(e).__name__}: {error_text}\n"
                    "[!] Automatic recovery was attempted where the error appeared temporary. "
                    "The saved source video and completed clips were kept."
                )
        finally:
            if looped_source_path and os.path.exists(looped_source_path):
                try:
                    os.remove(looped_source_path)
                except OSError as exc:
                    self.log(
                        f"[!] Could not remove temporary looped source "
                        f"'{looped_source_path}': {exc}"
                    )

            def _finish_pipeline():
                if self._closing_requested:
                    self.destroy()
                    return
                self.start_btn.configure(state="normal", text="✨ Generate 4K Shorts")
                self.stop_btn.configure(state="disabled", text="⏹ Stop")
                self._cancel_event = None

            self.after(0, _finish_pipeline)
