# TC-Media Server

**TC-Media Server** is a lightweight, high-performance media server and web-based video streaming solution with native Smart TV support, automated subtitle injection, multi-track audio transcoding, and a clean Video.js player engine.

---

## Key Features

### 1. Clean Video.js Engine (Zero External Plugin Dependencies)
- Fully decoupled from third-party plugins (no external hotkeys or mobileUi bundles required).
- Uses local `pluginBuffer.html` generated from official NPM releases for maximum stability and security.
- 100% verified compatibility across legacy Smart TVs (Opera TV / Vewd 2016, older Tizen, webOS) as well as modern PC and mobile browsers.

### 2. Smart TV & Mobile Touch Navigation
- **Smart TV Remote Integration**: Full mapping for Tizen, webOS, and Vewd multimedia keys (Play, Pause, FastForward, Rewind, Stop).
- **Mobile Touch Gestures**: Double-tap on the left/right screen sides to seek +/-10 seconds with animated on-screen bubbles.
- **Desktop Keyboard Shortcuts**: Native bindings for Space/K (Play/Pause), Left/Right/J/L (Seek +/-10s), Up/Down (Volume), F (Fullscreen), and M (Mute).
- **Auto-hiding HUD**: Back button and title labels gracefully fade out during playback and stay locked when audio/subtitle menus are active.

### 3. Most Recently Used (MRU) History Tracking
- Whenever a video is opened, the server automatically updates its timestamp inside the `urlFolder/` directory.
- The media library automatically prioritizes and displays recently watched movies at the very top of the library across all connected clients.

### 4. Midpoint Video Snapshot Thumbnails
- Instead of static generic placeholders, the server probes video duration via `ffprobe` and extracts a real frame snapshot from the exact middle (`duration / 2`) using `ffmpeg`.
- Thumbnails are stored in `imageFolder/` using deterministic MD5 path hashes and served on-demand with fallback protection.

### 5. On-the-Fly Audio Transcoding & Web Audio API Sync
- Automatic multi-track discovery via `ffprobe` (e.g. English [eac3], Czech [aac], etc.).
- Real-time background conversion of unsupported formats (EAC3, AC3, DTS) into dual-channel AAC/ADTS streams via `ffmpeg`.
- Precise synchronization and drift compensation between video and audio playback rates with Web Audio API gain routing.

### 6. Interactive Video Queue & Playback Resuming
- **Queue Mode**: Click 'Create Queue' to pick multiple episodes or films; they run sequentially with auto-progression on video end.
- **Resume Playback**: Remembers playback progress in `localStorage` and prompts to resume from the last saved second.
- **Full Deletion**: One-click deletion on video cards removes the video file, associated `.srt`/`.vtt` subtitles, cached thumbnails, and history entries.

---

## Project Structure

```
tc-media-server/
├── server.py              # Main multi-threaded HTTP server & media backend
├── plugin_updater_gui.py  # GUI tool to fetch & build clean Video.js profiles from NPM
├── pluginBuffer.html      # Bundled Video.js CSS & JS engine (offline / cached)
├── setup_tc_media.sh      # Automated Linux / Raspberry Pi installation script
├── urlFolder/             # MRU watch history records (auto-generated)
├── imageFolder/           # Midpoint video thumbnails cache (auto-generated)
├── LICENSE                # MIT License
└── README.md              # Project documentation
```

---

## Installation & Setup

### Automated Setup (Debian / Ubuntu / Raspberry Pi OS)

Clone the repository and run the setup script as root:

```bash
git clone https://github.com/tomascerny95/tc-media-server.git
cd tc-media-server
sudo chmod +x setup_tc_media.sh
sudo ./setup_tc_media.sh
```

### Quick Update / Reinstall

To quickly update to the latest version and apply changes:

```bash
cd tc-media-server
git fetch origin && git reset --hard origin/main && sudo bash ./setup_tc_media.sh
```

The setup script will automatically:
1. Install required packages: `python3`, `python3-requests`, `python3-tk`, `ffmpeg`, and `qbittorrent-nox`.
2. Prepare the media directory at `/dlna` and set appropriate read/write permissions.
3. Create and enable the systemd service `tc-media-player.service` on port `5000`.
4. Create and enable headless `qbittorrent.service` on port `8080`.

---

## Default Endpoints

- **Web Media Player**: `http://<SERVER_IP>:5000`
- **qBittorrent WebUI**: `http://<SERVER_IP>:8080`
- **Shared Media Directory**: `/dlna`

---

## Service Management

```bash
# Check status of media player
sudo systemctl status tc-media-player.service

# Restart media player after modifications
sudo systemctl restart tc-media-player.service

# View live server logs
journalctl -u tc-media-player.service -f
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
