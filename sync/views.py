import os
import jwt
import psutil
import subprocess
import sys
import json
import logging
from decimal import Decimal
from datetime import datetime, date, timedelta
from functools import wraps
from decimal import Decimal, ROUND_HALF_UP
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .sql_helper import get_connection, _get_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PAIR_PASSWORD = os.getenv("PAIR_PASSWORD", "IMC-MOBILE")

# ✅ Make JWT robust: default secret if env missing (so login won’t fail silently)
JWT_SECRET = os.getenv("JWT_SECRET") or "dev-secret-change-me"
JWT_ALGO   = os.getenv("JWT_ALGO", "HS256")


# ------------------ helpers ------------------
def _extract_token(request):
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        return None
    return hdr.split(" ", 1)[1]

def _decode(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        token = _extract_token(request)
        if not token:
            return JsonResponse({"detail": "Token missing"}, status=401)
        try:
            payload = _decode(token)
            request.userid = payload["sub"]
        except jwt.ExpiredSignatureError:
            return JsonResponse({"detail": "Token expired"}, status=401)
        except jwt.PyJWTError:
            return JsonResponse({"detail": "Invalid token"}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped

def _to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(str(x))
    except Exception:
        return None

def _coerce_date(v):
    """
    Accepts date objects, ISO strings 'YYYY-MM-DD', 'YYYY/MM/DD', or empty -> use today's date.
    SQL Anywhere understands DATE, but passing a Python date is safest.
    """
    if isinstance(v, date):
        return v
    if not v:
        return date.today()
    s = str(v).strip().replace("/", "-")
    # try common formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # fallback: today
    return date.today()


# ------------------ endpoints ------------------
@csrf_exempt
@require_http_methods(["POST"])
def pair_check(request):
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    logging.info("📱 Pair check request from: %s", data)

    if data.get("password") != PAIR_PASSWORD:
        logging.error("❌ Invalid password")
        return JsonResponse({"detail": "Invalid password"}, status=401)

    exe_name = "TASK_MST_SYNC.exe"
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(base_dir, exe_name)

    if not os.path.exists(exe_path):
        logging.error("❌ TASK_MST_SYNC.exe not found at %s", exe_path)
        return JsonResponse({"detail": "TASK_MST_SYNC.exe not found"}, status=404)

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and "TASK_MST_SYNC.exe" in proc.info["name"]:
                logging.info("🔄 SyncService already running (PID %s)", proc.info["pid"])
                return JsonResponse({"status": "success", "message": "SyncService already running", "pair_successful": True})
        except Exception:
            continue

    try:
        subprocess.Popen([exe_path], cwd=base_dir)
        logging.info("✅ SyncService started")
        return JsonResponse({"status": "success", "message": "SyncService launched successfully", "pair_successful": True})
    except Exception as e:
        logging.error("❌ Failed to start SyncService: %s", e)
        return JsonResponse({"detail": f"Failed to start sync service: {e}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    """
    POST { "userid": "...", "password": "..." }
    Fixes:
      • default JWT secret so encode never crashes
      • clearer error messages
    """
    try:
        data = json.loads(request.body or b"{}")
        userid = (data.get("userid") or "").strip()
        password = (data.get("password") or "").strip()
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    if not userid or not password:
        return JsonResponse({"detail": "userid & password required"}, status=400)

    logging.info("🔐 Login attempt for user: %s", userid)

    try:
        conn = get_connection()
        cur = conn.cursor()
        # SQL Anywhere compatible positional parameters (?)
        cur.execute("SELECT id, pass FROM acc_users WHERE id = ? AND pass = ?", (userid, password))
        row = cur.fetchone()
    except Exception as dbx:
        logging.exception("DB error during login")
        return JsonResponse({"detail": f"DB error: {dbx}"}, status=500)
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass

    if not row:
        logging.warning("❌ Invalid credentials")
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    payload = {"sub": userid, "exp": datetime.utcnow() + timedelta(days=7)}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    # PyJWT v2 returns a str already; in v1 it may be bytes
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    logging.info("✅ Login successful")
    return JsonResponse({"status": "success", "message": "Login successful", "user_id": row[0], "token": token})


@jwt_required
@require_http_methods(["GET"])
def verify_token(request):
    logging.info("✅ Token verified for user: %s", request.userid)
    return JsonResponse({"status": "success", "userid": request.userid})
@jwt_required
@require_http_methods(["GET"])
def data_download(request):
    logging.info("📥 Data download request")
    conn = get_connection()
    cur = conn.cursor()

    try:
        # MASTER DATA
        cur.execute("""
            SELECT code, name, place
            FROM acc_master
            WHERE super_code = 'SUNCR'
        """)
        master_rows = cur.fetchall()
        master_data = [
            {"code": r[0], "name": r[1], "place": r[2]}
            for r in master_rows
        ]

        # PRODUCT + BATCH
        cur.execute("""
            SELECT 
                p.code,
                p.name,
                pb.barcode,
                pb.quantity,
                pb.salesprice,
                pb.bmrp,
                pb.cost,
                pb.text1
            FROM acc_product p
            LEFT JOIN acc_productbatch pb
                ON p.code = pb.productcode
        """)
        product_rows = cur.fetchall()

        product_data = []

        for r in product_rows:
            barcode = r[2]

            # ❌ SKIP if barcode is NULL or empty
            if not barcode:
                continue

            product_data.append({
                "code": r[0],
                "name": r[1],
                "barcode": barcode,
                "quantity": _to_float(r[3]),
                "salesprice": _to_float(r[4]),
                "bmrp": _to_float(r[5]),
                "cost": _to_float(r[6]),
                "text1": r[7]
            })

        return JsonResponse({
            "status": "success",
            "master_data": master_data,
            "product_data": product_data
        })

    except Exception as e:
        logging.exception("data_download failed")
        return JsonResponse(
            {"detail": f"Failed to download: {e}"},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass





# ------------------------------------------------------------------
#  helper that returns the next PK for acc_purchaseorderdetails
# ------------------------------------------------------------------
def _next_detail_slno(cur):
    cur.execute("SELECT MAX(slno) FROM acc_purchaseorderdetails")
    row = cur.fetchone()[0]
    return int(row or 0) + 1


# ------------------------------------------------------------------
#  group flat rows into one entry (one master) by entry key
# ------------------------------------------------------------------
def _group_orders(raw_orders):
    """
    Normalizes 'orders' into a list of:
      { supplier_code, order_date, userid, otype, products:[{barcode,quantity,rate,mrp}, ...] }
    Supports:
      A) Already-grouped objects with 'products'
      B) Many flat rows for the same entry (entry_no/entryid/orderno)
    """
    if any(isinstance(o.get("products"), list) and o["products"] for o in raw_orders):
        normalized = []
        for o in raw_orders:
            products = o.get("products") or []
            if not products and all(k in o for k in ("barcode", "quantity", "rate", "mrp")):
                products = [{
                    "barcode":  o["barcode"],
                    "quantity": o["quantity"],
                    "rate":     o["rate"],
                    "mrp":      o["mrp"]
                }]
            normalized.append({
                "supplier_code": o["supplier_code"],
                "order_date":    _coerce_date(o.get("order_date")),
                "userid":        o.get("userid"),
                "otype":         o.get("otype", "O"),
                "products":      products
            })
        return normalized

    # flat → grouped
    buckets = {}
    for r in raw_orders:
        key = (
            r.get("entry_no")
            or r.get("entryno")
            or r.get("entryid")
            or r.get("orderno")
            or f"{r.get('supplier_code')}|{r.get('order_date')}"
        )
        b = buckets.setdefault(key, {
            "supplier_code": r["supplier_code"],
            "order_date":    _coerce_date(r.get("order_date")),
            "userid":        r.get("userid"),
            "otype":         r.get("otype", "O"),
            "products":      []
        })
        b["products"].append({
            "barcode":  r["barcode"],
            "quantity": r["quantity"],
            "rate":     r["rate"],
            "mrp":      r["mrp"]
        })
    return list(buckets.values())








def _to_decimal(x, default="0"):
    """
    Safely coerce numbers into Decimal for money math.
    Returns Decimal(default) if x is None/invalid.
    """
    try:
        if x is None:
            return Decimal(default)
        if isinstance(x, Decimal):
            return x
        return Decimal(str(x))
    except Exception:
        return Decimal(default)

def _to_float(x, default=0.0):
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


# ------------------------------------------------------------------
#  upload_orders – ONE masterslno per logical entry (items share it)
# ------------------------------------------------------------------
@csrf_exempt
@jwt_required
@require_http_methods(["POST"])
def upload_orders(request):
    try:
        payload = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    rows = payload.get("orders") or []
    if not rows:
        return JsonResponse({"detail": "No orders supplied"}, status=400)

    logging.info("📤 Uploading %s rows to acc_purchaseorderdetails ONLY", len(rows))

    conn = get_connection()
    cur = conn.cursor()

    try:
        # 🔢 get last slno
        cur.execute("SELECT MAX(slno) FROM acc_purchaseorderdetails")
        last_slno = int(cur.fetchone()[0] or 0)

        inserted = []

        for row in rows:
            last_slno += 1

            slno        = last_slno
            masterslno = -1000                        # ✅ fixed value

            item    = (row.get("item") or "").strip()[:30]
            qty     = _to_decimal(row.get("qty"))
            remark  = row.get("remark")
            barcode = (row.get("barcode") or "").strip()
            date1   = _coerce_date(row.get("date1"))
            text1   = row.get("text1")
            mrp     = _to_decimal(row.get("mrp"))

            cur.execute("""
                INSERT INTO acc_purchaseorderdetails
                    (slno, masterslno, item, qty, remark,
                     barcode, date1, text1, mrp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slno,
                masterslno,
                item,
                float(qty),
                remark,
                barcode,
                date1,
                text1,
                float(mrp)
            ))

            inserted.append(slno)

        conn.commit()

        return JsonResponse({
            "status": "success",
            "message": "Details inserted successfully",
            "rows_inserted": len(inserted),
            "slno_list": inserted
        })

    except Exception as exc:
        conn.rollback()
        logging.exception("❌ Upload failed")
        return JsonResponse({"detail": f"Upload failed: {exc}"}, status=500)

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass










@require_http_methods(["GET"])
def get_status(request):
    cfg = _get_config()
    primary = cfg.get("ip", "unknown")
    all_ips = cfg.get("all_ips", [])
    return JsonResponse({
        "status": "online",
        "message": "SyncAnywhere server is running",
        "primary_ip": primary,
        "all_available_ips": all_ips,
        "connection_urls": [f"http://{ip}:8000" for ip in all_ips],
        "pair_password_hint": f"Password starts with: {PAIR_PASSWORD[:3]}...",
        "server_time": datetime.now().isoformat(),
        "instructions": {
            "mobile_setup": "Try connecting to any of the URLs listed in 'connection_urls'",
            "troubleshooting": [
                "Ensure both devices are on the same WiFi network",
                "Try each IP address if the first one doesn't work",
                "Check firewall settings on the server computer",
                "Verify port 8000 is not blocked"
            ]
        }
    })


@jwt_required
@require_http_methods(["GET"])
def get_product_details(request):
    """
    Returns combined product details from acc_product and acc_productbatch
    (joined on code = productcode)
    """
    logging.info("📦 Product details request")
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT 
                p.code, p.name, p.catagory, p.product, p.brand, p.unit, p.taxcode,
                pb.productcode, pb.barcode, pb.quantity, pb.cost, pb.bmrp,
                pb.salesprice, pb.secondprice, pb.thirdprice, pb.supplier, pb.expirydate
            FROM acc_product p
            LEFT JOIN acc_productbatch pb ON p.code = pb.productcode
            ORDER BY p.code
        """)

        rows = cur.fetchall()
        out = []

        for r in rows:
            expiry = r[16]
            if expiry:
                expiry = expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry)

            out.append({
                "code": r[0],
                "name": r[1],
                "catagory": r[2],
                "product": r[3],
                "brand": r[4],
                "unit": r[5],
                "taxcode": r[6],
                "productcode": r[7],
                "barcode": r[8],
                "quantity": _to_float(r[9]),
                "cost": _to_float(r[10]),
                "bmrp": _to_float(r[11]),
                "salesprice": _to_float(r[12]),
                "secondprice": _to_float(r[13]),
                "thirdprice": _to_float(r[14]),
                "supplier": r[15],
                "expirydate": expiry
            })

        return JsonResponse({
            "status": "success",
            "count": len(out),
            "data": out
        })

    except Exception as e:
        logging.exception("get_product_details failed")
        return JsonResponse(
            {"detail": f"Failed to fetch product details: {e}"},
            status=500
        )

    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass




# SELECT *
# FROM acc_purchaseorderdetails
# WHERE masterslno = -1000
# ORDER BY slno DESC;