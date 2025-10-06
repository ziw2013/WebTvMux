# ======================================================
# build_macos.spec — WebTvMux macOS Final Stable Build
# ======================================================

import os
import shutil
import glob
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

app_name = "WebTvMux"
entry_script = "main.py"
build_temp = os.path.join("dist", f"{app_name}_temp")
final_dist = os.path.join("dist", app_name)
app_bundle = os.path.join("dist", f"{app_name}.app")
dmg_path = os.path.join("dist", f"{app_name}.dmg")

# --- Clean build folders first ---
print("🧹 Cleaning previous build artifacts...")
for d in ["build", "dist"]:
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
os.makedirs(build_temp, exist_ok=True)

# --- Collect all needed PySide6 submodules ---
hiddenimports = collect_submodules("PySide6")

# --- Exclude heavy unused Qt modules ---
excluded_modules = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtQuick3D", "PySide6.QtCharts",
    "PySide6.QtSql", "PySide6.QtShaderTools", "PySide6.QtGraphs",
    "PySide6.QtQuick3DRuntimeRender"
]

# --- Add binary + config data ---
datas = []
def include_folder(src, dest):
    folder_path = os.path.abspath(src)
    if os.path.isdir(folder_path):
        for root, _, files in os.walk(folder_path):
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, folder_path)
                datas.append((full_path, os.path.join(dest, os.path.dirname(rel_path))))

include_folder("bin", "bin")
include_folder("config", "config")

print("📦 Including data files:")
for src, dest in datas:
    print(f"  - {src} → {dest}/")

# --- Main build phase ---
a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)

# --- Collect output to temp dir ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=os.path.basename(build_temp),
    destdir=os.path.dirname(build_temp),
)

# --- Post-build bundle creation ---
print("\n📦 Creating macOS .app bundle...")

def create_app_bundle():
    if os.path.exists(app_bundle):
        shutil.rmtree(app_bundle)
    os.makedirs(os.path.join(app_bundle, "Contents", "MacOS"), exist_ok=True)
    os.makedirs(os.path.join(app_bundle, "Contents", "Resources"), exist_ok=True)

    # Move collected app into Contents/MacOS
    shutil.move(build_temp, os.path.join(app_bundle, "Contents", "MacOS", app_name))

    # Write Info.plist
    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>{app_name}</string>
    <key>CFBundleDisplayName</key><string>{app_name}</string>
    <key>CFBundleExecutable</key><string>{app_name}</string>
    <key>CFBundleIdentifier</key><string>com.webtvmux.app</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
    <key>CFBundleShortVersionString</key><string>1.0.0</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>"""
    with open(os.path.join(app_bundle, "Contents", "Info.plist"), "w") as f:
        f.write(info_plist)

    print(f"✅ App bundle created: {app_bundle}")

    # --- Create .dmg ---
    print("📦 Creating DMG image...")
    os.system(f"hdiutil create -volname {app_name} -srcfolder '{app_bundle}' -ov -format UDZO '{dmg_path}'")
    print(f"✅ DMG created: {dmg_path}")

create_app_bundle()
print(f"\n🎉 Build complete! Output: {app_bundle} and {dmg_path}\n")
