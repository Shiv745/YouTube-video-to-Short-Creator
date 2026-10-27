import os
import shutil
from pathlib import Path


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
