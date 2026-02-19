import os
import sys
import threading
import socket
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import re

from PIL import Image, ImageTk   # ✅ for logo

# ===============================
# HIDE CONSOLE (WINDOWS)
# ===============================
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

# ===============================
# BASE DIR (EXE SAFE)
# ===============================
def base_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = base_dir()

# ===============================
# IMPORT BACKEND
# ===============================
import SyncService

PORT = 8000

# ===============================
# GET LOCAL IP
# ===============================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# ===============================
# STDOUT REDIRECT → UI LOG
# ===============================
class Redirect:
    def __init__(self, widget):
        self.widget = widget

    def write(self, msg):
        if not msg.strip():
            return

        ts = datetime.now().strftime("%H:%M:%S")

        tag = "info"
        if "running" in msg:
            tag = "success"
        if "ERROR" in msg or "Exception" in msg:
            tag = "error"

        self.widget.after(
            0,
            self.widget.insert,
            tk.END,
            f"[{ts}] {msg}\n",
            tag
        )
        self.widget.after(0, self.widget.see, tk.END)

    def flush(self):
        pass

# ===============================
# BACKEND CONTROL
# ===============================
backend_running = False

def start_backend():
    global backend_running
    if backend_running:
        return

    backend_running = True
    update_status(True)

    def run():
        global backend_running
        try:
            SyncService.main()
        except SystemExit:
            messagebox.showerror(
                "License Error",
                "Unauthorized client or TASK MST not enabled"
            )
        except Exception as e:
            log.insert(tk.END, f"❌ Backend crashed: {e}\n", "error")

        backend_running = False
        update_status(False)

    threading.Thread(target=run, daemon=True).start()

def stop_backend():
    if not backend_running:
        return
    if messagebox.askyesno("Stop Service", "Stop TASK MST Sync Service?"):
        os._exit(0)

def update_status(running):
    if running:
        status_dot.config(bg="#22c55e")
        status_lbl.config(text="ONLINE", fg="#22c55e")
    else:
        status_dot.config(bg="#ef4444")
        status_lbl.config(text="OFFLINE", fg="#ef4444")

# ===============================
# GUI ROOT
# ===============================
root = tk.Tk()
root.title("TASK MST Sync Tool")
root.geometry("1100x650")
root.configure(bg="#f8fafc")

# ✅ WINDOW / TASKBAR ICON
try:
    root.iconbitmap(os.path.join(BASE_DIR, "TASK_MST.ico"))
except Exception:
    pass

# ===============================
# HEADER
# ===============================
header = tk.Frame(root, bg="#ffffff", height=120)
header.pack(fill="x")
header.pack_propagate(False)

header_inner = tk.Frame(header, bg="#ffffff")
header_inner.pack(fill="both", expand=True, padx=30, pady=20)

# ---- LEFT (LOGO + TITLE)
left = tk.Frame(header_inner, bg="#ffffff")
left.pack(side="left")

try:
    img = Image.open(os.path.join(BASE_DIR, "TASK_MST.png")).resize((60, 60))
    logo_img = ImageTk.PhotoImage(img)
    logo_lbl = tk.Label(left, image=logo_img, bg="#ffffff")
    logo_lbl.image = logo_img
    logo_lbl.pack(side="left", padx=(0, 15))
except Exception:
    pass

title_box = tk.Frame(left, bg="#ffffff")
title_box.pack(side="left")

tk.Label(
    title_box,
    text="TASK MST SYNC TOOL",
    font=("Segoe UI", 22, "bold"),
    fg="#0f172a",
    bg="#ffffff"
).pack(anchor="w")

tk.Label(
    title_box,
    text="Professional Data Synchronization Service",
    font=("Segoe UI", 11),
    fg="#64748b",
    bg="#ffffff"
).pack(anchor="w")

# ---- RIGHT (STATUS)
right = tk.Frame(header_inner, bg="#ffffff")
right.pack(side="right")

status_dot = tk.Label(right, bg="#ef4444", width=2, height=1)
status_dot.pack(side="left", padx=(0, 6))

status_lbl = tk.Label(
    right,
    text="OFFLINE",
    font=("Segoe UI", 11, "bold"),
    fg="#ef4444",
    bg="#ffffff"
)
status_lbl.pack(side="left")

# ===============================
# BUTTONS
# ===============================
btns = tk.Frame(root, bg="#f8fafc")
btns.pack(pady=15)

tk.Button(
    btns,
    text="▶ Start Service",
    bg="#22c55e",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    padx=20,
    pady=10,
    relief="flat",
    command=start_backend
).pack(side="left", padx=8)

tk.Button(
    btns,
    text="■ Stop Service",
    bg="#ef4444",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    padx=20,
    pady=10,
    relief="flat",
    command=stop_backend
).pack(side="left")

# ===============================
# INFO
# ===============================
info = tk.Frame(root, bg="#f8fafc")
info.pack(fill="x", padx=30, pady=10)

tk.Label(
    info,
    text=f"Server URL: http://{LOCAL_IP}:{PORT}",
    font=("Segoe UI", 12, "bold"),
    fg="#2563eb",
    bg="#f8fafc"
).pack(anchor="w")

# ===============================
# LOG AREA
# ===============================
log_frame = tk.Frame(root, bg="#0f172a")
log_frame.pack(fill="both", expand=True, padx=30, pady=(10, 20))

log = tk.Text(
    log_frame,
    bg="#0f172a",
    fg="#e2e8f0",
    font=("Consolas", 10),
    relief="flat"
)
log.pack(fill="both", expand=True)

log.tag_config("success", foreground="#22c55e")
log.tag_config("error", foreground="#ef4444")
log.tag_config("info", foreground="#3b82f6")

# Redirect stdout/stderr
sys.stdout = Redirect(log)
sys.stderr = Redirect(log)

update_status(False)
log.insert(tk.END, "⚡ TASK MST Sync Tool ready\n", "info")

root.mainloop()
