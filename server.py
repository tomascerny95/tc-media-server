#!/usr/bin/env python3
"""
TC-Media Server - Media Library & Clean Video.js Player.
- Clean Video.js integration via pluginBuffer.html (no external plugin deps).
- MRU video tracking via 'urlFolder' (recently watched videos bumped to the top).
- Mid-video thumbnail generation on-demand via ffmpeg into 'imageFolder'.
- Native touch gestures (double-tap seek + bubbles), PC hotkeys, and Smart TV remote.
- Video queue mode with automatic progression.
- Resume playback modal with saved position in localStorage.
- Real-time on-the-fly audio transcoding (EAC3/AC3 to AAC) via ffmpeg + Web Audio API.
"""
import os
import sys
import re
import json
import time
import shutil
import hashlib
import threading
import subprocess
import mimetypes
import urllib.parse
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# --- KONFIGURACE A CESTY ---
HOST = "0.0.0.0"
PORT = 5000
MEDIA_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/dlna")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUFFER_FILE = os.path.join(BASE_DIR, "pluginBuffer.html")
FOLDER_URLS = os.path.join(BASE_DIR, "urlFolder")
FOLDER_IMAGES = os.path.join(BASE_DIR, "imageFolder")

for d in [MEDIA_DIR, FOLDER_URLS, FOLDER_IMAGES]:
    os.makedirs(d, exist_ok=True)

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
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("text/vtt", ".vtt")
mimetypes.add_type("image/jpeg", ".jpg")

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

THUMB_LOCK = threading.Lock()

# ==============================================================================
# POMOCNÉ FUNKCE: ID, HISTORIE V URLFOLDER, NÁHLEDY V IMAGEFOLDER
# ==============================================================================
def get_video_id(rel_path: str) -> str:
    """Vytvoří bezpečný MD5 hash z relativní cesty videa."""
    return hashlib.md5(rel_path.strip("/\\").encode("utf-8")).hexdigest()

def bump_video_to_top(rel_path: str):
    """Uloží nebo aktualizuje záznam o přehrání videa do složky urlFolder."""
    vid_id = get_video_id(rel_path)
    now_ts = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_name = re.sub(r'[\\/*?:"<>|]', "", os.path.basename(rel_path))[:40]
    new_filename = f"{now_ts}_{vid_id}_{clean_name}.txt"
    new_path = os.path.join(FOLDER_URLS, new_filename)

    try:
        # Odstraníme starší záznamy pro toto video z urlFolder
        for f in os.listdir(FOLDER_URLS):
            if f.endswith(".txt") and f"_{vid_id}_" in f:
                try:
                    os.remove(os.path.join(FOLDER_URLS, f))
                except Exception:
                    pass

        with open(new_path, "w", encoding="utf-8") as fp:
            fp.write(rel_path.strip("/\\") + "\n")
    except Exception as e:
        print(f"[!] Chyba zapisu do urlFolder: {e}")

def get_recent_paths_order() -> list:
    """Vrátí seznam relativních cest seřazených od nejnověji zhlédnutého."""
    if not os.path.exists(FOLDER_URLS):
        return []
    
    files = [f for f in os.listdir(FOLDER_URLS) if f.endswith(".txt")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(FOLDER_URLS, x)), reverse=True)
    
    recent_paths = []
    seen = set()
    for fname in files:
        fpath = os.path.join(FOLDER_URLS, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                for line in fp:
                    p = line.strip()
                    if p and p not in seen:
                        recent_paths.append(p)
                        seen.add(p)
        except Exception:
            pass
    return recent_paths

def get_video_duration_seconds(full_path: str) -> float:
    """Zjistí délku videa v sekundách pomocí ffprobe."""
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            full_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0

def generate_midpoint_thumbnail(video_rel_path: str) -> str:
    """Vytvoří snímek přesně uprostřed videa a uloží jej do imageFolder."""
    vid_id = get_video_id(video_rel_path)
    thumb_path = os.path.join(FOLDER_IMAGES, f"{vid_id}.jpg")

    if os.path.exists(thumb_path):
        return thumb_path

    if not shutil.which("ffmpeg"):
        return ""

    full_video_path = os.path.join(MEDIA_DIR, video_rel_path.lstrip("/\\"))
    if not os.path.exists(full_video_path):
        return ""

    with THUMB_LOCK:
        if os.path.exists(thumb_path):
            return thumb_path

        duration = get_video_duration_seconds(full_video_path)
        seek_sec = max(5.0, duration / 2.0) if duration > 10 else 2.0

        tmp_thumb = thumb_path + ".tmp.jpg"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(seek_sec),
            "-i", full_video_path,
            "-vframes", "1",
            "-q:v", "3",
            "-vf", "scale=360:-1",
            tmp_thumb
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            if res.returncode == 0 and os.path.exists(tmp_thumb) and os.path.getsize(tmp_thumb) > 100:
                os.replace(tmp_thumb, thumb_path)
                return thumb_path
        except Exception as e:
            print(f"[!] Chyba generovani nahledu pro {video_rel_path}: {e}")
        finally:
            if os.path.exists(tmp_thumb):
                try:
                    os.remove(tmp_thumb)
                except Exception:
                    pass

    return ""

def get_buffer_content() -> str:
    """Načte pluginBuffer.html (vygenerovaný skriptem plugin_updater_gui.py)."""
    search_paths = [
        BUFFER_FILE,
        os.path.join(BASE_DIR, "buffer.html")
    ]
    for p in search_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                print(f"[!] Chyba čtení {p}: {e}")
    return ""

def format_sub_label(filename: str) -> str:
    base = os.path.splitext(filename)[0]
    tokens = re.split(r'[-_. ]+', base.lower())
    for t in tokens:
        if t in LANG_MAP:
            return f"{LANG_MAP[t]} ({t})"
    return filename

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
            is_matched = (sub_base == video_base or sub_base.startswith(video_base))
            subtitles.append({
                "name": format_sub_label(f),
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

def delete_video_and_associated_files(rel_path: str):
    """Smaže video, související titulky, náhled z imageFolder i záznam z urlFolder."""
    abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
    vid_id = get_video_id(rel_path)

    # 1. Smazání z urlFolder
    if os.path.exists(FOLDER_URLS):
        for f in os.listdir(FOLDER_URLS):
            if f"_{vid_id}_" in f:
                try:
                    os.remove(os.path.join(FOLDER_URLS, f))
                except Exception:
                    pass

    # 2. Smazání z imageFolder
    img_thumb = os.path.join(FOLDER_IMAGES, f"{vid_id}.jpg")
    if os.path.exists(img_thumb):
        try:
            os.remove(img_thumb)
        except Exception:
            pass

    # 3. Smazání videa
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
            print(f"[SMAZÁNO] Video: {abs_path}")
        except Exception as e:
            print(f"[!] Nelze smazat video {abs_path}: {e}")

    # 4. Smazání souvisejících titulků
    folder = os.path.dirname(abs_path)
    base_name = os.path.splitext(os.path.basename(abs_path))[0].lower()
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                f_base = os.path.splitext(f)[0].lower()
                if f_base == base_name or f_base.startswith(base_name):
                    try:
                        os.remove(os.path.join(folder, f))
                        print(f"[SMAZÁNO] Související titulky: {f}")
                    except Exception as e:
                        print(f"[!] Nelze smazat titulky {f}: {e}")

# ==============================================================================
# HTML KNIHOVNY VIDEÍ
# ==============================================================================
LIBRARY_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TC-Media Server</title>
    <link rel="shortcut icon" href="__FAVICON__">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1e242c; color: #f0f0f0; margin: 0; padding: 20px 0; }
        .container { width: 92%; max-width: 1200px; margin: 0 auto; background: #2a313c; padding: 25px 30px; border-radius: 8px; border: 1px solid #3a414c; }
        h1 { text-align: center; color: #fff; margin-bottom: 25px; font-size: 2.6rem; font-weight: 700; }
        .url-form { display: flex; justify-content: center; margin-bottom: 12px; gap: 10px; }
        .url-form input { width: 100%; max-width: 480px; padding: 12px 18px; border: 1px solid #3a414c; border-radius: 6px; background: #1e242c; color: #fff; font-size: 1rem; }
        .actions-bar { display: flex; justify-content: center; margin-bottom: 25px; }
        .btn-queue { padding: 10px 22px; background: #2a313c; color: #fff; border: 2px solid #e54c4c; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 1rem; transition: all 0.2s; }
        .btn-queue:hover { background: #e54c4c; }
        .btn-queue.active { background: #2e7d32; border-color: #4caf50; }
        .video-list { text-align: center; }
        .video-item { position: relative; display: inline-flex; flex-direction: column; vertical-align: top; width: 220px; height: 250px; margin: 12px; text-align: left; background: #232933; border: 1px solid #3a414c; border-radius: 8px; overflow: hidden; color: inherit; transition: border-color 0.2s, box-shadow 0.2s; }
        .video-item.in-queue { border-color: #e54c4c; box-shadow: 0 0 12px rgba(229,76,76,0.6); }
        .queue-badge { display: none; position: absolute; top: 8px; left: 8px; background: #e54c4c; color: #fff; width: 30px; height: 30px; border-radius: 50%; align-items: center; justify-content: center; font-weight: bold; font-size: 1rem; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.8); }
        .video-item.in-queue .queue-badge { display: flex; }
        .video-thumbnail { width: 100%; height: 120px; background: #14171d; display: block; cursor: pointer; }
        .video-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
        .video-details { padding: 12px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .video-details p { margin: 0 0 10px 0; font-weight: 500; font-size: 0.9rem; word-break: break-all; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .video-links { margin-top: auto; border-top: 1px solid #3a414c; padding-top: 10px; display: flex; gap: 8px; }
        .btn-play, .btn-del { flex: 1; text-align: center; padding: 6px 10px; border-radius: 4px; font-size: 0.85rem; font-weight: 600; cursor: pointer; text-decoration: none; border: 1px solid #e54c4c; background: transparent; transition: all 0.2s; }
        .btn-play { color: #e54c4c; }
        .btn-play:hover { background: #e54c4c; color: #fff; }
        .btn-del { border-color: #ff5252; color: #ff5252; }
        .btn-del:hover { background: #ff5252; color: #fff; }
        .loading { text-align: center; color: #888; margin: 30px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>TC-Media Server</h1>
        <form class="url-form" id="searchForm">
            <input type="text" id="searchInput" placeholder="Hledat v knihovně...">
        </form>
        <div class="actions-bar">
            <button type="button" id="btnQueue" class="btn-queue" onclick="toggleQueueMode()">Vytvořit frontu</button>
        </div>
        <div class="video-list"></div>
        <div class="loading">Načítám videa...</div>
    </div>
    <script>
        var page = 1, query = '', loading = false, finished = false;
        var list = document.querySelector('.video-list');
        var loader = document.querySelector('.loading');
        var searchInput = document.getElementById('searchInput');
        var queueMode = false;
        var queueList = [];
        var defaultPlaceholder = '__DEFAULT_THUMB__';

        function updateQueueButtonText() {
            var btn = document.getElementById("btnQueue");
            if (!queueMode) {
                btn.className = "btn-queue";
                btn.textContent = "Vytvořit frontu";
            } else {
                btn.className = "btn-queue active";
                if (queueList.length === 0) {
                    btn.textContent = "Klikněte na videa pro přidání (Zrušit)";
                } else {
                    btn.textContent = "Konec a spustit frontu (" + queueList.length + ")";
                }
            }
        }

        function toggleQueueMode() {
            if (!queueMode) {
                queueMode = true;
                queueList = [];
                updateQueueButtonText();
                renderQueueBadges();
            } else {
                if (queueList.length > 0) {
                    sessionStorage.setItem("videoQueue", JSON.stringify(queueList.slice(1)));
                    window.location.href = '/player?video=' + encodeURIComponent(queueList[0]);
                } else {
                    queueMode = false;
                    updateQueueButtonText();
                    renderQueueBadges();
                }
            }
        }

        function handleVideoCardClick(e, path) {
            if (!queueMode) return;
            e.preventDefault();
            e.stopPropagation();

            var idx = queueList.indexOf(path);
            if (idx > -1) {
                queueList.splice(idx, 1);
            } else {
                queueList.push(path);
            }
            updateQueueButtonText();
            renderQueueBadges();
        }

        function renderQueueBadges() {
            var items = document.querySelectorAll(".video-item");
            for (var i = 0; i < items.length; i++) {
                var el = items[i];
                var path = el.getAttribute("data-path");
                var badge = el.querySelector(".queue-badge");
                var idx = queueList.indexOf(path);
                if (queueMode && idx > -1) {
                    el.classList.add("in-queue");
                    badge.textContent = (idx + 1).toString();
                } else {
                    el.classList.remove("in-queue");
                    badge.textContent = "";
                }
            }
        }

        function deleteVideo(path, itemElement) {
            if (!confirm("Opravdu chcete smazat toto video a související titulky z disku?")) return;
            fetch('/api/delete-video', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === 'ok') {
                    if (itemElement) itemElement.remove();
                    var qIdx = queueList.indexOf(path);
                    if (qIdx > -1) {
                        queueList.splice(qIdx, 1);
                        updateQueueButtonText();
                        renderQueueBadges();
                    }
                } else {
                    alert("Chyba při mazání: " + (data.error || "Neznámá chyba"));
                }
            })
            .catch(function(err) { alert("Chyba komunikace se serverem."); });
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function loadVideos() {
            if (loading || finished) return;
            loading = true;
            loader.style.display = 'block';
            fetch('/api/videos?page=' + page + '&q=' + encodeURIComponent(query))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data && data.length > 0) {
                        data.forEach(function(v) {
                            var item = document.createElement('div');
                            item.className = 'video-item';
                            item.setAttribute('data-path', v.path);

                            item.addEventListener('click', function(e) {
                                handleVideoCardClick(e, v.path);
                            });

                            var playUrl = '/player?video=' + encodeURIComponent(v.path);
                            var safeTitle = escapeHtml(v.title);

                            item.innerHTML = 
                                '<div class="queue-badge"></div>' +
                                '<a class="video-thumbnail" href="' + playUrl + '">' +
                                    '<img src="' + v.thumbnail + '" onerror="this.onerror=null;this.src=defaultPlaceholder;" loading="lazy">' +
                                '</a>' +
                                '<div class="video-details">' +
                                    '<p title="' + safeTitle + '">' + safeTitle + '</p>' +
                                    '<div class="video-links">' +
                                        '<a class="btn-play" href="' + playUrl + '">Přehrát</a>' +
                                        '<button type="button" class="btn-del">Smazat</button>' +
                                    '</div>' +
                                '</div>';

                            var thumbLink = item.querySelector('.video-thumbnail');
                            thumbLink.addEventListener('click', function(e) {
                                if (queueMode) { e.preventDefault(); }
                            });

                            var playLink = item.querySelector('.btn-play');
                            playLink.addEventListener('click', function(e) {
                                if (queueMode) {
                                    e.preventDefault();
                                    handleVideoCardClick(e, v.path);
                                }
                            });

                            var delBtn = item.querySelector('.btn-del');
                            delBtn.addEventListener('click', function(e) {
                                e.stopPropagation();
                                deleteVideo(v.path, item);
                            });

                            list.appendChild(item);
                        });
                        page++;
                    }

                    if (!data || data.length < 20) {
                        finished = true;
                        loader.textContent = (page === 1 && (!data || data.length === 0)) ? 'Žádná videa nenalezena v knihovně.' : 'Všechna videa načtena.';
                    } else {
                        loader.style.display = 'none';
                    }
                    loading = false;
                    renderQueueBadges();
                })
                .catch(function(err) {
                    console.error("Chyba při načítání videí:", err);
                    loader.textContent = 'Chyba při načítání videí ze serveru.';
                    loading = false;
                });
        }

        var searchTimeout = null;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {
                query = searchInput.value.trim();
                list.innerHTML = '';
                page = 1;
                finished = false;
                loadVideos();
            }, 250);
        });

        document.getElementById('searchForm').addEventListener('submit', function(e) {
            e.preventDefault();
        });

        window.addEventListener('scroll', function() {
            if (window.innerHeight + window.scrollY >= document.documentElement.offsetHeight - 250) {
                loadVideos();
            }
        });

        loadVideos();
    </script>
</body>
</html>
"""

# ==============================================================================
# HTML STRÁNKA PŘEHRÁVAČE S NATIVNÍM ČISTÝM VIDEO.JS
# ==============================================================================
def build_player_page(video_path: str) -> str:
    file_name = os.path.basename(video_path) if video_path else "Přehrávač"
    stream_url = f"/stream?path={urllib.parse.quote(video_path)}" if video_path else ""

    track_tags = []
    if video_path:
        subs = find_subtitles_in_dir(video_path)
        for s in subs:
            sub_url = f"/subtitle?path={urllib.parse.quote(s['path'])}"
            def_attr = " default" if s["default"] else ""
            label = s['name']
            track_tags.append(f'\t\t<track src="{sub_url}" kind="subtitles" label="{label}"{def_attr} />')

    tracks_html = "\n".join(track_tags)
    audio_tracks = get_audio_tracks(video_path) if video_path else []
    audio_tracks_json = json.dumps(audio_tracks)
    buffer_inject = get_buffer_content()

    html = f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>{file_name} - TC-Media Server</title>
    <link rel="shortcut icon" href="{FAVICON_BASE64}" />
    <style>
        html, body {{
            margin: 0; padding: 0; width: 100vw; height: 100vh; height: 100dvh;
            background-color: black; color: #f0f0f0; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            touch-action: manipulation;
        }}
        #titleLabel {{
            position: fixed; top: 18px; left: 18px; z-index: 999998;
            color: #ffffff; font-size: 1.05rem; font-weight: 600;
            text-shadow: 0 2px 6px rgba(0,0,0,0.95); white-space: nowrap;
            overflow: hidden; text-overflow: ellipsis; max-width: calc(100vw - 190px);
            pointer-events: none; transition: opacity 0.3s ease;
        }}
        #btnBack {{
            position: fixed; top: 14px; right: 16px; z-index: 999999;
            background: rgba(30, 36, 44, 0.9); color: #ffffff;
            padding: 9px 16px; border-radius: 6px; font-weight: bold; font-size: 0.95rem;
            border: 1px solid #4a5462; box-shadow: 0 4px 12px rgba(0,0,0,0.6);
            cursor: pointer; touch-action: manipulation;
            transition: opacity 0.3s ease, background 0.2s ease;
            -webkit-tap-highlight-color: transparent;
        }}
        #btnBack:hover {{ background: #e54c4c; border-color: #e54c4c; }}
        #videoPlayer {{ position: absolute; top: 0; left: 0; width: 100% !important; height: 100% !important; }}
        .video-js .vjs-control-bar {{ font-size: 15px !important; height: 46px !important; }}
        body.tv-mode .video-js .vjs-control-bar {{ font-size: 18px !important; height: 52px !important; }}
        .video-js .vjs-progress-control .vjs-slider {{ height: 6px !important; }}
        body.tv-mode .video-js .vjs-progress-control .vjs-slider {{ height: 8px !important; }}
        .video-js .vjs-menu-button-popup .vjs-menu .vjs-menu-content {{ font-size: 1.15em !important; bottom: 2.2em !important; }}
        .video-js .vjs-menu-content li.vjs-menu-item {{ padding: 10px 15px !important; font-size: 15px !important; cursor: pointer; }}
        body.tv-mode .video-js .vjs-menu-content li.vjs-menu-item {{ padding: 14px 20px !important; font-size: 18px !important; }}
        .seek-bubble {{
            position: fixed; top: 50%; transform: translateY(-50%) scale(0.8);
            background: rgba(0, 0, 0, 0.75); color: #ffffff; padding: 16px 26px;
            border-radius: 50px; font-size: 1.3rem; font-weight: bold; pointer-events: none;
            z-index: 99999; opacity: 0; transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            border: 1px solid rgba(255,255,255,0.2); box-shadow: 0 4px 20px rgba(0,0,0,0.8);
        }}
        .seek-left {{ left: 12%; }}
        .seek-right {{ right: 12%; }}
        .seek-bubble.show {{ opacity: 1; transform: translateY(-50%) scale(1.1); }}
        #resumeModal {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.85); display: none; flex-direction: column;
            justify-content: center; align-items: center; z-index: 1000000;
        }}
        .modal-box {{
            background: #1e242c; padding: 30px 25px; border-radius: 12px;
            border: 1px solid #3a414c; width: 85%; max-width: 500px; text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }}
        .btn-resume {{
            display: inline-block; margin: 10px; padding: 14px 26px;
            border-radius: 8px; font-size: 1.15rem; font-weight: bold;
            cursor: pointer; transition: all 0.2s; color: #ffffff; border: none;
        }}
        .btn-resume-continue {{ background: #2e7d32; border: 2px solid #4caf50; }}
        .btn-resume-continue:hover {{ background: #388e3c; transform: scale(1.05); }}
        .btn-resume-restart {{ background: #37474f; border: 2px solid #78909c; }}
        .btn-resume-restart:hover {{ background: #455a64; transform: scale(1.05); }}
    </style>
{buffer_inject}
</head>
<body>
    <span id="titleLabel">{file_name}</span>
    <button id="btnBack">Zpět na seznam</button>

    <div id="bubbleLeft" class="seek-bubble seek-left">-10s</div>
    <div id="bubbleRight" class="seek-bubble seek-right">+10s</div>

    <div id="resumeModal">
        <div class="modal-box">
            <h2 style="margin-top: 0; color: #ffffff;">{file_name}</h2>
            <p style="color: #cfd8dc; font-size: 1.15rem; margin-bottom: 8px;">Máte rozkoukané video.</p>
            <p id="resumeTimeDesc" style="color: #ffb74d; font-size: 1.3rem; font-weight: bold; margin: 10px 0 25px 0;"></p>
            <div>
                <button id="btnResumeYes" class="btn-resume btn-resume-continue">Pokračovat ve sledování</button>
                <button id="btnResumeNo" class="btn-resume btn-resume-restart">Pustit od začátku</button>
            </div>
        </div>
    </div>

    <video id="videoPlayer" class="video-js vjs-big-play-centered" controls preload="auto" crossorigin="anonymous">
        <source src="{stream_url}" type="video/mp4">
{tracks_html}
        <p class="vjs-no-js">Povolte JavaScript pro přehrávání videa.</p>
    </video>
    <audio id="altAudio" preload="auto" style="display:none;"></audio>

    <script>
        if (/tv|smarttv|vewd|opera tv|tizen|web0s|webos|viera|bravia|nettv|hbbtv/i.test(navigator.userAgent)) {{
            document.body.classList.add("tv-mode");
        }}

        var audioTracksData = {audio_tracks_json};
        var currentAudioId = "0";
        var basePath = "{urllib.parse.quote(video_path)}";
        var resumeKey = "tc_resume_" + basePath;

        var altAudio = document.getElementById('altAudio');
        var isAltAudio = false;
        var altAudioBaseTime = 0;
        var isProgrammaticSeek = false;
        var audioCtx = null;
        var videoGain = null;

        var btnBack = document.getElementById("btnBack");
        var titleLabel = document.getElementById("titleLabel");
        var bubbleLeft = document.getElementById("bubbleLeft");
        var bubbleRight = document.getElementById("bubbleRight");
        var resumeModal = document.getElementById("resumeModal");
        var btnResumeYes = document.getElementById("btnResumeYes");
        var btnResumeNo = document.getElementById("btnResumeNo");
        var resumeTimeDesc = document.getElementById("resumeTimeDesc");

        function formatSec(sec) {{
            var s = Math.floor(sec);
            var hrs = Math.floor(s / 3600);
            var mins = Math.floor((s % 3600) / 60);
            var secs = s % 60;
            var pM = (mins < 10 && hrs > 0 ? "0" : "") + mins;
            var pS = (secs < 10 ? "0" : "") + secs;
            return hrs > 0 ? (hrs + ":" + pM + ":" + pS) : (mins + ":" + pS);
        }}

        function goBack() {{
            sessionStorage.removeItem("videoQueue");
            window.location.href = "/";
        }}
        btnBack.addEventListener("click", goBack);
        btnBack.addEventListener("touchend", function(e) {{ e.preventDefault(); goBack(); }});

        function setHeaderVisible(visible) {{
            var op = visible ? "1" : "0";
            var pe = visible ? "auto" : "none";
            btnBack.style.opacity = op;
            btnBack.style.pointerEvents = pe;
            titleLabel.style.opacity = op;
        }}

        function triggerSeekBubble(side) {{
            var target = side === "left" ? bubbleLeft : bubbleRight;
            target.classList.add("show");
            setTimeout(function() {{ target.classList.remove("show"); }}, 600);
        }}

        function initTouchGestures(p) {{
            var el = p.el();
            var lastTap = 0;
            var singleTapTimer = null;
            var wasActiveOnTouch = false;

            el.addEventListener("touchstart", function(e) {{
                if (e.target.closest && (e.target.closest(".vjs-control-bar") || e.target.closest("#btnBack"))) return;
                wasActiveOnTouch = p.userActive();
            }}, {{ passive: true }});

            el.addEventListener("touchend", function(e) {{
                if (e.target.closest && (e.target.closest(".vjs-control-bar") || e.target.closest("#btnBack"))) return;

                var now = Date.now();
                var diff = now - lastTap;
                var touch = e.changedTouches[0];
                var rect = el.getBoundingClientRect();
                var x = touch.clientX - rect.left;

                if (diff < 320 && diff > 50) {{
                    clearTimeout(singleTapTimer);
                    if (x < rect.width * 0.45) {{
                        p.currentTime(Math.max(0, p.currentTime() - 10));
                        triggerSeekBubble("left");
                    }} else if (x > rect.width * 0.55) {{
                        p.currentTime(Math.min(p.duration() || 0, p.currentTime() + 10));
                        triggerSeekBubble("right");
                    }}
                    lastTap = 0;
                }} else {{
                    lastTap = now;
                    singleTapTimer = setTimeout(function() {{
                        p.userActive(!wasActiveOnTouch);
                    }}, 280);
                }}
            }});
        }}

        function initPcHotkeys(p) {{
            if (/tv|smarttv|vewd|opera tv|tizen|web0s|webos|viera|bravia|nettv|hbbtv/i.test(navigator.userAgent)) return;

            window.addEventListener("keydown", function(e) {{
                if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
                if (resumeModal.style.display === "flex") return;

                var code = e.keyCode || e.which;
                var key = e.key;

                if (code === 32 || key === " " || code === 75 || key === "k" || key === "K") {{
                    e.preventDefault();
                    if (p.paused()) {{ p.play(); }} else {{ p.pause(); }}
                    p.userActive(true);
                }} else if (code === 37 || key === "ArrowLeft" || code === 74 || key === "j" || key === "J") {{
                    e.preventDefault();
                    p.currentTime(Math.max(0, p.currentTime() - 10));
                    triggerSeekBubble("left");
                    p.userActive(true);
                }} else if (code === 39 || key === "ArrowRight" || code === 76 || key === "l" || key === "L") {{
                    e.preventDefault();
                    p.currentTime(Math.min(p.duration() || 0, p.currentTime() + 10));
                    triggerSeekBubble("right");
                    p.userActive(true);
                }} else if (code === 38 || key === "ArrowUp") {{
                    e.preventDefault();
                    p.volume(Math.min(1, p.volume() + 0.1));
                    p.userActive(true);
                }} else if (code === 40 || key === "ArrowDown") {{
                    e.preventDefault();
                    p.volume(Math.max(0, p.volume() - 0.1));
                    p.userActive(true);
                }} else if (code === 70 || key === "f" || key === "F") {{
                    e.preventDefault();
                    if (p.isFullscreen()) {{ p.exitFullscreen(); }} else {{ p.requestFullscreen(); }}
                }} else if (code === 77 || key === "m" || key === "M") {{
                    e.preventDefault();
                    p.muted(!p.muted());
                    p.userActive(true);
                }}
            }});
        }}

        function initTvRemote(p) {{
            try {{
                if (window.tizen && tizen.tvinputdevice) {{
                    var tvKeys = ["MediaPlayPause", "MediaPlay", "MediaPause", "MediaFastForward", "MediaRewind", "MediaStop"];
                    tvKeys.forEach(function(k) {{ try {{ tizen.tvinputdevice.registerKey(k); }} catch(e) {{}} }});
                }}
            }} catch(e) {{}}

            window.addEventListener("keydown", function(e) {{
                if (resumeModal.style.display === "flex") return;
                var code = e.keyCode || e.which;
                var key = e.key || "";

                if (code === 415 || code === 19 || code === 179 || code === 10252 ||
                    key === "MediaPlayPause" || key === "MediaPlay" || key === "MediaPause" || key === "Play" || key === "Pause") {{
                    e.preventDefault();
                    if (p.paused()) {{ p.play(); }} else {{ p.pause(); }}
                    p.userActive(true);
                }} else if (code === 417 || code === 228 || code === 10233 || code === 176 ||
                         key === "MediaFastForward" || key === "FastForward" || key === "MediaTrackNext") {{
                    e.preventDefault();
                    p.currentTime(Math.min(p.duration() || 0, p.currentTime() + 10));
                    triggerSeekBubble("right");
                    p.userActive(true);
                }} else if (code === 412 || code === 227 || code === 10232 || code === 177 ||
                         key === "MediaRewind" || key === "Rewind" || key === "MediaTrackPrevious") {{
                    e.preventDefault();
                    p.currentTime(Math.max(0, p.currentTime() - 10));
                    triggerSeekBubble("left");
                    p.userActive(true);
                }} else if (code === 413 || code === 178 || key === "MediaStop" || key === "Stop") {{
                    e.preventDefault();
                    p.pause();
                    p.currentTime(0);
                    p.userActive(true);
                }}
            }});
        }}

        var player = videojs('videoPlayer', {{
            controls: true,
            autoplay: true,
            preload: "auto",
            inactivityTimeout: 5000,
            controlBar: {{
                audioTrackButton: true
            }}
        }}, function() {{
            var p = this;
            var rawVideo = p.el().querySelector('video');

            function ensureAudioGraph() {{
                if (!audioCtx) {{
                    try {{
                        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                        var src = audioCtx.createMediaElementSource(rawVideo);
                        videoGain = audioCtx.createGain();
                        src.connect(videoGain);
                        videoGain.connect(audioCtx.destination);
                    }} catch (e) {{}}
                }}
                if (audioCtx && audioCtx.state === 'suspended') {{
                    audioCtx.resume();
                }}
            }}

            function updateLevels() {{
                if (isAltAudio) {{
                    if (videoGain) videoGain.gain.value = 0;
                    altAudio.volume = p.volume();
                    altAudio.muted = p.muted();
                }} else {{
                    if (videoGain) videoGain.gain.value = 1;
                    altAudio.pause();
                }}
            }}

            function startAltAudioStream(seekTime) {{
                if (!isAltAudio) return;
                ensureAudioGraph();

                var targetTime = Math.max(0, seekTime !== undefined ? seekTime : (p.currentTime() || 0));
                altAudioBaseTime = targetTime;

                altAudio.src = '/audio_stream?path=' + basePath + '&track=' + currentAudioId + '&t=' + targetTime;
                altAudio.volume = p.volume();
                altAudio.muted = p.muted();
                altAudio.playbackRate = p.playbackRate();
                altAudio.load();

                var onAudioReady = function() {{
                    altAudio.removeEventListener('playing', onAudioReady);
                    if (isAltAudio) {{
                        var diff = p.currentTime() - targetTime;
                        if (Math.abs(diff) > 0.15) {{
                            isProgrammaticSeek = true;
                            p.currentTime(targetTime);
                        }}
                        updateLevels();
                    }}
                }};

                altAudio.addEventListener('playing', onAudioReady, {{ once: true }});
                if (!p.paused()) {{
                    altAudio.play().catch(function(e){{}});
                }}
            }}

            // RESUME MODAL LOGIKA
            var savedTime = parseFloat(localStorage.getItem(resumeKey) || "0");
            p.one('loadedmetadata', function() {{
                var dur = p.duration() || 0;
                if (savedTime > 15 && (dur <= 0 || savedTime < dur - 25)) {{
                    p.pause();
                    resumeTimeDesc.textContent = "Rozkoukáno v čase: " + formatSec(savedTime);
                    resumeModal.style.display = "flex";
                    btnResumeYes.focus();

                    btnResumeYes.onclick = function() {{
                        resumeModal.style.display = "none";
                        p.currentTime(savedTime);
                        if (isAltAudio) startAltAudioStream(savedTime);
                        p.play();
                    }};

                    btnResumeNo.onclick = function() {{
                        resumeModal.style.display = "none";
                        localStorage.removeItem(resumeKey);
                        p.currentTime(0);
                        if (isAltAudio) startAltAudioStream(0);
                        p.play();
                    }};
                }} else {{
                    p.play();
                }}
            }});

            var lastSave = 0;
            p.on('timeupdate', function() {{
                var now = Date.now();
                if (now - lastSave > 3000) {{
                    lastSave = now;
                    var cur = p.currentTime();
                    var dur = p.duration() || 0;
                    if (cur > 15 && (dur <= 0 || cur < dur - 25)) {{
                        localStorage.setItem(resumeKey, cur.toString());
                    }}
                }}
            }});

            // PŘECHOD VE FRONTĚ VIDEÍ
            p.on('ended', function() {{
                localStorage.removeItem(resumeKey);
                try {{
                    var qRaw = sessionStorage.getItem("videoQueue");
                    if (qRaw) {{
                        var queue = JSON.parse(qRaw);
                        if (Array.isArray(queue) && queue.length > 0) {{
                            var nextVideo = queue.shift();
                            sessionStorage.setItem("videoQueue", JSON.stringify(queue));
                            window.location.href = '/player?video=' + encodeURIComponent(nextVideo);
                            return;
                        }} else {{
                            sessionStorage.removeItem("videoQueue");
                        }}
                    }}
                }} catch(e) {{}}
            }});

            p.on('volumechange', function() {{ updateLevels(); }});
            p.on('play', function() {{
                ensureAudioGraph();
                updateLevels();
                if (isAltAudio && altAudio.src && altAudio.paused) {{
                    altAudio.play().catch(function(e){{}});
                }}
            }});

            p.on('pause', function() {{
                if (isAltAudio) altAudio.pause();
            }});

            p.on('seeked', function() {{
                if (isProgrammaticSeek) {{
                    isProgrammaticSeek = false;
                    return;
                }}
                if (isAltAudio) {{
                    startAltAudioStream(p.currentTime());
                }}
            }});

            setInterval(function() {{
                if (!isAltAudio || p.paused() || altAudio.paused || altAudio.readyState < 2) return;
                var currentAudioTime = altAudioBaseTime + altAudio.currentTime;
                var currentVideoTime = p.currentTime();
                var diff = currentVideoTime - currentAudioTime;

                if (Math.abs(diff) < 0.08) {{
                    altAudio.playbackRate = p.playbackRate();
                }} else if (diff > 0.08 && diff < 0.6) {{
                    altAudio.playbackRate = p.playbackRate() * 1.05;
                }} else if (diff < -0.08 && diff > -0.6) {{
                    altAudio.playbackRate = p.playbackRate() * 0.95;
                }}
            }}, 500);

            if (audioTracksData.length > 1) {{
                audioTracksData.forEach(function(t) {{
                    p.audioTracks().addTrack(new videojs.AudioTrack({{
                        id: t.id,
                        kind: 'alternative',
                        label: t.label,
                        language: t.lang,
                        enabled: t.default
                    }}));
                }});

                p.audioTracks().addEventListener('change', function() {{
                    ensureAudioGraph();
                    for (var i = 0; i < p.audioTracks().length; i++) {{
                        var tr = p.audioTracks()[i];
                        if (tr.enabled && tr.id !== currentAudioId) {{
                            currentAudioId = tr.id;
                            if (tr.id === "0") {{
                                isAltAudio = false;
                                altAudio.pause();
                                altAudio.removeAttribute('src');
                                updateLevels();
                            }} else {{
                                isAltAudio = true;
                                startAltAudioStream(p.currentTime());
                            }}
                            break;
                        }}
                    }}
                }});
            }}

            p.on('useractive', function() {{ setHeaderVisible(true); }});
            p.on('userinactive', function() {{
                var isMenuOpen = p.el().querySelector('.vjs-lock-showing');
                if (isMenuOpen) {{
                    p.userActive(true);
                    return;
                }}
                setHeaderVisible(false);
            }});

            var playerDom = p.el();
            ['click', 'touchstart', 'mousemove'].forEach(function(ev) {{
                playerDom.addEventListener(ev, function(e) {{
                    if (e.target.closest && (e.target.closest('.vjs-menu') || e.target.closest('.vjs-subs-caps-button') || e.target.closest('.vjs-audio-button'))) {{
                        p.userActive(true);
                    }}
                }}, true);
            }});

            initTouchGestures(p);
            initPcHotkeys(p);
            initTvRemote(p);
            setTimeout(function() {{ p.trigger('resize'); }}, 200);
        }});
    </script>
</body>
</html>"""
    return html

def convert_srt_to_vtt(srt_text: str) -> str:
    vtt = "WEBVTT\n\n"
    converted = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt_text)
    return vtt + converted

# ==============================================================================
# HTTP HANDLER
# ==============================================================================
class MediaHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def is_safe_path(self, rel_path: str) -> bool:
        if not rel_path:
            return False
        abs_path = os.path.abspath(os.path.join(MEDIA_DIR, rel_path.lstrip("/\\")))
        return os.path.commonpath([MEDIA_DIR, abs_path]) == MEDIA_DIR and os.path.exists(abs_path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/delete-video":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len).decode("utf-8"))
            rel_path = body.get("path", "")
            if not self.is_safe_path(rel_path):
                data = json.dumps({"status": "error", "error": "Neplatná cesta"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(data)
                return

            delete_video_and_associated_files(rel_path)
            data = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "Not Found")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = LIBRARY_HTML.replace("__FAVICON__", FAVICON_BASE64).replace("__DEFAULT_THUMB__", DEFAULT_THUMBNAIL)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/player":
            v_path = query.get("video", [""])[0]
            if v_path and self.is_safe_path(v_path):
                bump_video_to_top(v_path)

            html = build_player_page(v_path)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/videos":
            # 1. Projdeme všechny soubory na disku
            disk_videos = {}
            for root, _, files in os.walk(MEDIA_DIR):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        abs_path = os.path.join(root, f)
                        rel_path = os.path.relpath(abs_path, MEDIA_DIR)
                        rel_dir = os.path.relpath(root, MEDIA_DIR)
                        if rel_dir == ".":
                            rel_dir = ""
                        disk_videos[rel_path] = {"name": f, "path": rel_path, "dir": rel_dir}

            # 2. Seřadíme videa: naposledy sledovaná z urlFolder nahoru, zbytek pod ně
            recent_paths = get_recent_paths_order()
            ordered_videos = []
            seen = set()

            for rp in recent_paths:
                if rp in disk_videos:
                    ordered_videos.append(disk_videos[rp])
                    seen.add(rp)

            for rp, vinfo in sorted(disk_videos.items(), key=lambda x: x[1]["name"].lower()):
                if rp not in seen:
                    ordered_videos.append(vinfo)

            # 3. Vyhledávací filtr
            q_str = query.get("q", [""])[0].lower().strip()
            if q_str:
                filtered = [v for v in ordered_videos if q_str in v["name"].lower() or q_str in v["dir"].lower()]
            else:
                filtered = ordered_videos

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
                    "thumbnail": f"/images/{get_video_id(v['path'])}.jpg?vpath={urllib.parse.quote(v['path'])}"
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

        elif path.startswith("/images/") and path.endswith(".jpg"):
            # Obsluha obrázku: pokud neexistuje, ffmpeg vygeneruje snímek z poloviny videa
            img_filename = os.path.basename(path)
            target_thumb = os.path.join(FOLDER_IMAGES, img_filename)

            if not os.path.exists(target_thumb):
                v_rel = query.get("vpath", [""])[0]
                if v_rel and self.is_safe_path(v_rel):
                    generate_midpoint_thumbnail(v_rel)

            if os.path.exists(target_thumb):
                try:
                    with open(target_thumb, "rb") as f:
                        img_data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(img_data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(img_data)
                    return
                except Exception:
                    pass

            self.send_response(302)
            self.send_header("Location", DEFAULT_THUMBNAIL)
            self.end_headers()
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

        elif path == "/audio_stream":
            rel_path = query.get("path", [""])[0]
            track_idx = query.get("track", ["1"])[0]
            start_t = query.get("t", ["0"])[0]

            if not self.is_safe_path(rel_path):
                self.send_error(404, "Zvuk nenalezen")
                return

            full_path = os.path.join(MEDIA_DIR, rel_path.lstrip("/\\"))

            cmd = ["ffmpeg", "-v", "error"]
            try:
                t_val = float(start_t)
                if t_val > 0:
                    cmd.extend(["-ss", str(t_val)])
            except ValueError:
                pass

            cmd.extend([
                "-i", full_path,
                "-map", f"0:a:{track_idx}",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                "-flush_packets", "1",
                "-f", "adts",
                "pipe:1"
            ])

            proc = None
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self.send_response(200)
                self.send_header("Content-Type", "audio/aac")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                while True:
                    chunk = proc.stdout.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if proc:
                    try:
                        proc.kill()
                        proc.wait()
                    except Exception:
                        pass
            return

        else:
            self.send_error(404, "Not Found")

    def handle_range_streaming(self, file_path: str):
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            self.send_error(404, "Soubor nenalezen")
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
    print("=== TC-Media Server ===")
    print(f"Knihovna médií : {MEDIA_DIR}")
    print(f"Historie (MRU) : {FOLDER_URLS}")
    print(f"Náhledy (střed): {FOLDER_IMAGES}")
    print(f"Běží na adrese : http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), MediaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončuji server...")
        server.server_close()

if __name__ == "__main__":
    run_server()
