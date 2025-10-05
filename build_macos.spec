# ===========================================
# build_macos.spec — WebTvMux (Final Verified Build)
# ===========================================

import os
import glob
import time
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect minimal PySide6 modules ---
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

# --- Exclude unused / heavy modules ---
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

# --- Clean old build artifacts safely ---
for d in ["build", "dist"]:
    if os.path.exists(d):
        print(f"🧹 Removing old {d}/ folder...")
        os.system(f"rm -rf {d}")
    os.makedirs(d, exist_ok=True)

# --- Gather data files (bin + config) ---
root = os.path.abspath(".")
datas = []
for folder, dest in [("bin", "bin"), ("config", "config")]:
    folder_path = os.path.join(root, folder)
    if os.path.isdir(folder_path):
        for f in glob.glob(os.path.join(folder_path, "*")):
            if os.path.isfile(f):
                datas.append((os.path.abspath(f), dest))

print("\n📦 Files to include:")
for f, dest in datas:
    print(f"  - {f} → {dest}/")

# --- Ensure build directories exist (for GitHub Actions safety) ---
os.makedirs(os.path.join(root, "build"), exist_ok=True)
os.makedirs(os.path.join(root, "build", "build_macos"), exist_ok=True)  # critical fix
os.makedirs(os.path.join(root, "dist"), exist_ok=True)

# --- Main Analysis ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)

# --- Filter out invalid or recursive datas (Final Safe Fix) ---
valid_datas = []
for item in a.datas:
    src = item[0]
    dest = item[1]
    typecode = item[2] if len(item) > 2 else "DATA"

    # ✅ Skip if nonexistent or a directory
    if not os.path.exists(src) or not os.path.isfile(src):
        continue

    # ✅ Skip anything inside build/ or dist/ (prevents recursion)
    if "/dist/" in src or "/build/" in src:
        continue

    # ✅ Skip anything referencing WebTvMux output folder itself
    if src.endswith("WebTvMux") or "dist/WebTvMux" in src:
        continue

    valid_datas.append((src, dest, typecode))

print("\n✅ Final data entries included in COLLECT:")
for src, dest, _ in valid_datas:
    print(f"  - {src} → {dest}")

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    valid_datas,
    strip=False,
    upx=False,
    name=app_name,
)

# ===================================================================
# Post-build: Create .app bundle and DMG *after* PyInstaller finishes
# ===================================================================

def create_bundle():
    app_path = os.path.join("dist", f"{app_name}.app")
    src_folder = os.path.join("dist", app_name)

    # Wait until PyInstaller actually produces dist/WebTvMux
    for _ in range(30):
        if os.path.exists(src_folder):
            break
        time.sleep(1)

    if not os.path.exists(src_folder):
        print(f"⚠️ Skipping bundle creation — {src_folder} not found.")
        return

    print(f"\n📦 Creating .app bundle at {app_path}")
    os.makedirs(os.path.join(app_path, "Contents", "MacOS"), exist_ok=True)
    os.makedirs(os.path.join(app_path, "Contents", "Resources"), exist_ok=True)

    # Copy all collected files into Contents/MacOS
    os.system(f"cp -R '{src_folder}/' '{app_path}/Contents/MacOS/'")

    # --- Generate Info.plist ---
    info_plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>{app_name}</string>
    <key>CFBundleDisplayName</key><string>{app_name}</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>CFBundleIdentifier</key><string>com.webtvmux.app</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>'''
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "w") as f:
        f.write(info_plist)

    print(f"✅ Info.plist written: {plist_path}")
    print("✅ .app bundle created successfully.")

    # --- Create DMG safely ---
    dmg_path = os.path.join("dist", f"{app_name}.dmg")
    try:
        os.system(
            f"hdiutil create -volname {app_name} "
            f"-srcfolder '{app_path}' -ov -format UDZO '{dmg_path}'"
        )
        print(f"✅ DMG created: {dmg_path}")
    except Exception as e:
        print(f"⚠️ DMG creation failed: {e}")

# ✅ Only run bundle creation after build, not during PyInstaller import
if os.environ.get("PYINSTALLER_RUNNING") != "true":
    create_bundle()
