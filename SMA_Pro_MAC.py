import os
import sys
import re
import json
import csv
import time
import random
import datetime
import threading
import urllib.request
import urllib.parse
import http.cookiejar
import zipfile
import subprocess
import stat
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import customtkinter as ctk
from PIL import Image, ImageTk
import requests
import browser_cookie3
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import whisper
import ssl # <-- 1. Add this import

# --- Auto-Updater Configuration ---
APP_VERSION = "v1.0.0"
GITHUB_REPO = "zparrishSEA/SVP-Pro-MAC"
# ----------------------------------

# --- MAC SSL PATCH ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
# ---------------------

# --- Dummy Console Patch for Windowed PyInstaller Apps ---
class DummySysStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass

if sys.stdout is None: sys.stdout = DummySysStream()
if sys.stderr is None: sys.stderr = DummySysStream()
# --------------------------------------------------------------

def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def open_mac_full_disk_access():
    msg = "Please grant Full Disk Access to SEA Media Archiver so it can save your media.\n\nWe will now open System Settings for you. Please toggle the switch next to the app, then restart it."
    messagebox.showwarning("Permission Required", msg)

    # This command safely opens the exact macOS settings page
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])

def check_mac_permissions(self, browser_selection):
        # 1. Non-macOS platforms (Windows / Linux)
        # Returns True immediately so Windows and Linux users are never prompted
        if sys.platform != "darwin":
            return True

        # 2. Multi-path mapping to support both modern and legacy macOS versions
        paths_map = {
            "Safari": [
                "~/Library/Containers/com.apple.Safari/Data/Library/Cookies",
                "~/Library/Cookies" # Legacy macOS path
            ],
            "Chrome": [
                "~/Library/Application Support/Google/Chrome"
            ],
            "Firefox": [
                "~/Library/Application Support/Firefox"
            ],
            "Edge": [
                "~/Library/Application Support/Microsoft Edge"
            ],
            "Brave": [
                "~/Library/Application Support/BraveSoftware/Brave-Browser"
            ],
            "Opera": [
                "~/Library/Application Support/com.operasoftware.Opera"
            ]
        }

        candidate_paths = paths_map.get(browser_selection, [])
        if not candidate_paths:
            return True

        # 3. Test each candidate path for permission blocks
        for relative_path in candidate_paths:
            target_dir = os.path.expanduser(relative_path)

            # If this folder path doesn't exist on this OS version, check the next candidate
            if not os.path.exists(target_dir):
                continue

            try:
                # Attempt to read the directory
                os.listdir(target_dir)
                return True  # Access is granted!
            except PermissionError:
                # macOS Full Disk Access is actively blocking an existing folder
                self.open_mac_full_disk_access()
                return False
            except Exception:
                pass

        # If no paths were blocked by a PermissionError, allow execution to proceed
        return True

# -----------------------------
# Configuration & Storage Paths (macOS)
# -----------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'SEAMediaArchiverPro')
os.makedirs(APP_DATA_DIR, exist_ok=True)

if APP_DATA_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = APP_DATA_DIR + os.pathsep + os.environ.get("PATH", "")

# Removed .exe extensions
YTDLP_BIN = os.path.join(APP_DATA_DIR, "yt-dlp")
FFMPEG_BIN = os.path.join(APP_DATA_DIR, "ffmpeg")
FFPROBE_BIN = os.path.join(APP_DATA_DIR, "ffprobe")

# macOS specific URLs
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
FFMPEG_URL = "https://evermeet.cx/ffmpeg/getrelease/zip"
FFPROBE_URL = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"

class SEAMediaArchiverUnifiedApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SEA Media Archiver")
        self.geometry("850x700")
        self.minsize(850, 700)
        self.resizable(True, True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.after(200, self.apply_window_icon)

        self.fb_cookie_path = None
        self.yt_cookie_path = None
        self.impersonate_target = "Safari"  # Default impersonation target
        self.found_videos_list = []

        self.setup_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.auth_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.download_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.search_frame = ctk.CTkFrame(self, fg_color="transparent")

        for frame in (self.setup_frame, self.auth_frame, self.mode_frame, self.download_frame, self.search_frame):
            frame.grid_columnconfigure(0, weight=1)

        self.download_frame.grid_rowconfigure(8, weight=1)
        self.search_frame.grid_rowconfigure(3, weight=1)

        self.build_setup_interface()
        self.build_mode_interface()
        self.build_download_interface()
        self.build_search_interface()

        self.bind("<Return>", self.start_download)
        self.check_and_route_user()

        self.transcript_cache = {}
        self.current_search_keywords = []
        self.check_for_updates()

    def check_for_updates(self):
        def update_worker():
            try:
                # Suppress unverified HTTPS warnings for the updater
                import urllib3
                urllib3.disable_warnings()

                api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                # Using verify=False bypasses macOS strict certificate blocks
                response = requests.get(api_url, timeout=5, verify=False)

                if response.status_code == 200:
                    data = response.json()
                    latest_version = data.get("tag_name", "")
                    release_url = data.get("html_url", "")

                    if latest_version and latest_version != APP_VERSION:
                        self.after(0, lambda: self.prompt_update(latest_version, release_url))
            except Exception:
                pass # Fail silently if no internet connection or repo is private

        threading.Thread(target=update_worker, daemon=True).start()

    def prompt_update(self, latest_version, release_url):
        msg = f"A new version ({latest_version}) is available!\n\nYou are currently on {APP_VERSION}.\nWould you like to download the new version?"
        if messagebox.askyesno("Update Available", msg):
            webbrowser.open(release_url)

    def create_context_menu(self, ctk_entry):
        menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white", activebackground="#38d8c3", activeforeground="black")
        menu.add_command(label="Cut", command=lambda: ctk_entry._entry.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: ctk_entry._entry.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: ctk_entry._entry.event_generate("<<Paste>>"))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        ctk_entry.bind("<Button-2>", show_menu)
        ctk_entry.bind("<Button-3>", show_menu)
        ctk_entry._entry.bind("<Button-2>", show_menu)
        ctk_entry._entry.bind("<Button-3>", show_menu)

    def apply_window_icon(self):
        try:
            # macOS prefers PNG for window icons
            icon_file_path = resource_path("my_icon.png")
            pil_icon = Image.open(icon_file_path)
            self.tk_icon = ImageTk.PhotoImage(pil_icon)
            self.iconphoto(True, self.tk_icon)
        except Exception: pass

    def hide_all_frames(self):
        self.setup_frame.grid_forget()
        self.auth_frame.grid_forget()
        self.mode_frame.grid_forget()
        self.download_frame.grid_forget()
        self.search_frame.grid_forget()

    def build_setup_interface(self):
        self.setup_title = ctk.CTkLabel(self.setup_frame, text="Initializing System Tooling", font=ctk.CTkFont(size=24, weight="bold"))
        self.setup_title.grid(row=0, column=0, pady=(180, 10))
        self.setup_subtitle = ctk.CTkLabel(self.setup_frame, text="Downloading required media modules silently. Please wait...", text_color="gray")
        self.setup_subtitle.grid(row=1, column=0, pady=(0, 30))
        self.setup_progress = ctk.CTkProgressBar(self.setup_frame, width=450)
        self.setup_progress.grid(row=2, column=0, pady=10)
        self.setup_progress.configure(mode="indeterminate")
        self.setup_status = ctk.CTkLabel(self.setup_frame, text="Connecting to servers...", text_color="yellow")
        self.setup_status.grid(row=3, column=0, pady=5)

    def make_executable(self, path):
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC)

    def check_and_route_user(self):
        """Always routes through the setup screen on startup to fetch fresh binary tools."""
        self.hide_all_frames()
        self.setup_frame.grid(row=0, column=0, sticky="nsew")
        self.setup_progress.start()
        threading.Thread(target=self.silent_installer_worker, daemon=True).start()

    def silent_installer_worker(self):
        """Downloads and overwrites Mac-specific yt-dlp, FFmpeg, and FFprobe on every launch."""
        try:
            # 1. Always download the latest yt-dlp binary
            self.after(0, lambda: self.setup_status.configure(text="Acquiring latest yt-dlp core architecture..."))
            if os.path.exists(YTDLP_BIN):
                os.remove(YTDLP_BIN)
            urllib.request.urlretrieve(YTDLP_URL, YTDLP_BIN)
            self.make_executable(YTDLP_BIN)

            # 2. Always download the latest FFmpeg & FFprobe archives
            self.after(0, lambda: self.setup_status.configure(text="Acquiring latest media components (FFmpeg & FFprobe)..."))
            zip_ffm = os.path.join(APP_DATA_DIR, "ffm_temp.zip")
            zip_ffp = os.path.join(APP_DATA_DIR, "ffp_temp.zip")
            urllib.request.urlretrieve(FFMPEG_URL, zip_ffm)
            urllib.request.urlretrieve(FFPROBE_URL, zip_ffp)

            # Extract FFmpeg
            self.after(0, lambda: self.setup_status.configure(text="Configuring execution modules..."))
            if os.path.exists(FFMPEG_BIN):
                os.remove(FFMPEG_BIN)
            with zipfile.ZipFile(zip_ffm, 'r') as zf:
                with zf.open("ffmpeg") as src, open(FFMPEG_BIN, "wb") as dst:
                    dst.write(src.read())

            # Extract FFprobe
            if os.path.exists(FFPROBE_BIN):
                os.remove(FFPROBE_BIN)
            with zipfile.ZipFile(zip_ffp, 'r') as zf:
                with zf.open("ffprobe") as src, open(FFPROBE_BIN, "wb") as dst:
                    dst.write(src.read())

            # Make them executable for macOS
            self.make_executable(FFMPEG_BIN)
            self.make_executable(FFPROBE_BIN)

            # Cleanup temporary zip files
            if os.path.exists(zip_ffm): os.remove(zip_ffm)
            if os.path.exists(zip_ffp): os.remove(zip_ffp)

            # Transition to authentication screen upon success
            self.after(0, lambda: [self.setup_progress.stop(), self.show_auth_screen()])

        except Exception as e:
            # Fallback: If offline or download fails, check if we already have working binaries locally
            ytdlp_valid = os.path.exists(YTDLP_BIN) and os.path.getsize(YTDLP_BIN) > 0
            ffmpeg_valid = os.path.exists(FFMPEG_BIN) and os.path.getsize(FFMPEG_BIN) > 0
            ffprobe_valid = os.path.exists(FFPROBE_BIN) and os.path.getsize(FFPROBE_BIN) > 0

            if ytdlp_valid and ffmpeg_valid and ffprobe_valid:
                self.after(0, lambda: [
                    self.setup_progress.stop(),
                    self.show_auth_screen()
                ])
            else:
                self.after(0, lambda e=e: messagebox.showerror(
                    "Setup Failure",
                    f"Unable to download required tools on launch and no local files were found:\n{str(e)}"
                ))
                self.after(0, lambda: self.setup_status.configure(text="Setup aborted.", text_color="red"))

    def show_auth_screen(self):
        self.hide_all_frames()
        self.auth_frame.grid(row=0, column=0, sticky="nsew")

        try:
            logo_raw = Image.open(resource_path("logo.png"))
            orig_w, orig_h = logo_raw.size
            target_w = 260
            target_h = int((orig_h / orig_w) * target_w)
            logo_img = ctk.CTkImage(light_image=logo_raw, dark_image=logo_raw, size=(target_w, target_h))
            self.logo_label = ctk.CTkLabel(self.auth_frame, image=logo_img, text="")
            self.logo_label.grid(row=0, column=0, pady=(60, 10))
        except Exception: pass

        top_pad = 10 if hasattr(self, 'logo_label') else 150
        ctk.CTkLabel(self.auth_frame, text="Account Authentication", font=ctk.CTkFont(size=24, weight="bold"), text_color="#38d8c3").grid(row=1, column=0, pady=(top_pad, 10))
        info_text = "To download private media and search effectively, we need to securely connect to your browser session.\nSelect the browser where you are currently logged into Facebook and YouTube:"
        ctk.CTkLabel(self.auth_frame, text=info_text, text_color="gray", wraplength=400, justify="center").grid(row=2, column=0, pady=(0, 30))

        self.auth_browser_var = ctk.StringVar(value="Safari")
        dropdown = ctk.CTkOptionMenu(
            self.auth_frame,
            variable=self.auth_browser_var,
            values=["Safari", "Firefox", "Chrome", "Edge", "Brave", "Opera"],
            width=220, height=40,
            fg_color="#2abfae", button_color="#2eae9e", button_hover_color="#21a394", text_color="#2b2b2b",
            dropdown_hover_color="#38d8c3",
            command=self.run_automated_extraction
        )
        dropdown.grid(row=3, column=0, pady=10)

    def run_automated_extraction(self, browser_selection):
        if browser_selection == "Select Browser...": return

        # --- 1. Check permissions for the selected browser first ---
        if not self.check_mac_permissions(browser_selection):
            # If access is blocked, reset the dropdown and stop the process
            self.auth_browser_var.set("Select Browser...")
            return
        # -------------------------------------------------------------

        # 2. Define our single master cookie file
        master_cookie_file = os.path.join(APP_DATA_DIR, "master_cookies.txt")

        # 3. Attempt to extract the cookies
        try:
            if browser_selection == "Firefox": cj = browser_cookie3.firefox()
            elif browser_selection == "Chrome": cj = browser_cookie3.chrome()
            elif browser_selection == "Edge": cj = browser_cookie3.edge()
            elif browser_selection == "Brave": cj = browser_cookie3.brave()
            elif browser_selection == "Opera": cj = browser_cookie3.opera()
            elif browser_selection == "Safari": cj = browser_cookie3.safari()
            else: cj = None

            if not cj:
                messagebox.showwarning("Cookies Not Found", f"Could not find login data in {browser_selection}.")
                self.auth_browser_var.set("Select Browser...")
                return

            # Track if we successfully find our required session cookies
            fb_found = False
            yt_found = False

            master_cookie_file = os.path.join(APP_DATA_DIR, "master_cookies.txt")

            with open(master_cookie_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                for cookie in cj:
                    if "facebook.com" in cookie.domain: fb_found = True
                    if "youtube.com" in cookie.domain: yt_found = True

                    # Extract variables safely
                    expires = str(int(cookie.expires)) if cookie.expires else '0'
                    domain_specified = 'TRUE' if cookie.domain.startswith('.') else 'FALSE'
                    secure = 'TRUE' if cookie.secure else 'FALSE'

                    # Write ALL cookies across the entire web into the master file
                    f.write(f"{cookie.domain}\t{domain_specified}\t{cookie.path}\t{secure}\t{expires}\t{cookie.name}\t{cookie.value}\n")

            # --- Flag Expired or Missing Sessions ---
            if not fb_found and not yt_found:
                messagebox.showwarning(
                    "Session Expired",
                    f"We couldn't find an active session for Facebook or YouTube in {browser_selection}.\n\nPlease open your browser, log out and log back in, then try connecting again."
                )
                self.auth_browser_var.set("Select Browser...")
                return
            # ---------------------------------------------

            # Point both variables to the new master file so you don't have to rewrite the rest of your app!
            self.fb_cookie_path = master_cookie_file
            self.yt_cookie_path = master_cookie_file

            # Map the user's browser choice to the correct yt-dlp impersonate target
            if browser_selection == "Edge":
                self.impersonate_target = "edge"
            elif browser_selection == "Safari":
                self.impersonate_target = "safari"
            else:
                self.impersonate_target = "chrome" # Chrome, Brave, Opera, and Firefox all safely use Chrome impersonation
            self.show_mode_selection()

        except Exception as e:
            messagebox.showerror("Extraction Error", f"Failed to extract cookies from {browser_selection}.\nError: {e}")
            self.auth_browser_var.set("Select Browser...")

    def build_mode_interface(self):
        # 1. Setup Full-Size Logo at Top Center (Replacing Pauly)
        try:
            logo_raw = Image.open(resource_path("logo.png"))
            orig_w, orig_h = logo_raw.size
            target_w = 260
            target_h = int((orig_h / orig_w) * target_w)
            logo_img = ctk.CTkImage(light_image=logo_raw, dark_image=logo_raw, size=(target_w, target_h))

            self.hub_logo_label = ctk.CTkLabel(self.mode_frame, image=logo_img, text="")
            self.hub_logo_label.grid(row=0, column=0, pady=(60, 10))
        except Exception:
            pass

        # 2. Main Title Label (Added pady=80 on the bottom to push buttons down)
        top_pad = 10 if hasattr(self, 'hub_logo_label') else 180
        ctk.CTkLabel(self.mode_frame, text="Select Mode", font=ctk.CTkFont(size=24, weight="bold")).grid(row=1, column=0, pady=(top_pad, 80))

        # 3. Button Frame & Button Icons
        btn_frame = ctk.CTkFrame(self.mode_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0)

        try:
            scope_raw = Image.open(resource_path("scope.png"))
            scope_icon = ctk.CTkImage(light_image=scope_raw, dark_image=scope_raw, size=(56, 56))
        except Exception:
            scope_icon = None

        try:
            chest_raw = Image.open(resource_path("chest.png"))
            chest_icon = ctk.CTkImage(light_image=chest_raw, dark_image=chest_raw, size=(28, 28))
        except Exception:
            chest_icon = None

        # 4. Create the Buttons
        ctk.CTkButton(
            btn_frame,
            text=" Search YouTube",
            image=scope_icon,
            command=self.open_search_mode,
            width=240,
            height=60,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#6c4fa1",
            hover_color="#58266d",
            text_color="#ffffff"
        ).grid(row=0, column=0, padx=15)

        # We assign this to a variable (save_btn) so we can attach Pauly to it!
        save_btn = ctk.CTkButton(
            btn_frame,
            text=" Save Media",
            image=chest_icon,
            command=self.open_download_mode,
            width=240,
            height=60,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#6c4fa1",
            hover_color="#58266d",
            text_color="#ffffff"
        )
        save_btn.grid(row=0, column=1, padx=15)

        # 5. Perch Pauly on the Save Media Button
        try:
            pauly_raw = Image.open(resource_path("pauly.png"))
            target_h_pauly = 140 # Restored to your original larger size!
            target_w_pauly = int((pauly_raw.width / pauly_raw.height) * target_h_pauly)
            pauly_img = ctk.CTkImage(light_image=pauly_raw, dark_image=pauly_raw, size=(target_w_pauly, target_h_pauly))

            # CHANGE 1: Set the master to self.mode_frame to prevent clipping
            # Explicitly set fg_color to transparent so it blends with the background
            pauly_label = ctk.CTkLabel(self.mode_frame, image=pauly_img, text="", fg_color="transparent")

            # CHANGE 2: Use rely=0.0 and anchor="s" to rest the bounding box exactly on top of the button
            # relx=0.85 shifts him nicely to the right side of the button
            pauly_label.place(in_=save_btn, relx=0.85, rely=0.0, anchor="s")
        except Exception:
            pass

    def show_mode_selection(self):
        self.hide_all_frames()
        self.mode_frame.grid(row=0, column=0, sticky="nsew")

    def open_search_mode(self):
        self.hide_all_frames()
        self.search_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

    def open_download_mode(self):
        self.hide_all_frames()
        self.download_frame.grid(row=0, column=0, sticky="nsew")

    def build_search_interface(self):
        # Update row configurations to allow the table to expand correctly with the new cards
        self.search_frame.grid_rowconfigure(0, weight=0)
        self.search_frame.grid_rowconfigure(1, weight=0)
        self.search_frame.grid_rowconfigure(2, weight=0)
        self.search_frame.grid_rowconfigure(3, weight=0)
        self.search_frame.grid_rowconfigure(4, weight=1)

        card_title_color = "#38d8c3"
        dropdown_bg = "#2abfae"
        dropdown_arrow = "#2eae9e"
        dropdown_hover = "#21a394"
        dropdown_text = "#2b2b2b"

        # --- Top Navigation Bar ---
        top_bar = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=20)

        # Create 3 equal columns to balance the layout perfectly
        top_bar.grid_columnconfigure(0, weight=1)
        top_bar.grid_columnconfigure(1, weight=1)
        top_bar.grid_columnconfigure(2, weight=1)

        # Left: Back Button
        ctk.CTkButton(top_bar, text="? Back to Menu", command=self.show_mode_selection, width=120, height=32, fg_color="#444444", hover_color="#555555").grid(row=0, column=0, sticky="w")

        # Right: Title
        ctk.CTkLabel(top_bar, text="YouTube Transcript Search", font=ctk.CTkFont(size=18, weight="bold"), text_color=card_title_color).grid(row=0, column=2, sticky="e")

        # --- Card 1: Search Query Settings ---
        self.query_card = ctk.CTkFrame(self.search_frame, corner_radius=10)
        self.query_card.grid(row=1, column=0, sticky="ew", pady=(5, 5), padx=20)
        self.query_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.query_card, text="Search Query Settings", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        ctk.CTkLabel(self.query_card, text="Keywords (comma-separated):").grid(row=1, column=0, padx=15, pady=(5, 12), sticky="w")
        self.keywords_entry = ctk.CTkEntry(self.query_card, placeholder_text="e.g. LifeWise, LifeWise Academy")
        self.keywords_entry.grid(row=1, column=1, padx=15, pady=(5, 12), sticky="ew")
        self.keywords_entry.insert(0, "LifeWise, LifeWise Academy")
        self.create_context_menu(self.keywords_entry)

        # --- Card 2: Advanced Search Filters ---
        self.filters_card = ctk.CTkFrame(self.search_frame, corner_radius=10)
        self.filters_card.grid(row=2, column=0, sticky="ew", pady=(5, 5), padx=20)

        ctk.CTkLabel(self.filters_card, text="Advanced Search Filters", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=15, pady=12, sticky="w")

        ctk.CTkLabel(self.filters_card, text="Look Back:").grid(row=0, column=1, padx=(5, 2), pady=12)
        self.lookback_var = ctk.StringVar(value="Any Time")
        self.lookback_dropdown = ctk.CTkOptionMenu(
            self.filters_card, variable=self.lookback_var,
            values=["Any Time", "Today", "This Week", "This Month", "This Year"],
            width=120, fg_color=dropdown_bg, button_color=dropdown_arrow,
            button_hover_color=dropdown_hover, text_color=dropdown_text, dropdown_hover_color=card_title_color
        )
        self.lookback_dropdown.grid(row=0, column=2, padx=(0, 15), pady=12)

        ctk.CTkLabel(self.filters_card, text="Max Transcripts:").grid(row=0, column=3, padx=(5, 2), pady=12)
        self.max_results_entry = ctk.CTkEntry(self.filters_card, width=70)
        self.max_results_entry.grid(row=0, column=4, padx=(0, 15), pady=12)
        self.max_results_entry.insert(0, "250")
        self.create_context_menu(self.max_results_entry)

        ctk.CTkLabel(self.filters_card, text="Max Hits:").grid(row=0, column=5, padx=(5, 2), pady=12)
        self.max_hits_entry = ctk.CTkEntry(self.filters_card, width=70)
        self.max_hits_entry.grid(row=0, column=6, padx=(0, 15), pady=12)
        self.max_hits_entry.insert(0, "50") # Default stops after finding 50 matches
        self.create_context_menu(self.max_hits_entry)

        # --- Search Controls & Status ---
        control_frame = ctk.CTkFrame(self.search_frame, fg_color="transparent")
        control_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 5))
        # Give column 0 weight so it expands and pushes column 1 (the button) to the far right
        control_frame.grid_columnconfigure(0, weight=1)

        # Status label now on the left (column 0)
        self.search_status_label = ctk.CTkLabel(
            control_frame,
            text="Ready to search.",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="gray"
        )
        self.search_status_label.grid(row=0, column=0, sticky="w")

        # Search button now on the right (column 1)
        self.search_btn = ctk.CTkButton(
            control_frame,
            text="Start YouTube Search",
            command=self.start_search_thread,
            height=38,
            width=200,
            fg_color="#6c4fa1",
            hover_color="#58266d",
            text_color="#ffffff",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.search_btn.grid(row=0, column=1, sticky="e")

        # --- Results Table ---
        self.results_frame = ctk.CTkFrame(self.search_frame, corner_radius=10)
        self.results_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=10)
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.results_frame, text="Matched Videos:", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b", rowheight=24)
        style.map("Treeview", background=[("selected", "#2abfae")], foreground=[("selected", "#2b2b2b")])

        self.tree = ttk.Treeview(self.results_frame, columns=("Title", "Channel", "URL"), show="headings", height=12)
        self.tree.heading("Title", text="Video Title")
        self.tree.heading("Channel", text="Channel")
        self.tree.heading("URL", text="YouTube URL")
        self.tree.column("Title", width=350)
        self.tree.column("Channel", width=200)
        self.tree.column("URL", width=250)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        action_box = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        action_box.grid(row=2, column=0, pady=(0, 10))

        ctk.CTkButton(action_box, text="View Transcript", command=self.view_highlighted_transcript, fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkButton(action_box, text="Download Video", command=self.send_to_downloader, fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkButton(action_box, text="Watch on YouTube", command=self.open_in_youtube, fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)

    def start_search_thread(self):
        raw_keywords = self.keywords_entry.get().strip()
        if not raw_keywords: return messagebox.showerror("Input Error", "Please provide at least one search keyword.")

        self.current_search_keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        self.transcript_cache.clear()

        # Capture our new settings safely
        try:
            max_results = int(self.max_results_entry.get().strip())
            max_hits = int(self.max_hits_entry.get().strip())
        except ValueError:
            return messagebox.showerror("Input Error", "Max Transcripts and Max Hits must be numbers.")

        look_back_choice = self.lookback_var.get()

        self.search_btn.configure(state="disabled")
        self.search_status_label.configure(text="Scraping YouTube for latest uploads...", text_color="yellow")
        for item in self.tree.get_children(): self.tree.delete(item)

        # Pass the new variables to the worker
        threading.Thread(target=self.run_search_worker, args=(self.current_search_keywords, max_results, max_hits, look_back_choice), daemon=True).start()

    def run_search_worker(self, search_keywords, max_results, max_hits, look_back_choice):
        # 1. Map the user's dropdown choice to YouTube's native date filter parameters
        lookback_map = {
            "Any Time": "EgIQAQ%3D%3D",   # Videos only
            "Today": "EgQIAhAB",          # Videos only, Today
            "This Week": "EgQIAxAB",      # Videos only, This Week
            "This Month": "EgQIBBAB",     # Videos only, This Month
            "This Year": "EgQIBRAB"       # Videos only, This Year
        }
        sp_param = lookback_map.get(look_back_choice, "EgIQAQ%3D%3D")

        # 2. Build the exclusion list from the All-Time Master Sheet
        user_profile = os.path.expanduser('~')
        target_parent_dir = os.path.join(user_profile, 'Downloads', 'SEA Media Archiver', 'You Tube Search Results')
        master_filename = os.path.join(target_parent_dir, "All_Time_Matches.csv")

        excluded_video_ids = set()
        if os.path.isfile(master_filename):
            try:
                with open(master_filename, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        url = row.get('YouTube URL', '')
                        if 'v=' in url:
                            # Extract just the ID so it's easy to compare
                            excluded_video_ids.add(url.split('v=')[-1])
            except Exception:
                pass # If it fails to read, we just proceed with an empty exclusion list

        ydl_opts = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True, 'playlistend': max_results}
        all_videos_dict = {}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for keyword in search_keywords:
                encoded_kw = urllib.parse.quote(keyword)
                try:
                    # Append our specific date filter parameter to the URL
                    search_results = ydl.extract_info(f"https://www.youtube.com/results?search_query={encoded_kw}&sp={sp_param}", download=False)
                    if search_results and 'entries' in search_results:
                        for entry in list(search_results['entries']):
                            if entry and entry.get('id'):
                                vid_id = entry.get('id')
                                # 3. Check if this video is already in our Master Sheet!
                                if vid_id not in excluded_video_ids:
                                    all_videos_dict[vid_id] = {
                                        'title': entry.get('title', 'Untitled Video'),
                                        'channel': entry.get('uploader', 'Unknown Channel')
                                    }
                except Exception: pass

        all_videos = [{'videoId': k, 'title': v['title'], 'channel': v['channel']} for k, v in all_videos_dict.items()]

        if not all_videos:
            self.after(0, lambda: self.search_status_label.configure(text="No new videos found.", text_color="gray"))
            return self.after(0, lambda: self.search_btn.configure(state="normal"))

        self.after(0, lambda: self.search_status_label.configure(text=f"Scanning {len(all_videos)} transcripts for keywords...", text_color="yellow"))

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"})

        if self.yt_cookie_path and os.path.exists(self.yt_cookie_path):
            try:
                cookie_jar = http.cookiejar.MozillaCookieJar(self.yt_cookie_path)
                cookie_jar.load(ignore_discard=True, ignore_expires=True)
                session.cookies = cookie_jar
                transcript_api = YouTubeTranscriptApi(http_client=session)
            except Exception: transcript_api = YouTubeTranscriptApi()
        else: transcript_api = YouTubeTranscriptApi()

        search_keywords_lower = [kw.lower() for kw in search_keywords]
        total_matches = 0
        matched_videos = []

        for index, video in enumerate(all_videos, start=1):
            self.after(0, lambda i=index, t=len(all_videos): self.search_status_label.configure(text=f"Scanning {i}/{t} transcripts..."))
            video_url = f"https://www.youtube.com/watch?v={video['videoId']}"

            try:
                transcript = transcript_api.fetch(video['videoId'])
                full_text_lines = []
                has_match = False

                for entry in transcript:
                    text = entry.text.replace('\n', ' ')
                    mins, secs = int(entry.start // 60), int(entry.start % 60)
                    formatted_line = f"[{mins:02d}:{secs:02d}] {text.strip()}"
                    full_text_lines.append(formatted_line)

                    if not has_match and any(kw in text.lower() for kw in search_keywords_lower):
                        has_match = True

                if has_match:
                    matched_videos.append(video)
                    total_matches += 1
                    self.transcript_cache[video_url] = "\n".join(full_text_lines)
                    self.after(0, lambda v=video, u=video_url: self.tree.insert("", "end", values=(v['title'], v['channel'], u)))

            except Exception: pass

            # 4. Stop scanning if we have reached our Max Hits limit
            if total_matches >= max_hits:
                break

            time.sleep(random.uniform(1.5, 3.0))

        # Updated CSV Export: Individual Sheet AND All-Time Master Sheet
        if matched_videos:
            os.makedirs(target_parent_dir, exist_ok=True)
            date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")

            csv_filename = os.path.join(target_parent_dir, f"Matched_YouTube_Videos_{date_str}.csv")
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['Video Title', 'Channel', 'YouTube URL'])
                writer.writeheader()
                for v in matched_videos:
                    writer.writerow({
                        'Video Title': v['title'],
                        'Channel': v['channel'],
                        'YouTube URL': f"https://www.youtube.com/watch?v={v['videoId']}"
                    })

            file_exists = os.path.isfile(master_filename)
            with open(master_filename, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['Video Title', 'Channel', 'YouTube URL', 'Date Found'])
                if not file_exists:
                    writer.writeheader()

                for v in matched_videos:
                    writer.writerow({
                        'Video Title': v['title'],
                        'Channel': v['channel'],
                        'YouTube URL': f"https://www.youtube.com/watch?v={v['videoId']}",
                        'Date Found': date_str
                    })

            self.after(0, lambda: messagebox.showinfo("Export Successful", f"Found {len(matched_videos)} matches!\n\nSaved to individual sheet AND appended to All_Time_Matches.csv in your You Tube Search Results folder."))

        self.after(0, lambda: self.search_status_label.configure(text=f"Scan complete. Found {total_matches} videos matching keywords.", text_color="#38d8c3"))
        self.after(0, lambda: self.search_btn.configure(state="normal"))

    def view_highlighted_transcript(self):
        """Creates a popup window to read the cached transcript and snaps to the first highlighted keyword."""
        selected = self.tree.selection()
        if not selected: return messagebox.showwarning("Selection Required", "Please select a video row first.")

        # URL is at index 2 because Channel is at index 1
        video_title = self.tree.item(selected[0])["values"][0]
        video_url = self.tree.item(selected[0])["values"][2]

        transcript_text = self.transcript_cache.get(video_url, "Transcript data could not be found in cache.")

        dialog = ctk.CTkToplevel(self)
        dialog.title("Full Transcript Viewer")
        dialog.geometry("700x650")
        dialog.transient(self)

        # Apply the custom window icon
        try:
            dialog.after(200, lambda: dialog.iconphoto(False, self.tk_icon))
        except Exception:
            pass

        ctk.CTkLabel(dialog, text=video_title, font=ctk.CTkFont(size=14, weight="bold"), wraplength=650).pack(pady=(15, 5), padx=10)

        textbox = ctk.CTkTextbox(dialog, font=ctk.CTkFont(size=13), wrap="word")
        textbox.pack(fill="both", expand=True, padx=20, pady=(5, 15))

        textbox.insert("1.0", transcript_text)

        # Setup the highlight tag
        textbox.tag_config("highlight", background="#38d8c3", foreground="#2b2b2b")

        # Track the absolute earliest occurrence in the text box
        earliest_match = None

        # Scan and tag the keywords
        for kw in self.current_search_keywords:
            start_pos = "1.0"
            while True:
                start_pos = textbox.search(kw, start_pos, stopindex=tk.END, nocase=True)
                if not start_pos:
                    break

                if not earliest_match or textbox.compare(start_pos, "<", earliest_match):
                    earliest_match = start_pos

                end_pos = f"{start_pos}+{len(kw)}c"
                textbox.tag_add("highlight", start_pos, end_pos)
                start_pos = end_pos

        textbox.configure(state="disabled") # Make read-only

        # Snap the view to the first keyword hit
        if earliest_match:
            textbox.see(earliest_match)

        # === UPDATED: Save Transcript Logic with Dedicated Folder ===
        def save_transcript_to_file():
            # 1. Build the path to Downloads/SEA Media Archiver/You Tube Transcripts
            user_profile = os.path.expanduser('~')
            target_transcript_dir = os.path.join(user_profile, 'Downloads', 'SEA Media Archiver', 'You Tube Transcripts')

            # 2. Ensure the directory exists
            os.makedirs(target_transcript_dir, exist_ok=True)

            # 3. Clean the video title of invalid filename characters
            safe_title = "".join([c for c in video_title if c.isalpha() or c.isdigit() or c == ' ']).rstrip()
            default_filename = f"{safe_title[:50]}_Transcript.txt"

            # 4. Open save dialog pointing to target_transcript_dir
            file_path = filedialog.asksaveasfilename(
                parent=dialog,
                title="Save Transcript As...",
                initialdir=target_transcript_dir,
                initialfile=default_filename,
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
            )

            if file_path:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"Title: {video_title}\n")
                        f.write(f"URL: {video_url}\n")
                        f.write(f"{'='*60}\n\n")
                        f.write(transcript_text)
                    messagebox.showinfo("Success", "Transcript saved successfully!", parent=dialog)
                except Exception as e:
                    messagebox.showerror("Save Error", f"Could not save file:\n{e}", parent=dialog)

        # Add the Save Button at the bottom of the window
        save_btn = ctk.CTkButton(
            dialog,
            text="Save Transcript to Text File",
            command=save_transcript_to_file,
            fg_color="#6c4fa1",
            hover_color="#58266d",
            text_color="#ffffff",
            font=ctk.CTkFont(weight="bold"),
            height=36
        )
        save_btn.pack(pady=(0, 15))

    def open_in_youtube(self):
        selected = self.tree.selection()
        if not selected: return messagebox.showwarning("Selection Required", "Please select a video row first.")
        webbrowser.open(self.tree.item(selected[0])["values"][2])

    def send_to_downloader(self):
        selected = self.tree.selection()
        if not selected: return messagebox.showwarning("Selection Required", "Please select a video row from the table first.")
        video_url = self.tree.item(selected[0])["values"][2]
        self.open_download_mode()
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, video_url)

    def format_timestamp_input(self, event):
        widget = event.widget
        if event.keysym in ("Backspace", "Delete", "Left", "Right", "Tab"): return
        current_text = widget.get()
        digits = re.sub(r'\D', '', current_text)[:6]
        if not digits: return
        formatted = ""
        if len(digits) <= 2: formatted = digits
        elif len(digits) <= 4: formatted = f"{digits[:2]}:{digits[2:]}"
        else: formatted = f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"
        widget.delete(0, tk.END)
        widget.insert(0, formatted)

    def format_seconds_to_time(self, seconds):
        if not seconds: return "00:00"
        seconds = int(seconds)
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        if hrs > 0: return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def show_stream_selection_dialog(self, entries):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Video Stream")
        dialog.geometry("540x440")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        header_label = ctk.CTkLabel(dialog, text=f"Multiple Streams Detected ({len(entries)})", font=ctk.CTkFont(size=15, weight="bold"), text_color="#38d8c3")
        header_label.pack(pady=(15, 10))

        scroll_frame = ctk.CTkScrollableFrame(dialog, width=490, height=340)
        scroll_frame.pack(padx=15, pady=(0, 15), fill="both", expand=True)

        for idx, entry in enumerate(entries, start=1):
            raw_title = entry.get("title") or f"Stream {idx}"
            duration_str = self.format_seconds_to_time(entry.get("duration"))
            res = entry.get("height") or entry.get("resolution") or "SD"
            res_display = f"{res}p" if str(res).isdigit() else str(res)
            ext = (entry.get("ext") or "mp4").upper()
            stream_url = entry.get("url") or entry.get("webpage_url")

            card = ctk.CTkFrame(scroll_frame, corner_radius=8)
            card.pack(fill="x", pady=5, padx=5)
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", padx=10, pady=10, fill="x", expand=True)

            ctk.CTkLabel(info_frame, text=f"{raw_title[:45]}...", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"Duration: {duration_str}   |   Resolution: {res_display}   |   Format: {ext}", font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(anchor="w", pady=(2, 0))

            def make_download_handler(target_url):
                return lambda: [dialog.destroy(), self.download_btn.configure(state="disabled"), threading.Thread(target=self.download_worker, args=(target_url,), daemon=True).start()]

            dl_btn = ctk.CTkButton(card, text="Download", command=make_download_handler(stream_url), width=90, height=32, fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff", font=ctk.CTkFont(weight="bold"))
            dl_btn.pack(side="right", padx=10, pady=10)

    def show_success_dialog(self, target_folder):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Success")
        dialog.geometry("440x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        msg_label = ctk.CTkLabel(dialog, text="Files compiled successfully inside your Downloads/SEA Media Archiver folder!", wraplength=380, font=ctk.CTkFont(size=13))
        msg_label.pack(pady=(30, 20))
        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(pady=10)

        def open_folder_action():
            path_to_open = target_folder if os.path.exists(target_folder) else os.path.dirname(target_folder)
            subprocess.call(["open", path_to_open])
            dialog.destroy()

        open_btn = ctk.CTkButton(btn_box, text="Open Folder", command=open_folder_action, width=130, height=36, fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff", font=ctk.CTkFont(weight="bold"))
        open_btn.pack(side="left", padx=10)
        ok_btn = ctk.CTkButton(btn_box, text="OK", command=dialog.destroy, width=100, height=36, fg_color="#444444", hover_color="#555555")
        ok_btn.pack(side="left", padx=10)

    def build_download_interface(self):
        self.top_bar = ctk.CTkFrame(self.download_frame, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, pady=(15, 0), padx=20, sticky="ew")
        self.top_bar.grid_columnconfigure(0, weight=1)
        self.top_bar.grid_columnconfigure(1, weight=0)
        self.top_bar.grid_columnconfigure(2, weight=1)

        # Back Button on the left
        back_btn = ctk.CTkButton(
            self.top_bar,
            text="? Back to Menu",
            command=self.show_mode_selection,
            width=130,
            height=32,
            fg_color="#444444",
            hover_color="#555555"
        )
        back_btn.grid(row=0, column=0, sticky="nw")

        # Centered Logo
        try:
            logo_file_path = resource_path("logo.png")
            raw_image = Image.open(logo_file_path)
            orig_width, orig_height = raw_image.size
            target_width = 260
            target_height = int((orig_height / orig_width) * target_width)
            logo_image = ctk.CTkImage(light_image=raw_image, dark_image=raw_image, size=(target_width, target_height))
            self.logo_label = ctk.CTkLabel(self.top_bar, image=logo_image, text="")
        except Exception:
            self.logo_label = ctk.CTkLabel(self.top_bar, text="[ SEA Media Archiver ]", font=ctk.CTkFont(size=26, weight="bold"))
        self.logo_label.grid(row=0, column=1, sticky="n")

        self.url_entry = ctk.CTkEntry(self.download_frame, placeholder_text="Paste Video or Page URL here...", width=760, height=38)
        self.url_entry.grid(row=2, column=0, pady=(10, 15))
        self.create_context_menu(self.url_entry)

        card_title_color = "#38d8c3"
        self.dropdown_bg = "#2abfae"
        self.dropdown_arrow = "#2eae9e"
        self.dropdown_hover = "#21a394"
        self.dropdown_text = "#2b2b2b"

        self.media_card = ctk.CTkFrame(self.download_frame, corner_radius=10)
        self.media_card.grid(row=3, column=0, pady=6, padx=20, sticky="ew")
        ctk.CTkLabel(self.media_card, text="Media Export Settings", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=(15, 15), pady=12, sticky="w")
        ctk.CTkLabel(self.media_card, text="Format:").grid(row=0, column=1, padx=(5, 2), pady=12)

        self.format_var = ctk.StringVar(value="mp4")
        self.format_dropdown = ctk.CTkOptionMenu(self.media_card, variable=self.format_var, values=["mp4", "mkv", "webm", "mov", "avi"], width=80, fg_color=self.dropdown_bg, button_color=self.dropdown_arrow, button_hover_color=self.dropdown_hover, text_color=self.dropdown_text, dropdown_hover_color="#38d8c3")
        self.format_dropdown.grid(row=0, column=2, padx=(0, 12), pady=12)

        ctk.CTkLabel(self.media_card, text="Quality:").grid(row=0, column=3, padx=(5, 2), pady=12)
        self.quality_var = ctk.StringVar(value="Best Available")
        self.quality_dropdown = ctk.CTkOptionMenu(self.media_card, variable=self.quality_var, values=["Best Available", "1080p", "720p", "480p", "360p"], width=125, fg_color=self.dropdown_bg, button_color=self.dropdown_arrow, button_hover_color=self.dropdown_hover, text_color=self.dropdown_text, dropdown_hover_color="#38d8c3")
        self.quality_dropdown.grid(row=0, column=4, padx=(0, 15), pady=12)

        self.audio_only_var = ctk.BooleanVar(value=False)
        self.audio_checkbox = ctk.CTkCheckBox(self.media_card, text="Audio Only (MP3)", variable=self.audio_only_var, command=self.toggle_audio_only)
        self.audio_checkbox.grid(row=0, column=5, padx=(10, 15), pady=12)

        self.sub_card = ctk.CTkFrame(self.download_frame, corner_radius=10)
        self.sub_card.grid(row=4, column=0, pady=6, padx=20, sticky="ew")
        ctk.CTkLabel(self.sub_card, text="Subtitles & Transcripts", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=(15, 25), pady=12, sticky="w")
        self.srt_var = ctk.BooleanVar(value=False)
        self.srt_checkbox = ctk.CTkCheckBox(self.sub_card, text="Save Subtitles (.srt)", variable=self.srt_var)
        self.srt_checkbox.grid(row=0, column=1, padx=15, pady=12)
        self.transcript_var = ctk.BooleanVar(value=False)
        self.transcript_checkbox = ctk.CTkCheckBox(self.sub_card, text="Save Transcript (.txt)", variable=self.transcript_var)
        self.transcript_checkbox.grid(row=0, column=2, padx=(15, 15), pady=12)

        self.time_card = ctk.CTkFrame(self.download_frame, corner_radius=10)
        self.time_card.grid(row=5, column=0, pady=6, padx=20, sticky="ew")
        ctk.CTkLabel(self.time_card, text="Clip Section", font=ctk.CTkFont(size=13, weight="bold"), text_color=card_title_color).grid(row=0, column=0, padx=(15, 15), pady=12, sticky="w")
        self.use_time_var = ctk.BooleanVar(value=False)
        self.time_checkbox = ctk.CTkCheckBox(self.time_card, text="Save Clip Only", variable=self.use_time_var, command=self.toggle_time_inputs)
        self.time_checkbox.grid(row=0, column=1, padx=(0, 15), pady=12)

        self.start_label = ctk.CTkLabel(self.time_card, text="Start:")
        self.start_label.grid(row=0, column=2, padx=(5, 2), pady=12)
        self.start_entry = ctk.CTkEntry(self.time_card, width=90, placeholder_text="00:00:00", state="disabled")
        self.start_entry.grid(row=0, column=3, padx=(0, 10), pady=12)
        self.start_entry.bind("<KeyRelease>", self.format_timestamp_input)
        self.create_context_menu(self.start_entry)

        self.end_label = ctk.CTkLabel(self.time_card, text="End:")
        self.end_label.grid(row=0, column=4, padx=(5, 2), pady=12)
        self.end_entry = ctk.CTkEntry(self.time_card, width=90, placeholder_text="00:00:00", state="disabled")
        self.end_entry.grid(row=0, column=5, padx=(0, 15), pady=12)
        self.end_entry.bind("<KeyRelease>", self.format_timestamp_input)
        self.create_context_menu(self.end_entry)

        self.progress_bar = ctk.CTkProgressBar(self.download_frame, width=760)
        self.progress_bar.grid(row=6, column=0, pady=(16, 4))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(self.download_frame, text="Ready", text_color="gray")
        self.status_label.grid(row=7, column=0, pady=2)

        self.download_btn = ctk.CTkButton(self.download_frame, text="Download Media", command=self.start_download, width=210, height=42, font=ctk.CTkFont(size=14, weight="bold"), fg_color="#6c4fa1", hover_color="#58266d", text_color="#ffffff")
        self.download_btn.grid(row=8, column=0, pady=(12, 18))

    def toggle_audio_only(self):
        if self.audio_only_var.get():
            state, fg, btn, hover, txt = "disabled", "#3a3a3a", "#2d2d2d", "#2d2d2d", "#777777"
        else:
            state, fg, btn, hover, txt = "normal", self.dropdown_bg, self.dropdown_arrow, self.dropdown_hover, self.dropdown_text
        self.format_dropdown.configure(state=state, fg_color=fg, button_color=btn, button_hover_color=hover, text_color=txt)
        self.quality_dropdown.configure(state=state, fg_color=fg, button_color=btn, button_hover_color=hover, text_color=txt)

    def toggle_time_inputs(self):
        if self.use_time_var.get():
            self.start_entry.configure(state="normal")
            self.end_entry.configure(state="normal")
            if not self.start_entry.get(): self.start_entry.insert(0, "00:00:00")
            if not self.end_entry.get(): self.end_entry.insert(0, "00:00:00")
        else:
            self.start_entry.delete(0, tk.END)
            self.end_entry.delete(0, tk.END)
            self.start_entry.configure(state="disabled")
            self.end_entry.configure(state="disabled")

    def start_download(self, event=None):
        url = self.url_entry.get().strip()
        if not url: return messagebox.showerror("Validation Error", "Please provide a valid URL.")
        if self.download_btn.cget("state") == "disabled": return

        self.download_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(text="Analyzing page streams...", text_color="white")
        threading.Thread(target=self.inspection_worker, args=(url,), daemon=True).start()

    def inspection_worker(self, url):
        try:
            if "facebook.com" in url or "fb.watch" in url:
                url = url.replace("m.facebook.com", "www.facebook.com")
                url = url.replace("://fb.watch", "://www.facebook.com/watch")
                match = re.search(r'/videos/(\d+)', url)
                if match: url = f"https://www.facebook.com/watch/?v={match.group(1)}"
                elif "?" in url and "v=" not in url: url = url.split("?")[0]

            entries = []
            cmd = [YTDLP_BIN, "-J", "--flat-playlist", "--no-warnings", "--ffmpeg-location", APP_DATA_DIR, "--impersonate", self.impersonate_target]

            if self.fb_cookie_path and os.path.exists(self.fb_cookie_path):
                cmd.extend(["--cookies", self.fb_cookie_path])

            cmd.append(url)
            process = subprocess.run(cmd, capture_output=True, text=True)

            if process.returncode == 0 and process.stdout:
                data = json.loads(process.stdout)
                if "_type" in data and data.get("_type") == "playlist" and "entries" in data:
                    entries = [e for e in data["entries"] if e]

            if len(entries) > 1:
                self.after(0, lambda: self.status_label.configure(text="Select a stream from the popup window.", text_color="cyan"))
                self.after(0, lambda: self.download_btn.configure(state="normal"))
                self.after(0, lambda: self.show_stream_selection_dialog(entries))
            elif len(entries) == 1:
                self.after(0, lambda: threading.Thread(target=self.download_worker, args=(entries[0]["url"],), daemon=True).start())
            else:
                self.after(0, lambda: threading.Thread(target=self.download_worker, args=(url,), daemon=True).start())
        except Exception:
            self.after(0, lambda: threading.Thread(target=self.download_worker, args=(url,), daemon=True).start())

    def parse_srt_time(self, time_str):
        """Converts timestamp strings (HH:MM:SS or HH:MM:SS,mmm) into float seconds."""
        time_str = time_str.strip().replace('.', ',')
        parts = time_str.split(':')
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h = 0
            m, s = parts
        else:
            return 0.0

        if ',' in s:
            sec, msec = s.split(',')
        else:
            sec, msec = s, '0'

        return int(h) * 3600 + int(m) * 60 + int(sec) + (int(msec) / 1000.0)

    def format_whisper_timestamp(self, seconds):
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        msecs = int(round((seconds % 1) * 1000))
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

    def process_subtitles_and_transcripts(self, folder_path):
        try:
            srt_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".srt")]

            # Determine if the clip section feature is currently active
            use_clip = self.use_time_var.get()
            clip_start_sec = 0.0
            clip_end_sec = float('inf')

            if use_clip:
                start_str = self.start_entry.get().strip() or "00:00:00"
                end_str = self.end_entry.get().strip()
                clip_start_sec = self.parse_srt_time(start_str)
                if end_str:
                    clip_end_sec = self.parse_srt_time(end_str)

            # --- Whisper Local AI Fallback ---
            if not srt_files and (self.transcript_var.get() or self.srt_var.get()):
                media_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.mp4', '.mkv', '.webm', '.mp3', '.mov', '.avi'))]
                if media_files:
                    self.after(0, lambda: self.status_label.configure(text="Generating local AI transcript with built-in Whisper...", text_color="yellow"))
                    media_path = os.path.join(folder_path, media_files[0])

                    self.after(0, lambda: self.progress_bar.configure(mode="indeterminate"))
                    self.after(0, lambda: self.progress_bar.start())

                    model = whisper.load_model("base", download_root=APP_DATA_DIR)
                    result = model.transcribe(media_path, fp16=False)
                    base_name = os.path.splitext(media_files[0])[0]

                    if self.srt_var.get():
                        srt_path = os.path.join(folder_path, f"{base_name}.srt")
                        with open(srt_path, "w", encoding="utf-8") as srt_file:
                            for i, segment in enumerate(result["segments"], start=1):
                                start = self.format_whisper_timestamp(segment["start"])
                                end = self.format_whisper_timestamp(segment["end"])
                                text = segment["text"].strip()
                                srt_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")

                    if self.transcript_var.get():
                        txt_path = os.path.join(folder_path, f"{base_name}.txt")
                        clean_text = result["text"].strip()
                        with open(txt_path, "w", encoding="utf-8") as txt_file:
                            txt_file.write(clean_text)

                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))

                return

            # --- Process Downloaded YouTube Subtitles (.srt) ---
            for file in srt_files:
                srt_path = os.path.join(folder_path, file)
                txt_path = os.path.splitext(srt_path)[0] + ".txt"

                with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Split SRT into individual subtitle blocks
                blocks = re.split(r'\n\s*\n', content.strip())
                filtered_blocks = []
                clean_dialogue = []

                for block in blocks:
                    lines = [l.strip() for l in block.splitlines() if l.strip()]
                    if not lines:
                        continue

                    time_line_idx = -1
                    for idx, line in enumerate(lines):
                        if '-->' in line:
                            time_line_idx = idx
                            break

                    if time_line_idx != -1:
                        time_parts = lines[time_line_idx].split('-->')
                        start_sub_sec = self.parse_srt_time(time_parts[0])
                        end_sub_sec = self.parse_srt_time(time_parts[1])

                        # Skip blocks outside of our active clip range
                        if use_clip:
                            if end_sub_sec < clip_start_sec or start_sub_sec > clip_end_sec:
                                continue

                        filtered_blocks.append(lines)

                        # Extract clean dialogue lines for .txt file
                        text_lines = lines[time_line_idx + 1:]
                        for line in text_lines:
                            line = re.sub(r'<[^>]+>', '', line)
                            if line.isupper():
                                line = line.capitalize()
                            if clean_dialogue and clean_dialogue[-1] == line:
                                continue
                            if ">>" in line and clean_dialogue and clean_dialogue[-1] != "":
                                clean_dialogue.append("")
                            clean_dialogue.append(line)

                # Write out filtered SRT
                if self.srt_var.get():
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        for idx, lines in enumerate(filtered_blocks, start=1):
                            f.write(f"{idx}\n")
                            f.write("\n".join(lines[lines.index(next(l for l in lines if '-->' in l)):]) + "\n\n")
                else:
                    os.remove(srt_path)

                # Write out filtered TXT transcript
                if self.transcript_var.get():
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write("\n".join(clean_dialogue))

        except Exception as e:
            self.after(0, lambda err=str(e): self.status_label.configure(text=f"Transcript error: {err}", text_color="red"))
            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))

    def download_worker(self, url):
        console_output_logs = []
        try:
            if "facebook.com" in url or "fb.watch" in url:
                url = url.replace("m.facebook.com", "www.facebook.com")
                url = url.replace("://fb.watch", "://www.facebook.com/watch")
                match = re.search(r'/videos/(\d+)', url)
                if match: url = f"https://www.facebook.com/watch/?v={match.group(1)}"
                elif "?" in url and "v=" not in url: url = url.split("?")[0]

            user_profile = os.environ.get('HOME', os.path.expanduser('~'))
            target_parent_dir = os.path.join(user_profile, 'Downloads', 'SEA Media Archiver')

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            outtmpl = os.path.join(target_parent_dir, '%(title).60s', f'%(title).60s_{timestamp}.%(ext)s')

            cmd = [
                YTDLP_BIN, "--newline", "--no-playlist", "--ffmpeg-location", APP_DATA_DIR,
                "-o", outtmpl, "--restrict-filenames", "--no-warnings", "--impersonate", self.impersonate_target,
                "--downloader-args", "ffmpeg:-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            ]

            if self.audio_only_var.get(): cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            else:
                selected_format = self.format_var.get().lower()
                selected_quality = self.quality_var.get()
                if selected_quality == "1080p": fmt_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
                elif selected_quality == "720p": fmt_str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
                elif selected_quality == "480p": fmt_str = "bestvideo[height<=480]+bestaudio/best[height<=480]"
                elif selected_quality == "360p": fmt_str = "bestvideo[height<=360]+bestaudio/best[height<=360]"
                else: fmt_str = "bestvideo+bestaudio/best"
                cmd.extend(["-f", fmt_str, "--merge-output-format", selected_format, "--remux-video", selected_format])

            if self.use_time_var.get():
                start_time = self.start_entry.get().strip() or "00:00:00"
                end_time = self.end_entry.get().strip()
                if end_time: cmd.extend(["--download-sections", f"*{start_time}-{end_time}", "--force-keyframes-at-cuts"])

            if self.srt_var.get() or self.transcript_var.get():
                cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt", "--sleep-subtitles", "1"])

            if self.fb_cookie_path and os.path.exists(self.fb_cookie_path):
                cmd.extend(["--cookies", self.fb_cookie_path])

            cmd.append(url)

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')
            video_title = None

            for line in process.stdout:
                console_output_logs.append(line.strip())
                if "[download] Destination:" in line:
                    video_title = os.path.basename(os.path.dirname(line.split("[download] Destination:")[-1].strip()))
                elif "has already been downloaded" in line:
                    match = re.search(r'\[download\]\s+(.*?)\s+has already been downloaded', line)
                    if match: video_title = os.path.basename(os.path.dirname(match.group(1).strip()))
                elif "[Merger] Merging formats into" in line:
                    match = re.search(r'\[Merger\] Merging formats into "(.*?)"', line)
                    if match: video_title = os.path.basename(os.path.dirname(match.group(1).strip()))

                if "[download]" in line and "%" in line:
                    match = re.search(r'([0-9.]+)%', line)
                    if match:
                        percent = float(match.group(1)) / 100.0
                        self.after(0, lambda p=percent: self.progress_bar.set(p))
                        self.after(0, lambda p=percent: self.status_label.configure(text=f"Downloading... {int(p * 100)}%"))

            process.wait()

            if process.returncode == 0:
                specific_folder = target_parent_dir
                if video_title:
                    test_folder = os.path.join(target_parent_dir, video_title)
                    if os.path.exists(test_folder): specific_folder = test_folder

                if (self.srt_var.get() or self.transcript_var.get()) and os.path.exists(specific_folder) and specific_folder != target_parent_dir:
                    self.process_subtitles_and_transcripts(specific_folder)

                self.after(0, lambda: self.progress_bar.set(1.0))
                self.after(0, lambda: self.status_label.configure(text="Download Complete!", text_color="green"))
                self.after(0, lambda f=specific_folder: self.show_success_dialog(f))
            else:
                relevant_errors = [l for l in console_output_logs if "ERROR:" in l or "failed" in l.lower()]
                error_details = "\n".join(relevant_errors[-3:]) if relevant_errors else "Unknown backend error."

                # --- NEW: Detect yt-dlp cookie/login expiration ---
                # We convert the errors to lowercase to safely check for keywords
                error_lower = error_details.lower()

                # 403, "sign in", and "cookie" are the most common flags yt-dlp throws when a session expires
                if "sign in" in error_lower or "cookie" in error_lower or "403" in error_lower:
                    self.after(0, lambda: self.status_label.configure(text="Session Expired.", text_color="red"))
                    self.after(0, lambda: messagebox.showwarning(
                        "Authentication Failed",
                        "Your browser session was rejected or has expired.\n\nPlease open your browser, log out of the website, log back in, and restart this application to refresh your cookies."
                    ))
                else:
                    self.after(0, lambda: self.status_label.configure(text="Download failed.", text_color="red"))
                    self.after(0, lambda err=error_details: messagebox.showerror("Extraction Error", f"The extraction process failed.\n\nDetails:\n{err}"))
                # --------------------------------------------------

        except Exception as e:
            self.after(0, lambda e=e: messagebox.showerror("System Error", f"An exception occurred:\n{str(e)}"))
        finally:
            self.after(0, lambda: self.download_btn.configure(state="normal"))

if __name__ == "__main__":
    app = SEAMediaArchiverUnifiedApp()
    app.mainloop()