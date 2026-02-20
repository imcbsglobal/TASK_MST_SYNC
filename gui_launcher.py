import os
import sys
import threading
import socket
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import re

from PIL import Image, ImageTk

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

        if "running" in msg.lower():
            tag = "success"
        if "error" in msg.lower() or "exception" in msg.lower():
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

def update_status(running):
    if running:
        status_indicator.config(bg="#22c55e")
        status_label.config(text="ONLINE", fg="#22c55e")
        start_btn.config(state="disabled")
        stop_btn.config(state="normal")
    else:
        status_indicator.config(bg="#ef4444")
        status_label.config(text="OFFLINE", fg="#ef4444")
        start_btn.config(state="normal")
        stop_btn.config(state="disabled")

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

    if messagebox.askyesno(
        "Stop Service",
        "Are you sure you want to stop the service?\n\nAll connections will be closed."
    ):
        os._exit(0)

# ===============================
# GUI ROOT
# ===============================
root = tk.Tk()
root.title("TASK MST Sync Tool - Professional Edition")
root.geometry("1200x700")
root.configure(bg="#f8fafc")

try:
    root.iconbitmap(os.path.join(BASE_DIR, "TASK_MST.ico"))
except Exception:
    pass

# ===============================
# HEADER
# ===============================
header = tk.Frame(root, bg="#ffffff", height=140)
header.pack(fill="x")
header.pack_propagate(False)

header_inner = tk.Frame(header, bg="#ffffff")
header_inner.pack(fill="both", expand=True, padx=30, pady=20)

# ---- LEFT (LOGO + TITLE)
left = tk.Frame(header_inner, bg="#ffffff")
left.pack(side="left")

try:
    img = Image.open(os.path.join(BASE_DIR, "TASK_MST.png")).resize((48, 48))
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

status_card = tk.Frame(right, bg="#f1f5f9")
status_card.pack(padx=20, pady=12)

tk.Label(
    status_card,
    text="STATUS:",
    font=("Segoe UI", 9, "bold"),
    fg="#64748b",
    bg="#f1f5f9"
).pack(side="left", padx=(0, 10))

status_indicator = tk.Label(status_card, bg="#ef4444", width=2, height=1)
status_indicator.pack(side="left", padx=(0, 8))

status_label = tk.Label(
    status_card,
    text="OFFLINE",
    font=("Segoe UI", 11, "bold"),
    fg="#ef4444",
    bg="#f1f5f9"
)
status_label.pack(side="left")

# ===============================
# BUTTONS
# ===============================
btn_container = tk.Frame(root, bg="#f8fafc")
btn_container.pack(pady=20)

start_btn = tk.Button(
    btn_container,
    text="▶  Start Service",
    command=start_backend,
    bg="#22c55e",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    padx=25,
    pady=12,
    relief="flat",
    cursor="hand2"
)
start_btn.pack(side="left", padx=8)

stop_btn = tk.Button(
    btn_container,
    text="■  Stop Service",
    command=stop_backend,
    bg="#ef4444",
    fg="white",
    font=("Segoe UI", 10, "bold"),
    padx=25,
    pady=12,
    relief="flat",
    cursor="hand2",
    state="disabled"
)
stop_btn.pack(side="left")

# ===============================
# INFO CARDS
# ===============================
info = tk.Frame(root, bg="#f8fafc")
info.pack(fill="x", padx=30, pady=(0, 20))

tk.Label(
    info,
    text="🌐 Server Address",
    font=("Segoe UI", 10, "bold"),
    fg="#475569",
    bg="#f8fafc"
).pack(anchor="w")

tk.Label(
    info,
    text=f"http://{LOCAL_IP}:{PORT}",
    font=("Segoe UI", 14, "bold"),
    fg="#2563eb",
    bg="#f8fafc"
).pack(anchor="w")

# ===============================
# LOG AREA
# ===============================
log_container = tk.Frame(root, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
log_container.pack(fill="both", expand=True, padx=30, pady=(0, 20))

log_header = tk.Frame(log_container, bg="#f8fafc", height=45)
log_header.pack(fill="x")

tk.Label(
    log_header,
    text="📊 Server Activity Monitor",
    font=("Segoe UI", 11, "bold"),
    fg="#0f172a",
    bg="#f8fafc"
).pack(side="left", padx=15, pady=10)

log_frame = tk.Frame(log_container, bg="#0f172a")
log_frame.pack(fill="both", expand=True)

log = tk.Text(
    log_frame,
    bg="#0f172a",
    fg="#e2e8f0",
    font=("Consolas", 10),
    relief="flat",
    padx=15,
    pady=10
)
log.pack(fill="both", expand=True)

log.tag_config("success", foreground="#22c55e")
log.tag_config("error", foreground="#ef4444")
log.tag_config("info", foreground="#3b82f6")

# Redirect stdout/stderr
sys.stdout = Redirect(log)
sys.stderr = Redirect(log)

update_status(False)
log.insert(tk.END, "⚡ TASK MST Sync Tool initialized\n", "info")

root.mainloop()