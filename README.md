# TC-Media Server

A lightweight, headless media server and cinema-mode web video player optimized for Raspberry Pi and Linux, designed to run directly from a local Git repository.

---

## Overview

TC-Media Server combines a clean, modern web library and video player with headless torrent management. It serves as an ultra-low-footprint alternative to heavy media servers like Plex or Jellyfin by completely avoiding background databases, telemetry, and heavy transcoding daemons.

### Key Components

- **Web Video Player (Port 5000):** Pure Python HTTP service providing a searchable video catalog and a responsive cinema-mode HTML5 player (powered by Video.js).
- **Headless qBittorrent-nox (Port 8080):** Web-managed BitTorrent client downloading directly to the shared media path.
- **Shared Storage (/dlna):** Unified directory for media files with automated permission management.

---

## Features

- **Multi-Track Audio Switching:** Detects embedded audio streams (e.g., English, Czech) via ffprobe and allows seamless switching directly from the player interface.
- **On-the-Fly Audio Transcoding:** Automatically streams unsupported audio codecs (such as Dolby Digital Plus EAC3, AC3, and DTS) into universal AAC stereo in real-time with negligible CPU usage.
- **Dynamic Lip-Sync Calibration:** Intelligent timestamp alignment and playback rate adjustments prevent audio delay or video freezing during stream transitions.
- **HTTP 206 Partial Content:** Full byte-range seeking (scrubbing) support for smooth timeline navigation.
- **Subtitles on the Fly:** Automatic discovery of local .srt and .vtt subtitles with dynamic conversion of SRT subtitles into compliant WebVTT streams.
- **Web Audio API Isolation:** Independent audio gain nodes prevent playback loops or accidental mute states when switching tracks.
- **Minimal Footprint:** Idles near 0% CPU and requires minimal RAM, making it ideal for Raspberry Pi 3/4/5 and low-power hardware.
- **Systemd Integration:** Fully managed by systemd background services (tc-media-player.service and qbittorrent.service) with auto-start on boot.

---

## Architecture & Ports

| Service | Port | Description |
| :--- | :--- | :--- |
| **TC-Media Player** | `5000` | Web catalog library and video player |
| **qBittorrent WebUI** | `8080` | Torrent management interface |
| **Media Path** | `/dlna` | Default storage directory for media files |

---

## Prerequisites

- Debian / Ubuntu / Raspberry Pi OS
- Python 3.8+
- FFmpeg & ffprobe
- qBittorrent-nox

*(All packages and dependencies are automatically configured by the setup script).*

---

## Quick Installation

1. **Clone the repository:**
```bash
git clone https://github.com/tomascerny95/tc-media-server.git
cd tc-media-server
```

2. **Run the automated setup script:**
```bash
chmod +x setup_tc_media.sh
sudo ./setup_tc_media.sh
```

3. **Access the web interfaces:**
   - **Video Library & Player:** http://<YOUR_IP>:5000
   - **qBittorrent Management:** http://<YOUR_IP>:8080 *(default username: admin, check terminal for temporary password on first run)*

---

## Manual Execution

You can also run the server directly without systemd:

```bash
# Start server with default directory (/dlna)
python3 server.py

# Or specify a custom media directory
python3 server.py /path/to/my/videos
```

---

## Project Structure

```text
tc-media-server/
├── buffer.html          # Cinema-mode player assets (Video.js, plugins, styles)
├── server.py            # Core Python HTTP server (API, streaming, audio conversion)
├── setup_tc_media.sh    # Automated installation and systemd deployment script
├── README.md            # Project documentation
└── LICENSE              # Open source license
```

---

## Endpoints

- `GET /` - Main searchable media library interface.
- `GET /player?video=<path>` - Cinema-mode video player view.
- `GET /stream?path=<path>` - HTTP 206 partial content direct video stream.
- `GET /audio_stream?path=<path>&track=<index>&t=<seconds>` - Real-time AAC audio stream for secondary tracks.
- `GET /subtitle?path=<path>` - WebVTT subtitle stream (SRT converted on the fly).
- `GET /api/videos?page=<num>&q=<query>` - JSON API for library search and pagination.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
