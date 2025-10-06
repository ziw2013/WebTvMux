# ===============================================
# build_macos.spec — Final Stable (Folder Fix)
# ===============================================

import os
import glob
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- Ensure build folder exists ---
build_dir = os.path.join("build", "build_macos")
os.makedirs(build_dir, exist_ok=True)
print(f"📁 Ensured build path: {build_dir}")

# --- Gather data files ---
root = os.path.abspath(".")
datas = []

for folder, dest in [("bin", "bin"), ("config", "config")]:
    folder_path = os.path.join(root, folder)
    if os.path.isdir(folder_path):
        for f in glob.glob(os.path.join(folder_path, "*")):
            if os.path.isfile(f):
                datas.append((os.path.abspath(f), dest))
print("\n📦 Including data files:")
for f, dest in datas:
    print(f"  - {f} → {dest}//")

# --- Hidden imports (minimal Qt) ---
hiddenimports = collect_submodules(
    "PySide6",
    filter=lambda m: not (
        m.startswith("PySide6.QtQml")
        or m.startswith("PySide6.QtQuick")
        or m.startswith("PySide6.QtWebEngine")
        or m.startswith("PySide6.QtMultimedia")
        or m.startswith("PySide6.QtCharts")
        or m.startswith("PySide6.QtDataVisualization")
        or m.startswith("PySide6.Qt3DCore")
        or m.startswith("PySide6.QtGraphs")
    ),
)

excluded_modules = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib",
    "PIL", "PyQt5", "pytest",
]

# --- Analysis ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
    name="build_macos",
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, name=app_name, console=False)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_name,
)

# --- Post Build: Create DMG ---
if __name__ == "__main__":
    import subprocess
    app_path = os.path.join("dist", f"{app_name}.app")
    dmg_path = os.path.join("dist", f"{app_name}.dmg")

    if os.path.isdir(app_path):
        print(f"📦 Creating DMG: {dmg_path}")
        subprocess.run(
            ["hdiutil", "create", "-volname", app_name, "-srcfolder", app_path, "-ov", "-format", "UDZO", dmg_path],
            check=False,
        )
        print(f"✅ DMG created successfully at: {dmg_path}")
    else:
        print(f"⚠️ Could not find {app_path}, skipping DMG creation.")
