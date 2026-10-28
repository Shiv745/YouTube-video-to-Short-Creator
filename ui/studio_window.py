import os
import re
import sys
import subprocess
import threading
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
from core.constants import MAX_SHORT_DURATION_SECONDS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class KixyStudioApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KixyStudio 4K — AI Viral Shorts & Reels Creator")
        self.geometry("1120x740")
        self.minsize(1020, 680)
        self.configure(fg_color="#0B0F19")

        self.local_video_path = None
        self._cancel_event = None
        self.output_dir = os.path.abspath("output_4k_shorts")
        os.makedirs(self.output_dir, exist_ok=True)

        self._build_layout()

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
            brand_frame, text=" K ", font=("Inter", 20, "bold"),
            fg_color="#FACC15", text_color="#0B0F19", corner_radius=8, width=38, height=38
        )
        logo_badge.pack(side="left")

        title_lbl = ctk.CTkLabel(
            brand_frame, text=" kixy.studio 4K", font=("Inter", 21, "bold"), text_color="#F9FAFB"
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
        ).grid(row=0, column=0, padx=18, pady=(14, 6), sticky="ew")

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
        self.log("KixyStudio 4K Engine Initialized.")
        self.log(f"Output Directory: {self.output_dir}")

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
                self.progress_bar.set(progress)
        self.after(0, _update)

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

            score = clip_data.get("virality_score", 95)
            badge = ctk.CTkLabel(
                header, text=f"🔥 {score}/100 VIRAL SCORE",
                font=("Inter", 11, "bold"), fg_color="#065F46", text_color="#34D399", corner_radius=6, padx=8, pady=2
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
        threading.Thread(
            target=self._pipeline_worker,
            args=(source_input, api_key, self._cancel_event),
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

    def _pipeline_worker(
        self,
        source_input: str,
        api_key: str,
        cancel_event: threading.Event,
    ):
        try:
            self._check_cancelled(cancel_event)
            max_clips = int(self.clip_slider.get())
            res_preset = self.res_menu.get()
            layout_mode = self.layout_menu.get()
            caption_style = self.caption_menu.get()
            whisper_model = self.whisper_menu.get()

            # Step 1: Acquire Source Video
            if os.path.exists(source_input):
                video_path = source_input
                self.set_status("Step 1/4: Using local source video...", 0.2)
                self.log(f"\n[1/4] Loaded local video: {video_path}")
            else:
                self.set_status("Step 1/4: Downloading highest-resolution video from YouTube...", 0.1)
                self.log("\n[1/4] Downloading source video via yt-dlp...")
                info = VideoDownloader.download_youtube_video(
                    source_input,
                    output_path="temp_source.mp4",
                    progress_callback=lambda msg: self.set_status(f"Step 1/4: {msg}", 0.18),
                    cancel_event=cancel_event,
                )
                video_path = info["filepath"]
                self.log(f" -> Downloaded '{info['title']}' ({info['resolution']})")

            # Step 2: Whisper Word-Level Transcription
            self._check_cancelled(cancel_event)
            self.set_status("Step 2/4: Transcribing audio with word-level timestamps...", 0.35)
            self.log(f"\n[2/4] Running Whisper ({whisper_model}) speech-to-text...")
            transcriber = AudioTranscriber(model_size=whisper_model)
            whisper_result = transcriber.transcribe_with_words(video_path, log_callback=self.log)
            self._check_cancelled(cancel_event)
            formatted_transcript = AudioTranscriber.format_for_llm(whisper_result)
            self.log(f" -> Extracted {len(whisper_result.get('segments', []))} speech segments.")

            # Step 3: Gemini Viral Clip Selection
            self._check_cancelled(cancel_event)
            self.set_status("Step 3/4: Gemini AI analyzing hooks & virality scores...", 0.60)
            self.log(f"\n[3/4] Finding top {max_clips} viral hooks with Gemini 3.8 Flash...")
            finder = ViralClipFinder(api_key=api_key)
            clips = finder.find_best_clips(
                formatted_transcript,
                max_clips=max_clips,
                max_sec=MAX_SHORT_DURATION_SECONDS,
                log_callback=self.log,
            )
            self._check_cancelled(cancel_event)
            self.log(f" -> Gemini selected {len(clips)} high-retention clips.")

            # Step 4: 4K Smart Render + Animated Subtitles
            self.log(f"\n[4/4] Rendering vertical shorts in {res_preset}...")
            for idx, clip in enumerate(clips, 1):
                self._check_cancelled(cancel_event)
                progress_val = 0.60 + (0.38 * (idx / max(1, len(clips))))
                safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", clip.get("title", f"clip_{idx}"))
                self.set_status(f"Step 4/4: Rendering 4K Short #{idx} ({safe_title})...", progress_val)

                start_s = float(clip["start"])
                end_s = min(
                    float(clip["end"]),
                    start_s + MAX_SHORT_DURATION_SECONDS,
                )
                clip["end"] = end_s

                ass_path = os.path.join(self.output_dir, f"temp_subs_{idx}.ass")
                SubtitleGenerator.generate_4k_ass_subtitles(
                    whisper_result, start_s, end_s, ass_path, style_preset=caption_style
                )

                out_file = os.path.join(self.output_dir, f"4K_Short_{idx}_{safe_title}.mp4")
                try:
                    VideoEngine4K.render_4k_short(
                        source_video=video_path,
                        output_file=out_file,
                        start_sec=start_s,
                        end_sec=end_s,
                        ass_subtitle_file=ass_path,
                        layout_mode=layout_mode,
                        resolution_preset=res_preset,
                        log_callback=self.log,
                        cancel_event=cancel_event,
                    )
                finally:
                    if os.path.exists(ass_path):
                        try:
                            os.remove(ass_path)
                        except OSError as exc:
                            self.log(f"[!] Could not remove temporary subtitle file '{ass_path}': {exc}")

                self.log(f" -> Saved 4K Short: {out_file}")
                self.add_clip_card(idx, clip, out_file, res_preset)

            self._check_cancelled(cancel_event)
            self.set_status("✅ All 4K Viral Shorts Rendered & Ready to Upload!", 1.0)
            self.log("\n🎉 Render Complete! Click 'Open 4K Output Folder' to view your videos.")

        except PipelineCancelledError:
            self.set_status("⏹ Processing stopped.", 0.0)
            self.log("\n⏹ Processing stopped by user.")
        except InvalidGeminiApiKeyError as e:
            self.set_status("❌ Gemini API key rejected. Update it and retry.", 0.0)
            self.log(f"\n[!] ERROR: {e}")
        except GeminiServiceUnavailableError as e:
            self.set_status("❌ Gemini is temporarily unavailable. Try again shortly.", 0.0)
            self.log(f"\n[!] ERROR: {e}")
        except Exception as e:
            self.set_status("❌ Error during processing. Check console log.", 0.0)
            self.log(f"\n[!] ERROR: {str(e)}")
        finally:
            def _finish_pipeline():
                self.start_btn.configure(state="normal", text="✨ Generate 4K Shorts")
                self.stop_btn.configure(state="disabled", text="⏹ Stop")
                self._cancel_event = None

            self.after(0, _finish_pipeline)
