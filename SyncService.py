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
import requests
from typing import List, Tuple

# ============================= INTERNAL CONSTANTS =============================
DB_UID = "dba"
DB_PWD = "(*$^)"
DEFAULT_PORT = 8000
DJANGO_SETTINGS = "django_sync.settings"

ACTIVATE_API     = "https://activate.imcbs.com/corporate-clientid/list/"
CLIENT_LIST_API  = "https://activate.imcbs.com/client-id-list/get-client-ids/"

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
        "client_id": None,
        "settings": DJANGO_SETTINGS,
    }

    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            user = json.load(f) or {}
        cfg.update(user)

    if not cfg.get("dsn"):
        raise RuntimeError("DSN missing in config.json")

    if not cfg.get("client_id"):
        raise RuntimeError("client_id missing in config.json")

    cfg["dsn"] = _strip_comment(cfg["dsn"])
    cfg["client_id"] = _strip_comment(cfg["client_id"])
    return cfg

# ----------------------------- LICENSE CHECK ---------------------------------
def is_task_mst_enabled(client_id: str) -> bool:
    try:
        res = requests.get(ACTIVATE_API, timeout=10)
        res.raise_for_status()
        payload = res.json()

        if not payload.get("success"):
            return False

        for corp in payload.get("data", []):
            for shop in corp.get("shops", []):
                if shop.get("client_id") == client_id:
                    return "TASK MST" in shop.get("projects", [])

        return False

    except Exception as e:
        print(f"License validation failed: {e}")
        return False

# ----------------------------- MISEL MATCH CHECK -----------------------------
def check_misel_company_match(client_id: str, dsn: str) -> bool:
    """
    Validates that DBA.misel.firm_name and address1 match the API's
    company_name and place for this client_id.
    Prints mismatch details to stdout (→ red in UI terminal).
    Returns True if everything matches, False on any mismatch/error.
    """
    # 1. Fetch the client list
    try:
        res = requests.get(CLIENT_LIST_API, timeout=10)
        res.raise_for_status()
        payload = res.json()
    except Exception as e:
        print(f"⚠️  Could not reach client-id-list API: {e}")
        # Non-fatal — allow startup if API is unreachable
        return True

    if not payload.get("status"):
        print("⚠️  Client-id-list API returned status=false — skipping misel check")
        return True

    # 2. Find this client_id in the list
    api_entry = None
    for entry in payload.get("data", []):
        if entry.get("client_id") == client_id:
            api_entry = entry
            break

    if api_entry is None:
        print(f"⚠️  client_id '{client_id}' not found in client-id-list API — skipping misel check")
        return True

    api_company = (api_entry.get("company_name") or "").strip()
    api_place   = (api_entry.get("place") or "").strip()

    # 3. Query DBA.misel for firm_name and address1
    try:
        try:
            import sqlanydb
        except ImportError:
            print("⚠️  sqlanydb not available — skipping misel check")
            return True

        conn = sqlanydb.connect(DSN=dsn, UID=DB_UID, PWD=DB_PWD)
        cur  = conn.cursor()
        cur.execute("SELECT firm_name, address1 FROM DBA.misel")
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️  Could not read DBA.misel for validation: {e}")
        # Non-fatal — allow startup if DB read fails here
        return True

    if row is None:
        print("⚠️  DBA.misel is empty — skipping company match check")
        return True

    db_firm    = (row[0] or "").strip()
    db_address = (row[1] or "").strip()

    # 4. Compare (case-insensitive)
    firm_ok    = db_firm.lower()    == api_company.lower()
    address_ok = db_address.lower() == api_place.lower()

    if firm_ok and address_ok:
        print(f"✅ Company verified: '{db_firm}' | '{db_address}'")
        return True

    # 5. Report mismatches
    if not firm_ok:
        print(f"❌ MISMATCH — firm_name: DB='{db_firm}'  |  API company_name='{api_company}'")
    if not address_ok:
        print(f"❌ MISMATCH — address1:  DB='{db_address}'  |  API place='{api_place}'")
    print("❌ ERROR: Company data mismatch detected — sync aborted. Please verify firm_name and address1 in DBA.misel.")
    return False


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

    # 🏢 MISEL COMPANY / ADDRESS VALIDATION  (runs first so mismatch always visible)
    misel_ok = check_misel_company_match(cfg["client_id"], cfg["dsn"])

    # 🔐 LICENSE VALIDATION
    if not is_task_mst_enabled(cfg["client_id"]):
        print("❌ Unauthorized client or TASK MST not enabled")
        sys.exit(1)

    if not misel_ok:
        sys.exit(1)

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