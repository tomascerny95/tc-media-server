#!/usr/bin/env python3
"""
TC-Media Server - Custom Televize Library & Video.js Player.
- Knihovna s kartami videí a okamžitým výběrem titulků.
- Přehrávač s Video.js strukturou bez poster obrázku.
- Obsah souboru buffer.html se vkládá přesně mezi </head> a <body>.
- Range streaming (HTTP 206) a automatická konverze SRT -> WebVTT.
"""
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
MEDIA_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/dlna")
BUFFER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buffer.html")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
CHUNK_SIZE = 64 * 1024

mimetypes.init()
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("text/vtt", ".vtt")

FAVICON_BASE64 = (
    "data:image/x-icon;base64,AAABAAYAAAAAAAEAIADqMAAAZgAAAICAAAABACAAKAgBAFAxAABAQAAAAQAgAChCAAB4OQEAMDAAAAEAIACoJQAAoHsBACAgAA"
    "ABACAAqBAAAEihAQAQEAAAAQAgAGgEAADwsQEAiVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAAAwsUlEQVR42u2dWXMkyZHf/xGRWVkXzgLQF/qY"
    "me65umeGxyx3luRybR+l1cpMJpPpUabPJTN9BJkepBcdtmvUrkhxODyG5FzsOfpAN7objRt1ZWa4HgpAhkfWTAFVBaCA9B+NNGYhIysrD+9wD/e/K+xDRARBE"
    "AqBUkoBgD7rExEE4ewQAyAIBUYMgCAUGDEAglBgxAAIQoERAyAIBUYMgCAUmOCsT6BwuCUXRKAk4X/vdgGy2XaSglJnH0tAHPMxYcg2Vb0OVSplH2jd++9xiG"
    "N+bkkCarXcHwKkaf48VPY9yhggcB4xrfh5AYAJgF5aunAGiAE4TawFuS8vEezz53yXx4/Yi0Yb67Dr69l2pwP79Ckbo69cYS9R+NO/hrl+/XBblctQtfrxTvXF"
    "C/a99vlzJH/4mJ/71oZ3HlehoijbnpuHmpvLzqNSgblxg49pLHADoJQYhFNEXABBKDBiAAShwIgBEIQCIzGAYSEXw0/w0w=="
)

THUMBNAIL_SVG = urllib.parse.quote("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 214 120" width="214" height="120">
  <rect width="214" height="120" fill="#14171d"/>
  <circle cx="107" cy="60" r="28" fill="#e54c4c" opacity="0.85"/>
  <polygon points="101,46 120,60 101,74" fill="#ffffff"/>
</svg>""")
DEFAULT_THUMBNAIL = f"data:image/svg+xml;utf8,{THUMBNAIL_SVG}"

# --- ŠABLONA KNIHOVNY ---
LIBRARY_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Televize</title>
    <link rel="shortcut icon" href="__FAVICON__">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1e242c; color: #f0f0f0; margin: 0; padding: 20px 0; }
        .container { width: 92%; max-width: 1200px; margin: 0 auto; background: #2a313c; padding: 25px 30px; border-radius: 8px; border: 1px solid #3a414c; }
        h1 { text-align: center; color: #fff; margin-bottom: 30px; font-size: 2.8rem; font-weight: 700; }
        .url-form { display: flex; justify-content: center; margin-bottom: 40px; gap: 10px; }
        .url-form input { width: 100%; max-width: 450px; padding: 12px 18px; border: 1px solid #3a414c; border-radius: 6px; background: #1e242c; color: #fff; font-size: 1rem; }
        .url-form button { padding: 12px 22px; background: #e54c4c; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .url-form button:hover { background: #c93a3a; }
        .video-list { text-align: center; }
        .video-item { display: inline-flex; flex-direction: column; vertical-align: top; width: 220px; min-height: 275px; margin: 12px; text-align: left; background: #232933; border: 1px solid #3a414c; border-radius: 8px; overflow: hidden; }
        .video-thumbnail { width: 100%; height: 120px; background: #14171d; display: block; }
        .video-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
        .video-details { padding: 12px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .video-details p { margin: 0 0 10px 0; font-weight: 500; font-size: 0.9rem; word-break: break-all; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .sub-select { width: 100%; background: #1e242c; color: #fff; border: 1px solid #3a414c; border-radius: 4px; padding: 5px; font-size: 0.75rem; margin-bottom: 10px; }
        .play-link { display: inline-block; text-align: center; border: 1px solid #e54c4c; color: #e54c4c; padding: 6px 14px; border-radius: 4px; text-decoration: none; font-size: 0.85rem; font-weight: 600; }
        .play-link:hover { background: #e54c4c; color: #fff; }
        .loading { text-align: center; color: #888; margin: 30px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Televize</h1>
        <form class="url-form">
            <input type="text" name="q" placeholder="Hledat video v knihovně...">
            <button type="submit">Hledat</button>
        </form>
        <div class="video-list"></div>
        <div class="loading">Načítám...</div>
    </div>
    <script>
        var page = 1, query = '', loading = false, finished = false;
        var list = document.querySelector('.video-list');
        var loader = document.querySelector('.loading');
        var form = document.querySelector('.url-form');
        var input = form.querySelector('input');

        function loadVideos() {
            if (loading || finished) return;
            loading = true;
            loader.style.display = 'block';
            fetch('/api/videos?page=' + page + '&q=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(data => {
                    if (data.length > 0) {
                        data.forEach(v => {
                            var item = document.createElement('div');
                            item.className = 'video-item';
                            var opts = '<option value="">-- Bez titulků --</option>';
                            if (v.availableSubtitles) {
                                v.availableSubtitles.forEach(s => {
                                    opts += '<option value="' + encodeURIComponent(s.path) + '" ' + (s.matched ? 'selected':'') + '>' + s.name + '</option>';
                                });
                            }
                            function getUrl(sub) {
                                return '/player?video=' + encodeURIComponent(v.path) + (sub ? '&sub=' + sub : '');
                            }
                            var curUrl = getUrl(v.matchedSub ? encodeURIComponent(v.matchedSub) : '');
                            item.innerHTML = 
                                '<a href="' + curUrl + '" target="_blank" class="t-link"><div class="video-thumbnail"><img src="' + v.thumbnail + '"></div></a>' +
                                '<div class="video-details">' +
                                    '<a href="' + curUrl + '" target="_blank" style="color:inherit;text-decoration:none;"><p title="' + v.title + '">' + v.title + '</p></a>' +
                                    '<select class="sub-select">' + opts + '</select>' +
                                    '<a href="' + curUrl + '" target="_blank" class="play-link">Přehrát ↗</a>' +
                                '</div>';
                            var sel = item.querySelector('.sub-select');
                            sel.addEventListener('change', () => {
                                var updated = getUrl(sel.value);
                                item.querySelectorAll('a').forEach(a => a.href = updated);
                            });
                            list.appendChild(item);
                        });
                        page++;
                    }
                    if (data.length < 20) {
                        finished = true;
                        loader.textContent = 'Vše načteno.';
                    } else {
                        loader.style.display = 'none';
                    }
                    loading = false;
                });
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            list.innerHTML = '';
            page = 1;
            finished = false;
            query = input.value.trim();
            loadVideos();
        });

        window.addEventListener('scroll', () => {
            if (window.innerHeight + window.scrollY >= document.documentElement.offsetHeight - 250) {
                loadVideos();
            }
        });

        loadVideos();
    </script>
</body>
</html>
"""

def get_buffer_content() -> str:
    """Načte přesný obsah souboru buffer.html, pokud existuje."""
    if os.path.exists(BUFFER_FILE):
        try:
            with open(BUFFER_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[!] Chyba při čtení buffer.html: {e}")
    return ""

def build_player_page(video_path: str, sub_path: str) -> str:
    file_name = os.path.basename(video_path) if video_path else "Přehrávač"
    stream_url = f"/stream?path={urllib.parse.quote(video_path)}" if video_path else ""
    
    sub_tag = ""
    if sub_path:
        sub_url = f"/subtitle?path={urllib.parse.quote(sub_path)}"
        sub_tag = f'\t\t<track src="{sub_url}" kind="captions" label="Titulky: cze - 1" />'

    buffer_inject = get_buffer_content()

    html = f"""<head>
\t<title>{file_name}</title>
\t<link rel="shortcut icon" href="{FAVICON_BASE64}" />
</head>
{buffer_inject}
<body>
\t<video id="videoPlayer" class="video-js vjs-big-play-centered">
{sub_tag}
\t\t<p class="vjs-no-js">Chcete-li zobrazit toto video, povolte JavaScript a zvažte upgrade na webový prohlížeč, který <a href="https://videojs.com/html5-video-support/" target="_blank" >podporuje HTML5 video</a></p>
\t</video>
\t<script>
\t\tvideojs('videoPlayer',{{
\t\t\t"controls" : true,
\t\t\tplugins: {{
\t\t\t\tvideoJsResolutionSwitcher: {{}}, 
\t\t\t\thotkeys: {{}},
\t\t\t\tmobileUi: {{
\t\t\t\t\tfullscreen: {{
\t\t\t\t\t\tenterOnRotate: true,
\t\t\t\t\t\texitOnRotate: true,
\t\t\t\t\t\tlockOnRotate: false,
\t\t\t\t\t\tlockToLandscapeOnEnter: false,
\t\t\t\t\t\tiOS: false,
\t\t\t\t\t\tdisabled: false
\t\t\t\t\t}}, touchControls: {{
\t\t\t\t\t\tseekSeconds: 10,
\t\t\t\t\t\ttapTimeout: 300,
\t\t\t\t\t\tdisableOnEnd: false,
\t\t\t\t\t\tdisabled: false,
\t\t\t\t\t}}
\t\t\t\t}},
\t\t\t}}
\t\t}}, function(){{
\t\t\tvar player = this;
\t\t\tplayer.updateSrc(
\t\t\t\t[
\t\t\t\t\t{{
\t\t\t\t\t\tsrc: '{stream_url}',
\t\t\t\t\t\ttype: 'video/mp4',
\t\t\t\t\t\tlabel: 'Kvalita: 720p - 0'
\t\t\t\t\t}},
\t\t\t\t]
\t\t\t)
\t\t}}
\t\t);
\t</script>
</body>"""
    return html


def convert_srt_to_vtt(srt_text: str) -> str:
    vtt = "WEBVTT\n\n"
    converted = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text)
    return vtt + converted


class MediaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def is_safe_path(self, rel_path: str) -> bool:
        if not rel_path:
            return False
        abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
        return os.path.commonpath([MEDIA_DIR, abs_path]) == MEDIA_DIR and os.path.exists(abs_path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = LIBRARY_HTML.replace("__FAVICON__", FAVICON_BASE64)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/player":
            v_path = query.get("video", [""])[0]
            s_path = query.get("sub", [""])[0]
            html = build_player_page(v_path, s_path)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/videos":
            all_videos = []
            all_subs = []
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
                        all_subs.append(item)

            q_str = query.get("q", [""])[0].lower().strip()
            if q_str:
                filtered = [v for v in all_videos if q_str in v["name"].lower() or q_str in v["dir"].lower()]
            else:
                filtered = all_videos

            try:
                page = int(query.get("page", ["1"])[0])
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                page, limit = 1, 20

            paged = filtered[(page - 1) * limit : page * limit]
            result = []
            for v in paged:
                v_base = os.path.splitext(v["name"])[0].lower()
                matched_sub = None
                avail = []
                for s in all_subs:
                    s_base = os.path.splitext(s["name"])[0].lower()
                    is_match = (s_base == v_base)
                    if is_match and not matched_sub:
                        matched_sub = s["path"]
                    avail.append({"name": s["name"], "path": s["path"], "matched": is_match})

                result.append({
                    "title": v["name"],
                    "path": v["path"],
                    "dir": v["dir"],
                    "thumbnail": DEFAULT_THUMBNAIL,
                    "matchedSub": matched_sub,
                    "availableSubtitles": avail
                })

            data = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
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

                vtt = convert_srt_to_vtt(raw) if ext == ".srt" else (raw if raw.startswith("WEBVTT") else "WEBVTT\n\n" + raw)
                data = vtt.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/vtt; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
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
                left = content_length
                while left > 0:
                    chunk = f.read(min(CHUNK_SIZE, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def run_server():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    print("=== TC-Media Server ===")
    print(f"Složka médií : {MEDIA_DIR}")
    print(f"Buffer soubor: {BUFFER_FILE}")
    print(f"Běží na      : http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončuji server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
