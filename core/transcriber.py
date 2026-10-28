import whisper

from core.ffmpeg import ensure_ffmpeg_on_path


class AudioTranscriber:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None

    def load(self, log_callback=None):
        if self.model is None:
            ensure_ffmpeg_on_path()
            if log_callback:
                log_callback(f"Loading OpenAI Whisper '{self.model_size}' model locally...")
            self.model = whisper.load_model(self.model_size)

    def transcribe_with_words(self, video_path: str, log_callback=None) -> dict:
        self.load(log_callback)
        if log_callback:
            log_callback("Transcribing audio with word-level timestamps for animated captions...")
        result = self.model.transcribe(video_path, word_timestamps=True, verbose=None)
        return result

    @staticmethod
    def format_for_llm(whisper_result: dict) -> str:
        lines = []
        for seg in whisper_result.get("segments", []):
            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()
            lines.append(f"[{start:.2f}s - {end:.2f}s] {text}")
        return "\n".join(lines)
