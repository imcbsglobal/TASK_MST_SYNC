# build.py — one-click packager for TASK_MST_SYNC (GUI + Django backend)

import os
import sys
import subprocess
import shutil
import venv
import textwrap

# =============================================================================
# PROJECT SETTINGS
# =============================================================================
PROJECT_NAME = "TASK_MST_SYNC"          # Final EXE name
ENTRY_SCRIPT = "gui_launcher.py"        # GUI entry point
ICON_FILE = "TASK_MST.ico"              # ✅ EXE ICON

# (source, destination-inside-dist)
EXTRA_DATA = [
    ("config.json", "."),          # ✅ only config.json
    ("django_sync", "django_sync"),
    ("db.sqlite3", "."),            # optional starter DB
    ("TASK_MST.png", "."),          # UI logo
    ("TASK_MST.ico", "."),          # icon (runtime / backup)
]

REQUIREMENTS = [
    "pyinstaller",
    "Django",
    "psutil",
    "pyjwt",
    "pyodbc",
    "python-dotenv",
    "djangorestframework",
    "djangorestframework-simplejwt",
    "django-cors-headers",
]

# =============================================================================
# PATHS
# =============================================================================
DIST_ROOT = f"{PROJECT_NAME.lower()}_dist"
BUILD_DIR = "build"
DIST_DIR = "dist"
VENV_DIR = ".buildvenv"

# =============================================================================
# HELPERS
# =============================================================================
def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)

def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        print("🔧 Creating build virtualenv...")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    return (
        os.path.join(VENV_DIR, "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(VENV_DIR, "bin", "python")
    )

def pip_install(py):
    print("📦 Installing dependencies...")
    run([py, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"])
    run([py, "-m", "pip", "install", *REQUIREMENTS])

    if os.path.exists("requirements.txt"):
        run([py, "-m", "pip", "install", "-r", "requirements.txt"])

def add_data_arg(src, dst):
    sep = ";" if os.name == "nt" else ":"
    return f"{src}{sep}{dst}"

def copy_extra(dist_root):
    for src, dst in EXTRA_DATA:
        if not os.path.exists(src):
            continue

        if os.path.isdir(src):
            target = os.path.join(dist_root, dst)
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            target_dir = dist_root if dst == "." else os.path.join(dist_root, dst)
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(target_dir, os.path.basename(src)))

# =============================================================================
# BUILD
# =============================================================================
def build():
    py = ensure_venv()
    pip_install(py)

    # Clean previous builds (VERY IMPORTANT for icon refresh)
    for p in (BUILD_DIR, DIST_DIR, DIST_ROOT, f"{PROJECT_NAME}.spec"):
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)

    # --add-data args
    add_data = []
    for src, dst in EXTRA_DATA:
        if os.path.exists(src):
            add_data += ["--add-data", add_data_arg(src, dst)]

    # Django safety
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_sync.settings")

    # ================= PYINSTALLER COMMAND =================
    cmd = [
        py, "-m", "PyInstaller",
        "--onefile",
        "--windowed",                      # ✅ no console
        f"--name={PROJECT_NAME}",
        f"--icon={ICON_FILE}",             # ✅ EXE ICON

        "--collect-all", "django",
        "--collect-submodules", "django",
        "--collect-submodules", "django_sync",

        *add_data,
        ENTRY_SCRIPT,
    ]

    print("\n🚀 Building GUI EXE with icon...")
    run(cmd)

    # Final distribution folder
    os.makedirs(DIST_ROOT, exist_ok=True)

    exe_name = f"{PROJECT_NAME}.exe" if os.name == "nt" else PROJECT_NAME
    shutil.copy2(
        os.path.join(DIST_DIR, exe_name),
        os.path.join(DIST_ROOT, exe_name)
    )

    copy_extra(DIST_ROOT)

    # README
    with open(os.path.join(DIST_ROOT, "README.txt"), "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(f"""
        {PROJECT_NAME}
        =============================

        ▶ Double-click {exe_name} to start the UI.

        Included:
        - config.json
        - django_sync/
        - db.sqlite3 (optional)
        - TASK_MST.png
        - TASK_MST.ico

        You can edit config.json
        without rebuilding the EXE.
        """))

    print("\n✅ BUILD SUCCESSFUL")
    print("📦 Output folder:", os.path.abspath(DIST_ROOT))

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    try:
        build()
    except subprocess.CalledProcessError:
        print("\n❌ Build failed (PyInstaller error)")
        sys.exit(1)
    except Exception as e:
        print("\n❌ Build failed:", e)
        sys.exit(1)
