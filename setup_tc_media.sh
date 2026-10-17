#!/usr/bin/env bash
# ==============================================================================
# TC-Media Server - Automated Setup & Deployment Script
# ==============================================================================

set -e

# Kontrola root oprávnění (sudo)
if [ "$EUID" -ne 0 ]; then
    echo "[!] Spusťte prosím skript s právy root (např. sudo ./setup_tc_media.sh)"
    exit 1
fi

REAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_DIR="/dlna"

echo "=============================================="
echo "    TC-Media Server - Installation Script"
echo "=============================================="
echo "[+] Detected user     : $REAL_USER"
echo "[+] Script directory  : $SCRIPT_DIR"

# 1. Aktualizace a instalace všech potřebných balíčků
echo "[+] Updating repositories and installing packages..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-evdev \
    ffmpeg \
    qbittorrent-nox \
    cec-utils

# 2. Konfigurace adresáře pro média
echo "[+] Configuring media directory: $MEDIA_DIR..."
mkdir -p "$MEDIA_DIR"
chown -R "$REAL_USER:$REAL_USER" "$MEDIA_DIR"
chmod -R 775 "$MEDIA_DIR"

# 3. Konfigurace HDMI-CEC a virtuální myši (uinput)
echo "[+] Configuring HDMI-CEC & uinput permissions..."
modprobe uinput || true
echo "uinput" > /etc/modules-load.d/uinput.conf

cat << 'EOF' > /etc/udev/rules.d/99-uinput.rules
KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
EOF

udevadm control --reload-rules || true
udevadm trigger || true

# Přidání uživatele do multimediálních a vstupních skupin
usermod -a -G audio,video,input,render "$REAL_USER" || true

# 4. Vytvoření systemd služby pro TC-Media Player
echo "[+] Creating systemd service: tc-media-player.service..."
cat << EOF > /etc/systemd/system/tc-media-player.service
[Unit]
Description=TC-Media Video Player & CEC Daemon
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
SupplementaryGroups=input video audio render
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/server.py $MEDIA_DIR
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 5. Vytvoření systemd služby pro qBittorrent-nox
echo "[+] Creating systemd service: qbittorrent.service..."
cat << EOF > /etc/systemd/system/qbittorrent.service
[Unit]
Description=qBittorrent-nox Headless Client
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
ExecStart=/usr/bin/qbittorrent-nox
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 6. Znovunačtení služeb a jejich spuštění
echo "[+] Reloading daemon and starting services..."
systemctl daemon-reload
systemctl enable --now tc-media-player.service
systemctl enable --now qbittorrent.service

# Zjištění primární IP adresy zařízení
IP_ADDR=$(hostname -I | awk '{print $1}')
if [ -z "$IP_ADDR" ]; then
    IP_ADDR="127.0.0.1"
fi

echo "=============================================="
echo "        Installation Completed Successfully!"
echo "=============================================="
echo "Web Video Player : http://${IP_ADDR}:5000"
echo "qBittorrent WebUI: http://${IP_ADDR}:8080"
echo "Media directory  : $MEDIA_DIR"
echo ""
echo "Audio support    : FFmpeg and ffprobe are ready."
echo "Remote support   : HDMI-CEC TV virtual mouse enabled."
echo "=============================================="
