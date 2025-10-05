# ===========================================
# build_macos.spec — WebTvMux (Final Fixed Inclusion)
# ===========================================

import os
import glob
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

# --- Excluded modules ---
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

# --- Gather data files ---
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

# --- Analysis ---
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

# --- Executable ---
exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,
    icon=os.path.abspath("icon.icns") if os.path.exists("icon.icns") else None,
)

# --- Collect everything into one folder ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_name,
)

# --- Now build macOS .app from collected folder ---
app_path = os.path.join("dist", f"{app_name}.app")
src_folder = os.path.join("dist", app_name)

def create_bundle():
    print(f"\n📦 Creating .app bundle at {app_path}")
    os.makedirs(os.path.join(app_path, "Contents", "MacOS"), exist_ok=True)
    os.makedirs(os.path.join(app_path, "Contents", "Resources"), exist_ok=True)

    # Move collected files into Contents/MacOS
    os.system(f"cp -R '{src_folder}/' '{app_path}/Contents/MacOS/'")

    # Create basic Info.plist
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
    with open(os.path.join(app_path, "Contents", "Info.plist"), "w") as f:
        f.write(info_plist)

    print("✅ .app bundle created successfully.")

    # --- Create DMG ---
    dmg_path = os.path.join("dist", f"{app_name}.dmg")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder '{app_path}' -ov -format UDZO '{dmg_path}'"
    )
    print(f"✅ DMG created: {dmg_path}")

create_bundle()
