# ===========================================
# build_macos.spec — WebTvMux (Lean & Stable Build)
# ===========================================

import os
import time
import shutil
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect minimal PySide6 subset ---
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

    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineQuick2", "PySide6.QtWebEngine", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQmlModels", "PySide6.QtQmlWorkerScript",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",

    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner",

    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",

    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
																  
    "PySide6.Qt3DLogic", "PySide6.Qt3DQuick", "PySide6.Qt3DQuickExtras", "PySide6.Qt3DQuickRender",
    "PySide6.QtGraphs", "PySide6.QtDataVisualization",

    "PySide6.QtOpenGL", "PySide6.QtShaderTools", "PySide6.QtQuick3D",
    "PySide6.QtQuick3DAssetImport", "PySide6.QtQuick3DRender", "PySide6.QtQuick3DUtils",
    "PySide6.QtQuick3DRuntimeRender", "PySide6.QtLocation",

    "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtCharts", "PySide6.QtSql",
    "PySide6.QtTextToSpeech", "PySide6.QtSerialPort", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPrintSupport",
]

# --- Clean old build/dist ---
for d in ["build", "dist"]:
    if os.path.exists(d):
        print(f"🧹 Removing old {d}/ folder...")
        shutil.rmtree(d, ignore_errors=True)
os.makedirs("build/build_macos", exist_ok=True)
os.makedirs("dist", exist_ok=True)

root = os.path.abspath(".")

# --- Base PyInstaller analysis ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=True,  # ✅ reduces duplication of modules
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)

# ✅ Use temporary folder to avoid recursion
app_temp_name = f"{app_name}_temp"

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # ✅ skip UPX for mac stability
    name=app_temp_name,
)

# ===================================================================
# 🏗️ Post-build optimization and bundle creation
# ===================================================================
def post_build():
    src_temp = os.path.join("dist", app_temp_name)
    final_folder = os.path.join("dist", app_name)
    app_path = os.path.join("dist", f"{app_name}.app")

    # Wait until folder exists
    for _ in range(30):
        if os.path.isdir(src_temp):
            break
        time.sleep(1)
    if not os.path.isdir(src_temp):
        print(f"❌ dist/{app_temp_name} not found or not a directory.")
        return

    # 🧹 Remove any preexisting file/folder
    if os.path.exists(final_folder):
        if os.path.isfile(final_folder):
            os.remove(final_folder)
        else:
            shutil.rmtree(final_folder, ignore_errors=True)

    # ✅ Rename temp → final
    shutil.move(src_temp, final_folder)
    print(f"✅ Renamed build folder: {app_temp_name} → {app_name}")

    # --- Copy bin/config into build ---
    for folder in ["bin", "config"]:
        if os.path.isdir(folder):
            dest = os.path.join(final_folder, folder)
            os.makedirs(dest, exist_ok=True)
            for f in glob.glob(os.path.join(folder, "*")):
                shutil.copy(f, dest)
                print(f"📦 Copied {f} → {dest}")
        else:
            print(f"⚠️ Missing local folder: {folder}")

    # --- Cleanup unused Qt frameworks ---
    qt_dir = os.path.join(final_folder, "PySide6")
    if os.path.isdir(qt_dir):
        print("🧹 Removing unused Qt frameworks...")
        for name in [
            "Qt3DCore", "Qt3DRender", "Qt3DExtras", "QtQml", "QtQuick",
            "QtWebEngineCore", "QtWebEngineWidgets", "QtWebChannel",
            "QtPdf", "QtMultimedia", "QtCharts", "QtSql", "QtSensors",
            "QtPositioning", "QtNfc", "QtLocation", "QtOpenGL",
        ]:
            path = os.path.join(qt_dir, f"{name}.dylib")
            if os.path.exists(path):
                os.remove(path)
                print(f"  🗑️ Removed {name}.dylib")

    # --- Strip debug symbols ---
    print("🔧 Stripping debug symbols from .dylib files...")
    os.system(f"find '{final_folder}' -name '*.dylib' -exec strip -S {{}} \\; 2>/dev/null || true")

    # --- Remove unneeded folders ---
    for sub in ["qml", "translations", "examples", "tests", "plugins"]:
        path = os.path.join(final_folder, sub)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            print(f"  🗑️ Removed {sub}/")

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

    # --- chmod binaries ---
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

    # --- Summary ---
    print("\n📁 Final .app structure:")
    os.system(f"find '{app_path}' -maxdepth 3")

# Only run post-build outside PyInstaller runtime
if os.environ.get("PYINSTALLER_RUNNING") != "true":
    post_build()
