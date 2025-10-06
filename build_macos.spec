# ===========================================
# build_macos.spec — WebTvMux (Final macOS Build)
# Ensures bin/ and config/ included inside Contents/MacOS/
# Optimized to reduce unnecessary Qt modules
# ===========================================

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Tree

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

# --- Exclude heavy or unused modules ---
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

# --- Include entire folders using Tree() ---
root = os.path.abspath(".")
datas = []
if os.path.isdir(os.path.join(root, "bin")):
    datas.append(Tree(os.path.join(root, "bin"), prefix="bin"))
if os.path.isdir(os.path.join(root, "config")):
    datas.append(Tree(os.path.join(root, "config"), prefix="config"))

print("\n📦 Including folders recursively:")
for d in datas:
    src_path = getattr(d, "path", "unknown")
    prefix = getattr(d, "prefix", "")
    print(f"  - {os.path.basename(src_path)} → {prefix}/")

# --- Core Analysis ---
a = Analysis(
    [entry_script],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excluded_modules,
    noarchive=False,
)

# --- Package Python bytecode ---
pyz = PYZ(a.pure)

# --- Build main executable ---
exe = EXE(
    pyz,
    a.scripts,
    name=app_name,
    console=False,  # True for debug mode
    strip=True,     # ✅ remove debug symbols
    upx=False,       # ✅ compress binary safely
)

# --- Create .app bundle directly ---
app_bundle = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon=None,  # Optional: replace with "icon.icns"
    bundle_identifier="com.webtvmux.app",
    info_plist={
        "CFBundleName": app_name,
        "CFBundleDisplayName": app_name,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleIdentifier": "com.webtvmux.app",
        "NSHighResolutionCapable": True,
    },
    datas=datas,  # ✅ embed bin/ and config folders directly inside Contents/MacOS/
)

print("\n✅ macOS .app build configured successfully — bin and config will be inside Contents/MacOS/")
