# ===========================================
# build_macos.spec — WebTvMux (Simplified Non-Recursive macOS Build)
# ===========================================

import os
import time
import shutil
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- minimal PySide6 subset ---
hiddenimports = collect_submodules(
    "PySide6",
    filter=lambda m: not (
        m.startswith("PySide6.Addons")
        or m.startswith("PySide6.QtWebEngine")
        or m.startswith("PySide6.QtQml")
        or m.startswith("PySide6.QtQuick")
        or m.startswith("PySide6.QtQuick3D")
    ),
)

excluded_modules = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib",
    "PIL", "PIL.ImageTk", "PyQt5", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtMultimedia",
    "PySide6.Qt3DCore", "PySide6.QtGraphs",
    "PySide6.QtDataVisualization", "PySide6.QtOpenGL",
    "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtPrintSupport",
]

# --- Clean previous builds ---
for d in ["build", "dist"]:
    if os.path.exists(d):
        print(f"🧹 Removing old {d}/ folder...")
        shutil.rmtree(d, ignore_errors=True)
os.makedirs("dist", exist_ok=True)

root = os.path.abspath(".")

# --- Analysis without data (avoids recursion) ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)
app_coll = BUNDLE(exe, name=app_name)

# ===================================================================
# Post-build: copy bin/config, chmod, and build DMG
# ===================================================================

def post_build():
    src_folder = os.path.join("dist", app_name)
    app_path = os.path.join("dist", f"{app_name}.app")

    # Wait for PyInstaller output
    for _ in range(30):
        if os.path.exists(src_folder):
            break
        time.sleep(1)
    if not os.path.exists(src_folder):
        print(f"❌ Build folder not found: {src_folder}")
        return

    # --- copy bin + config into built folder ---
    for folder in ["bin", "config"]:
        if os.path.isdir(folder):
            dest = os.path.join(src_folder, folder)
            os.makedirs(dest, exist_ok=True)
            for f in glob.glob(os.path.join(folder, "*")):
                shutil.copy(f, dest)
                print(f"📦 Copied {f} → {dest}")

    # --- create .app bundle ---
    print(f"\n📦 Creating .app bundle at {app_path}")
    os.makedirs(os.path.join(app_path, "Contents", "MacOS"), exist_ok=True)
    os.makedirs(os.path.join(app_path, "Contents", "Resources"), exist_ok=True)
    os.system(f"cp -R '{src_folder}/' '{app_path}/Contents/MacOS/'")

    # Info.plist
    plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{app_name}</string>
  <key>CFBundleIdentifier</key><string>com.webtvmux.app</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>'''
    with open(os.path.join(app_path, "Contents", "Info.plist"), "w") as f:
        f.write(plist)

    # --- chmod binaries ---
    bin_path = os.path.join(app_path, "Contents", "MacOS", "bin")
    if os.path.isdir(bin_path):
        for file in os.listdir(bin_path):
            os.chmod(os.path.join(bin_path, file), 0o755)
            print(f"  ✅ chmod +x {file}")

    # --- create DMG ---
    dmg = os.path.join("dist", f"{app_name}.dmg")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder '{app_path}' -ov -format UDZO '{dmg}'"
    )
    print(f"✅ DMG created: {dmg}")

if os.environ.get("PYINSTALLER_RUNNING") != "true":
    post_build()
