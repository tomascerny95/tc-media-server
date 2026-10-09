#!/usr/bin/env python3
"""
TC-Media Server - Custom Library & Video.js Player.
- Main page: Card-based library matching custom Televize theme (#1e242c / #e54c4c).
- Player page (/player): Video.js cinema player with Hotkeys, Mobile gestures, and auto-subtitles.
- HTTP 206 Range requests (RFC 7233) for timeline seeking.
- Automatic SRT to WebVTT conversion on the fly.
"""
import os
import sys
import re
import json
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION ---
HOST = "0.0.0.0"
PORT = 5000
MEDIA_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/dlna")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
CHUNK_SIZE = 64 * 1024  # 64 KB memory-friendly streaming chunks

mimetypes.init()
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("text/vtt", ".vtt")

# --- HTML 1: CUSTOM CARD-BASED MEDIA LIBRARY ---
CATALOG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TC-Media Library</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #1e242c;
            color: #f0f0f0;
            margin: 0;
            padding: 20px 0;
            min-height: 100vh;
        }
        .container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            background-color: #2a313c;
            padding: 25px 30px;
            border-radius: 8px;
            border: 1px solid #3a414c;
        }
        h1 {
            text-align: center;
            color: #ffffff;
            margin-top: 10px;
            margin-bottom: 25px;
            font-size: 2.6rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .sub-header {
            text-align: center;
            color: #999999;
            font-size: 0.9rem;
            margin-bottom: 30px;
        }
        .url-form {
            display: flex;
            justify-content: center;
            margin-bottom: 35px;
            gap: 10px;
        }
        .url-form input[type="text"] {
            width: 100%;
            max-width: 480px;
            padding: 12px 18px;
            border: 1px solid #3a414c;
            border-radius: 6px;
            font-size: 1rem;
            background-color: #1e242c;
            color: #f0f0f0;
            outline: none;
            transition: border-color 0.2s;
        }
        .url-form input[type="text"]:focus {
            border-color: #e54c4c;
        }
        .url-form input[type="text"]::placeholder {
            color: #999999;
        }
        .url-form button {
            padding: 12px 22px;
            background-color: #e54c4c;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: background-color 0.2s;
        }
        .url-form button:hover {
            background-color: #c93a3a;
        }
        .video-list {
            text-align: center;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 20px;
        }
        .video-item {
            display: inline-flex;
            flex-direction: column;
            width: 240px;
            min-height: 290px;
            text-align: left;
            background-color: #1e242c;
            border: 1px solid #3a414c;
            border-radius: 8px;
            overflow: hidden;
            transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
        }
        .video-item:hover {
            transform: translateY(-3px);
            border-color: #e54c4c;
            box-shadow: 0 8px 20px rgba(0,0,0,0.4);
        }
        .video-thumbnail {
            width: 100%;
            height: 130px;
            background: linear-gradient(135deg, #14171d, #252b36);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-decoration: none;
            color: #f0f0f0;
            position: relative;
            cursor: pointer;
        }
        .video-thumbnail svg {
            width: 44px;
            height: 44px;
            fill: #e54c4c;
            transition: transform 0.2s;
        }
        .video-item:hover .video-thumbnail svg {
            transform: scale(1.15);
        }
        .video-badge {
            position: absolute;
            bottom: 8px;
            right: 8px;
            background-color: rgba(0, 0, 0, 0.7);
            font-size: 0.7rem;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            color: #e54c4c;
            text-transform: uppercase;
        }
        .video-details {
            padding: 12px 14px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .video-title-link {
            text-decoration: none;
            color: inherit;
        }
        .video-title-link:hover p {
            color: #e54c4c;
        }
        .video-details p {
            margin: 0 0 8px 0;
            font-weight: 600;
            font-size: 0.95rem;
            word-break: break-all;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            line-height: 1.35;
        }
        .video-dir-hint {
            font-size: 0.75rem;
            color: #888888;
            margin-bottom: 10px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sub-select-wrapper {
            margin-bottom: 12px;
        }
        .sub-select-wrapper select {
            width: 100%;
            background-color: #2a313c;
            border: 1px solid #3a414c;
            color: #f0f0f0;
            padding: 6px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            outline: none;
            cursor: pointer;
        }
        .sub-select-wrapper select:focus {
            border-color: #e54c4c;
        }
        .video-links {
            padding-top: 10px;
            border-top: 1px solid #3a414c;
            text-align: center;
            margin-top: auto;
        }
        .video-links .btn-play {
            display: block;
            width: 100%;
            text-align: center;
            text-decoration: none;
            background-color: transparent;
            border: 1px solid #e54c4c;
            color: #e54c4c;
            padding: 8px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            transition: background-color 0.2s, color 0.2s;
        }
        .video-links .btn-play:hover {
            background-color: #e54c4c;
            color: #ffffff;
        }
        .load-more-container {
            text-align: center;
            margin-top: 40px;
            padding-bottom: 10px;
        }
        .loading-indicator {
            color: #999999;
            font-size: 1.1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Televize</h1>
        <div class="sub-header">Media Directory: __MEDIA_DIR__</div>

        <form class="url-form" onsubmit="event.preventDefault();">
            <input type="text" id="searchInput" placeholder="Hledat video v knihovně...">
            <button type="button" id="clearBtn">Vymazat</button>
        </form>

        <div class="video-list" id="videoContainer"></div>

        <div class="load-more-container">
            <div class="loading-indicator" id="loadingText">Načítám média...</div>
        </div>
    </div>

    <script>
        let mediaData = { videos: [], subtitles: [] };
        const videoContainer = document.getElementById('videoContainer');
        const loadingText = document.getElementById('loadingText');
        const searchInput = document.getElementById('searchInput');
        const clearBtn = document.getElementById('clearBtn');

        async function init() {
            try {
                const res = await fetch('/api/media');
                mediaData = await res.json();
                renderVideos(mediaData.videos);
            } catch (err) {
                console.error("Error loading media:", err);
                loadingText.textContent = "Chyba při načítání dat.";
            }
        }

        function renderVideos(videos) {
            videoContainer.innerHTML = '';
            if (videos.length === 0) {
                loadingText.textContent = "Nenalezena žádná videa.";
                return;
            }
            loadingText.textContent = `Zobrazeno ${videos.length} videí`;

            videos.forEach(v => {
                const item = document.createElement('div');
                item.className = 'video-item';

                const ext = v.name.split('.').pop() || 'video';
                const vBase = v.name.substring(0, v.name.lastIndexOf('.')).toLowerCase() || v.name.toLowerCase();
                const matchedSub = mediaData.subtitles.find(s => {
                    const sBase = s.name.substring(0, s.name.lastIndexOf('.')).toLowerCase() || s.name.toLowerCase();
                    return sBase === vBase;
                });

                let optionsHtml = '<option value="">-- Bez titulků --</option>';
                mediaData.subtitles.forEach(s => {
                    const isSelected = matchedSub && matchedSub.path === s.path ? 'selected' : '';
                    optionsHtml += `<option value="${encodeURIComponent(s.path)}" ${isSelected}>${s.name}</option>`;
                });

                const initialSub = matchedSub ? encodeURIComponent(matchedSub.path) : '';
                const initialUrl = `/player?video=${encodeURIComponent(v.path)}${initialSub ? '&sub=' + initialSub : ''}`;

                item.innerHTML = `
                    <a href="${initialUrl}" target="_blank" class="video-thumbnail" title="Spustit ${v.name}">
                        <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        <span class="video-badge">${ext}</span>
                    </a>
                    <div class="video-details">
                        <div>
                            <a href="${initialUrl}" target="_blank" class="video-title-link">
                                <p title="${v.name}">${v.name}</p>
                            </a>
                            <div class="video-dir-hint" title="${v.dir || '.'}">${v.dir || 'Kořenová složka'}</div>
                        </div>
                        <div class="sub-select-wrapper">
                            <select class="sub-picker" title="Vyberte titulky">
                                ${optionsHtml}
                            </select>
                        </div>
                        <div class="video-links">
                            <a href="${initialUrl}" target="_blank" class="btn-play">Přehrát ↗</a>
                        </div>
                    </div>
                `;

                const selectEl = item.querySelector('.sub-picker');
                const linkThumb = item.querySelector('.video-thumbnail');
                const linkTitle = item.querySelector('.video-title-link');
                const linkBtn = item.querySelector('.btn-play');

                selectEl.addEventListener('change', () => {
                    const chosen = selectEl.value;
                    const updatedUrl = `/player?video=${encodeURIComponent(v.path)}${chosen ? '&sub=' + chosen : ''}`;
                    linkThumb.href = updatedUrl;
                    linkTitle.href = updatedUrl;
                    linkBtn.href = updatedUrl;
                });

                videoContainer.appendChild(item);
            });
        }

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            const filtered = mediaData.videos.filter(v =>
                v.name.toLowerCase().includes(query) || (v.dir && v.dir.toLowerCase().includes(query))
            );
            renderVideos(filtered);
        });

        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            renderVideos(mediaData.videos);
        });

        init();
    </script>
</body>
</html>
"""

# --- HTML 2: VIDEO.JS CINEMA-STYLE PLAYER (OPENS IN NEW TAB) ---
PLAYER_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Přehrávání</title>

    <!-- Video.js Base CSS -->
    <link href="https://vjs.zencdn.net/7.20.3/video-js.min.css" rel="stylesheet" />
    <!-- Video.js Mobile UI CSS -->
    <link href="https://cdn.jsdelivr.net/npm/videojs-mobile-ui@0.7.0/dist/videojs-mobile-ui.css" rel="stylesheet" />

    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: #000000;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .player-bar {
            background-color: #1e242c;
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.95rem;
            z-index: 10;
            border-bottom: 1px solid #3a414c;
        }
        .video-title {
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 75vw;
            color: #ffffff;
        }
        .close-hint {
            color: #e54c4c;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: color 0.15s;
        }
        .close-hint:hover { color: #ff7878; }
        .video-wrapper {
            flex: 1;
            position: relative;
            background: #000000;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .video-js {
            width: 100% !important;
            height: 100% !important;
        }
        .vjs-big-play-button {
            top: 50% !important;
            left: 50% !important;
            transform: translate(-50%, -50%) !important;
            background-color: rgba(229, 76, 76, 0.85) !important;
            border-color: #e54c4c !important;
            border-radius: 50% !important;
            width: 70px !important;
            height: 70px !important;
            line-height: 70px !important;
        }
        .video-js .vjs-play-progress {
            background-color: #e54c4c !important;
        }
        video::cue {
            background-color: rgba(0, 0, 0, 0.8) !important;
            color: #ffffff !important;
            font-size: 1.25rem !important;
        }
    </style>
</head>
<body>
    <div class="player-bar">
        <span class="video-title" id="titleDisplay">Načítám video...</span>
        <a href="javascript:window.close()" class="close-hint">&#10005; Zavřít kartu</a>
    </div>

    <div class="video-wrapper">
        <video id="videoPlayer" class="video-js vjs-default-skin vjs-big-play-centered" controls playsinline preload="auto">
            <p class="vjs-no-js">
                Pro zobrazení videa povolte JavaScript a použijte prohlížeč podporující HTML5 video.
            </p>
        </video>
    </div>

    <!-- Video.js & Plugins -->
    <script src="https://vjs.zencdn.net/7.20.3/video.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/videojs-hotkeys@0.2.28/videojs.hotkeys.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/videojs-mobile-ui@0.7.0/dist/videojs-mobile-ui.min.js"></script>

    <script>
        const params = new URLSearchParams(window.location.search);
        const videoPath = params.get('video');
        const subPath = params.get('sub');
        const titleDisplay = document.getElementById('titleDisplay');

        if (!videoPath) {
            titleDisplay.textContent = "Chyba: Nebylo vybráno žádné video.";
        } else {
            const fileName = decodeURIComponent(videoPath).split('/').pop().split('\\\\').pop();
            document.title = fileName + " - Televize";
            titleDisplay.textContent = fileName;

            const player = videojs('videoPlayer', {
                autoplay: true,
                controls: true,
                responsive: true,
                fluid: false,
                sources: [{
                    src: '/stream?path=' + encodeURIComponent(videoPath),
                    type: 'video/mp4'
                }],
                plugins: {
                    hotkeys: {
                        volumeStep: 0.1,
                        seekStep: 5,
                        enableModifiersForNumbers: false
                    },
                    mobileUi: {
                        fullscreen: {
                            enterOnRotate: true,
                            exitOnRotate: true,
                            lockOnRotate: false,
                            iOS: false,
                            disabled: false
                        },
                        touchControls: {
                            seekSeconds: 10,
                            tapTimeout: 300,
                            disableOnEnd: false,
                            disabled: false
                        }
                    }
                }
            });

            if (subPath) {
                player.ready(() => {
                    player.addRemoteTextTrack({
                        kind: 'subtitles',
                        srclang: 'cs',
                        label: 'Titulky',
                        src: '/subtitle?path=' + encodeURIComponent(subPath),
                        default: true
                    }, false);

                    setTimeout(() => {
                        const tracks = player.textTracks();
                        if (tracks && tracks[0]) {
                            tracks[0].mode = 'showing';
                        }
                    }, 200);
                });
            }
        }
    </script>
</body>
</html>
"""

def convert_srt_to_vtt(srt_text: str) -> str:
    """Converts SRT timestamp format (00:00:00,000) to WebVTT format (00:00:00.000)."""
    vtt = "WEBVTT\n\n"
    converted = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text)
    return vtt + converted


class MediaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Quiet logging for performance

    def is_safe_path(self, rel_path: str) -> bool:
        """Prevent Directory Traversal attacks."""
        abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
        return os.path.commonpath([MEDIA_DIR, abs_path]) == MEDIA_DIR and os.path.exists(abs_path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Main Media Library Catalog
        if path in ("/", "/index.html"):
            html = CATALOG_HTML.replace("__MEDIA_DIR__", MEDIA_DIR)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. Dedicated Video.js Player Page (New Tab)
        elif path == "/player":
            content = PLAYER_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 3. JSON API with media & subtitle files
        elif path == "/api/media":
            videos = []
            subtitles = []

            for root, _, files in os.walk(MEDIA_DIR):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, MEDIA_DIR)
                    rel_dir = os.path.relpath(root, MEDIA_DIR)
                    if rel_dir == ".":
                        rel_dir = ""

                    item = {"name": f, "path": rel_path, "dir": rel_dir}
                    if ext in VIDEO_EXTENSIONS:
                        videos.append(item)
                    elif ext in SUBTITLE_EXTENSIONS:
                        subtitles.append(item)

            data = json.dumps({"videos": videos, "subtitles": subtitles}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # 4. Subtitle serving with SRT -> WebVTT conversion
        elif path == "/subtitle":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Subtitle not found")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))
            ext = os.path.splitext(full_path)[1].lower()

            try:
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                except UnicodeDecodeError:
                    with open(full_path, "r", encoding="cp1250", errors="ignore") as f:
                        raw = f.read()

                if ext == ".srt":
                    vtt_content = convert_srt_to_vtt(raw)
                else:
                    vtt_content = raw if raw.startswith("WEBVTT") else "WEBVTT\n\n" + raw

                encoded = vtt_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/vtt; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as e:
                self.send_error(500, f"Error: {e}")
            return

        # 5. Video streaming with HTTP 206 Range requests
        elif path == "/stream":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Video not found")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))
            self.handle_range_streaming(full_path)
            return

        else:
            self.send_error(404, "Not Found")

    def handle_range_streaming(self, file_path: str):
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            self.send_error(404, "Video not found")
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "video/mp4"

        range_header = self.headers.get("Range")

        # No Range requested -> send full file
        if not range_header:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            try:
                with open(file_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        range_match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not range_match:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return

        start_str, end_str = range_match.groups()
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1

        if start >= file_size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return

        if end >= file_size:
            end = file_size - 1

        content_length = (end - start) + 1

        self.send_response(206)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        try:
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = content_length
                while bytes_left > 0:
                    read_bytes = min(CHUNK_SIZE, bytes_left)
                    chunk = f.read(read_bytes)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def run_server():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    print(f"=== Televize Media Server ===")
    print(f"Media Directory : {MEDIA_DIR}")
    print(f"Server Running  : http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
