# ===========================================
# build_macos.spec — Final Stable Mac Build (Tree fix)
# ===========================================

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect PySide6 submodules ---
hiddenimports = collect_submodules("PySide6")

# --- Exclude heavy / unused modules ---
excluded_modules = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtMultimedia",
    "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtSql",
    "PySide6.QtShaderTools", "PySide6.QtGraphs"
]

# --- Include bin/ and config/ recursively ---
datas = []
if os.path.isdir("bin"):
    datas.append(Tree("bin", prefix="bin"))
if os.path.isdir("config"):
    datas.append(Tree("config", prefix="config"))

print("📦 Including folders recursively:")
for d in datas:
    try:
        print(f"  - {os.path.basename(d.name)} → {d.prefix}/")
    except Exception:
        print(f"  - Tree({d.root}) → {d.prefix}/")

# --- Core Analysis ---
a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=[*datas],  # ✅ Unpack list directly; avoids nested tuples
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

print("\n✅ Build spec successfully parsed. PyInstaller will now proceed.\n")
