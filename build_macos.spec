# ===========================================
# build_macos.spec — Final Stable Version (fixed datas)
# ===========================================

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree

app_name = "WebTvMux"
entry_script = "main.py"

hiddenimports = collect_submodules("PySide6")

excluded_modules = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtMultimedia",
    "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtSql",
    "PySide6.QtShaderTools", "PySide6.QtGraphs"
]

# --- Include entire bin/ and config/ folders recursively ---
datas = []
if os.path.isdir("bin"):
    datas.append(Tree("bin", prefix="bin"))
if os.path.isdir("config"):
    datas.append(Tree("config", prefix="config"))

print("📦 Including folders recursively:")
for d in datas:
    print(f"  - {getattr(d, 'name', 'unknown')} → {d.prefix}/")

# --- Core build steps ---
a = Analysis(
    [entry_script],
    pathex=["."],
    binaries=[],
    datas=datas,   # ✅ Tree() objects directly, not tuples
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name=app_name)
