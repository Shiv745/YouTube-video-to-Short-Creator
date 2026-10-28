# Shiv.Studio 4K — AI Viral Shorts & Reels Desktop Creator

A full-featured Python desktop application that downloads YouTube videos (or accepts local video clips), identifies viral moments using **Google Gemini AI**, tracks the speaker's face using **OpenCV**, burns in dynamic animated captions, and exports Shorts in portrait or landscape orientation.

---

## ✨ Key Features
1. **4K/1080p Rendering:** Exports using FFmpeg `lanczos` scaling, sharpening, and high-bitrate encoding.
2. **Portrait and Landscape Orientation:** Choose portrait (9:16) or landscape (16:9), then select a smart crop or blurred fit canvas. Face tracking assists with smart framing.
3. **Configurable Clip Duration:** Set minimum and maximum clip lengths in the sidebar from 1 to 180 seconds. Defaults preserve the original 25–29 second range, and rendering enforces the selected maximum.
4. **Short Source Videos:** Sources shorter than the selected minimum are looped to that minimum before transcription. If no speech is detected, the app renders the loop directly instead of sending an empty transcript for AI analysis.
5. **Optional Animated Captions (`.ass`):** Choose whether to burn word-level captions into the video with the sidebar toggle. When enabled, choose among 3 styles (*Hormozi Gold*, *Cyber Neon*, *Clean Minimal*).
6. **Broadcast Audio Mastering:** Automatically normalizes audio loudness to `-14 LUFS` (`loudnorm`) at `256 kbps` AAC so your Shorts sound punchy on mobile devices.
7. **Modern Dark Studio UI:** Built with `CustomTkinter`, featuring a sidebar settings panel, virality score cards, live telemetry logs, and VS Code single-click debugging.
8. **Pipeline Cancellation:** Stop an active run from the main toolbar; downloads and FFmpeg renders stop promptly, while transcription and Gemini requests stop after the current operation finishes.
9. **Persistent Source Downloads:** Completed YouTube downloads are saved in `downloaded_videos/` and reused on later runs for the same video, even when tracking query parameters or URL formats differ.
10. **YouTube Sign-In:** The app defaults to public-video mode and does not read browser cookies. If YouTube requires verification, choose the browser where you are signed in from the sidebar; the app reads those cookies locally through yt-dlp.
11. **AI Publishing Plan:** Ranks generated clips against each other and provides a comparison, title options, copy-ready descriptions and tags, target audience, and a suggested upload-time test window in the selected audience timezone. These are estimates, not view guarantees; validate timing with YouTube Analytics. Configure the target audience and timezone in the sidebar.
12. **Standalone Audio Studio (no Gemini key):** The separate Audio Studio tab accepts a local video or YouTube video link, optional local or YouTube/Instagram audio, independent 0–200% original/background volume controls, a 15-second preview, and full-length mixed-video export. Audio controls are intentionally kept in this tab, separate from AI Shorts. Video is copied when the source codec is MP4-compatible, otherwise it is re-encoded to H.264. Online media is cached locally.
13. **Progress and Recovery:** Shows download/render percentages, completed and remaining clips, and time estimates where measurable. Transcription and AI analysis show an activity indicator because those libraries do not expose reliable progress. Temporary errors retry automatically with bounded attempts; if Gemini 3.8 Flash remains unavailable, the app tries Gemini 3.6 Flash. Sign-in, invalid credentials, and other non-retryable errors remain visible in telemetry. If the optional publishing plan fails, clips still render and are ranked by their virality scores.
If yt-dlp reports that it cannot copy a browser cookie database, fully close that browser (including background processes) and retry, or select a different browser where you are signed in. The app does not retry this local browser-lock error because retrying cannot unlock the database.

---

## 🚀 Quick Start in VS Code

### 1. Install System Prerequisite (FFmpeg)
Ensure **FFmpeg** is installed and added to your system PATH:
- **Windows:** `winget install Gyan.FFmpeg`
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

### 2. Open in VS Code & Install Dependencies
Open the project folder in VS Code, open the Integrated Terminal (`Ctrl + ~`), and run:

```bash
python -m venv venv
# Activate on Windows:
venv\Scripts\activate
# Activate on macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Run the Application
Press **F5** in VS Code (pre-configured via `.vscode/launch.json`) or run:

```bash
python main.py
```

### 4. Configure Gemini
Create or retrieve a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey), paste it into the **Gemini API Key** field in the sidebar, and retry processing. A Google account password or unrelated Google Cloud key will not work.
