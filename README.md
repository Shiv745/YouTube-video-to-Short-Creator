# Shiv.Studio 4K — AI Viral Shorts & Reels Desktop Creator

A full-featured Python desktop application inspired by **kixy.ai** and **OpusClip** that downloads YouTube videos (or accepts local video clips), identifies the most viral moments using **Google Gemini AI**, tracks the speaker's face using **OpenCV**, burns in dynamic **Hormozi-style animated captions**, and exports crystal-clear **4K UHD (2160x3840) Vertical Shorts** ready for YouTube Shorts, Instagram Reels, and TikTok.

---

## ✨ Key Features
1. **True 4K UHD Vertical Rendering (2160x3840):** Uses FFmpeg `lanczos` scaling + `unsharp` luma/chroma sharpening + `CRF 18` high-bitrate encoding for ultra-crisp uploads.
2. **Vertical Framing:** Defaults to **Blurred Cinema Canvas (9:16)**, keeping the complete source frame visible over a blurred background to avoid unwanted zoom/cropping. **Smart Face Crop (Full 9:16)** remains available when you prefer a tightly cropped vertical shot with active-speaker tracking.
3. **Configurable Clip Duration:** Set minimum and maximum clip lengths in the sidebar from 1 to 180 seconds. Defaults preserve the original 25–29 second range, and rendering enforces the selected maximum.
4. **Short Source Videos:** Sources shorter than the selected minimum are looped to that minimum before transcription. If no speech is detected, the app renders the loop directly instead of sending an empty transcript for AI analysis.
5. **Optional Animated Captions (`.ass`):** Choose whether to burn word-level captions into the video with the sidebar toggle. When enabled, choose among 3 styles (*Hormozi Gold*, *Cyber Neon*, *Clean Minimal*).
6. **Broadcast Audio Mastering:** Automatically normalizes audio loudness to `-14 LUFS` (`loudnorm`) at `256 kbps` AAC so your Shorts sound punchy on mobile devices.
7. **Modern Dark Studio UI:** Built with `CustomTkinter`, featuring a sidebar settings panel, virality score cards, live telemetry logs, and VS Code single-click debugging.
8. **Pipeline Cancellation:** Stop an active run from the main toolbar; downloads and FFmpeg renders stop promptly, while transcription and Gemini requests stop after the current operation finishes.
9. **Persistent Source Downloads:** Completed YouTube downloads are saved in `downloaded_videos/` and reused on later runs for the same video, even when tracking query parameters or URL formats differ.
10. **YouTube Sign-In:** The app defaults to public-video mode and does not read browser cookies. If YouTube requires verification, choose the browser where you are signed in from the sidebar; the app reads those cookies locally through yt-dlp.
11. **AI Publishing Plan:** Ranks generated clips against each other and provides a comparison, title options, copy-ready descriptions and tags, target audience, and a suggested upload-time test window in the selected audience timezone. These are estimates, not view guarantees; validate timing with YouTube Analytics. Configure the target audience and timezone in the sidebar.
12. **Audio Mixing and Preview:** Keep the source audio, lower or mute it, and optionally mix in a local audio file or audio from a supported YouTube/Instagram link. Independently adjust original and background-audio levels from 0% to 200%, preview a 15-second mix before rendering, and stop preview playback at any time. Online audio is cached locally for reuse.
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
