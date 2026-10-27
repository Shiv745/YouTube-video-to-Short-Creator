import os

class SubtitleGenerator:
    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        if seconds < 0:
            seconds = 0
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int(round((seconds - int(seconds)) * 100))
        if centis >= 100:
            centis = 99
        return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"

    @classmethod
    def generate_4k_ass_subtitles(cls, whisper_result: dict, clip_start: float, clip_end: float, ass_output_path: str, style_preset: str = "Hormozi Gold"):
        # 4K UHD Vertical Resolution: 2160 x 3840
        # Colors in ASS format: &HAABBGGRR
        styles = {
            "Hormozi Gold": {
                "primary": "&H0000D7FF",   # Vibrant Gold/Yellow
                "secondary": "&H00FFFFFF", # White
                "outline": "&H00000000",   # Thick Black Outline
                "fontsize": 135
            },
            "Cyber Neon": {
                "primary": "&H00FFFF00",   # Neon Cyan
                "secondary": "&H00FF00FF", # Magenta
                "outline": "&H00101010",
                "fontsize": 130
            },
            "Clean Minimal": {
                "primary": "&H00FFFFFF",   # Crisp White
                "secondary": "&H00D0D0D0",
                "outline": "&H00000000",
                "fontsize": 120
            }
        }
        st = styles.get(style_preset, styles["Hormozi Gold"])

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 2160
PlayResY: 3840
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{st['fontsize']},{st['primary']},{st['secondary']},{st['outline']},&H80000000,-1,0,0,0,100,100,2,0,1,12,6,2,140,140,680,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Collect words inside the clip window
        words = []
        for seg in whisper_result.get("segments", []):
            seg_words = seg.get("words", [])
            if seg_words:
                for w in seg_words:
                    w_start = float(w.get("start", 0.0))
                    w_end = float(w.get("end", 0.0))
                    w_text = w.get("word", "").strip()
                    if w_end > clip_start and w_start < clip_end and w_text:
                        words.append({
                            "start": max(0.0, w_start - clip_start),
                            "end": max(0.05, w_end - clip_start),
                            "word": w_text.upper()
                        })
            else:
                # Fallback if word timestamps are unavailable
                s_start = float(seg.get("start", 0.0))
                s_end = float(seg.get("end", 0.0))
                if s_end > clip_start and s_start < clip_end:
                    words.append({
                        "start": max(0.0, s_start - clip_start),
                        "end": max(0.1, s_end - clip_start),
                        "word": seg.get("text", "").strip().upper()
                    })

        # Group into punchy 3-word phrases with pop-in scale animation
        events = []
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            chunk = words[i:i + chunk_size]
            if not chunk:
                continue
            start_t = cls._format_ass_time(chunk[0]["start"])
            end_t = cls._format_ass_time(chunk[-1]["end"])
            phrase = " ".join(item["word"] for item in chunk)
            # Add dynamic pop animation tag
            anim_tag = r"{\fscx115\fscy115\t(0,120,\fscx100\fscy100)}"
            events.append(f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{anim_tag}{phrase}")

        with open(ass_output_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")
        return ass_output_path
