# ===========================================
# build_macos.spec — WebTvMux (Optimized macOS Build)
# ===========================================

import os
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect essential PySide6 modules only ---
hiddenimports = collect_submodules(
    "PySide6",
    filter=lambda m: not (
        m.startswith("PySide6.QtWebEngine")
        or m.startswith("PySide6.QtQml")
        or m.startswith("PySide6.QtQuick")
        or m.startswith("PySide6.QtQuick3D")
        or m.startswith("PySide6.Qt3D")
        or m.startswith("PySide6.QtPdf")
        or m.startswith("PySide6.QtShaderTools")
        or m.startswith("PySide6.QtGraphs")
        or m.startswith("PySide6.QtMultimedia")
        or m.startswith("PySide6.Addons")
    ),
)

# --- Exclude heavy and unused modules ---
excluded_modules = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib",
    "PIL", "pytest", "PyQt5",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DExtras", "PySide6.QtDataVisualization",
    "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtPrintSupport",
    "PySide6.QtGraphs", "PySide6.QtQuick3D", "PySide6.QtShaderTools",
    "PySide6.QtPdf",
]

# --- Explicitly include binaries and config files ---
datas = [
    (os.path.join("bin", "ffmpeg"), "bin"),
    (os.path.join("bin", "ffprobe"), "bin"),
    (os.path.join("bin", "yt-dlp"), "bin"),
    (os.path.join("config", "languages.json"), "config"),
]

print("\n📦 Including resources:")
for f, dest in datas:
    print(f"  - {f} → {dest}/")

# --- Build analysis ---
a = Analysis(
    [entry_script],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

# --- Package Python code ---
pyz = PYZ(a.pure)

# --- Build the main executable ---
exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,  # set True for debugging
    strip=True,     # ✅ remove debug symbols (smaller)
    upx=True,       # ✅ compress binaries (safe on macOS arm64)
)

# --- Bundle into .app directly ---
app_bundle = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon=None,  # Optional: use "icon.icns" if available
    bundle_identifier="com.webtvmux.app",
    info_plist={
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleIdentifier": "com.webtvmux.app",
        "NSHighResolutionCapable": True,
    },
    datas=datas,  # ✅ embed bin/ and config/
)

print("\n✅ WebTvMux optimized .app build configuration ready.")
