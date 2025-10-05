# ===========================================
# build_macos.spec — WebTvMux (macOS Unsigned Stable Build)
# ===========================================

import os
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect PySide6 modules safely ---
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

# --- Exclude unused or heavy modules ---
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

# --- Gather all resource files (absolute paths) ---
bin_files = [(os.path.abspath(f), "bin") for f in glob.glob("bin/*") if os.path.isfile(f)]
config_files = [(os.path.abspath(f), "config") for f in glob.glob("config/*") if os.path.isfile(f)]

print("\n📦 Files to include in build:")
for f, dest in bin_files + config_files:
    print(f"  - {f} → {dest}/")

# --- Analysis stage ---
a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=bin_files + config_files,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    hookspath=[],
    noarchive=False,
)

# --- Bundle pure Python modules ---
pyz = PYZ(a.pure)

# --- Create executable ---
exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,
    icon=os.path.abspath("icon.icns") if os.path.exists("icon.icns") else None,
    bundle_identifier="com.webtvmux.app",
)

# --- Bundle into macOS .app ---
coll = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon=os.path.abspath("icon.icns") if os.path.exists("icon.icns") else None,
    bundle_identifier="com.webtvmux.app",
    info_plist={
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSMinimumSystemVersion": "10.14",
        "NSHighResolutionCapable": True,
    },
)

# --- Create DMG automatically ---
dmg_path = os.path.join("dist", f"{app_name}.dmg")

def create_dmg():
    print(f"\n📦 Creating DMG at {dmg_path}\n")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder dist/{app_name}.app -ov -format UDZO {dmg_path}"
    )

if os.path.exists(f"dist/{app_name}.app"):
    create_dmg()
    print("✅ DMG creation complete.")
else:
    print("⚠️ .app not found — PyInstaller may have failed.")
