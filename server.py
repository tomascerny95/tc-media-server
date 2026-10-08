#!/usr/bin/env python3
"""
TC-Media Server - Lightweight web video library & player.
- Main page: Catalog of videos with subtitle selection & "Open in New Tab" buttons.
- Player page (/player): Dedicated cinema-style player opening in a new tab.
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

# --- HTML 1: MEDIA CATALOG (LIST OF VIDEOS) ---
CATALOG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TC-Media Library</title>
    <style>
        :root {
            --bg-main: #0f1115;
            --bg-card: #181b22;
            --bg-hover: #222630;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --border: #2e3440;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            min-height: 100vh;
            padding: 25px 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 15px;
        }
        header h1 { font-size: 1.5rem; font-weight: 600; }
        .badge { font-size: 0.85rem; color: var(--text-muted); }
        .search-box input {
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 12px 16px;
            border-radius: 8px;
            outline: none;
            font-size: 0.95rem;
        }
        .search-box input:focus { border-color: var(--accent); }
        .video-grid {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .video-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            transition: border-color 0.15s, background-color 0.15s;
        }
        .video-card:hover {
            border-color: var(--accent);
            background-color: var(--bg-hover);
        }
        .video-info {
            flex: 1;
            min-width: 0;
        }
        .video-title {
            font-size: 1.05rem;
            font-weight: 600;
            word-break: break-all;
            margin-bottom: 4px;
        }
        .video-dir {
            font-size: 0.8rem;
            color: var(--text-muted);
        }
        .video-actions {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }
        select {
            background: var(--bg-main);
            color: var(--text-main);
            border: 1px solid var(--border);
            padding: 8px 12px;
            border-radius: 6px;
            outline: none;
            cursor: pointer;
            font-size: 0.85rem;
            max-width: 250px;
        }
        select:focus { border-color: var(--accent); }
        .btn-open {
            background-color: var(--accent);
            color: #ffffff;
            text-decoration: none;
            padding: 9px 18px;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: background 0.15s;
            white-space: nowrap;
        }
        .btn-open:hover { background-color: var(--accent-hover); }
        .empty-state {
            text-align: center;
            color: var(--text-muted);
            padding: 40px 0;
        }
        @media (max-width: 768px) {
            .video-card {
                flex-direction: column;
                align-items: flex-start;
            }
            .video-actions {
                width: 100%;
                justify-content: space-between;
            }
            select { flex: 1; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>TC-Media Library</h1>
            <span class="badge">Directory: __MEDIA_DIR__</span>
        </header>

        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search videos...">
        </div>

        <div class="video-grid" id="videoGrid">
            <div class="empty-state">Loading library...</div>
        </div>
    </div>

    <script>
        let mediaData = { videos: [], subtitles: [] };

        async function init() {
            try {
                const res = await fetch('/api/media');
                mediaData = await res.json();
                renderVideos(mediaData.videos);
            } catch (err) {
                console.error("Failed to load media:", err);
                document.getElementById('videoGrid').innerHTML = '<div class="empty-state">Error loading media.</div>';
            }
        }

        function renderVideos(videos) {
            const container = document.getElementById('videoGrid');
            if (videos.length === 0) {
                container.innerHTML = '<div class="empty-state">No video files found in __MEDIA_DIR__.</div>';
                return;
            }
            container.innerHTML = '';

            videos.forEach(v => {
                const card = document.createElement('div');
                card.className = 'video-card';

                // Find auto-matching subtitle by basename
                const vBase = v.name.substring(0, v.name.lastIndexOf('.')).toLowerCase() || v.name.toLowerCase();
                const matchedSub = mediaData.subtitles.find(s => {
                    const sBase = s.name.substring(0, s.name.lastIndexOf('.')).toLowerCase() || s.name.toLowerCase();
                    return sBase === vBase;
                });

                // Build subtitle selector options
                let optionsHtml = '<option value="">-- No Subtitles --</option>';
                mediaData.subtitles.forEach(s => {
                    const isSelected = matchedSub && matchedSub.path === s.path ? 'selected' : '';
                    optionsHtml += `<option value="${encodeURIComponent(s.path)}" ${isSelected}>${s.name} (${s.dir || '.'})</option>`;
                });

                const initialSub = matchedSub ? encodeURIComponent(matchedSub.path) : '';
                const initialUrl = `/player?video=${encodeURIComponent(v.path)}${initialSub ? '&sub=' + initialSub : ''}`;

                card.innerHTML = `
                    <div class="video-info">
                        <div class="video-title">${v.name}</div>
                        <div class="video-dir">${v.dir ? v.dir + ' • ' : ''}Video</div>
                    </div>
                    <div class="video-actions">
                        <select class="sub-picker" title="Select subtitles">
                            ${optionsHtml}
                        </select>
                        <a href="${initialUrl}" target="_blank" class="btn-open">
                            <span>Open in New Tab &#8599;</span>
                        </a>
                    </div>
                `;

                // Update link when subtitle selection changes
                const selectEl = card.querySelector('.sub-picker');
                const linkEl = card.querySelector('.btn-open');
                selectEl.addEventListener('change', () => {
                    const chosenSub = selectEl.value;
                    linkEl.href = `/player?video=${encodeURIComponent(v.path)}${chosenSub ? '&sub=' + chosenSub : ''}`;
                });

                container.appendChild(card);
            });
        }

        document.getElementById('searchInput').addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            const filtered = mediaData.videos.filter(v =>
                v.name.toLowerCase().includes(q) || (v.dir && v.dir.toLowerCase().includes(q))
            );
            renderVideos(filtered);
        });

        init();
    </script>
</body>
</html>
"""

# --- HTML 2: DEDICATED CINEMA-STYLE PLAYER (OPENS IN NEW TAB) ---
PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Playback</title>
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
            background-color: rgba(15, 17, 21, 0.9);
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9rem;
            z-index: 10;
        }
        .video-title {
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 75vw;
        }
        .close-hint {
            color: #9ca3af;
            text-decoration: none;
            font-size: 0.85rem;
        }
        .close-hint:hover { color: #ffffff; }
        .video-wrapper {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            background: #000;
        }
        video {
            width: 100%;
            height: 100%;
            max-height: calc(100vh - 45px);
            outline: none;
        }
        video::cue {
            background-color: rgba(0, 0, 0, 0.8);
            color: #ffffff;
            font-size: 1.25rem;
        }
    </style>
</head>
<body>
    <div class="player-bar">
        <span class="video-title" id="titleDisplay">Loading video...</span>
        <a href="javascript:window.close()" class="close-hint">&#10005; Close Tab</a>
    </div>

    <div class="video-wrapper">
        <video id="player" controls autoplay playsinline></video>
    </div>

    <script>
        const params = new URLSearchParams(window.location.search);
        const videoPath = params.get('video');
        const subPath = params.get('sub');

        const player = document.getElementById('player');
        const titleDisplay = document.getElementById('titleDisplay');

        if (!videoPath) {
            titleDisplay.textContent = "Error: No video specified.";
        } else {
            const fileName = decodeURIComponent(videoPath).split('/').pop().split('\\\\').pop();
            document.title = fileName + " - TC-Media";
            titleDisplay.textContent = fileName;

            player.src = '/stream?path=' + encodeURIComponent(videoPath);

            if (subPath) {
                const track = document.createElement('track');
                track.kind = 'subtitles';
                track.label = 'Subtitles';
                track.srclang = 'en';
                track.src = '/subtitle?path=' + encodeURIComponent(subPath);
                track.default = true;
                player.appendChild(track);

                setTimeout(() => {
                    if (player.textTracks && player.textTracks[0]) {
                        player.textTracks[0].mode = 'showing';
                    }
                }, 150);
            }

            player.play().catch(() => {});
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

        # 1. Main Media Catalog
        if path in ("/", "/index.html"):
            html = CATALOG_HTML.replace("__MEDIA_DIR__", MEDIA_DIR)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. Dedicated Video Player Page (New Tab)
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
    print(f"=== TC-Media Server ===")
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
