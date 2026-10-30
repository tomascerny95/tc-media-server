import os
import io
import tarfile
import threading
from datetime import datetime
import requests

import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext

# Cílový soubor, který načítá televize.py
BUFFER_FILENAME = "pluginBuffer.html"

# Profily verzí Video.js (stahuje se pouze čisté Video.js bez doplňků)
PROFILES = {
    "7.10.2": {
        "title": "Video.js 7.10.2 (Ověřeno pro Vewd / Opera TV 2016)",
        "badge": "Doporučeno pro vaši TV",
        "badge_color": "#81c784",
        "desc": "Původní stabilní verze. Obsahuje ES5 kód a polyfilly pro staré televizní prohlížeče (Vewd 2016, starší Tizen a webOS). 100% jistota funkčnosti.",
        "exact_version": "7.10.2"
    },
    "7.21.7": {
        "title": "Video.js 7.21.7 (Novější Smart TV od roku 2018+)",
        "badge": "Pro novější TV",
        "badge_color": "#ffb74d",
        "desc": "Poslední vydání řady 7. Vhodné pro novější televize (Tizen 4+, webOS 4+) a starší PC. Na Vewd 2016 nefunguje.",
        "exact_version": "7.21.7"
    },
    "8.x": {
        "title": "Video.js 8.x LTS (Moderní PC, mobily a tablety)",
        "badge": "Pouze pro moderní zařízení",
        "badge_color": "#e57373",
        "desc": "Nejnovější řada s moderním kódem a podporou do roku 2028. Určeno pro Chrome, Firefox, Edge a moderní mobily. Na starých TV nefunguje.",
        "exact_version": None  # Zjistí se automaticky z NPM
    }
}

# ==============================================================================
# STAHOVÁNÍ POUZE VIDEO.JS Z OFICIÁLNÍHO NPM REGISTRU
# ==============================================================================
def get_latest_v8_from_npm(log_func):
    """Najde nejnovější verzi z řady 8."""
    log_func("[NPM] Zjišťuji nejnovější verzi Video.js 8.x...")
    r = requests.get("https://registry.npmjs.org/video.js", timeout=10)
    if r.status_code != 200:
        return "8.24.1"
    versions = [v for v in r.json().get("versions", {}).keys() if v.startswith("8.") and "-" not in v]
    if not versions:
        return "8.24.1"
    versions.sort(key=lambda s: [int(u) for u in s.split(".") if u.isdigit()])
    latest = versions[-1]
    log_func(f"[NPM] Nalezena nejnovější verze: {latest}")
    return latest

def get_file_from_npm(package_name: str, version: str, target_subpath: str, log_func):
    """Stáhne a rozbalí soubor z oficiálního .tgz archivu z NPM."""
    tarball_url = f"https://registry.npmjs.org/{package_name}/-/{package_name}-{version}.tgz"
    log_func(f"[NPM] Stahuji balíček: {package_name}@{version}...")
    
    res = requests.get(tarball_url, timeout=25)
    if res.status_code != 200:
        raise Exception(f"Chyba při stahování balíčku z NPM (HTTP {res.status_code})")

    with tarfile.open(fileobj=io.BytesIO(res.content), mode="r:gz") as tar:
        expected = f"package/{target_subpath}".replace("\\", "/")
        target_member = None
        for member in tar.getmembers():
            if member.name.lower() == expected.lower() or member.name.lower().endswith("/" + target_subpath.lower()):
                target_member = member
                break

        if not target_member:
            raise FileNotFoundError(f"V balíčku {version} nebyl nalezen '{target_subpath}'")

        content = tar.extractfile(target_member).read().decode("utf-8", errors="ignore")
        log_func(f"  -> Rozbalen soubor: '{target_member.name}' ({len(content)} znaků)")
        return content

# ==============================================================================
# GRAFICKÉ ROZHRANÍ (TKINTER)
# ==============================================================================
class CleanVideoJsUpdaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Správce Video.js (Čistý přehrávač)")
        self.root.geometry("640x630")
        self.root.configure(bg="#1e242c")
        self.root.resizable(False, False)

        # Vycentrování na střed obrazovky
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self.selected_profile_key = tk.StringVar(value="7.10.2")

        self.setup_ui()
        self.refresh_file_status()
        self.update_description()

    def setup_ui(self):
        title_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        sub_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        body_font = tkfont.Font(family="Segoe UI", size=9)
        btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")

        # Záhlaví
        tk.Label(
            self.root, text="Stahování čistého přehrávače Video.js",
            font=title_font, fg="#ffffff", bg="#1e242c"
        ).pack(pady=(12, 4))

        # Panel stavu souboru pluginBuffer.html
        self.status_frame = tk.Frame(self.root, bg="#242a33", bd=1, relief="solid")
        self.status_frame.pack(fill="x", padx=20, pady=6)

        self.lbl_file_info = tk.Label(
            self.status_frame, text="Zjišťuji stav souboru...",
            font=body_font, fg="#90a4ae", bg="#242a33", justify="left"
        )
        self.lbl_file_info.pack(anchor="w", padx=12, pady=8)

        # Sekce s výběrem verzí
        profiles_frame = tk.LabelFrame(
            self.root, text=" Zvolte verzi Video.js ",
            font=sub_font, fg="#ffffff", bg="#1e242c", bd=1, relief="groove"
        )
        profiles_frame.pack(fill="x", padx=20, pady=6)

        for key, p in PROFILES.items():
            rb = tk.Radiobutton(
                profiles_frame, text=p["title"],
                variable=self.selected_profile_key, value=key,
                font=sub_font, fg="#f0f0f0", selectcolor="#242a33", bg="#1e242c",
                activebackground="#1e242c", activeforeground="#ffffff",
                command=self.update_description
            )
            rb.pack(anchor="w", padx=12, pady=(6, 0))

        # Popis vybraného profilu
        self.desc_frame = tk.Frame(self.root, bg="#181d24", bd=1, relief="solid")
        self.desc_frame.pack(fill="x", padx=20, pady=6)

        self.lbl_badge = tk.Label(
            self.desc_frame, text="", font=sub_font, bg="#181d24"
        )
        self.lbl_badge.pack(anchor="w", padx=12, pady=(6, 2))

        self.lbl_desc = tk.Label(
            self.desc_frame, text="", font=body_font, fg="#cfd8dc",
            bg="#181d24", justify="left", wraplength=570
        )
        self.lbl_desc.pack(anchor="w", padx=12, pady=(0, 6))

        # Akční tlačítko
        self.btn_download = tk.Button(
            self.root, text=f"Stáhnout a zapsat do {BUFFER_FILENAME}",
            font=btn_font, bg="#e54c4c", fg="#ffffff",
            activebackground="#c93a3a", activeforeground="#ffffff",
            relief="flat", cursor="hand2", command=self.start_download_thread
        )
        self.btn_download.pack(fill="x", padx=20, pady=10, ipady=6)

        # Log konzole
        self.log_area = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, height=9,
            bg="#14181d", fg="#dcdcdc", insertbackground="#ffffff",
            font=("Consolas", 9), bd=0, relief="flat"
        )
        self.log_area.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # Spodní lišta
        bottom_frame = tk.Frame(self.root, bg="#1e242c")
        bottom_frame.pack(fill="x", padx=20, pady=(0, 12))

        tk.Button(
            bottom_frame, text="Otevřít složku",
            font=body_font, bg="#2a313c", fg="#ffffff",
            relief="flat", cursor="hand2", command=lambda: os.startfile(os.getcwd())
        ).pack(side="left")

        tk.Button(
            bottom_frame, text="Vyčistit záznam",
            font=body_font, bg="#2a313c", fg="#ffffff",
            relief="flat", cursor="hand2", command=lambda: self.log_area.delete("1.0", tk.END)
        ).pack(side="right")

    def update_description(self):
        key = self.selected_profile_key.get()
        p = PROFILES[key]
        self.lbl_badge.config(text=f"● {p['badge']}", fg=p["badge_color"])
        self.lbl_desc.config(text=p["desc"])

    def log(self, msg):
        def _append():
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
        self.root.after(0, _append)

    def refresh_file_status(self):
        if os.path.exists(BUFFER_FILENAME):
            size_kb = os.path.getsize(BUFFER_FILENAME) / 1024
            mtime = os.path.getmtime(BUFFER_FILENAME)
            dt_str = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y v %H:%M:%S")
            self.lbl_file_info.config(
                text=f"Aktivní soubor: {BUFFER_FILENAME} (PŘIPRAVEN)\nVelikost: {size_kb:.1f} KB | Poslední změna: {dt_str}",
                fg="#81c784"
            )
        else:
            self.lbl_file_info.config(
                text=f"Soubor {BUFFER_FILENAME} zatím neexistuje. Klikněte pro stažení.",
                fg="#ffb74d"
            )

    def start_download_thread(self):
        self.btn_download.config(state="disabled", text="Stahuji čisté Video.js...", bg="#555555")
        key = self.selected_profile_key.get()
        threading.Thread(target=self._worker, args=(key,), daemon=True).start()

    def _worker(self, key):
        profile = PROFILES[key]
        self.log("==================================================")
        self.log(f"Zahajuji stahování: {profile['title']}")

        try:
            # 1. Zjištění verze
            if profile["exact_version"]:
                target_version = profile["exact_version"]
            else:
                target_version = get_latest_v8_from_npm(self.log)

            # 2. Stažení CSS
            css_content = get_file_from_npm("video.js", target_version, "dist/video-js.min.css", self.log)

            # 3. Stažení JS
            js_content = get_file_from_npm("video.js", target_version, "dist/video.min.js", self.log)

            # Sestavení pluginBuffer.html POUZE s Video.js
            new_buffer = f"""<style>
    // https://unpkg.com/video.js@{target_version}/dist/video-js.min.css
{css_content}
</style>
<script>
    // https://unpkg.com/video.js@{target_version}/dist/video.min.js
{js_content}
</script>
"""

            # Přímé uložení do pluginBuffer.html bez vytváření .bak záloh
            with open(BUFFER_FILENAME, "w", encoding="utf-8") as f:
                f.write(new_buffer)

            self.log("--------------------------------------------------")
            self.log(f"ÚSPĚCH: Soubor '{BUFFER_FILENAME}' byl vygenerován!")
            self.log(f"Verze Video.js: {target_version} (Čistá instalace)")
            self.log("Nyní nezapomeňte restartovat aplikaci 'televize.py'.")
            self.log("==================================================")

        except Exception as e:
            self.log(f"\n[CHYBA] Proces selhal: {e}")
            self.log("==================================================")

        def _finish():
            self.btn_download.config(
                state="normal",
                text=f"Stáhnout a zapsat do {BUFFER_FILENAME}",
                bg="#e54c4c"
            )
            self.refresh_file_status()

        self.root.after(0, _finish)


if __name__ == "__main__":
    root = tk.Tk()
    app = CleanVideoJsUpdaterApp(root)
    root.mainloop()
