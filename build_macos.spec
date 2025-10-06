# ===========================================
# build_macos.spec — WebTvMux (Final Guaranteed Folder Build)
# ===========================================

import os
import time
import shutil
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Minimal PySide6 subset ---
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
os.makedirs("build/build_macos", exist_ok=True)

root = os.path.abspath(".")

# --- Analysis ---
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

# ✅ Use temporary name to avoid recursion
app_temp_name = f"{app_name}_temp"

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_temp_name,
)

# ===================================================================
# Post-build: rename folder, add bin/config, build .app + .dmg
# ===================================================================
def post_build():
    src_temp = os.path.join("dist", app_temp_name)
    final_folder = os.path.join("dist", app_name)
    app_path = os.path.join("dist", f"{app_name}.app")

    # Wait for temp folder
    for _ in range(30):
        if os.path.isdir(src_temp):
            break
        time.sleep(1)
    if not os.path.isdir(src_temp):
        print(f"❌ dist/{app_temp_name} not found or not a directory.")
        return

    # --- Rename to final name ---
    if os.path.exists(final_folder):
        shutil.rmtree(final_folder, ignore_errors=True)
    shutil.move(src_temp, final_folder)
    print(f"✅ Renamed build folder: {app_temp_name} → {app_name}")

    # --- Copy bin/config ---
    for folder in ["bin", "config"]:
        if os.path.isdir(folder):
            dest = os.path.join(final_folder, folder)
            os.makedirs(dest, exist_ok=True)
            for f in glob.glob(os.path.join(folder, "*")):
                shutil.copy(f, dest)
                print(f"📦 Copied {f} → {dest}")
        else:
            print(f"⚠️ Missing local folder: {folder}")

    # --- Create .app bundle ---
    print(f"\n📦 Creating .app bundle at {app_path}")
    os.makedirs(os.path.join(app_path, "Contents", "MacOS"), exist_ok=True)
    os.makedirs(os.path.join(app_path, "Contents", "Resources"), exist_ok=True)
    os.system(f"cp -R '{final_folder}/' '{app_path}/Contents/MacOS/'")

    # --- Info.plist ---
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
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "w") as f:
        f.write(plist)
    print(f"✅ Info.plist written: {plist_path}")

    # --- chmod bin files ---
    bin_path = os.path.join(app_path, "Contents", "MacOS", "bin")
    if os.path.isdir(bin_path):
        for file in os.listdir(bin_path):
            os.chmod(os.path.join(bin_path, file), 0o755)
            print(f"  ✅ chmod +x {file}")
    else:
        print("⚠️ bin folder not found inside .app")

    # --- Create DMG ---
    dmg_path = os.path.join("dist", f"{app_name}.dmg")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder '{app_path}' -ov -format UDZO '{dmg_path}'"
    )
    print(f"✅ DMG created: {dmg_path}")

    # --- Print tree summary ---
    print("\n📁 Final .app structure:")
    os.system(f"find '{app_path}' -maxdepth 3")

if os.environ.get("PYINSTALLER_RUNNING") != "true":
    post_build()
