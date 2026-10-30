# TC-Media Server

A lightweight, high-performance DLNA-compatible web media server and Video.js player tailored for desktop browsers, mobile devices, and Smart TVs.

## Features
- Clean Video.js Player: Zero external plugin dependencies. Built-in touch gestures, PC hotkeys, and Smart TV remote controls.
- MRU Tracking: Automatically sorts recently watched videos to the top (urlFolder).
- Midpoint Video Thumbnails: Automatically captures snapshots from the exact middle of videos on-demand (imageFolder).
- On-the-fly Audio Transcoding: Real-time conversion of EAC3/AC3 to AAC via FFmpeg.
- Video Queue Mode: Easy queue building with continuous auto-play support.
- Resume Playback: Remembers playback progress.

## Quick Installation (Linux / Raspberry Pi)
```bash
git clone https://github.com/tomascerny95/tc-media-server.git
cd tc-media-server
sudo chmod +x setup_tc_media.sh
sudo ./setup_tc_media.sh
```
