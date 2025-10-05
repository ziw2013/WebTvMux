# ================================
# File: main.py
# ================================
import sys, json, subprocess
from pathlib import Path
from typing import Dict

from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import QMainWindow, QApplication, QTabWidget, QMessageBox, QFileDialog, QDialog

# Local imports
from prefs import PreferencesDialog
from utils import SettingsManager, FFMPEG, FFPROBE, YTDLP, load_languages
from tabs.download import DownloadTab
from tabs.mux import MuxTab
from tabs.demux import DemuxTab

if sys.platform == "win32":
    old_popen = subprocess.Popen

    def silent_popen(*args, **kwargs):
        # Always apply no-window flags unless overridden
        kwargs["startupinfo"] = kwargs.get("startupinfo") or subprocess.STARTUPINFO()
        kwargs["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return old_popen(*args, **kwargs)

    subprocess.Popen = silent_popen

class MainWindow(QMainWindow):
    settings_changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebTvMux")
        # Auto-resize based on screen resolution (80% of available screen)
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.8)
        h = int(screen.height() * 0.8)
        self.resize(w, h)
        self.setMinimumSize(900, 600)   # safe minimum size

        # Settings
        self.settings = SettingsManager()
        self.settings.load()

        # Tabs
        self.tabs = QTabWidget()
        self.tab_download = DownloadTab(self.settings)
        self.tab_mux = MuxTab(self.settings)
        self.tab_demux = DemuxTab(self.settings)
        self.tabs.addTab(self.tab_download, "Download")
        self.tabs.addTab(self.tab_mux, "Mux")
        self.tabs.addTab(self.tab_demux, "Demux")
        self.setCentralWidget(self.tabs)

        # Menu bar
        self._build_menu()

        # Status bar (read-only)
        self.status = self.statusBar()
        self._update_status_bar()

        # Wire updates
        self.tabs.currentChanged.connect(self._update_status_bar)
        self.settings_changed.connect(self._update_status_bar)
        # Tabs can emit when output dir changes
        self.tab_download.output_dir_changed.connect(self._update_status_bar)
        # self.tab_mux.output_dir_changed.connect(self._update_status_bar)
        #self.tab_demux.output_dir_changed.connect(self._update_status_bar)
        if hasattr(self.tab_mux, "output_dir_changed"):
            self.tab_mux.output_dir_changed.connect(self._update_status_bar)
        if hasattr(self.tab_demux, "output_dir_changed"):
            self.tab_demux.output_dir_changed.connect(self._update_status_bar)

    # ---- Menu ----
    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        act_prefs = file_menu.addAction("Preferences…")
        act_prefs.triggered.connect(self.open_prefs)
        file_menu.addSeparator()
        act_exit = file_menu.addAction("Exit")
        act_exit.triggered.connect(self.close)

        help_menu = menubar.addMenu("&Help")
        act_about = help_menu.addAction("About")
        act_about.triggered.connect(self.about)

    def open_prefs(self):
        dlg = PreferencesDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:   # ✅ correct
            self.settings.save()
            # push updates to tabs
            self.tab_download.refresh_settings()
            self.tab_mux.refresh_settings()
            self.tab_demux.refresh_settings()
            self.settings_changed.emit()

    def about(self):
        QMessageBox.information(self, "About WebTvMux",
            "WebTvMux — downloader, muxer, and demuxer for media files.\n"
            "Uses yt-dlp + ffprobe/ffmpeg.\n"
            "Status bar shows per-tab overwrite policy and output directory.")

    # ---- Status bar text ----
    def _update_status_bar(self):
        idx = self.tabs.currentIndex()
        tab_name = self.tabs.tabText(idx)
        policies: Dict[str, str] = self.settings.data.get("overwrite_policy", {})
        last_out_dirs: Dict[str, str] = self.settings.data.get("last_output_dir", {})
        key = tab_name.lower()
        pol = policies.get(key, "safe").capitalize()
        out_dir = last_out_dirs.get(key, str(Path.cwd()))
        self.status.showMessage(f"{tab_name} overwrite policy: {pol} | Output dir: {out_dir}")


def main():
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    # --- Sanity check for missing runtime files ---
    from pathlib import Path
    missing = []
    for name, path in [
        ("ffmpeg", FFMPEG),
        ("ffprobe", FFPROBE),
        ("yt-dlp", YTDLP),
    ]:
        if not Path(path).exists():
            missing.append(f"bin/{name}.exe")

    from utils import load_languages
    lang_data = load_languages()
    if not lang_data:
        missing.append("config/languages.json")

    if missing:
        QMessageBox.warning(
            None,
            "Missing dependencies",
            "Please copy these files next to the app before running:\n\n  - " + "\n  - ".join(missing)
        )

    w = MainWindow()
    w.show()

    # 🔑 Cleanup all workers on app exit
    app.aboutToQuit.connect(w.tab_download.cleanup_on_exit)
    app.aboutToQuit.connect(w.tab_mux.cleanup_on_exit)
    app.aboutToQuit.connect(w.tab_demux.cleanup_on_exit)
    sys.exit(app.exec())



if __name__ == "__main__":
    main()