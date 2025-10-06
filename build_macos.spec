# ===========================================
# build_macos.spec — Final Stable Universal Version
# ===========================================

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree, TOC

app_name = "WebTvMux"
entry_script = "main.py"

# --- Collect PySide6 submodules ---
hiddenimports = collect_submodules("PySide6")

# --- Exclude unused Qt modules to minimize size ---
excluded_modules = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtQuick3D", "PySide6.QtCharts",
    "PySide6.QtSql", "PySide6.QtShaderTools", "PySide6.QtGraphs",
]

# --- Include bin/ and config/ folders recursively ---
datas_list = []
if os.path.isdir("bin"):
    datas_list.append(("bin", "bin"))
if os.path.isdir("config"):
    datas_list.append(("config", "config"))

print("📦 Including folders recursively:")
for src, dest in datas_list:
    print(f"  - {src} → {dest}/")

# ✅ Convert folders into TOC using Tree()
datas = TOC([])
for src, dest in datas_list:
    if os.path.isdir(src):
        datas += Tree(src, prefix=dest).toc
    elif os.path.isfile(src):
        datas.append((src, dest))

# --- Core Analysis ---
a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=datas,
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
