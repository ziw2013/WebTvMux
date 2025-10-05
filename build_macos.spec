# ===========================================
# build_macos.spec — WebTvMux (macOS Unsigned, Stable Build)
# ===========================================

import os
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect necessary PySide6 modules ---
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

# --- Exclude unused heavy Qt/Python modules ---
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

# --- Gather all absolute resource paths ---
root = os.path.abspath(".")
bin_dir = os.path.join(root, "bin")
config_dir = os.path.join(root, "config")

datas = []
for folder, dest in [(bin_dir, "bin"), (config_dir, "config")]:
    if os.path.isdir(folder):
        for f in glob.glob(os.path.join(folder, "*")):
            if os.path.isfile(f):
                datas.append((f, dest))

print("\n📦 Resources included in build:")
for src, dest in datas:
    print(f"  - {src} → {dest}/")

# --- Main analysis ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    hookspath=[],
    noarchive=False,
)

# --- Package Python bytecode ---
pyz = PYZ(a.pure)

# --- Create main executable ---
exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,
    icon=os.path.abspath("icon.icns") if os.path.exists("icon.icns") else None,
    bundle_identifier="com.webtvmux.app",
)

# --- Bundle into .app structure ---
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

# --- Auto-create DMG package ---
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
