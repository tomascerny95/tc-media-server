#!/usr/bin/env bash
set -e

# Resolve absolute path to the git repository directory
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_DIR="/dlna"

# Ensure root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run this script with root privileges: sudo ./setup_tc_media.sh"
  exit 1
fi

# Fully automatic detection of the regular user (UID >= 1000)
TARGET_USER="${SUDO_USER:-$(awk -F: '$3 >= 1000 && $3 < 60000 {print $1; exit}' /etc/passwd)}"

if [ -z "$TARGET_USER" ]; then
  echo "[!] Error: Failed to detect a valid system user!"
  exit 1
fi

# Verify server.py presence in the repository
if [ ! -f "$REPO_DIR/server.py" ]; then
  echo "[!] Error: server.py not found in $REPO_DIR!"
  exit 1
fi

echo "=========================================================="
echo "  TC-Media Server Setup"
echo "  Running in-place from : $REPO_DIR"
echo "  Target User           : $TARGET_USER"
echo "=========================================================="

echo "=== [1/4] Installing system packages ==="
apt update
apt install -y qbittorrent-nox python3

echo "=== [2/4] Configuring directories and permissions ==="
# Prepare /dlna shared media directory
mkdir -p "$MEDIA_DIR"
chown -R "${TARGET_USER}:${TARGET_USER}" "$MEDIA_DIR"
chmod -R 775 "$MEDIA_DIR"

# Ensure repo files are executable and owned by the user (allows git pull without sudo)
chmod +x "$REPO_DIR/server.py"
chown -R "${TARGET_USER}:${TARGET_USER}" "$REPO_DIR"

echo "=== [3/4] Configuring systemd services (in-place from Git) ==="

# 1. qBittorrent daemon service
cat << EOF > /etc/systemd/system/qbittorrent.service
[Unit]
Description=BitTorrent Client Daemon ($TARGET_USER)
After=network.target

[Service]
Type=forking
User=$TARGET_USER
Group=$TARGET_USER
UMask=002
ExecStart=/usr/bin/qbittorrent-nox -d --webui-port=8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 2. TC-Media Video Player service (runs directly from the Git repository)
cat << EOF > /etc/systemd/system/tc-media-player.service
[Unit]
Description=TC Media Web Video Player ($TARGET_USER)
After=network.target

[Service]
Type=simple
User=$TARGET_USER
Group=$TARGET_USER
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/python3 $REPO_DIR/server.py $MEDIA_DIR
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "=== [4/4] Enabling and starting services ==="
systemctl daemon-reload
systemctl enable qbittorrent.service
systemctl enable tc-media-player.service

systemctl restart qbittorrent.service
systemctl restart tc-media-player.service

IP_ADDR=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================================="
echo " Setup complete! Running in-place from: $REPO_DIR"
echo "=========================================================="
echo " 1. Web Video Player : http://${IP_ADDR}:5000"
echo "    -> Watching dir  : $MEDIA_DIR"
echo ""
echo " 2. qBittorrent WebUI: http://${IP_ADDR}:8080"
echo "    -> Set Default Save Path to: $MEDIA_DIR"
echo "       (Options -> Downloads -> Default Save Path)"
echo "=========================================================="
