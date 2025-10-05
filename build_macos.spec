# ===========================================
# build_macos.spec — WebTvMux (macOS Unsigned Build)
# ===========================================

import os
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect only necessary PySide6 modules ---
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

# --- Excluded heavy/unused modules ---
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

# --- Gather data files from bin/ and config/ dynamically ---
bin_files = [(f, "bin") for f in glob.glob("bin/*")]
config_files = [(f, "config") for f in glob.glob("config/*")]

print("📦 Including resources:")
for f, dest in bin_files + config_files:
    print(f"  - {f} → {dest}/")

# --- Main analysis ---
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

# --- Bundle Python bytecode ---
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

# --- Bundle into .app ---
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

# --- Create DMG after build ---
dmg_path = os.path.join("dist", f"{app_name}.dmg")

def create_dmg():
    print(f"📦 Creating DMG at {dmg_path}")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder dist/{app_name}.app -ov -format UDZO {dmg_path}"
    )

if os.path.exists(f"dist/{app_name}.app"):
    create_dmg()
    print("✅ DMG creation complete.")
else:
    print("⚠️ .app not found — PyInstaller may have failed.")
