#!/bin/bash

# Kontrola root prav
if [ "$EUID" -ne 0 ]; then
  echo "Prosím, spusťte tento skript jako root (použijte sudo)."
  exit
fi

echo "--- Zahajuji instalaci TC-Media Serveru ---"

# 1. Instalace balíčků
apt update && apt install -y qbittorrent-nox minidlna

# 2. Nastavení uživatele
if ! id "qbittorrent" &>/dev/null; then
    useradd -r -m qbittorrent
    echo "Uživatel qbittorrent vytvořen."
fi
usermod -a -G qbittorrent $SUDO_USER

# 3. Vytvoření systemd služby pro qBittorrent
cat > /etc/systemd/system/qbittorrent.service <<EOF
[Unit]
Description=BitTorrent Client
After=network.target

[Service]
Type=forking
User=qbittorrent
Group=qbittorrent
UMask=002
ExecStart=/usr/bin/qbittorrent-nox -d --webui-port=8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 4. Konfigurace MiniDLNA
cp /etc/minidlna.conf /etc/minidlna.conf.bak
cat > /etc/minidlna.conf <<EOF
media_dir=/home/qbittorrent/Downloads
db_dir=/var/cache/minidlna
log_dir=/var/log/minidlna
friendly_name=TC-Media
inotify=yes
EOF

# Nastavení oprávnění pro složku stahování
mkdir -p /home/qbittorrent/Downloads
chown -R qbittorrent:qbittorrent /home/qbittorrent/Downloads
chmod -R 775 /home/qbittorrent/Downloads

# 5. Spuštění služeb
systemctl daemon-reload
systemctl enable qbittorrent.service minidlna
systemctl restart qbittorrent.service minidlna

echo "--- Instalace hotova! ---"
echo "WebUI qBittorrent běží na portu 8080."
echo "MiniDLNA (TC-Media) je aktivní."
