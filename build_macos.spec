# ===========================================
# build_macos.spec — WebTvMux (Final Stable Build)
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
        or m.startswith("PySide6.QtMultimedia")
        or m.startswith("PySide6.Qt3DRender")
        or m.startswith("PySide6.QtGraphs")
        or m.startswith("PySide6.QtPdf")
        or m.startswith("PySide6.QtShaderTools")
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

# --- Ensure build folder exists ---
os.makedirs("build/build_macos", exist_ok=True)
print("📁 Ensured build path: build/build_macos")

# --- Include required folders ---
root = os.path.abspath(".")
datas = []

for src, dest in [
    ("bin/ffmpeg", "bin"),
    ("bin/ffprobe", "bin"),
    ("bin/yt-dlp", "bin"),
    ("bin/yt-dlp_macos", "bin"),
    ("config/languages.json", "config"),
]:
    if os.path.exists(src):
        datas.append((os.path.abspath(src), dest))

print("📦 Including data files:")
for f, dest in datas:
    print(f"  - {f} → {dest}//")

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

exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,
    icon=None
)

# --- Collect into .app directly ---
app_bundle = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon=None,
    bundle_identifier="com.webtvmux.app",
    info_plist={
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)

# --- Output to dist/WebTvMux.app ---
coll = COLLECT(
    app_bundle,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=f"{app_name}_macos",  # prevent conflict with inner WebTvMux folder
)

print("\n✅ macOS build process configured successfully.")
