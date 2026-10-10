#!/bin/bash
# ==============================================================================
# TC-Media Server - Instalační a konfigurační skript
# Zahrnuje: Python 3, qBittorrent-nox a FFmpeg (ffprobe) pro Raspberry Pi / Linux
# ==============================================================================

set -e

# Kontrola root práv
if [ "$EUID" -ne 0 ]; then
    echo "[-] Tento skript musí být spuštěn jako root (např. sudo ./setup_tc_media.sh)"
    exit 1
fi

# Zjištění reálného uživatele a adresáře skriptu
ACTUAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_DIR="/dlna"

echo "=================================================="
echo "    Instalace a nastavení TC-Media Serveru        "
echo "=================================================="
echo "[i] Uživatel        : ${ACTUAL_USER}"
echo "[i] Adresář repozitáře: ${SCRIPT_DIR}"
echo "[i] Složka médií    : ${MEDIA_DIR}"
echo "--------------------------------------------------"

# 1. Instalace potřebných balíčků
echo "[+] Aktualizuji repozitáře a instaluji balíčky (python3, qbittorrent-nox, ffmpeg)..."
apt-get update
apt-get install -y python3 qbittorrent-nox ffmpeg

# 2. Vytvoření a oprávnění pro sdílenou složku /dlna
echo "[+] Nastavuji adresář médií ${MEDIA_DIR}..."
mkdir -p "${MEDIA_DIR}"
chown -R "${ACTUAL_USER}:${ACTUAL_USER}" "${MEDIA_DIR}"
chmod -R 777 "${MEDIA_DIR}"

# 3. Vytvoření systemd služby pro Web Player (tc-media-player)
echo "[+] Vytvářím systemd službu: tc-media-player.service..."
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

# 4. Vytvoření systemd služby pro qBittorrent
echo "[+] Vytvářím systemd službu: qbittorrent.service..."
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

# 5. Načtení a spuštění služeb
echo "[+] Načítám a spouštím systemd služby..."
systemctl daemon-reload

systemctl enable tc-media-player.service
systemctl restart tc-media-player.service

systemctl enable qbittorrent.service
systemctl restart qbittorrent.service

# 6. Zjištění lokální IP adresy
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "=================================================="
echo "          Instalace úspěšně dokončena!            "
echo "=================================================="
echo "Webový přehrávač : http://${LOCAL_IP}:5000"
echo "qBittorrent WebUI: http://${LOCAL_IP}:8080"
echo "Složka pro média : ${MEDIA_DIR}"
echo ""
echo "Podpora audia: FFmpeg a ffprobe jsou připraveny k použití."
echo "=================================================="
