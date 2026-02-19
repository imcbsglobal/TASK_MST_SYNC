#!/usr/bin/env python3
"""
SyncService — freeze-aware Django launcher

Usage style:
- Build once (PyInstaller).
- After that, only edit the external config.json.
- config.json contains ONLY "dsn".
- All other values are internal.
- Always auto-select IP and run migrations.
"""

import json
import os
import socket
import sys
from typing import List, Tuple

# ============================= INTERNAL CONSTANTS =============================
DB_UID = "dba"
DB_PWD = "(*$^)"
DEFAULT_PORT = 8000
DJANGO_SETTINGS = "django_sync.settings"

# ----------------------------- helpers ---------------------------------------
def _exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _strip_comment(s: str) -> str:
    if not isinstance(s, str):
        return s
    return s.split("#", 1)[0].strip()

# ----------------------------- config ----------------------------------------
def load_config(exe_dir: str) -> dict:
    cfg_path = os.path.join(exe_dir, "config.json")
    cfg = {
        "ip": "auto",
        "port": DEFAULT_PORT,
        "dsn": None,
        "settings": DJANGO_SETTINGS,
    }

    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            user = json.load(f) or {}
        cfg.update(user)

    if not cfg.get("dsn"):
        raise RuntimeError("DSN missing in config.json")

    cfg["dsn"] = _strip_comment(cfg["dsn"])
    return cfg

# ----------------------------- IP auto-pick ----------------------------------
def ipv4_candidates() -> list[str]:
    cands = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        cands.append(s.getsockname()[0])
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip != "127.0.0.1":
                cands.append(ip)
    except Exception:
        pass

    seen, uniq = set(), []
    for ip in cands:
        if ip not in seen:
            seen.add(ip)
            uniq.append(ip)
    return uniq

def select_bind_ip(port: int) -> Tuple[str, list[str]]:
    tried = []
    for ip in ipv4_candidates():
        tried.append(ip)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((ip, port))
            s.close()
            return ip, tried
        except Exception:
            pass
    tried.append("0.0.0.0")
    return "0.0.0.0", tried

# ----------------------------- Django setup ----------------------------------
def bootstrap_django(settings: str, proj_root: str):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)
    import django
    django.setup()

def apply_migrations():
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)

def run_server(bind_ip: str, port: int):
    from django.core.management import call_command
    call_command("runserver", f"{bind_ip}:{port}", use_reloader=False)

# ----------------------------- Main ------------------------------------------
def main():
    exe_dir = _exe_dir()
    cfg = load_config(exe_dir)

    # ENV (ONLY FROM config.json)
    os.environ["DB_DSN"] = cfg["dsn"]
    os.environ["DB_UID"] = DB_UID
    os.environ["DB_PWD"] = DB_PWD

    bootstrap_django(cfg.get("settings", DJANGO_SETTINGS), exe_dir)

    port = int(cfg.get("port", DEFAULT_PORT))
    bind_ip, _ = select_bind_ip(port)

    # 🔕 SILENT MIGRATION
    apply_migrations()

    # ✅ ONE clean log line only
    print(f"🟢 Backend running on http://{bind_ip}:{port}")

    run_server(bind_ip, port)

# ----------------------------- Entry -----------------------------------------
if __name__ == "__main__":
    main()
