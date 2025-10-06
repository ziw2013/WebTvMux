# ===========================================
# build_macos.spec — WebTvMux Final macOS Build (PyInstaller ≥6.9 compatible)
# ===========================================

import os
import glob
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect PySide6 submodules ---
hiddenimports = collect_submodules("PySide6")

# --- Exclude heavy / unused Qt modules ---
excluded_modules = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtQuick3D", "PySide6.QtCharts",
    "PySide6.QtSql", "PySide6.QtShaderTools", "PySide6.QtGraphs",
]

# --- Build datas list manually ---
datas = []

def include_folder(folder, dest):
    """Recursively include all files from folder into datas."""
    folder_path = os.path.abspath(folder)
    if os.path.isdir(folder_path):
        for root, _, files in os.walk(folder_path):
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, folder_path)
                datas.append((full_path, os.path.join(dest, os.path.dirname(rel_path))))

# Add bin and config folders
include_folder("bin", "bin")
include_folder("config", "config")

print("📦 Including data files:")
for src, dest in datas:
    print(f"  - {src} → {dest}")

# --- Core Analysis ---
a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=datas,  # ✅ each entry is (src, dest)
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

# --- Build executable ---
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)

# --- Collect all outputs ---
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_name,
)

print("\n✅ Spec file parsed successfully. PyInstaller will now build.\n")
