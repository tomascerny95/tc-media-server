#!/usr/bin/env python3
"""
TC-Media Server - Media Library & Video.js Player.
- Automated detection of subtitles and audio tracks.
- Direct Play (HTTP 206) for default audio tracks.
- Ultra-fast in-memory HLS streaming for secondary audio tracks (EAC3->AAC):
  Normalized PTS timestamps (avoids PTS gaps when switching mid-movie),
  zero SD card wear (RAM disk via /dev/shm), 100% compatible with Smart TVs & Mobile.
"""
import os
import sys
import re
import json
import time
import shutil
import tempfile
import subprocess
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION ---
HOST = "0.0.0.0"
PORT = 5000
MEDIA_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/dlna")
BUFFER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buffer.html")

# RAM disk (/dev/shm) - eliminates SD card writes completely
HLS_BASE_DIR = "/dev/shm/tc_hls" if os.path.exists("/dev/shm") else os.path.join(tempfile.gettempdir(), "tc_hls")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}
CHUNK_SIZE = 64 * 1024

LANG_MAP = {
    "cze": "Czech", "ces": "Czech", "cs": "Czech",
    "eng": "English", "en": "English",
    "slo": "Slovak", "slk": "Slovak", "sk": "Slovak",
    "ger": "German", "deu": "German", "de": "German",
    "fre": "French", "fra": "French", "fr": "French",
    "spa": "Spanish", "es": "Spanish",
    "ita": "Italian", "it": "Italian",
    "rus": "Russian", "ru": "Russian",
    "jpn": "Japanese", "ja": "Japanese",
    "pol": "Polish", "pl": "Polish",
    "und": "Undefined"
}

mimetypes.init()
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-msvideo", ".avi")
mimetypes.add_type("application/x-mpegURL", ".m3u8")
mimetypes.add_type("video/MP2T", ".ts")
mimetypes.add_type("text/vtt", ".vtt")

FAVICON_BASE64 = (
    "data:image/x-icon;base64,AAABAAYAAAAAAAEAIADqMAAAZgAAAICAAAABACAAKAgBAFAxAABAQAAAAQAgAChCAAB4OQEAMDAAAAEAIACoJQAAoHsBACAgAA"
    "ABACAAqBAAAEihAQAQEAAAAQAgAGgEAADwsQEAiVBORw0KGgoAAAASUhEUgAAAQAAAAEACAYAAABccqhmAAAwsUlEQVR42u2dWXMkyZHf/xGRWVkXzgLQF/qY"
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

active_hls_proc = None

def cleanup_active_hls():
    global active_hls_proc
    if active_hls_proc:
        try:
            active_hls_proc.kill()
            active_hls_proc.wait()
        except Exception:
            pass
        active_hls_proc = None

LIBRARY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TC-Media Server</title>
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
        .video-item { display: inline-flex; flex-direction: column; vertical-align: top; width: 220px; min-height: 235px; margin: 12px; text-align: left; background: #232933; border: 1px solid #3a414c; border-radius: 8px; overflow: hidden; text-decoration: none; color: inherit; transition: transform 0.15s, border-color 0.15s; }
        .video-item:hover { transform: translateY(-3px); border-color: #e54c4c; }
        .video-thumbnail { width: 100%; height: 120px; background: #14171d; display: block; }
        .video-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
        .video-details { padding: 12px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .video-details p { margin: 0 0 10px 0; font-weight: 500; font-size: 0.9rem; word-break: break-all; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .play-link { display: inline-block; text-align: center; border: 1px solid #e54c4c; color: #e54c4c; padding: 6px 14px; border-radius: 4px; text-decoration: none; font-size: 0.85rem; font-weight: 600; margin-top: auto; }
        .video-item:hover .play-link { background: #e54c4c; color: #fff; }
        .loading { text-align: center; color: #888; margin: 30px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>TC-Media Server</h1>
        <form class="url-form">
            <input type="text" name="q" placeholder="Search library...">
            <button type="submit">Search</button>
        </form>
        <div class="video-list"></div>
        <div class="loading">Loading...</div>
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
                            var item = document.createElement('a');
                            item.className = 'video-item';
                            item.href = '/player?video=' + encodeURIComponent(v.path);
                            item.target = '_blank';
                            item.innerHTML = 
                                '<div class="video-thumbnail"><img src="' + v.thumbnail + '"></div>' +
                                '<div class="video-details">' +
                                    '<p title="' + v.title + '">' + v.title + '</p>' +
                                    '<div class="play-link">Play ↗</div>' +
                                '</div>';
                            list.appendChild(item);
                        });
                        page++;
                    }
                    if (data.length < 20) {
                        finished = true;
                        loader.textContent = data.length === 0 && page === 1 ? 'No videos found.' : 'All videos loaded.';
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
    if os.path.exists(BUFFER_FILE):
        try:
            with open(BUFFER_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[!] Error reading buffer.html: {e}")
    return ""

def find_subtitles_in_dir(video_rel_path: str):
    video_full_path = os.path.join(MEDIA_DIR, video_rel_path.lstrip("/\\"))
    folder = os.path.dirname(video_full_path)
    video_base = os.path.splitext(os.path.basename(video_full_path))[0].lower()

    subtitles = []
    if not os.path.isdir(folder):
        return subtitles

    for f in sorted(os.listdir(folder)):
        ext = os.path.splitext(f)[1].lower()
        if ext in SUBTITLE_EXTENSIONS:
            sub_full = os.path.join(folder, f)
            sub_rel = os.path.relpath(sub_full, MEDIA_DIR)
            sub_base = os.path.splitext(f)[0].lower()
            is_matched = (sub_base == video_base)
            subtitles.append({
                "name": f,
                "path": sub_rel,
                "default": is_matched
            })

    if subtitles and not any(s["default"] for s in subtitles):
        subtitles[0]["default"] = True

    return subtitles

def get_audio_tracks(video_rel_path: str):
    if not shutil.which("ffprobe"):
        return []

    video_full_path = os.path.join(MEDIA_DIR, video_rel_path.lstrip("/\\"))
    if not os.path.exists(video_full_path):
        return []

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index:stream_tags=language,title:stream=codec_name",
            "-of", "json",
            video_full_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode != 0:
            return []

        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        tracks = []

        for i, s in enumerate(streams):
            tags = s.get("tags") or {}
            raw_lang = (tags.get("language") or tags.get("LANGUAGE") or "").lower()
            title = tags.get("title") or tags.get("TITLE") or ""
            codec = s.get("codec_name", "")

            lang_label = LANG_MAP.get(raw_lang, raw_lang.upper() if raw_lang else f"Audio {i+1}")
            if title and title.lower() != raw_lang:
                label = f"{lang_label} ({title})"
            else:
                label = lang_label

            if codec:
                label += f" [{codec}]"

            tracks.append({
                "id": str(i),
                "label": label,
                "lang": raw_lang or "und",
                "default": (i == 0)
            })

        return tracks
    except Exception as e:
        print(f"[!] Error detecting audio tracks: {e}")
        return []

def build_player_page(video_path: str) -> str:
    file_name = os.path.basename(video_path) if video_path else "Player"
    stream_url = f"/stream?path={urllib.parse.quote(video_path)}" if video_path else ""

    track_tags = []
    if video_path:
        subs = find_subtitles_in_dir(video_path)
        for s in subs:
            sub_url = f"/subtitle?path={urllib.parse.quote(s['path'])}"
            def_attr = " default" if s["default"] else ""
            label = f"Subtitles: {s['name']}"
            track_tags.append(f'\t\t<track src="{sub_url}" kind="captions" label="{label}"{def_attr} />')

    tracks_html = "\n".join(track_tags)
    audio_tracks = get_audio_tracks(video_path) if video_path else []
    audio_tracks_json = json.dumps(audio_tracks)
    buffer_inject = get_buffer_content()

    html = f"""<head>
\t<title>{file_name} - TC-Media Server</title>
\t<link rel="shortcut icon" href="{FAVICON_BASE64}" />
\t<style>
\t\t#tv-spinner {{
\t\t\tdisplay: none;
\t\t\tposition: absolute;
\t\t\ttop: 50%;
\t\t\tleft: 50%;
\t\t\ttransform: translate(-50%, -50%);
\t\t\tz-index: 1000;
\t\t\tbackground: rgba(0, 0, 0, 0.85);
\t\t\tcolor: white;
\t\t\tpadding: 15px 25px;
\t\t\tborder-radius: 8px;
\t\t\tfont-size: 1.1rem;
\t\t\tfont-family: sans-serif;
\t\t\ttext-align: center;
\t\t\tborder: 1px solid #555;
\t\t}}
\t</style>
</head>
{buffer_inject}<body>
\t<div id="tv-spinner">Starting stream...</div>
\t<video id="videoPlayer" class="video-js vjs-big-play-centered" controls preload="auto">
\t\t<source src="{stream_url}">
{tracks_html}
\t\t<p class="vjs-no-js">To view this video please enable JavaScript.</p>
\t</video>
\t<script>
\t\tvar audioTracksData = {audio_tracks_json};
\t\tvar currentAudioId = "0";
\t\tvar basePath = "{urllib.parse.quote(video_path)}";
\t\tvar spinner = document.getElementById('tv-spinner');

\t\tvar player = videojs('videoPlayer', {{
\t\t\tcontrols: true,
\t\t\tcontrolBar: {{
\t\t\t\taudioTrackButton: true
\t\t\t}},
\t\t\tplugins: {{
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
\t\t\t\t\t\tdisabled: false
\t\t\t\t\t}}
\t\t\t\t}}
\t\t\t}}
\t\t}}, function() {{
\t\t\tvar p = this;

\t\t\tfunction loadHlsStream(startTime) {{
\t\t\t\tspinner.style.display = 'block';
\t\t\t\tfetch('/api/start_hls?path=' + basePath + '&track=' + currentAudioId + '&t=' + Math.floor(startTime))
\t\t\t\t\t.then(function(res) {{ return res.json(); }})
\t\t\t\t\t.then(function(data) {{
\t\t\t\t\t\tspinner.style.display = 'none';
\t\t\t\t\t\tif (data.status === 'ready') {{
\t\t\t\t\t\t\tp.src({{ src: data.url + '?v=' + Date.now(), type: 'application/x-mpegURL' }});
\t\t\t\t\t\t\tp.play().catch(function(e){{}});
\t\t\t\t\t\t}} else {{
\t\t\t\t\t\t\talert('Stream error: ' + (data.message || 'Unknown error'));
\t\t\t\t\t\t}}
\t\t\t\t\t}})
\t\t\t\t\t.catch(function(err) {{
\t\t\t\t\t\tspinner.style.display = 'none';
\t\t\t\t\t\talert('Error loading stream: ' + err);
\t\t\t\t\t}});
\t\t\t}}

\t\t\tif (audioTracksData.length > 1) {{
\t\t\t\taudioTracksData.forEach(function(t) {{
\t\t\t\t\tp.audioTracks().addTrack(new videojs.AudioTrack({{
\t\t\t\t\t\tid: t.id,
\t\t\t\t\t\tkind: 'alternative',
\t\t\t\t\t\tlabel: t.label,
\t\t\t\t\t\tlanguage: t.lang,
\t\t\t\t\t\tenabled: t.default
\t\t\t\t\t}}));
\t\t\t\t}});

\t\t\t\tp.audioTracks().addEventListener('change', function() {{
\t\t\t\t\tfor (var i = 0; i < p.audioTracks().length; i++) {{
\t\t\t\t\t\tvar tr = p.audioTracks()[i];
\t\t\t\t\t\tif (tr.enabled && tr.id !== currentAudioId) {{
\t\t\t\t\t\t\tcurrentAudioId = tr.id;
\t\t\t\t\t\t\tvar savedTime = p.currentTime();
\t\t\t\t\t\t\tvar wasPaused = p.paused();

\t\t\t\t\t\t\tif (tr.id === "0") {{
\t\t\t\t\t\t\t\t// Zpět na výchozí stopu (Čeština) - Direct Play
\t\t\t\t\t\t\t\tp.src({{ src: '/stream?path=' + basePath }});
\t\t\t\t\t\t\t\tp.one('loadedmetadata', function() {{
\t\t\t\t\t\t\t\t\tp.currentTime(savedTime);
\t\t\t\t\t\t\t\t\tif (!wasPaused) p.play();
\t\t\t\t\t\t\t\t}});
\t\t\t\t\t\t\t}} else {{
\t\t\t\t\t\t\t\t// Přepnutí na angličtinu s přesným časem bez PTS chyb
\t\t\t\t\t\t\t\tloadHlsStream(savedTime);
\t\t\t\t\t\t\t}}
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\t}}
\t\t\t\t\t}}
\t\t\t\t}});
\t\t\t}}
\t\t}});
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
            html = build_player_page(v_path)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/videos":
            all_videos = []
            for root, _, files in os.walk(MEDIA_DIR):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, MEDIA_DIR)
                    rel_dir = os.path.relpath(root, MEDIA_DIR)
                    if rel_dir == ".":
                        rel_dir = ""
                    if ext in VIDEO_EXTENSIONS:
                        all_videos.append({"name": f, "path": rel_path, "dir": rel_dir})

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
            result = [
                {
                    "title": v["name"],
                    "path": v["path"],
                    "dir": v["dir"],
                    "thumbnail": DEFAULT_THUMBNAIL
                }
                for v in paged
            ]

            data = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/start_hls":
            global active_hls_proc
            rel_path = query.get("path", [""])[0]
            track_idx = query.get("track", ["1"])[0]
            start_t = query.get("t", ["0"])[0]

            if not self.is_safe_path(rel_path):
                self.send_error(404, "Video not found")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))

            cleanup_active_hls()

            session_dir = os.path.join(HLS_BASE_DIR, "session")
            shutil.rmtree(session_dir, ignore_errors=True)
            os.makedirs(session_dir, exist_ok=True)

            m3u8_file = os.path.join(session_dir, "stream.m3u8")

            cmd = ["ffmpeg", "-v", "error", "-y"]
            try:
                t_val = float(start_t)
                if t_val > 0:
                    cmd.extend(["-ss", str(t_val)])
            except ValueError:
                pass

            # ZÁSADNÍ PARAMETRY:
            # -avoid_negative_ts make_zero srovná časovou osu obrazu i zvuku na nulu (žádný 50minutový rozestup)
            # discont_start přikáže přehrávači okamžitý start
            cmd.extend([
                "-i", full_path,
                "-map", "0:v:0",
                "-map", f"0:a:{track_idx}",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                "-avoid_negative_ts", "make_zero",
                "-f", "hls",
                "-hls_time", "3",
                "-hls_list_size", "8",
                "-hls_flags", "delete_segments+temp_file+discont_start",
                "-hls_segment_filename", "seg_%03d.ts",
                "stream.m3u8"
            ])

            print(f"[+] Starting in-memory HLS stream (RAM) for track #{track_idx} at {start_t}s...")
            active_hls_proc = subprocess.Popen(
                cmd,
                cwd=session_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            is_ready = False
            for _ in range(300):
                if active_hls_proc.poll() is not None:
                    print("[!] FFmpeg process terminated early.")
                    break

                if os.path.exists(m3u8_file) and os.path.getsize(m3u8_file) > 20:
                    ts_files = [f for f in os.listdir(session_dir) if f.endswith(".ts") and not f.endswith(".tmp")]
                    if len(ts_files) >= 1:
                        first_ts = os.path.join(session_dir, ts_files[0])
                        if os.path.getsize(first_ts) > 100 * 1024:
                            is_ready = True
                            break
                time.sleep(0.1)

            if is_ready:
                resp = json.dumps({"status": "ready", "url": "/hls/session/stream.m3u8"}).encode("utf-8")
            else:
                resp = json.dumps({"status": "error", "message": "Timeout generating stream"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        elif path.startswith("/hls/"):
            rel_hls = path[len("/hls/"):].lstrip("/\\")
            target_file = os.path.abspath(os.path.join(HLS_BASE_DIR, rel_hls))

            if not target_file.startswith(os.path.abspath(HLS_BASE_DIR)) or not os.path.exists(target_file):
                self.send_error(404, "Segment not found")
                return

            if target_file.endswith(".tmp"):
                self.send_error(404, "Segment still writing")
                return

            if target_file.endswith(".m3u8"):
                content_type = "application/x-mpegURL"
            elif target_file.endswith(".ts"):
                content_type = "video/MP2T"
            else:
                content_type = "application/octet-stream"

            try:
                with open(target_file, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
            return

        elif path == "/subtitle":
            rel_path = query.get("path", [""])[0]
            if not self.is_safe_path(rel_path):
                self.send_error(404, "Subtitles not found")
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
            self.send_error(404, "File not found")
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
            self.send_header("Access-Control-Allow-Origin", "*")
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
        self.send_header("Access-Control-Allow-Origin", "*")
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
    shutil.rmtree(HLS_BASE_DIR, ignore_errors=True)
    os.makedirs(HLS_BASE_DIR, exist_ok=True)
    print("=== TC-Media Server ===")
    print(f"Media directory : {MEDIA_DIR}")
    print(f"HLS memory path : {HLS_BASE_DIR} (RAM)")
    print(f"Running at      : http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        cleanup_active_hls()
        shutil.rmtree(HLS_BASE_DIR, ignore_errors=True)
        server.server_close()

if __name__ == "__main__":
    run_server()
