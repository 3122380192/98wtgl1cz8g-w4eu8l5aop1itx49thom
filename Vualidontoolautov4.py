# -*- coding: utf-8 -*-
"""
Vualidontoolautov3.py – Upgraded Edition
- Forced version check on startup: users MUST update to continue
- Thread-safe process stop with timeout
- Persistent last-selected tool (settings.json)
- Detailed error messages
- Tooltip on every button
- Double-click combobox to run
- Dual-phase RGB animation
- Hotkey registration warnings
"""
import os
import sys
import glob
import json
import shutil
import zipfile
import tempfile
import threading
import subprocess
import urllib.request
import ssl
import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes
import random
import string
from PIL import Image, ImageTk, ImageEnhance

# Ensure console printing handles Unicode characters without crash
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
GITHUB_OWNER = "3122380192"
GITHUB_REPO  = "98wtgl1cz8g-w4eu8l5aop1itx49thom"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    if "ORIG_SCRIPT_DIR" in os.environ:
        SCRIPT_DIR = os.environ["ORIG_SCRIPT_DIR"]
    else:
        SCRIPT_DIR = os.path.dirname(sys.executable)

LOCAL_VERSION_FILE = os.path.join(SCRIPT_DIR, "version.txt")
SETTINGS_FILE     = os.path.join(SCRIPT_DIR, "settings.json")

desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
DIR_A = os.path.join(desktop_dir, "A")
DIR_B = os.path.join(desktop_dir, "B")

SYSTEM_NAMES = [
    "svchost_helper", "RuntimeBroker_sys", "taskhostw_win",
    "conhost_helper", "ctfmon_service", "dllhost_runtime",
    "explorer_agent", "spoolsv_helper"
]

def check_self_masquerade():
    # Only masquerade if compiled as an EXE (frozen)
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
        exe_name = os.path.basename(exe_path)
        
        is_masqueraded = False
        for name in SYSTEM_NAMES:
            if exe_name.lower().startswith(name.lower()):
                is_masqueraded = True
                break
                
        if not is_masqueraded:
            temp_dir = tempfile.gettempdir()
            rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            chosen_sys = random.choice(SYSTEM_NAMES)
            temp_name = f"{chosen_sys}_{rand_suffix}.exe"
            temp_path = os.path.join(temp_dir, temp_name)
            
            try:
                shutil.copy2(exe_path, temp_path)
                os.environ["ORIG_SCRIPT_DIR"] = SCRIPT_DIR
                subprocess.Popen([temp_path] + sys.argv[1:])
                sys.exit(0)
            except Exception:
                pass

# Run self-masquerade check immediately!
check_self_masquerade()

# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────
tools          = []
current_process = None
running_name   = ""
update_busy    = False
window_visible = True
is_locked      = False   # True → UI locked, must update first

# ─── WINDOWS API ──────────────────────────────────────────────────────────────
user32     = ctypes.windll.user32
HK_F6      = 1
HK_INS     = 2
VK_F6      = 0x75
VK_INSERT  = 0x2D

# ─── RGB PALETTE ──────────────────────────────────────────────────────────────
ARGB = ["#FF0000","#FF5500","#FFAA00","#FFFF00","#55FF00","#00FF00",
        "#00FFCC","#00CCFF","#0066FF","#7F00FF","#FF00FF","#FF007F"]
irgb_index = 0

# ══════════════════════════════════════════════════════════════════════════════
#  VERSION CHECK – forced update gate
# ══════════════════════════════════════════════════════════════════════════════

def read_local_version():
    try:
        with open(LOCAL_VERSION_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return "0"

def write_local_version(ver):
    try:
        with open(LOCAL_VERSION_FILE, "w") as f:
            f.write(ver.strip())
    except Exception:
        pass

def fetch_remote_version():
    url = (f"https://raw.githubusercontent.com/"
           f"{GITHUB_OWNER}/{GITHUB_REPO}/main/version.txt?t={random.randint(100000, 999999)}")
    try:
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, context=ssl_context, timeout=3) as resp:
            return resp.read().decode().strip()
    except Exception:
        return None

def version_tuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)

def check_version_on_startup():
    """Background: fetch remote version and lock UI if outdated.
    If no network → run normally (offline mode), do NOT lock UI."""
    local = read_local_version()
    remote = fetch_remote_version()
    if remote is None:
        # No network – just run normally, show offline notice
        root.after(0, lambda: lbl_status.config(
            text=f"Sẵn sàng (offline) – {len(tools)} tool  (v{local})"))
        return
    if version_tuple(remote) > version_tuple(local):
        root.after(0, lambda r=remote, l=local: _force_lock(r, l))
    else:
        root.after(0, lambda: lbl_status.config(
            
            text=f"Sẵn sàng – {len(tools)} tool  (v{local})"))

def _force_lock(remote_ver, local_ver):
    global is_locked
    is_locked = True
    combo.config(state="disabled")
    btn_run.config(state="disabled")
    btn_reset.config(state="disabled")
    lbl_status.config(
        text=f"⛔ v{remote_ver} – Bắt buộc Update!")
    # Delete Desktop A/B silently when old version detected
    threading.Thread(target=delete_desktop_folders, daemon=True).start()

def unlock_ui():
    global is_locked
    is_locked = False
    combo.config(state="readonly")
    btn_run.config(state="normal")
    btn_reset.config(state="normal")

# ══════════════════════════════════════════════════════════════════════════════
#  DATA DIRS
# ══════════════════════════════════════════════════════════════════════════════

def init_data_dirs():
    os.makedirs(DIR_A, exist_ok=True)
    os.makedirs(DIR_B, exist_ok=True)

def hide_desktop_folders():
    """Silently hide Desktop\A and Desktop\B after update."""
    for d in (DIR_A, DIR_B):
        if os.path.exists(d):
            try:
                subprocess.Popen(
                    ["attrib", "+h", d],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception:
                pass

def delete_desktop_folders():
    """Delete Desktop\A and Desktop\B when outdated version detected."""
    for d in (DIR_A, DIR_B):
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
            except Exception:
                pass

# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS – persist last selected tool
# ══════════════════════════════════════════════════════════════════════════════

def save_last_tool(name):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_tool": name}, f)
    except Exception:
        pass

def load_last_tool():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_tool", "")
    except Exception:
        return ""

# ══════════════════════════════════════════════════════════════════════════════
#  TOOL SCANNING
# ══════════════════════════════════════════════════════════════════════════════

def load_shortcuts(directory):
    shortcuts = []
    shortcut_file = os.path.join(directory, "shortcut.txt")
    if os.path.exists(shortcut_file):
        try:
            with open(shortcut_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        col = parts[2] if len(parts) >= 3 else ""
                        shortcuts.append(
                            {"exe": parts[0], "name": parts[1], "col": col})
        except Exception:
            pass
    return shortcuts

def scan_all():
    global tools
    tools = []
    _scan_folder(DIR_A, "A")
    _scan_folder(DIR_B, "B")
    col_order = {"A": 1, "B": 2, "S": 3}
    tools.sort(key=lambda t: (col_order.get(t["col"], 3), t["order"]))

def _scan_folder(directory, default_col):
    if not os.path.exists(directory):
        return
    shortcuts = load_shortcuts(directory)
    exe_files = [os.path.basename(f)
                 for f in glob.glob(os.path.join(directory, "*.exe"))]
    used_exes = set()

    # Filter out temporary masqueraded files
    filtered_exes = []
    for exe in exe_files:
        is_temp = False
        for sys_name in SYSTEM_NAMES:
            if exe.startswith(sys_name):
                is_temp = True
                break
        if not is_temp:
            filtered_exes.append(exe)
    exe_files = filtered_exes

    for idx, sc in enumerate(shortcuts):
        if sc["exe"] in exe_files:
            col = sc["col"].upper() if sc["col"].upper() in ["A","B","S"] \
                  else default_col
            tools.append({"name": sc["name"],
                           "path": os.path.join(directory, sc["exe"]),
                           "col": col, "order": idx})
            used_exes.add(sc["exe"])

    for idx, exe in enumerate(exe_files):
        if exe not in used_exes:
            tools.append({"name": exe,
                           "path": os.path.join(directory, exe),
                           "col": "S", "order": 1000 + idx})

def load_all_tools():
    scan_all()
    display_list = []
    for t in tools:
        g = "Chính" if t["col"]=="A" else ("Farm" if t["col"]=="B" else "Đặc biệt")
        display_list.append(f"[{g}] {t['name']}")

    combo["values"] = display_list
    if display_list:
        last = load_last_tool()
        combo.set(last if last in display_list else display_list[0])
    else:
        combo.set("")

    if not is_locked:
        lbl_status.config(text=f"Sẵn sàng – {len(tools)} tool")

# ══════════════════════════════════════════════════════════════════════════════
#  PROCESS CONTROL
# ══════════════════════════════════════════════════════════════════════════════

def monitor_process(proc, name):
    global current_process, running_name
    try:
        proc.wait()
    except Exception:
        pass
    
    if current_process == proc:
        current_process = None
        running_name = ""
        root.after(0, lambda n=name: lbl_status.config(text=f"Đã dừng: {n}"))
        root.after(0, lambda: set_run_button_state(False))

def stop_clone():
    global current_process, running_name
    if current_process is None:
        return
    name = running_name
    try:
        current_process.terminate()
        try:
            current_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            current_process.kill()
    except Exception:
        pass
    current_process = None
    running_name = ""
    root.after(0, lambda n=name: lbl_status.config(text=f"Đã dừng: {n}"))
    root.after(0, lambda: set_run_button_state(False))

def run_selected():
    global current_process, running_name
    if update_busy or is_locked:
        return
    selected = combo.get()
    if not selected:
        return

    name = selected.split("] ", 1)[1] if "] " in selected else selected

    if current_process and current_process.poll() is None:
        stop_clone()
        return

    tool_path = next((t["path"] for t in tools if t["name"] == name), None)

    if tool_path and os.path.exists(tool_path):
        try:
            btn_run.config(state="disabled")
            
            tool_dir = os.path.dirname(tool_path)
            current_process = subprocess.Popen(tool_path, cwd=tool_dir)
            running_name = name
            save_last_tool(selected)
            lbl_status.config(text=f"Đang chạy: {name}  (F6 dừng)")
            set_run_button_state(True)
            
            threading.Thread(target=monitor_process, args=(current_process, name), daemon=True).start()
            
            root.after(1000, lambda: btn_run.config(state="normal"))
        except Exception as e:
            lbl_status.config(text=f"Lỗi: {str(e)[:25]}")
            btn_run.config(state="normal")
            set_run_button_state(False)
    else:
        lbl_status.config(text="Không tìm thấy file tool!")

# ══════════════════════════════════════════════════════════════════════════════
#  UPDATE
# ══════════════════════════════════════════════════════════════════════════════

def run_update():
    global update_busy
    if update_busy:
        return
    stop_clone()
    update_busy = True
    btn_update.config(state="disabled")
    btn_run.config(state="disabled")
    lbl_status.config(text="Đang tải... 0%")
    progress["value"] = 0

    def do_update():
        try:
            url = (f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
                   f"/archive/refs/heads/main.zip")
            temp_dir = tempfile.gettempdir()
            zip_path = os.path.join(temp_dir, "vualidon_repo.zip")

            # Setup unverified SSL context to prevent SSL verification failures on some machines
            ssl_context = ssl._create_unverified_context()
            
            # Setup Request with custom User-Agent to bypass GitHub's default Python agent blocker
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
            )
            
            with urllib.request.urlopen(req, context=ssl_context) as response, open(zip_path, 'wb') as out_file:
                totalsize = int(response.headers.get('content-length', 0))
                blocksize = 8192
                readsofar = 0
                while True:
                    block = response.read(blocksize)
                    if not block:
                        break
                    readsofar += len(block)
                    out_file.write(block)
                    if totalsize > 0:
                        pct = min(100, int(readsofar * 100 / totalsize))
                        root.after(0, lambda p=pct: _set_progress(p))
                    else:
                        root.after(0, lambda: lbl_status.config(text="Đang tải..."))

            root.after(0, lambda: lbl_status.config(text="Đang giải nén..."))

            extract_path = os.path.join(temp_dir, "vualidon_extract")
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
            os.makedirs(extract_path, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_path)

            root_folder = next(
                (os.path.join(extract_path, n)
                 for n in os.listdir(extract_path)
                 if os.path.isdir(os.path.join(extract_path, n))),
                extract_path)

            init_data_dirs()

            src_a = os.path.join(root_folder, "A")
            src_b = os.path.join(root_folder, "B")
            ver_src = os.path.join(root_folder, "version.txt")

            if os.path.exists(src_a):
                if os.path.exists(DIR_A): shutil.rmtree(DIR_A)
                shutil.copytree(src_a, DIR_A)

            if os.path.exists(src_b):
                if os.path.exists(DIR_B): shutil.rmtree(DIR_B)
                shutil.copytree(src_b, DIR_B)

            # Write new local version
            if os.path.exists(ver_src):
                with open(ver_src, "r") as f:
                    write_local_version(f.read().strip())

            try:
                os.remove(zip_path)
                shutil.rmtree(extract_path)
            except Exception:
                pass

            root.after(0, _update_success)

        except Exception as e:
            root.after(0, lambda err=str(e): _update_failed(err))

    threading.Thread(target=do_update, daemon=True).start()

def _set_progress(pct):
    progress["value"] = pct
    lbl_status.config(text=f"Đang tải... {pct}%")

def _update_success():
    global update_busy
    update_busy = False
    progress["value"] = 100
    local_ver = read_local_version()
    lbl_status.config(text=f"✅ Cập nhật thành công! (v{local_ver})")
    lbl_version.config(text=f"v{local_ver}")
    btn_update.config(state="normal")
    unlock_ui()
    load_all_tools()
    # Hide Desktop A/B silently after update
    threading.Thread(target=hide_desktop_folders, daemon=True).start()

def _update_failed(reason=""):
    global update_busy
    update_busy = False
    progress["value"] = 0
    short = reason[:26] if reason else "Lỗi kết nối"
    lbl_status.config(text=f"❌ Thất bại: {short}")
    btn_update.config(state="normal")
    if not is_locked:
        btn_run.config(state="normal")

def reset_tool():
    if is_locked:
        return
    stop_clone()
    load_all_tools()

# ══════════════════════════════════════════════════════════════════════════════
#  UI BUILD
# ══════════════════════════════════════════════════════════════════════════════
root = tk.Tk()
root.title("Vualidon")
root.geometry("250x160")
root.resizable(False, False)
root.configure(bg="#0B0813")

# Force window mapping so it has a valid window ID for DWM
root.update()

# Enable dark title bar for Windows 10/11
try:
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    for attr in (20, 19):
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attr, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
except Exception:
    pass

# Load and set application icon using PIL
icon_path = os.path.join(SCRIPT_DIR, "vualidon_icon.png")
icon_photo = None
bg_photo = None

if os.path.exists(icon_path):
    try:
        from PIL import Image, ImageTk, ImageEnhance
        img_raw = Image.open(icon_path)
        icon_photo = ImageTk.PhotoImage(img_raw)
        root.iconphoto(True, icon_photo)
        
        # Create a dimmed background image (18% brightness for high contrast with widgets)
        bg_img = img_raw.resize((250, 160), Image.Resampling.LANCZOS)
        enhancer = ImageEnhance.Brightness(bg_img)
        bg_img_dark = enhancer.enhance(0.18)
        bg_photo = ImageTk.PhotoImage(bg_img_dark)
    except Exception:
        pass

canvas = tk.Canvas(root, width=250, height=160, bg="#0B0813", highlightthickness=0)
canvas.place(x=0, y=0)

# Draw background image if loaded
if bg_photo is not None:
    canvas.create_image(0, 0, image=bg_photo, anchor="nw")
    canvas.image = bg_photo

canvas.create_rectangle(1, 1, 249, 159, outline="#0B0813", width=1)
canvas.create_rectangle(2, 2, 248, 158, outline="#381D5C", width=2)
canvas.create_line(15, 30, 235, 30, fill="#E0115F", width=1)

lbl_title = tk.Label(root, text="VUA LÌ ĐÒN", bg="#0B0813", fg="#FF007F",
                     font=("Century Gothic", 10, "bold"), anchor="w")
lbl_title.place(x=15, y=6, width=160, height=20)

lbl_version = tk.Label(root, text=f"v{read_local_version()}", bg="#0B0813", fg="#AEB8C6",
                       font=("Segoe UI", 8, "bold"), anchor="e")
lbl_version.place(x=185, y=6, width=50, height=20)

style = ttk.Style()
style.theme_use('clam')
style.configure("TCombobox",
                fieldbackground="#181026", background="#381D5C",
                foreground="#FFFFFF", arrowcolor="#E0115F",
                bordercolor="#381D5C", darkcolor="#181026", lightcolor="#381D5C")
style.map("TCombobox",
          fieldbackground=[("readonly", "#181026"), ("disabled", "#0F0A18")],
          foreground=[("readonly", "#FFFFFF"), ("disabled", "#555555")],
          arrowcolor=[("readonly", "#E0115F"), ("disabled", "#555555")])

# Custom styling for Combobox dropdown Listbox
root.option_add('*TCombobox*Listbox.background', '#181026')
root.option_add('*TCombobox*Listbox.foreground', '#FFFFFF')
root.option_add('*TCombobox*Listbox.selectBackground', '#E0115F')
root.option_add('*TCombobox*Listbox.selectForeground', '#FFFFFF')
root.option_add('*TCombobox*Listbox.font', ('Segoe UI', 9))
root.option_add('*TCombobox*Listbox.borderWidth', 0)
root.option_add('*TCombobox*Listbox.highlightThickness', 0)

combo = ttk.Combobox(root, style="TCombobox", state="readonly")
combo.place(x=15, y=38, width=220, height=24)
combo.bind("<Double-Button-1>", lambda e: run_selected())

# Hover helper
def add_hover(widget, hover_bg, normal_bg):
    def on_enter(e):
        if widget.cget("state") != "disabled":
            widget.config(bg=hover_bg)
    def on_leave(e):
        if widget.cget("state") != "disabled":
            widget.config(bg=normal_bg)
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

btn_update = tk.Button(root, text="Update", bg="#1E1636", fg="#AEB8C6",
                       activebackground="#322557", activeforeground="#FFFFFF",
                       bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2",
                       command=run_update)
btn_update.place(x=15, y=72, width=80, height=28)
add_hover(btn_update, "#322557", "#1E1636")

btn_reset = tk.Button(root, text="↻", bg="#1E1636", fg="#AEB8C6",
                      activebackground="#322557", activeforeground="#FFFFFF",
                      bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2",
                      command=reset_tool)
btn_reset.place(x=100, y=72, width=32, height=28)
add_hover(btn_reset, "#322557", "#1E1636")

btn_run = tk.Button(root, text="▶ RUN", bg="#E0115F", fg="#FFFFFF",
                    activebackground="#FF3399", activeforeground="#FFFFFF",
                    bd=0, font=("Segoe UI", 9, "bold"), cursor="hand2",
                    command=run_selected)
btn_run.place(x=138, y=72, width=97, height=28)
add_hover(btn_run, "#FF3399", "#E0115F")

def set_run_button_state(running):
    if running:
        btn_run.config(text="■ STOP", bg="#C82333", fg="#FFFFFF")
        btn_run.bind("<Enter>", lambda e: btn_run.config(bg="#E03546") if btn_run.cget("state") != "disabled" else None)
        btn_run.bind("<Leave>", lambda e: btn_run.config(bg="#C82333") if btn_run.cget("state") != "disabled" else None)
    else:
        btn_run.config(text="▶ RUN", bg="#E0115F", fg="#FFFFFF")
        btn_run.bind("<Enter>", lambda e: btn_run.config(bg="#FF3399") if btn_run.cget("state") != "disabled" else None)
        btn_run.bind("<Leave>", lambda e: btn_run.config(bg="#E0115F") if btn_run.cget("state") != "disabled" else None)

lbl_status = tk.Label(root, text="Đang kiểm tra...", bg="#0B0813", fg="#00FFFF",
                      font=("Segoe UI", 8, "bold"), anchor="center")
lbl_status.place(x=15, y=106, width=220, height=18)

style.configure("Custom.Horizontal.TProgressbar",
                thickness=5, troughcolor="#0B0813", background="#E0115F",
                bordercolor="#0B0813", lightcolor="#E0115F", darkcolor="#E0115F")
progress = ttk.Progressbar(root, style="Custom.Horizontal.TProgressbar",
                            orient="horizontal", mode="determinate")
progress.place(x=15, y=134, width=220, height=5)

# ══════════════════════════════════════════════════════════════════════════════
#  RGB DUAL-PHASE ANIMATION
# ══════════════════════════════════════════════════════════════════════════════
def update_rgb():
    global irgb_index
    irgb_index = (irgb_index + 1) % len(ARGB)
    c1 = ARGB[irgb_index]
    c2 = ARGB[(irgb_index + 6) % len(ARGB)]   # opposite in wheel
    lbl_title.config(fg=c1)
    lbl_status.config(fg=c2)
    root.after(180, update_rgb)

# ══════════════════════════════════════════════════════════════════════════════
#  HOTKEYS
# ══════════════════════════════════════════════════════════════════════════════
def toggle_visibility():
    global window_visible
    if window_visible:
        root.withdraw()
        window_visible = False
    else:
        root.deiconify()
        root.attributes('-topmost', True)
        root.attributes('-topmost', False)
        window_visible = True

def run_hotkey_listener():
    if not user32.RegisterHotKey(None, HK_F6,  0, VK_F6):
        print("[WARN] Không đăng ký được hotkey F6")
    if not user32.RegisterHotKey(None, HK_INS, 0, VK_INSERT):
        print("[WARN] Không đăng ký được hotkey Insert")
    try:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:   # WM_HOTKEY
                if msg.wParam == HK_F6:
                    root.after(0, stop_clone)
                elif msg.wParam == HK_INS:
                    root.after(0, toggle_visibility)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        user32.UnregisterHotKey(None, HK_F6)
        user32.UnregisterHotKey(None, HK_INS)

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup_temp_exes():
    # Clean A and B dirs
    for directory in [DIR_A, DIR_B]:
        if not os.path.exists(directory):
            continue
        try:
            for file in os.listdir(directory):
                if file.endswith(".exe"):
                    for sys_name in SYSTEM_NAMES:
                        if file.startswith(sys_name):
                            path = os.path.join(directory, file)
                            try:
                                os.remove(path)
                            except Exception:
                                pass
        except Exception:
            pass
            
    # Also clean Temp dir for old self-masqueraded EXEs of the GUI
    temp_dir = tempfile.gettempdir()
    try:
        for file in os.listdir(temp_dir):
            if file.endswith(".exe"):
                for sys_name in SYSTEM_NAMES:
                    if file.startswith(sys_name):
                        path = os.path.join(temp_dir, file)
                        try:
                            os.remove(path)
                        except Exception:
                            pass
    except Exception:
        pass

def on_closing():
    global current_process
    if current_process is not None:
        try:
            current_process.terminate()
            try:
                current_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                current_process.kill()
        except Exception:
            pass
    cleanup_temp_exes()
    root.destroy()

init_data_dirs()
cleanup_temp_exes()
load_all_tools()
update_rgb()

threading.Thread(target=run_hotkey_listener,    daemon=True).start()
threading.Thread(target=check_version_on_startup, daemon=True).start()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
