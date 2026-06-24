# TC-Media Server Setup Guide

## Advantages of this Setup

- **Low Resource Overhead:** Using `qbittorrent-nox` (headless) and `minidlna` ensures the Raspberry Pi remains fast and responsive, as there is no heavy desktop GUI running.
- **Centralized Storage:** All your media is stored in one place (`/home/qbittorrent/Downloads`), making it easy to manage and back up.
- **Universal Compatibility:** DLNA is supported by almost all Smart TVs, game consoles, and mobile apps (like VLC), meaning no extra software is needed on your playback devices.
- **Privacy & Control:** You own the hardware and the data. There are no subscription fees or third-party tracking involved in your local streaming.
- **Automated Management:** With `systemd`, both the torrent client and the media server start automatically on boot, making it a set-and-forget solution.


This guide covers the installation and configuration of a headless media server using **qBittorrent-nox** and **MiniDLNA** on a Raspberry Pi / Debian-based system.

## 1. qBittorrent-nox Setup

### Installation
```bash
sudo apt update
sudo apt install qbittorrent-nox
```

### User & Permissions
Create a dedicated user for qBittorrent and add your main user to the group:
```bash
sudo useradd -r -m qbittorrent
sudo usermod -a -G qbittorrent !!!!!!!!!!!!!USERNAME!!!!!!!!!!!!!
```

### Systemd Service Configuration
Create the service file at `/etc/systemd/system/qbittorrent.service`:
```ini
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
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable qbittorrent.service
sudo systemctl start qbittorrent.service
```

## 2. Nginx Reverse Proxy
To access the WebUI via Nginx, edit `/etc/nginx/sites-enabled/default` and restart the service:
```bash
sudo systemctl restart nginx
```

## 3. MiniDLNA (ReadyDLNA) Setup

### Installation
```bash
sudo apt install minidlna
```

### Configuration
Edit `/etc/minidlna.conf` with the following settings:
```conf
# Media directory
media_dir=/home/qbittorrent/Downloads

# Database and logs
db_dir=/var/cache/minidlna
log_dir=/var/log/minidlna

# Server name
friendly_name=TC-Media

# Auto-discovery
inotify=yes
```

Restart the service to apply changes:
```bash
sudo systemctl restart minidlna
```
