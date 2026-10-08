#!/usr/bin/env python3
import os
import sys
import re
import json
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# --- KONFIGURACE ---
HOST = "0.0.0.0"
PORT = 5000
# Výchozí složka, lze přepsat prvním argumentem z příkazové řádky: python3 server.py /cesta/k/videim
MEDIA_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/dlna")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}

CHUNK_SIZE = 64 * 1024  # 64 KB bloky pro streamování (nízké nároky na RAM)

mimetypes.init()
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("text/vtt", ".vtt")

# --- HTML/CSS/JS ŠABLONA ---
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RPi Media Player</title>
    <style>
        :root {
            --bg-main: #0f1115;
            --bg-card: #181b22;
            --bg-hover: #222630;
            --accent: #3b82f6;
            --accent-hover: #60a5fa;
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
            display: flex;
            flex-direction: column;
        }
        header {
            background-color: var(--bg-card);
            padding: 15px 25px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 { font-size: 1.25rem; font-weight: 600; }
        .container {
            display: grid;
            grid-template-columns: 350px 1fr;
            flex: 1;
            height: calc(100vh - 65px);
        }
        @media (max-width: 900px) {
            .container { grid-template-columns: 1fr; height: auto; }
        }
        /* Levý panel - seznam */
        .sidebar {
            background-color: var(--bg-card);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .search-box {
            padding: 15px;
            border-bottom: 1px solid var(--border);
        }
        .search-box input {
            width: 100%;
            background: var(--bg-main);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 10px 12px;
            border-radius: 6px;
            outline: none;
        }
        .search-box input:focus { border-color: var(--accent); }
        .video-list {
            list-style: none;
            overflow-y: auto;
            flex: 1;
        }
        .video-item {
            padding: 12px 15px;
            cursor: pointer;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
        }
        .video-item:hover { background-color: var(--bg-hover); }
        .video-item.active { background-color: var(--bg-hover); border-left: 4px solid var(--accent); }
        .video-item .title { font-size: 0.95rem; font-weight: 500; word-break: break-all; }
        .video-item .subtext { font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; }

        /* Pravý panel - přehrávač */
        .player-area {
            display: flex;
            flex-direction: column;
            padding: 25px;
            overflow-y: auto;
            background: var(--bg-main);
            gap: 20px;
        }
        .video-container {
            width: 100%;
            max-width: 1000px;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }
        video {
            width: 100%;
            max-height: 70vh;
            display: block;
            outline: none;
        }
        /* Styl titulků */
        video::cue {
            background-color: rgba(0, 0, 0, 0.75);
            color: #ffffff;
            font-size: 1.1rem;
        }
        .controls-card {
            max-width: 1000px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .control-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        label { font-size: 0.85rem; color: var(--text-muted); font-weight: 500; }
        select {
            background: var(--bg-main);
            color: var(--text-main);
            border: 1px solid var(--border);
            padding: 10px;
            border-radius: 6px;
            outline: none;
            cursor: pointer;
        }
        select:focus { border-color: var(--accent); }
        .empty-placeholder {
            margin: auto;
            color: var(--text-muted);
            text-align: center;
        }
    </style>
</head>
<body>
    <header>
        <h1>RPi Web Video Player</h1>
        <span style="font-size: 0.85rem; color: var(--text-muted);">Složka: __MEDIA_DIR__</span>
    </header>

    <div class="container">
        <aside class="sidebar">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Hledat video...">
            </div>
            <ul class="video-list" id="videoList"></ul>
        </aside>

        <main class="player-area">
            <div class="video-container" id="videoWrapper" style="display: none;">
                <video id="player" controls playsinline></video>
            </div>

            <div class="controls-card" id="controlsCard" style="display: none;">
                <h2 id="currentVideoTitle" style="font-size: 1.1rem; word-break: break-all;"></h2>
                <div class="control-group">
                    <label for="subSelect">Titulky (detekované i globální):</label>
                    <select id="subSelect">
                        <option value="">-- Bez titulků --</option>
                    </select>
                </div>
            </div>

            <div class="empty-placeholder" id="placeholder">
                <p>Vyberte video ze seznamu vlevo pro spuštění přehrávání.</p>
            </div>
        </main>
    </div>

    <script>
        let mediaData = { videos: [], subtitles: [] };
        let activeVideo = null;

        const player = document.getElementById('player');
        const videoWrapper = document.getElementById('videoWrapper');
        const controlsCard = document.getElementById('controlsCard');
        const placeholder = document.getElementById('placeholder');
        const videoList = document.getElementById('videoList');
        const searchInput = document.getElementById('searchInput');
        const subSelect = document.getElementById('subSelect');
        const currentVideoTitle = document.getElementById('currentVideoTitle');

        async function init() {
            try {
                const res = await fetch('/api/media');
                mediaData = await res.json();
                renderVideoList(mediaData.videos);
                populateSubtitles(mediaData.subtitles);
            } catch (err) {
                console.error("Chyba načítání médií:", err);
            }
        }

        function renderVideoList(videos) {
            videoList.innerHTML = '';
            videos.forEach(v => {
                const li = document.createElement('li');
                li.className = 'video-item';
                li.innerHTML = `
                    <div class="title">${v.name}</div>
                    <div class="subtext">${v.dir || '.'}</div>
                `;
                li.onclick = () => playVideo(v, li);
                videoList.appendChild(li);
            });
        }

        function populateSubtitles(subs) {
            subSelect.innerHTML = '<option value="">-- Bez titulků --</option>';
            subs.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.path;
                opt.textContent = `${s.name} (${s.dir || '.'})`;
                subSelect.appendChild(opt);
            });
        }

        function playVideo(video, element) {
            document.querySelectorAll('.video-item').forEach(el => el.classList.remove('active'));
            if (element) element.classList.add('active');

            activeVideo = video;
            placeholder.style.display = 'none';
            videoWrapper.style.display = 'block';
            controlsCard.style.display = 'flex';
            currentVideoTitle.textContent = video.name;

            // Vyčistit staré titulkové stopy
            while (player.firstChild) {
                player.removeChild(player.firstChild);
            }

            // Nastavit zdroj videa pro streamování s podporou Range
            player.src = '/stream?path=' + encodeURIComponent(video.path);

            // Pokus o automatickou detekci titulků (shodný název souboru bez přípony)
            const videoBaseName = video.name.substring(0, video.name.lastIndexOf('.')) || video.name;
            const matchedSub = mediaData.subtitles.find(s => {
                const subBaseName = s.name.substring(0, s.name.lastIndexOf('.')) || s.name;
                return subBaseName.toLowerCase() === videoBaseName.toLowerCase();
            });

            if (matchedSub) {
                subSelect.value = matchedSub.path;
                attachSubtitle(matchedSub.path);
            } else {
                subSelect.value = "";
            }

            player.load();
            player.play().catch(() => {});
        }

        function attachSubtitle(subPath) {
            // Odstranit existující <track>
            const oldTrack = player.querySelector('track');
            if (oldTrack) oldTrack.remove();

            if (!subPath) return;

            const track = document.createElement('track');
            track.kind = 'subtitles';
            track.label = 'Titulky';
            track.srclang = 'cs';
            // Titulky se načtou přes handler /subtitle (i .srt se vrátí jako WebVTT)
            track.src = '/subtitle?path=' + encodeURIComponent(subPath);
            track.default = true;
            player.appendChild(track);

            // Aktivovat stopu v textTracks
            setTimeout(() => {
                if (player.textTracks && player.textTracks[0]) {
                    player.textTracks[0].mode = 'showing';
                }
            }, 100);
        }

        subSelect.addEventListener('change', (e) => {
            attachSubtitle(e.target.value);
        });

        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const filtered = mediaData.videos.filter(v => 
                v.name.toLowerCase().includes(query) || (v.dir && v.dir.toLowerCase().includes(query))
            );
            renderVideoList(filtered);
        });

        init();
    </script>
</body>
</html>
"""

# --- POMOCNÉ FUNKCE PRO TITULKY ---
def convert_srt_to_vtt(srt_text: str) -> str:
    """Převádí SRT časové značky (00:00:00,000) na WebVTT (00:00:00.000)."""
    vtt = "WEBVTT\n\n"
    # Náhrada čárky za tečku v časových indexech SRT
    converted = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text)
    return vtt + converted


# --- HTTP REQUEST HANDLER ---
class MediaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Tiché logování (odkomentujte pro detailní ladění)
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def is_safe_path(self, rel_path: str) -> bool:
        """Ochrana proti Path Traversal útoku (../)."""
        abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
        return os.path.commonpath([MEDIA_DIR, abs_path]) == MEDIA_DIR and os.path.exists(abs_path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Hlavní rozhraní
        if path == "/" or path == "/index.html":
            html = HTML_TEMPLATE.replace("__MEDIA_DIR__", MEDIA_DIR)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. API pro seznam médií (JSON)
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

                    item = {
                        "name": f,
                        "path": rel_path,
                        "dir": rel_dir
                    }

                    if ext in VIDEO_EXTENSIONS:
                        videos.append(item)
                    elif ext in SUBTITLE_EXTENSIONS:
                        subtitles.append(item)

            data = json.dumps({"videos": videos, "subtitles": subtitles}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data)
            return

        # 3. Načtení titulků (s konverzí SRT -> VTT)
        elif path == "/subtitle":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Soubor nenalezen")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))
            ext = os.path.splitext(full_path)[1].lower()

            try:
                # Otevření se záložním kódováním
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
                self.send_header("Content-Length", str(len(encoded)))
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as e:
                self.send_error(500, f"Chyba při zpracování titulků: {e}")
            return

        # 4. Streamování videa s podporou HTTP Range (RFC 7233)
        elif path == "/stream":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Soubor nenalezen")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))
            self.handle_range_streaming(full_path)
            return

        else:
            self.send_error(404, "Nenalezeno")

    def handle_range_streaming(self, file_path: str):
        """Implementace HTTP 206 Partial Content pro přeskakování v čase."""
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            self.send_error(404, "Soubor nenalezen")
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "video/mp4"

        range_header = self.headers.get("Range")

        # Bez Range hlavičky -> pošle se celý soubor (HTTP 200)
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

        # Zpracování Range: bytes=start-end
        range_match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not range_match:
            self.send_response(416)  # Range Not Satisfiable
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

        self.send_response(206)  # Partial Content
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        # Posílání požadovaného rozsahu po blocích
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
    if not os.path.exists(MEDIA_DIR):
        print(f"Varování: Složka {MEDIA_DIR} neexistuje! Bude vytvořena...")
        os.makedirs(MEDIA_DIR, exist_ok=True)

    print(f"=== RPi Web Video Player ===")
    print(f"Kořenová složka médií: {MEDIA_DIR}")
    print(f"Běží na: http://{HOST}:{PORT}")

    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončuji server...")
        server.server_close()


if __name__ == "__main__":
    run_server()