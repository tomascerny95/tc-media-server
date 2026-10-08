# TC-Media Server

A lightweight, headless media server optimized for **Raspberry Pi** and Linux, running directly from the local Git repository.

- **qBittorrent-nox** on port `8080` (headless torrent management)
- **Web Video Player** on port `5000` (pure Python video player with subtitle support & HTTP 206 Range seeking)
- Shared media directory at `/dlna` with automated permissions

---

## ⚡ Features
- **Extremely Low Footprint**: Zero heavy database or indexing overhead (no DLNA/Plex/Jellyfin daemon bloat).
- **HTTP 206 Partial Content**: Smooth scrubbing and seeking support directly in the browser HTML5 player.
- **On-the-Fly Subtitle Parsing**: Automatically discovers `.srt` and `.vtt` subtitles, converting SRT to WebVTT dynamically.
- **In-Place Git Execution**: Runs straight from the cloned Git directory—seamless updates via `git pull`.

---

## 🚀 Installation on Raspberry Pi

The player runs directly from the cloned repository folder without needing extra build steps or system-wide copying:

```bash
# 1. Clone repository to your home directory
cd ~
git clone https://github.com/tomascerny95/tc-media-server.git

# 2. Enter folder and execute installer
cd tc-media-server
chmod +x setup_tc_media.sh
sudo ./setup_tc_media.sh
```

---

## 🌐 Web Interfaces

| Service | Address | Description |
|---|---|---|
| **Web Video Player** | `http://<RPI_IP>:5000` | Stream videos and subtitles from `/dlna` |
| **qBittorrent WebUI** | `http://<RPI_IP>:8080` | Manage torrent downloads |

> **Post-Installation Step:**  
> Open the qBittorrent WebUI (`http://<RPI_IP>:8080`), navigate to **Tools ➔ Options ➔ Downloads**, and set the **Default Save Path** to `/dlna`.

---

## 🔄 Updating

Since the application runs directly from this repository, updating to the latest version takes just two commands:

```bash
cd ~/tc-media-server
git pull
sudo systemctl restart tc-media-player
```

---

## 🛠️ Service Management (systemd)

```bash
# Check status
sudo systemctl status tc-media-player
sudo systemctl status qbittorrent

# Restart services
sudo systemctl restart tc-media-player
sudo systemctl restart qbittorrent

# View live player logs
journalctl -u tc-media-player -f
```

---

## 📄 License
MIT License
