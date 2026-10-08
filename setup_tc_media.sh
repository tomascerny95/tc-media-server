#!/usr/bin/env bash
set -e

# Resolve absolute path to the git repository directory
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_DIR="/dlna"

# Ensure script is run with root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run this script with root privileges: sudo ./setup_tc_media.sh"
  exit 1
fi

# Fully automatic detection of regular system user (UID >= 1000)
TARGET_USER="${SUDO_USER:-$(awk -F: '$3 >= 1000 && $3 < 60000 {print $1; exit}' /etc/passwd)}"
USER_HOME=$(eval echo "~$TARGET_USER")
QBIT_CONF_DIR="$USER_HOME/.config/qBittorrent"
QBIT_CONF_FILE="$QBIT_CONF_DIR/qBittorrent.conf"

if [ -z "$TARGET_USER" ]; then
  echo "[!] Error: Failed to detect a valid system user!"
  exit 1
fi

echo "=========================================================="
echo "  TC-Media Server Setup & Auto-Updater"
echo "  Running in-place from : $REPO_DIR"
echo "  Target User           : $TARGET_USER"
echo "=========================================================="

echo "=== [1/6] Stopping existing services (Safe Update) ==="
# Stop services before updating code to prevent race conditions or locked files
if systemctl is-active --quiet tc-media-player.service 2>/dev/null; then
    echo "-> Stopping tc-media-player.service..."
    systemctl stop tc-media-player.service
fi

if systemctl is-active --quiet qbittorrent.service 2>/dev/null; then
    echo "-> Stopping qbittorrent.service..."
    systemctl stop qbittorrent.service
fi

echo "=== [2/6] Pulling latest code from Git ==="
# If inside a Git repository, automatically pull updates under TARGET_USER
if [ -d "$REPO_DIR/.git" ]; then
    echo "-> Checking for updates on GitHub..."
    sudo -u "$TARGET_USER" git -C "$REPO_DIR" pull || echo "-> Note: Local changes present or already up to date."
fi

# Verify server.py is present in the repository
if [ ! -f "$REPO_DIR/server.py" ]; then
  echo "[!] Error: server.py not found in $REPO_DIR!"
  exit 1
fi

echo "=== [3/6] Installing & verifying system packages ==="
apt update
apt install -y qbittorrent-nox python3

echo "=== [4/6] Configuring directory permissions ==="
mkdir -p "$MEDIA_DIR"
chown -R "${TARGET_USER}:${TARGET_USER}" "$MEDIA_DIR"
chmod -R 775 "$MEDIA_DIR"

chmod +x "$REPO_DIR/server.py"
chown -R "${TARGET_USER}:${TARGET_USER}" "$REPO_DIR"

echo "=== [5/6] Pre-configuring qBittorrent (Passwordless WebUI) ==="
mkdir -p "$QBIT_CONF_DIR"

CONF_PATH="$QBIT_CONF_FILE" python3 - << 'EOF'
import os

conf_path = os.environ['CONF_PATH']
os.makedirs(os.path.dirname(conf_path), exist_ok=True)

lines = []
if os.path.exists(conf_path):
    with open(conf_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l for l in f if not any(k in l for k in [
            'WebUI\\AuthSubnetWhitelist',
            'WebUI\\Password',
            'WebUI\\BanDuration',
            'WebUI\\MaxAuthFailCount'
        ])]

if not any('[Preferences]' in l for l in lines):
    lines.append('\n[Preferences]\n')

out = []
for line in lines:
    out.append(line)
    if '[Preferences]' in line:
        out.append('WebUI\\AuthSubnetWhitelist=0.0.0.0/0\n')
        out.append('WebUI\\AuthSubnetWhitelistEnabled=true\n')
        out.append('WebUI\\BanDuration=0\n')

with open(conf_path, 'w', encoding='utf-8') as f:
    f.writelines(out)
EOF

chown -R "${TARGET_USER}:${TARGET_USER}" "$QBIT_CONF_DIR"

echo "=== [6/6] Starting services back up ==="

# 1. qBittorrent service unit
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

# 2. TC-Media Video Player service unit
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

systemctl daemon-reload
systemctl enable qbittorrent.service
systemctl enable tc-media-player.service

systemctl restart qbittorrent.service
systemctl restart tc-media-player.service

IP_ADDR=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================================="
echo " Update complete! Both services are back ONLINE."
echo "=========================================================="
echo " 1. Web Video Player : http://${IP_ADDR}:5000"
echo " 2. qBittorrent WebUI: http://${IP_ADDR}:8080"
echo "=========================================================="
