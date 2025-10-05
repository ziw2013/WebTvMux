# ===========================================
# build_macos.spec — WebTvMux (macOS Unsigned Build)
# ===========================================

import os
import zipfile
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect only core PySide6 modules ---
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

# --- Exclude all unused modules ---
excluded_modules = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib",
    "PIL", "PIL.ImageTk", "PyQt5", "pytest",
    # Heavy Qt modules
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtMultimedia",
    "PySide6.Qt3DCore", "PySide6.QtGraphs",
    "PySide6.QtDataVisualization", "PySide6.QtOpenGL",
    "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtPrintSupport",
]

# --- Main Analysis ---
a = Analysis(
    [entry_script],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,
    bundle_identifier="com.webtvmux.app",
)

# --- Create macOS .app bundle ---
coll = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon=os.path.abspath("icon.icns"),
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

# --- Create DMG package automatically ---
dmg_path = os.path.join("dist", f"{app_name}.dmg")

def create_dmg():
    print(f"📦 Creating DMG at {dmg_path}")
    os.system(f"hdiutil create -volname {app_name} -srcfolder dist/{app_name}.app -ov -format UDZO {dmg_path}")

if os.path.exists(f"dist/{app_name}.app"):
    create_dmg()
    print("✅ DMG creation complete.")
else:
    print("⚠️ .app not found — PyInstaller may have failed.")
