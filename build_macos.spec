# ===========================================
# build_macos.spec — WebTvMux (Fixed for GitHub Actions)
# ===========================================

import os
import glob
import shutil
from PyInstaller.utils.hooks import collect_submodules

app_name = "WebTvMux"
entry_script = "main.py"

# --- 1️⃣ Collect minimal PySide6 modules ---
hiddenimports = collect_submodules(
    "PySide6",
    filter=lambda m: not (
        m.startswith("PySide6.QtWebEngine")
        or m.startswith("PySide6.QtQml")
        or m.startswith("PySide6.QtQuick")
        or m.startswith("PySide6.QtQuick3D")
        or m.startswith("PySide6.QtQuick3DRuntimeRender")
        or m.startswith("PySide6.QtShaderTools")
        or m.startswith("PySide6.Qt3DRender")
        or m.startswith("PySide6.QtGraphs")
        or m.startswith("PySide6.QtPdf")
        or m.startswith("PySide6.QtMultimedia")
    ),
)

excluded_modules = [
    "tkinter", "numpy", "pandas", "scipy", "matplotlib", "pytest",
    "PIL", "PIL.ImageTk", "PyQt5",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuick3DRuntimeRender", "PySide6.QtShaderTools", "PySide6.Qt3DRender",
    "PySide6.Qt3DCore", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtMultimedia",
    "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtPrintSupport"
]

root = os.path.abspath(".")
datas = []
for folder, dest in [("bin", "bin"), ("config", "config")]:
    folder_path = os.path.join(root, folder)
    if os.path.isdir(folder_path):
        for f in glob.glob(os.path.join(folder_path, "*")):
            if os.path.isfile(f):
                datas.append((os.path.abspath(f), dest))

print("\n📦 Files to include:")
for f, dest in datas:
    print(f"  - {f} → {dest}/")

# --- Ensure build folder exists (fix for base_library.zip missing) ---
build_path = os.path.join("build", "build_macos")
os.makedirs(build_path, exist_ok=True)
print(f"📁 Ensured build path: {build_path}")

# --- Clean old outputs ---
for d in ["build", "dist"]:
    if os.path.exists(d):
        print(f"🧹 Removing old {d}/ folder...")
        shutil.rmtree(d, ignore_errors=True)

# --- Run analysis ---
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
exe = EXE(pyz, a.scripts, name=app_name, console=False)

app_temp = f"{app_name}_temp"
app_coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=app_temp,
)

# --- Post-build macOS bundle creation ---
def post_build():
    src_temp = os.path.join("dist", app_temp)
    app_path = os.path.join("dist", f"{app_name}.app")
    macos_folder = os.path.join(app_path, "Contents", "MacOS")

    print(f"\n📦 Creating macOS .app at {app_path}")
    shutil.rmtree(app_path, ignore_errors=True)
    os.makedirs(macos_folder, exist_ok=True)

    shutil.copytree(src_temp, macos_folder, dirs_exist_ok=True)

    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{app_name}</string>
  <key>CFBundleDisplayName</key><string>{app_name}</string>
  <key>CFBundleIdentifier</key><string>com.webtvmux.app</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>"""
    with open(os.path.join(app_path, "Contents", "Info.plist"), "w") as f:
        f.write(info_plist)

    print("🔏 Signing app ad-hoc...")
    os.system(f"codesign --force --deep --sign - '{app_path}' || true")

    dmg_path = os.path.join("dist", f"{app_name}.dmg")
    print("📀 Creating DMG...")
    os.system(
        f"hdiutil create -volname {app_name} "
        f"-srcfolder '{app_path}' -ov -format UDZO '{dmg_path}'"
    )

    shutil.rmtree(src_temp, ignore_errors=True)
    print("✅ Build complete — DMG ready.")

if __name__ == "__main__":
    post_build()
