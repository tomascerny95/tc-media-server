# TC-Media Server

A lightweight, headless media server optimized for **Raspberry Pi** and Linux, running directly from the local Git repository.

- **qBittorrent-nox** on port `8080` (headless torrent management)
- **Web Video Player** on port `5000` (pure Python video library with cinema-mode player in a new tab)
- Shared media directory at `/dlna` with automated permissions

---

## ⚡ Features
- **Extremely Low Footprint**: Zero heavy database or indexing overhead (no DLNA/Plex/Jellyfin daemon bloat).
- **Dedicated Player View**: Browse the library on the main page, select subtitles, and open video in a clean fullscreen cinema player in a new tab.
- **HTTP 206 Partial Content**: Smooth scrubbing and seeking support directly in the browser HTML5 player.
- **On-the-Fly Subtitle Parsing**: Automatically discovers `.srt` and `.vtt` subtitles, converting SRT to WebVTT dynamically.
- **In-Place Git Execution**: Runs straight from the cloned Git directory—seamless updates via `git pull`.

---

## 🚀 Installation on Raspberry Pi

```bash
# 1. Clone repository to your home directory
cd ~
git clone https://github.com/tomascerny95/tc-media-server.git

# 2. Enter folder, make script executable, and run installer
cd tc-media-server
chmod +x setup_tc_media.sh
sudo bash ./setup_tc_media.sh
```

---

## 🌐 Web Interfaces

| Service | Address | Description |
|---|---|---|
| **Web Video Player** | `http://<RPI_IP>:5000` | Browse media catalog & play videos |
| **qBittorrent WebUI** | `http://<RPI_IP>:8080` | Manage torrent downloads |

---

## ⚙️ Essential Post-Installation Settings (qBittorrent)

Open the qBittorrent WebUI at `http://<RPI_IP>:8080` and configure the following:

### 1. Storage Location
Navigate to **Tools ➔ Options ➔ Downloads**:
- Set **Default Save Path** to `/dlna`.

### 2. Tailscale & Domain Access (.local / .ts.net)
To access qBittorrent seamlessly without password prompts or domain blocking when using **mDNS (`.local`)** or **Tailscale (`.ts.net`)**, go to **Tools ➔ Options ➔ Web UI**:

- ✅ Check: **Bypass authentication for clients on localhost**
- ✅ Check: **Bypass authentication for clients in whitelisted subnets**
- In the IP subnet box, enter:
```text
0.0.0.0/0
::/0
```
- Under **Security**, uncheck the following options:
  - ❌ Uncheck: **Enable Host header validation** *(prevents domain-blocking on .local and Tailscale)*
  - ❌ Uncheck: **Enable Cross-Site Request Forgery (CSRF) protection**
  - ❌ Uncheck: **Enable clickjacking protection**

Click **Save** at the bottom.

---

## 🔄 Updating to the Latest Version

### Quick Update (Recommended)
Run this single compound command to reset any local changes, pull the latest code, and restart services:

```bash
cd ~/tc-media-server
git fetch origin && git reset --hard origin/main && chmod +x setup_tc_media.sh && sudo bash ./setup_tc_media.sh
```

---

## 🛠️ Troubleshooting Common Issues

### 1. qBittorrent asks for password on `tc-media.local` or Tailscale
- **Cause:** Domain access and Tailscale resolve to **IPv6** addresses. If only IPv4 was whitelisted, or if Host header validation is active, qBittorrent blocks access or prompts for credentials.
- **Fix:** In **Tools ➔ Options ➔ Web UI**, ensure `::/0` is added to the subnet whitelist and **Enable Host header validation** is unchecked.

---

### 2. `error: Your local changes would be overwritten by merge (Aborting)`
- **Cause:** Local file modifications or permission adjustments conflict with remote commits.
- **Fix:** Discard local changes and force-sync with the remote repository:
```bash
git fetch origin
git reset --hard origin/main
```

---

### 3. `sudo: ./setup_tc_media.sh: command not found`
- **Cause:** The script lost its execution bit (`+x`) during Git reset, or contains Windows CRLF line endings (`\r`).
- **Fix:** Remove carriage returns, re-apply execute permissions, and run via Bash:
```bash
sed -i 's/\r$//' setup_tc_media.sh
chmod +x setup_tc_media.sh
sudo bash ./setup_tc_media.sh
```

---

### 4. `./setup_tc_media.sh: Bad substitution` or `[: Illegal number:`
- **Cause:** The script was executed with `sh` (`sh ./setup_tc_media.sh`). In Debian/Raspberry Pi OS, `/bin/sh` points to `dash`, which lacks Bash syntax support.
- **Fix:** Always execute using `bash`:
```bash
sudo bash ./setup_tc_media.sh
```

---

## 🔧 Service Management (systemd)

```bash
# Check service status
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
