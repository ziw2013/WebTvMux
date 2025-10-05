from pathlib import Path
from typing import List, Dict
import subprocess, json, datetime, re, sys, os

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QThread, Qt
from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QAbstractItemView, QComboBox, QCheckBox, QTextEdit,
    QHeaderView, QProgressBar, QSplitter
)

from utils import LANGS_639_2, normalize_lang_code, FFMPEG, FFPROBE, lang_for_mux, load_languages, CONFIG_DIR
from utils import verify_tools
verify_tools()

INSTALL_DIR = str(Path(sys.argv[0]).resolve().parent)

# Windows-only creation flags
CREATE_NO_WINDOW = 0
STARTUPINFO = None
if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
# ---- ffprobe cache ----
_ffprobe_cache: dict[str, dict] = {}

def probe_file(path: str) -> dict:
    """Probe a media file with ffprobe and cache results in memory (streams + duration)."""
    if path in _ffprobe_cache:
        return _ffprobe_cache[path]

    cmd = [
        FFPROBE, "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name:stream_tags=language,title:stream_disposition=default",
        "-of", "json", path
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        startupinfo=STARTUPINFO,
        creationflags=CREATE_NO_WINDOW
    )
    out, err = proc.communicate(timeout=6)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {err.strip() or proc.returncode}")

    try:
        info = json.loads(out or "{}")
    except Exception:
        info = {}

    _ffprobe_cache[path] = info
    return info

# ---------- Logging widget ----------
class LogView(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
    def append_line(self, text: str):
        self.append(text)

# ---------- Load Languages ----------
def load_languages(path: Path) -> Dict[str, str]:
    """
    Smart load of languages: merge built-ins and JSON.
    JSON is used only if it adds more entries than defaults.
    """
    base = dict(LANGS_639_2)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if len(data) > len(LANGS_639_2):
                    base.update(data)
                else:
                    for k, v in data.items():
                        base[k] = v
        except Exception as e:
            print(f"[load_languages] warning: {e}")
    if "und" not in base:
        base["und"] = "Undetermined"
    return base

# ---------- Guess language from filename ----------
def guess_lang_from_filename(path: str, default_lang: str = "eng") -> str:
    name = Path(path).stem.lower()
    m = re.search(r'[_\-.]([a-z]{2,3})(?:[_\-.]|$)', name)
    if m:
        return normalize_lang_code(m.group(1), default_lang)
    return default_lang
    
class _ProbeWorker(QtCore.QThread):
    progress = QtCore.Signal(int)           # 0-100
    result = QtCore.Signal(int, dict)       # (file_index, info_json)
    error = QtCore.Signal(int, str)         # (file_index, message)
    finished_all = QtCore.Signal()

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.files = list(files)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = max(1, len(self.files))
        for i, fpath in enumerate(self.files):
            if self._stop:
                break

            try:
                info = probe_file(fpath)
                self.result.emit(i, info)
            except Exception as e:
                self.error.emit(i, str(e))

            self.progress.emit(int((i + 1) * 100 / total))
        # Emit once when the loop completes (or stops)
        self.finished_all.emit()
        
class _MuxWorker(QtCore.QThread):
    success = QtCore.Signal()
    failed = QtCore.Signal(str)

    def __init__(self, cmd, parent=None):
        super().__init__(parent)
        self.cmd = cmd

    def run(self):
        for exe in (FFMPEG, FFPROBE):
            if not os.path.exists(exe):
                raise FileNotFoundError(
                    f"Required tool not found: {exe}\n"
                    "Make sure the 'bin' folder with ffmpeg.exe, ffprobe.exe, and yt-dlp.exe "
                    "is next to your WebTvMux.exe."
                )
        try:
            # Use Popen so we could later parse progress if desired
            proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=STARTUPINFO, creationflags=CREATE_NO_WINDOW)
            # We keep it simple: wait until done; no GUI blocking since we're in a thread
            _, err = proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(err.strip() or f"ffmpeg exited {proc.returncode}")
            self.success.emit()
        except Exception as e:
            self.failed.emit(str(e))


# ---------- Mux Tab ----------
class MuxTab(QWidget):
    output_dir_changed = QtCore.Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.lang_map: Dict[str, str] = load_languages(CONFIG_DIR / "languages.json")
        
        # Auto-watch languages.json for changes
        self.lang_watcher = QFileSystemWatcher()
        lang_path = str(CONFIG_DIR / "languages.json")
        if os.path.exists(lang_path):
            self.lang_watcher.addPath(lang_path)
        self.lang_watcher.fileChanged.connect(self.reload_languages)

        # Add a Reload Languages button
        self.reload_lang_btn = QPushButton("Reload Languages")
        self.reload_lang_btn.clicked.connect(self.reload_languages)
        self.files: List[str] = []

        # File list + controls
        self.file_table = QTableWidget(0, 1)
        self.file_table.setHorizontalHeaderLabels(["Input Files"])
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)  # allows manual resize
        header.setStretchLastSection(True)  # last column stretches if space left


        self.add_btn = QPushButton("Add Files")
        self.add_folder_btn = QPushButton("Add Folder")
        self.rm_btn = QPushButton("Remove Selected")
        self.clear_btn = QPushButton("Clear All")
        self.up_btn = QPushButton("Move Up")
        self.down_btn = QPushButton("Move Down")
        self.scan_btn = QPushButton("Detect Tracks")

        # Streams table
        self.streams_table = QTableWidget(0, 9)
        self.streams_table.setHorizontalHeaderLabels([
            "Include", "File#", "Path", "Stream#", "Type", "Codec", "Language", "Title", "Default?"
        ])
        self.streams_table.setWordWrap(True)  # enable wrapping globally
        self.streams_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.streams_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.file_table.setWordWrap(True)
        self.streams_table.setWordWrap(True)

        # Output controls
        self.out_edit, self.out_btn = QLineEdit(), QPushButton("Browse Output")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mkv", "mp4", "mov"])
        self.start_btn = QPushButton("Mux")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log = LogView()

        # --- Splitter-based UI ---
        splitter = QSplitter(QtCore.Qt.Vertical)

        # Top section (file controls + file table)
        top_widget = QWidget()
        top_layout = QVBoxLayout()
        file_controls = QHBoxLayout()
        file_controls.addWidget(self.add_btn)
        file_controls.addWidget(self.add_folder_btn)
        file_controls.addWidget(self.rm_btn)
        file_controls.addWidget(self.clear_btn)
        file_controls.addWidget(self.up_btn)
        file_controls.addWidget(self.down_btn)
        file_controls.addWidget(self.scan_btn)
        file_controls.addWidget(self.reload_lang_btn)
        top_layout.addLayout(file_controls)
        top_layout.addWidget(self.file_table)
        top_widget.setLayout(top_layout)

        # Middle section (streams)
        mid_widget = QWidget()
        mid_layout = QVBoxLayout()
        mid_layout.addWidget(self.streams_table)
        mid_widget.setLayout(mid_layout)

        # Bottom section (output + progress + log)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout()
        row_out = QHBoxLayout()
        row_out.addWidget(QLabel("Output"))
        row_out.addWidget(self.out_edit)
        row_out.addWidget(self.out_btn)
        row_out.addWidget(QLabel("Format"))
        row_out.addWidget(self.format_combo)
        bottom_layout.addLayout(row_out)
        bottom_layout.addWidget(self.start_btn)
        bottom_layout.addWidget(self.progress_bar)
        bottom_layout.addWidget(self.log)
        bottom_widget.setLayout(bottom_layout)

        splitter.addWidget(top_widget)
        splitter.addWidget(mid_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        # Connections
        self.add_btn.clicked.connect(self.add_file_dialog)
        self.add_folder_btn.clicked.connect(self.add_folder_dialog)
        self.rm_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.clear_all)
        self.up_btn.clicked.connect(self.move_up)
        self.down_btn.clicked.connect(self.move_down)
        self.scan_btn.clicked.connect(self.detect_tracks)
        self.out_btn.clicked.connect(lambda: self.pick_file(self.out_edit, save=True))
        self.start_btn.clicked.connect(self.do_mux)
        
        
    def refresh_settings(self):
        lod = self.settings.data.get("last_output_dir", {})
        out_dir = lod.get("mux") or INSTALL_DIR   # (mux tab example)
        self.out_edit.setText(out_dir)   

    # ----- File list helpers -----
    
    def _any_stream_selected(self) -> bool:
        """True if any stream row checkbox is checked."""
        for row in range(self.streams_table.rowCount()):
            w = self.streams_table.cellWidget(row, 0)
            if isinstance(w, QCheckBox) and w.isChecked():
                return True
        return False

    def _update_start_enabled(self):
        """Enable Start only when at least one stream is selected."""
        self.start_btn.setEnabled(self._any_stream_selected())

    def _add_file(self, f: str):
        if f not in self.files:
            self.files.append(f)
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            item = QTableWidgetItem(Path(f).name)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.file_table.setItem(row, 0, item)
            self.file_table.resizeRowsToContents()

    def add_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select input files")
        for f in files:
            self._add_file(f)
        # auto-rescan after adding
        self.detect_tracks()

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            folder_path = Path(folder)
            for ext in ("*.mp4", "*.mkv", "*.mov", "*.mp3", "*.aac", "*.wav", "*.flac"):
                for f in folder_path.glob(ext):
                    self._add_file(str(f))
            # auto-rescan after adding
            self.detect_tracks()


    def remove_selected(self):
        rows = sorted(set(i.row() for i in self.file_table.selectedIndexes()), reverse=True)
        for r in rows:
            self.file_table.removeRow(r)
            if 0 <= r < len(self.files):
                self.files.pop(r)
        self.detect_tracks()

    def move_up(self):
        r = self.file_table.currentRow()
        if r > 0:
            self.files[r-1], self.files[r] = self.files[r], self.files[r-1]
            text = self.file_table.item(r, 0).text()
            self.file_table.item(r, 0).setText(self.file_table.item(r-1, 0).text())
            self.file_table.item(r-1, 0).setText(text)
            self.file_table.setCurrentCell(r-1, 0)
            self.detect_tracks()

    def move_down(self):
        r = self.file_table.currentRow()
        if r < self.file_table.rowCount() - 1 and r >= 0:
            self.files[r+1], self.files[r] = self.files[r], self.files[r+1]
            text = self.file_table.item(r, 0).text()
            self.file_table.item(r, 0).setText(self.file_table.item(r+1, 0).text())
            self.file_table.item(r+1, 0).setText(text)
            self.file_table.setCurrentCell(r+1, 0)
            self.detect_tracks()

    def pick_file(self, widget: QLineEdit, save=False):
        if save:
            f, _ = QFileDialog.getSaveFileName(self, "Select output file")
        else:
            f, _ = QFileDialog.getOpenFileName(self, "Select file")
        if f:
            widget.setText(f)
            if save:
                self.output_dir_changed.emit()
                
    def clear_all(self):
        # Clear file list
        self.files.clear()
        self.file_table.setRowCount(0)

        # Clear streams table
        self.streams_table.setRowCount(0)

        # Clear output field
        self.out_edit.clear()

        # Reset progress bar
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Clear log
        self.log.clear()

        self.log.append_line("All inputs, streams, and logs cleared.")
                
    def cleanup_on_exit(self):
        # stop probe worker
        if hasattr(self, "_probe_worker") and self._probe_worker:
            try:
                self._probe_worker.stop()
                self._probe_worker.quit()
                self._probe_worker.wait()
            except Exception:
                pass
            self._probe_worker = None
        # stop mux worker
        if hasattr(self, "_mux_worker") and self._mux_worker:
            try:
                self._mux_worker.quit()
                self._mux_worker.wait()
            except Exception:
                pass
            self._mux_worker = None

    # ----- Detect streams -----
    def detect_tracks(self):
        # Clear old rows and run probe in background
        self.streams_table.setRowCount(0)
        if not self.files:
            return

        self.log.append_line("Scanning tracks… (non-blocking)")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Disable buttons during scan
        for btn in (self.add_btn, self.add_folder_btn, self.rm_btn, self.up_btn, self.down_btn, self.scan_btn, self.start_btn):
            btn.setEnabled(False)

        self._probe_worker = _ProbeWorker(self.files, self)
        self._probe_worker.progress.connect(self.progress_bar.setValue)

        def _on_result(fi, info):
            streams = (info or {}).get("streams", [])
            fpath = self.files[fi]
            for s in streams:
                stype = s.get("codec_type")
                if stype not in ("audio", "video"):
                    continue
                row = self.streams_table.rowCount()
                self.streams_table.insertRow(row)

                chk = QCheckBox(); chk.setChecked(True)
                self.streams_table.setCellWidget(row, 0, chk)
                self.streams_table.setItem(row, 1, QTableWidgetItem(str(fi)))
                item = QTableWidgetItem(Path(fpath).name)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                self.streams_table.setItem(row, 2, item)
                self.streams_table.setItem(row, 3, QTableWidgetItem(str(s.get("index"))))
                self.streams_table.setItem(row, 4, QTableWidgetItem(stype))
                self.streams_table.setItem(row, 5, QTableWidgetItem(s.get("codec_name", "")))

                fname_code = guess_lang_from_filename(fpath, self.settings.data.get("default_lang", "eng"))
                norm_code = normalize_lang_code(fname_code, self.settings.data.get("default_lang", "eng"))
                lang_name = self.lang_map.get(norm_code, self.lang_map.get("und", "Undetermined"))
                combo = QComboBox(); combo.addItems(list(self.lang_map.values()))
                try:
                    idx = list(self.lang_map.values()).index(lang_name)
                    combo.setCurrentIndex(idx)
                except ValueError:
                    pass
                combo.setEnabled(stype == "audio")
                self.streams_table.setCellWidget(row, 6, combo)

                title = s.get("tags", {}).get("title", "")
                self.streams_table.setItem(row, 7, QTableWidgetItem(title))
                disp_default = s.get("disposition", {}).get("default", 0)
                self.streams_table.setItem(row, 8, QTableWidgetItem("yes" if disp_default else ""))
            self.streams_table.resizeRowsToContents()

        def _on_error(fi, msg):
            self.log.append_line(f"ffprobe failed for {self.files[fi]}: {msg}")

        def _on_done():
            self.progress_bar.setValue(100)
            for btn in (self.add_btn, self.add_folder_btn, self.rm_btn, self.up_btn, self.down_btn, self.scan_btn, self.start_btn):
                btn.setEnabled(True)
            self.log.append_line("Track detection finished.")
            self._probe_worker = None

        self._probe_worker.result.connect(_on_result)
        self._probe_worker.error.connect(_on_error)
        self._probe_worker.finished_all.connect(_on_done)
        self._probe_worker.start()


    # ----- Mux command -----
    def do_mux(self):
        ext = self.format_combo.currentText()
        o = self.out_edit.text().strip()
        if not o:
            outdir = Path(self.settings.data.get("last_output_dir", {}).get("mux", Path.cwd())) / "mux"
            outdir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            first_name = Path(self.files[0]).stem if self.files else "mux"
            o = str(outdir / f"{first_name}_mux_{ts}.{ext}")
            self.out_edit.setText(o)
            self.output_dir_changed.emit()
        else:
            if not o.lower().endswith(f".{ext}"):
                o = str(Path(o).with_suffix(f".{ext}"))
                self.out_edit.setText(o)

        if not self.files:
            QMessageBox.warning(self, "Mux", "Please add input files")
            return

        cmd = [FFMPEG]
        for f in self.files:
            cmd.extend(["-i", f])

        maps, meta = [], []
        a_out_index, v_out_index = 0, 0

        for r in range(self.streams_table.rowCount()):
            chk = self.streams_table.cellWidget(r, 0)
            if not (chk and chk.isChecked()):
                continue
            fi = int(self.streams_table.item(r, 1).text())
            stream_idx = int(self.streams_table.item(r, 3).text())
            stype = self.streams_table.item(r, 4).text()
            maps.extend(["-map", f"{fi}:{stream_idx}"])

            if stype == "audio":
                fpath = self.streams_table.item(r, 2).text()
                fname_code = guess_lang_from_filename(fpath, self.settings.data.get("default_lang", "eng"))
                lang_name = self.streams_table.cellWidget(r, 6).currentText()
                dropdown_code = next((k for k, v in self.lang_map.items() if v == lang_name), fname_code)
                norm_code = normalize_lang_code(dropdown_code, self.settings.data.get("default_lang", "eng"))
                mux_code = lang_for_mux(norm_code)   # floor → ina
                meta.extend([f"-metadata:s:a:{a_out_index}", f"language={mux_code}"])
                a_out_index += 1
            elif stype == "video":
                v_out_index += 1

        if not maps:
            QMessageBox.warning(self, "Mux", "No tracks selected to mux")
            return

        cmd.extend(maps)
        cmd.extend(meta)
        cmd.extend(["-map_metadata", "-1", "-c", "copy", o])

        self.progress_bar.setRange(0, 0)  # indeterminate while running
        self.start_btn.setEnabled(False)

        self._mux_worker = _MuxWorker(cmd, self)
        def _done_ok():
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.log.append_line(f"Muxing complete: {o}")
            self.start_btn.setEnabled(True)
            self._mux_worker = None

        def _done_fail(msg):
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.log.append_line(f"Muxing failed: {msg}")
            self.start_btn.setEnabled(True)
            self._mux_worker = None

        self._mux_worker.success.connect(_done_ok)
        self._mux_worker.failed.connect(_done_fail)
        self._mux_worker.start()

    def reload_languages(self):
        """Reload languages from config/languages.json and refresh dropdowns."""
        new_map = load_languages(CONFIG_DIR / "languages.json")
        if not new_map:
            self.log.append_line("⚠️ No languages found in JSON; keeping defaults.")
            return

        old_count = len(self.lang_map)
        self.lang_map = new_map
        self.log.append_line(f"✅ Reloaded {len(new_map)} languages (was {old_count}).")

        # Refresh existing dropdowns in the streams table
        for row in range(self.streams_table.rowCount()):
            widget = self.streams_table.cellWidget(row, 6)
            if isinstance(widget, QComboBox):
                current = widget.currentText()
                widget.clear()
                widget.addItems(list(self.lang_map.values()))
                # Keep the previous language selected if still valid
                if current in self.lang_map.values():
                    widget.setCurrentText(current)
                else:
                    widget.setCurrentText(self.lang_map.get("eng", "English"))
