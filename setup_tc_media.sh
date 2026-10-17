#!/bin/bash
# ==============================================================================
# TC-Media Server - Installation & Setup Script
# Features: Python 3, qBittorrent-nox, and FFmpeg (ffprobe) for Linux / Raspberry Pi
# ==============================================================================

set -e

# Root privilege check
if [ "$EUID" -ne 0 ]; then
    echo "[-] This script must be run as root (e.g. sudo ./setup_tc_media.sh)"
    exit 1
fi

# Detect actual user and script directory
ACTUAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_DIR="/dlna"

echo "=================================================="
echo "         TC-Media Server Setup Script             "
echo "=================================================="
echo "[i] User             : ${ACTUAL_USER}"
echo "[i] Repository path  : ${SCRIPT_DIR}"
echo "[i] Media directory  : ${MEDIA_DIR}"
echo "--------------------------------------------------"

# 1. Update repositories and install required packages
echo "[+] Updating package list and installing dependencies (python3, qbittorrent-nox, ffmpeg)..."
apt-get update
apt-get install -y python3 qbittorrent-nox ffmpeg

# 2. Setup shared media folder (/dlna)
echo "[+] Configuring media directory: ${MEDIA_DIR}..."
mkdir -p "${MEDIA_DIR}"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${MEDIA_DIR}"
chmod -R 777 "${MEDIA_DIR}"

# 3. Create systemd service for TC-Media Web Player
echo "[+] Creating systemd service: tc-media-player.service..."
cat <<EOF > /etc/systemd/system/tc-media-player.service
[Unit]
Description=TC-Media Server (Web Video Player)
After=network.target

[Service]
Type=simple
User=${ACTUAL_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/server.py ${MEDIA_DIR}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 4. Create systemd service for qBittorrent daemon
echo "[+] Creating systemd service: qbittorrent.service..."
cat <<EOF > /etc/systemd/system/qbittorrent.service
[Unit]
Description=qBittorrent Headless Daemon
After=network.target

[Service]
Type=forking
User=${ACTUAL_USER}
ExecStart=/usr/bin/qbittorrent-nox -d --webui-port=8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload systemd and start services
echo "[+] Reloading daemon and starting services..."
systemctl daemon-reload

systemctl enable tc-media-player.service
systemctl restart tc-media-player.service

systemctl enable qbittorrent.service
systemctl restart qbittorrent.service

# 6. Retrieve local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "=================================================="
echo "       Installation Completed Successfully!       "
echo "=================================================="
echo "Web Video Player : http://${LOCAL_IP}:5000"
echo "qBittorrent WebUI: http://${LOCAL_IP}:8080"
echo "Media directory  : ${MEDIA_DIR}"
echo ""
echo "Audio support: FFmpeg and ffprobe are ready."
echo "=================================================="
