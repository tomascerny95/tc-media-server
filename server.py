#!/usr/bin/env python3
"""
TC-Media Server - Custom Televize Library & Cinema Player.
- Library page: Televize card grid & instant links.
- Player page: Robust player with immediate stream loading & subtitle support.
- HTTP 206 Range streaming & automatic SRT to WebVTT conversion.
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
CHUNK_SIZE = 64 * 1024

mimetypes.init()
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("text/vtt", ".vtt")

THUMBNAIL_SVG = urllib.parse.quote("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 214 120" width="214" height="120">
  <rect width="214" height="120" fill="#14171d"/>
  <circle cx="107" cy="60" r="28" fill="#e54c4c" opacity="0.85"/>
  <polygon points="101,46 120,60 101,74" fill="#ffffff"/>
</svg>""")
DEFAULT_THUMBNAIL = f"data:image/svg+xml;utf8,{THUMBNAIL_SVG}"

# --- 1. ŠABLONA KNIHOVNY (TELEVIZE) ---
LIBRARY_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Televize</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #1e242c;
            color: #f0f0f0;
            margin: 0;
            padding: 20px 0;
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
            margin-bottom: 35px;
            font-size: 2.8rem;
            font-weight: 700;
        }
        .url-form {
            display: flex;
            justify-content: center;
            margin-bottom: 50px;
            gap: 10px;
        }
        .url-form input[type="text"] {
            width: 100%;
            max-width: 450px;
            padding: 12px 18px;
            border: 1px solid #3a414c;
            border-radius: 6px;
            font-size: 1rem;
            background-color: #1e242c;
            color: #f0f0f0;
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
        }
        .video-item {
            display: inline-flex;
            flex-direction: column;
            vertical-align: top;
            width: 214px;
            min-height: 275px;
            margin: 15px;
            text-align: left;
            background-color: #2a313c;
            border: 1px solid #3a414c;
            border-radius: 8px;
            overflow: hidden;
            box-sizing: border-box;
        }
        .video-thumbnail {
            width: 100%;
            height: 120px;
            background-color: #1c1e21;
            display: block;
            flex-shrink: 0;
            position: relative;
        }
        .video-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .video-details {
            padding: 12px;
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
            text-decoration: underline;
        }
        .video-details p {
            margin: 0 0 10px 0;
            font-weight: 500;
            font-size: 0.95rem;
            word-break: break-all;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .sub-select {
            width: 100%;
            background-color: #1e242c;
            color: #f0f0f0;
            border: 1px solid #3a414c;
            border-radius: 4px;
            padding: 5px;
            font-size: 0.75rem;
            margin-bottom: 10px;
            outline: none;
            cursor: pointer;
        }
        .video-links {
            padding-top: 10px;
            border-top: 1px solid #3a414c;
            text-align: center;
            margin-top: auto;
        }
        .video-links .play-link {
            display: inline-block;
            background-color: transparent;
            border: 1px solid #e54c4c;
            color: #e54c4c;
            padding: 6px 16px;
            border-radius: 4px;
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            transition: background-color 0.2s, color 0.2s;
        }
        .video-links .play-link:hover {
            background-color: #e54c4c;
            color: #ffffff;
        }
        .load-more-container {
            text-align: center;
            margin-top: 40px;
            padding-bottom: 20px;
            height: 50px;
        }
        .loading-indicator {
            display: none;
            text-align: center;
            font-size: 1.1em;
            color: #999999;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Televize</h1>
        <form class="url-form">
            <input type="text" name="url_input" placeholder="Hledat video v knihovně...">
            <button type="submit">Hledat</button>
        </form>
        <div class="video-list"></div>
        <div class="load-more-container">
            <div class="loading-indicator">Načítám...</div>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var videoListContainer = document.querySelector('.video-list');
            var loadingIndicator = document.querySelector('.loading-indicator');
            var urlForm = document.querySelector('.url-form');
            var urlInput = document.querySelector('input[name="url_input"]');
            var currentPage = 1, itemsPerPage = 20, isLoading = false, allDataLoaded = false;
            var currentQuery = '';

            function refreshVideoList() {
                videoListContainer.innerHTML = '';
                currentPage = 1;
                allDataLoaded = false;
                loadingIndicator.textContent = 'Načítám...';
                fetchAndDisplayVideos();
            }

            urlForm.addEventListener('submit', function(event) {
                event.preventDefault();
                currentQuery = urlInput.value.trim();
                refreshVideoList();
            });

            urlInput.addEventListener('input', function() {
                if (urlInput.value.trim() === '' && currentQuery !== '') {
                    currentQuery = '';
                    refreshVideoList();
                }
            });

            function displayVideos(videos) {
                var fragment = document.createDocumentFragment();
                videos.forEach(function(video) {
                    var videoItem = document.createElement('div');
                    videoItem.classList.add('video-item');

                    var optionsHtml = '<option value="">-- Bez titulků --</option>';
                    if (video.availableSubtitles) {
                        video.availableSubtitles.forEach(function(sub) {
                            var sel = sub.matched ? 'selected' : '';
                            optionsHtml += '<option value="' + encodeURIComponent(sub.path) + '" ' + sel + '>' + sub.name + '</option>';
                        });
                    }

                    function makeUrl(subPath) {
                        return '/player?video=' + encodeURIComponent(video.path) + (subPath ? '&sub=' + subPath : '');
                    }

                    var initSub = video.matchedSub ? encodeURIComponent(video.matchedSub) : '';
                    var currentUrl = makeUrl(initSub);

                    videoItem.innerHTML =
                        '<a href="' + currentUrl + '" target="_blank" class="thumb-link">' +
                            '<div class="video-thumbnail">' +
                                '<img src="' + video.thumbnail + '" alt="Náhled: ' + video.title + '" loading="lazy">' +
                            '</div>' +
                        '</a>' +
                        '<div class="video-details">' +
                            '<a href="' + currentUrl + '" target="_blank" class="video-title-link title-link">' +
                                '<p title="' + video.title + '">' + video.title + '</p>' +
                            '</a>' +
                            '<select class="sub-select" title="Vybrat titulky">' + optionsHtml + '</select>' +
                            '<div class="video-links">' +
                                '<a href="' + currentUrl + '" target="_blank" class="play-link">Přehrát ↗</a>' +
                            '</div>' +
                        '</div>';

                    var selectEl = videoItem.querySelector('.sub-select');
                    var thumbLink = videoItem.querySelector('.thumb-link');
                    var titleLink = videoItem.querySelector('.title-link');
                    var playLink = videoItem.querySelector('.play-link');

                    selectEl.addEventListener('change', function() {
                        var updated = makeUrl(selectEl.value);
                        thumbLink.href = updated;
                        titleLink.href = updated;
                        playLink.href = updated;
                    });

                    fragment.appendChild(videoItem);
                });
                videoListContainer.appendChild(fragment);
            }

            function resetLoadingState() {
                isLoading = false;
                if (!allDataLoaded) {
                    loadingIndicator.style.display = 'none';
                }
            }

            function fetchAndDisplayVideos() {
                if (isLoading || allDataLoaded) return;
                isLoading = true;
                loadingIndicator.style.display = 'block';

                var apiUrl = '/api/videos?page=' + currentPage + '&limit=' + itemsPerPage +
                             (currentQuery ? '&q=' + encodeURIComponent(currentQuery) : '');

                fetch(apiUrl)
                    .then(function(response) {
                        if (!response.ok) { throw new Error('Chyba sítě: ' + response.statusText); }
                        return response.json();
                    })
                    .then(function(newVideos) {
                        if (newVideos.length > 0) {
                            displayVideos(newVideos);
                            currentPage++;
                        }
                        if (newVideos.length < itemsPerPage) {
                            allDataLoaded = true;
                            loadingIndicator.textContent = newVideos.length === 0 && currentPage === 1 ?
                                'Nenalezena žádná videa.' : 'Všechna videa načtena.';
                        }
                        resetLoadingState();
                    })
                    .catch(function(error) {
                        console.error("Chyba při načítání videí:", error);
                        allDataLoaded = true;
                        loadingIndicator.textContent = 'Chyba při načítání dat.';
                    });
            }

            function handleScroll() {
                var scrollPosition = window.innerHeight + (window.scrollY || document.documentElement.scrollTop);
                var totalHeight = document.documentElement.offsetHeight;
                if (scrollPosition >= totalHeight - 300) {
                    fetchAndDisplayVideos();
                }
            }

            window.addEventListener('scroll', handleScroll);
            refreshVideoList();
        });
    </script>
</body>
</html>
"""

# --- 2. ŠABLONA PŘEHRÁVAČE (PŘÍMÉ STREAMOVÁNÍ + KONTROLA) ---
PLAYER_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Přehrávání</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #000000;
            color: #f0f0f0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .player-header {
            width: 100%;
            background-color: #1e242c;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #3a414c;
            z-index: 10;
        }
        .player-title {
            font-weight: 600;
            font-size: 1.05rem;
            color: #ffffff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 80vw;
        }
        .player-close {
            color: #e54c4c;
            text-decoration: none;
            font-size: 0.95rem;
            font-weight: 600;
            transition: color 0.15s;
        }
        .player-close:hover {
            color: #ff6b6b;
        }
        .video-box {
            flex: 1;
            width: 100%;
            height: calc(100vh - 50px);
            display: flex;
            justify-content: center;
            align-items: center;
            background: #000000;
        }
        video {
            width: 100%;
            height: 100%;
            max-height: calc(100vh - 50px);
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
    <div class="player-header">
        <span class="player-title" id="videoHeading">Načítám...</span>
        <a href="javascript:window.close()" class="player-close">&#10005; Zavřít kartu</a>
    </div>

    <div class="video-box">
        <video id="videoPlayer" controls autoplay playsinline preload="auto">
            Váš prohlížeč nepodporuje HTML5 video.
        </video>
    </div>

    <script>
        var params = new URLSearchParams(window.location.search);
        var videoPath = params.get('video');
        var subPath = params.get('sub');
        var heading = document.getElementById('videoHeading');
        var player = document.getElementById('videoPlayer');

        if (!videoPath) {
            heading.textContent = 'Chyba: Nebylo vybráno žádné video v URL parametru.';
        } else {
            var decoded = decodeURIComponent(videoPath);
            var fileName = decoded.split('/').pop().split('\\').pop();
            document.title = fileName + ' - Televize';
            heading.textContent = fileName;

            // Nastavení přímého zdroje pro streamování
            player.src = '/stream?path=' + encodeURIComponent(videoPath);

            // Nastavení titulků, pokud byly předány
            if (subPath) {
                var track = document.createElement('track');
                track.kind = 'subtitles';
                track.srclang = 'cs';
                track.label = 'Titulky';
                track.src = '/subtitle?path=' + encodeURIComponent(subPath);
                track.default = true;
                player.appendChild(track);

                setTimeout(function() {
                    if (player.textTracks && player.textTracks[0]) {
                        player.textTracks[0].mode = 'showing';
                    }
                }, 200);
            }

            // Klávesové zkratky pro pohodlné ovládání
            window.addEventListener('keydown', function(e) {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
                if (e.key === ' ' || e.code === 'Space') {
                    e.preventDefault();
                    if (player.paused) player.play(); else player.pause();
                } else if (e.key === 'ArrowRight') {
                    player.currentTime = Math.min(player.duration, player.currentTime + 5);
                } else if (e.key === 'ArrowLeft') {
                    player.currentTime = Math.max(0, player.currentTime - 5);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    player.volume = Math.min(1, player.volume + 0.1);
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    player.volume = Math.max(0, player.volume - 0.1);
                } else if (e.key === 'f' || e.key === 'F') {
                    if (!document.fullscreenElement) {
                        player.requestFullscreen().catch(function(){});
                    } else {
                        document.exitFullscreen().catch(function(){});
                    }
                }
            });

            player.play().catch(function(err) {
                console.log("Autoplay čeká na interakci uživatele:", err);
            });
        }
    </script>
</body>
</html>
"""

def convert_srt_to_vtt(srt_text: str) -> str:
    vtt = "WEBVTT\n\n"
    converted = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text)
    return vtt + converted


class MediaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def is_safe_path(self, rel_path: str) -> bool:
        abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
        return os.path.commonpath([MEDIA_DIR, abs_path]) == MEDIA_DIR and os.path.exists(abs_path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = LIBRARY_HTML.replace("__MEDIA_DIR__", MEDIA_DIR)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == "/player":
            content = PLAYER_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ("/api/videos", "/api/media"):
            all_videos = []
            all_subtitles = []

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
                        all_videos.append(item)
                    elif ext in SUBTITLE_EXTENSIONS:
                        all_subtitles.append(item)

            search_query = query.get("q", [""])[0].lower().strip()
            if search_query:
                filtered_videos = [
                    v for v in all_videos
                    if search_query in v["name"].lower() or search_query in v["dir"].lower()
                ]
            else:
                filtered_videos = all_videos

            try:
                page = int(query.get("page", ["1"])[0])
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                page, limit = 1, 20

            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paged_videos = filtered_videos[start_idx:end_idx]

            response_items = []
            for v in paged_videos:
                v_base = os.path.splitext(v["name"])[0].lower()

                matched_sub = None
                available_subs = []
                for s in all_subtitles:
                    s_base = os.path.splitext(s["name"])[0].lower()
                    is_match = (s_base == v_base)
                    if is_match and not matched_sub:
                        matched_sub = s["path"]
                    available_subs.append({
                        "name": s["name"],
                        "path": s["path"],
                        "matched": is_match
                    })

                response_items.append({
                    "title": v["name"],
                    "path": v["path"],
                    "dir": v["dir"],
                    "thumbnail": DEFAULT_THUMBNAIL,
                    "matchedSub": matched_sub,
                    "availableSubtitles": available_subs
                })

            data = json.dumps(response_items).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/subtitle":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Titulky nenalezeny")
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
                self.send_error(500, f"Chyba: {e}")
            return

        elif path == "/stream":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Video nenalezeno")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))
            self.handle_range_streaming(full_path)
            return

        else:
            self.send_error(404, "Nenalezeno")

    def handle_range_streaming(self, file_path: str):
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            self.send_error(404, "Video nenalezeno")
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "video/mp4"

        range_header = self.headers.get("Range")

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
    print(f"Složka médií : {MEDIA_DIR}")
    print(f"Server běží na : http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončuji server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
