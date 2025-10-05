from typing import List, Tuple, Optional, Dict
from pathlib import Path
import re
import urllib.request
from urllib.parse import urljoin
import datetime
import subprocess
import os, time

from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QAbstractItemView, QComboBox, QCheckBox,
    QTextEdit, QHeaderView, QProgressBar, QSplitter, QSpinBox
)
from PySide6.QtCore import QThread, Signal, QObject

from utils import verify_tools
verify_tools()

# If these utilities exist in your project, keep the import. Otherwise, remove or adapt.
try:
    from utils import (
        build_path_with_suffix, pick_video_suffix_from_format,
        normalize_lang_code, get_bin_path, FFMPEG, FFPROBE, YTDLP
    )
except Exception:
    # Fallback no-ops to keep the module importable if utils isn't present
    def build_path_with_suffix(path, *a, **k): return path
    def pick_video_suffix_from_format(*a, **k): return ".mp4"
    def normalize_lang_code(x): return x
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"
    YTDLP = "yt-dlp"
    

# ---------- Small log view ----------
# class LogView(QTextEdit):
    # def __init__(self, debug=False, logfile="download.log"):
        # super().__init__()
        # self.setReadOnly(True)
        # self.debug = debug
        # self.logfile = Path(logfile) if debug else None
        # if self.logfile:
            # try:
                # self.logfile.unlink()
            # except Exception:
                # pass

    # def append_line(self, t: str):
        # ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # line = f"[{ts}] {t}"
        # # QTextEdit::append must be called in the GUI thread; we only call this from slots
        # self.append(line)
        # if self.debug and self.logfile:
            # try:
                # with self.logfile.open("a", encoding="utf-8") as f:
                    # f.write(line + "\n")
            # except Exception:
                # pass
                
class LogView(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)

    def append_line(self, t: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append(f"[{ts}] {t}")


# ---------- yt-dlp logger ----------
class YTDlpLogger:
    def __init__(self, sink):
        self.sink = sink

    def debug(self, msg):
        if str(msg).strip():
            self.sink(str(msg))

    def info(self, msg):
        if str(msg).strip():
            self.sink(str(msg))

    def warning(self, msg):
        self.sink("WARNING: " + str(msg))

    def error(self, msg):
        self.sink("ERROR: " + str(msg))

# ---------- Worker ----------
class DownloadWorker(QObject):
    progress = Signal(int, str)  # (percent, label)
    log = Signal(str)
    finished = Signal(str)       # label
    cancelled = Signal(str)
    error = Signal(str, str)  # (msg, label)

    def __init__(self, opts, url, label=""):
        super().__init__()
        self.opts = dict(opts)
        self.url = url
        self.label = label
        self._cancelled = False
        self._proc = None

        # Ensure our hook is present, but do not assume any GUI objects
        hooks = list(self.opts.get("progress_hooks", []))
        hooks.append(self._progress_hook_emit_only)
        self.opts["progress_hooks"] = hooks

        # Make resume-friendly & safe defaults
        self.opts.setdefault("continuedl", True)    # continue partial downloads
        self.opts.setdefault("overwrites", False)   # don't overwrite existing
        self.opts.setdefault("nopart", False)       # use .part for robustness

    def cancel(self):
        """Request cancel gracefully, or kill process if running."""
        self._cancelled = True
        if self._proc and self._proc.poll() is None:  # still running
            try:
                self._proc.terminate()
            except Exception:
                try:
                    self._proc.kill()   # fallback (Windows etc.)
                except Exception:
                    pass


    # This hook is called by yt-dlp in the *worker* thread
    def _progress_hook_emit_only(self, d):
        # surface progress via signal; never touch GUI here
        if self._cancelled and d.get("status") == "downloading":
            raise Exception("Download cancelled by user")
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            done = d.get("downloaded_bytes", 0)
            pct = int(done * 100 / max(1, total))
            self.progress.emit(pct, self.label)
        elif d.get("status") == "finished":
            # 100% at finalize
            self.progress.emit(100, self.label)
            fn = d.get("filename")
            if fn:
                self.log.emit(f"Downloaded to {fn}")

    def run(self):
        try:
            # --- NEW: direct file bypass ---
            if self.url.lower().endswith((".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm")):
                self.log.emit(f"▶ Direct download: {self.label}")
                try:
                    import shutil
                    outfile = Path(self.opts["outtmpl"])
                    outfile.parent.mkdir(parents=True, exist_ok=True)

                    self.log.emit(f"Downloading direct file → {outfile}")
                    with urllib.request.urlopen(self.url) as resp, open(outfile, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    self.log.emit(f"✔ Saved direct file to {self.opts['outtmpl']}")
                    self.progress.emit(100, self.label)
                    self.finished.emit(self.label)
                except Exception as e:
                    self.log.emit(f"✖ Direct download failed: {e}")
                    self.error.emit(str(e), self.label)
                return
            # --- END bypass ---
            self.log.emit(f"▶ Starting {self.label}")
            self.log.emit(f"⬇️ Download starting: {self.label}")
            cmd = [YTDLP, "-f", self.opts.get("format", "best"), self.url]

            if "outtmpl" in self.opts:
                cmd.extend(["-o", self.opts["outtmpl"]])
            if self.opts.get("merge_output_format"):
                cmd.extend(["--merge-output-format", self.opts["merge_output_format"]])

            # Prevent console pop-up on Windows
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr into stdout
                text=True,
                bufsize=1,
                universal_newlines=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            # Stream output safely
            for line in iter(self._proc.stdout.readline, ''):
                if self._cancelled:
                    break
                line = line.strip()
                if not line:
                    continue
                if "[download]" in line and "%" in line:
                    m = re.search(r"(\d+(?:\.\d+)?)%", line)
                    if m:
                        pct = int(float(m.group(1)))
                        self.progress.emit(pct, self.label)
                    continue
                if not line.startswith("[debug]"):
                    self.log.emit(line)

            self._proc.wait()

            if self._cancelled:
                self.log.emit(f"✖ Cancelled {self.label}")
                self.cancelled.emit(self.label)
                return

            if self._proc.returncode != 0:
                self.log.emit(f"✖ yt-dlp failed with code {self._proc.returncode}")
                self.error.emit("yt-dlp failed", self.label)
            else:
                self.log.emit(f"✔ Finished {self.label}")
                self.finished.emit(self.label)

        except Exception as e:
            self.log.emit(f"✖ Error {self.label}: {e}")
            self.error.emit(str(e), self.label)


# ---------- Helpers ----------

# ---------- yt-dlp auto-update helper ----------
def ensure_ytdlp_latest():
    """Check and update yt-dlp automatically (non-blocking)."""
    try:
        subprocess.run([YTDLP, "-U"], timeout=15)
    except Exception as e:
        print(f"yt-dlp update check failed: {e}")

def extract_direct_media_file(url: str) -> str | None:
    """Try to find direct audio/video URLs in any webpage HTML."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Look for absolute media URLs
        m = re.search(r'["\'](https?://[^"\']+\.(?:mp3|mp4|m4a|ogg|wav|webm))["\']', html, re.IGNORECASE)
        if m:
            return m.group(1)

        # Look for relative media URLs
        m = re.search(r'["\'](/[^"\']+\.(?:mp3|mp4|m4a|ogg|wav|webm))["\']', html, re.IGNORECASE)
        if m:
            return urljoin(url, m.group(1))

        # Look for HLS streams
        m = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html, re.IGNORECASE)
        if m:
            return m.group(1)

    except Exception as e:
        print(f"extract_direct_media_file error: {e}")
    return None


def extract_un_media_file(url: str) -> Optional[str]:
    """Fetch a UN News page and try to extract the direct audio/video file URL."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Look for common file fields
        m = re.search(r'["\']file["\']\s*:\s*["\']([^"\']+\.(?:mp3|mp4))["\']', html)
        if m:
            file_url = m.group(1)
            if file_url.startswith("/"):
                # prefix relative URL
                from urllib.parse import urljoin
                file_url = urljoin(url, file_url)
            return file_url

        # fallback: look for "downloadurl"
        m = re.search(r'["\']downloadurl["\']\s*:\s*["\']([^"\']+)["\']', html)
        if m:
            file_url = m.group(1)
            if file_url.startswith("/"):
                from urllib.parse import urljoin
                file_url = urljoin(url, file_url)
            return file_url

    except Exception as e:
        print(f"extract_un_media_file error: {e}")
    return None

def derive_entry_id_from_webtv(url: str) -> Optional[str]:
    try:
        last = url.rstrip("/").split("/")[-1]
        if not last:
            return None
        if last.startswith("k"):
            last = last[1:]
        if last.startswith("1"):
            last = last[1:]
        if not last:
            return None
        return f"1_{last}"
    except Exception:
        return None

def fetch_entry_id_from_html(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Common patterns
        patterns = [
            r'data-entry=["\'](1_[0-9A-Za-z]+)["\']',
            r'entry_id[/"\\s:]+([0-9A-Za-z_]+)',
            r'["\']entry[_-]?id["\']\s*[:=]\s*["\']([0-9A-Za-z_]+)',
            r'kaltura.*?/entry_id/([0-9A-Za-z_]+)',
            r'data[-_]entryid=["\']([0-9A-Za-z_]+)',
            r'\b1_[0-9A-Za-z]+',
            r'"entryId"\s*:\s*"([0-9A-Za-z_]+)"',
            r'<iframe[^>]+entry_id/([0-9A-Za-z_]+)'
         ]

        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                return m.group(1)
                
        m = re.search(r'https://media\.un\.org/[^\s"\']+', html)
        if m:
            media_url = m.group(0)
            with urllib.request.urlopen(media_url) as resp2:
                media_html = resp2.read().decode("utf-8", errors="ignore")
            mm = re.search(r'"entry_id"\s*:\s*"([0-9A-Za-z_]+)"', media_html)
            if mm:
                return mm.group(1)

    except Exception as e:
        print(f"fetch_entry_id_from_html error: {e}")
    return None


def kaltura_embed_url(entry_id: str) -> str:
    return (
        "https://www.kaltura.com/index.php/extwidget/preview/"
        f"partner_id/2503451/uiconf_id/49754663/entry_id/{entry_id}/embed/iframe"
    )

# ---------- Main widget ----------
class DownloadTab(QWidget):
    output_dir_changed = QtCore.Signal()

    def __init__(self, settings):
        super().__init__()
        self._progress_map = {}
        self.settings = settings
        self.default_lang = self.settings.data.get("default_lang", "eng")
        
        # URL + extractor
        self.url_edit = QLineEdit()
        self.url_edit.textChanged.connect(self._on_url_changed)

        # Entry id
        self.entry_edit = QLineEdit()
        self.entry_edit.setPlaceholderText("Optional: Kaltura entry_id (auto-filled if found)")

        # Output dir
        self.dir_edit = QLineEdit(self.settings.data.get("last_output_dir", {}).get("download", str(Path.cwd())))
        self.dir_btn = QPushButton("Browse")
        
        self.url_edit.textChanged.connect(self._auto_handle_url)
        #self.entry_edit.textChanged.connect(self._auto_handle_url)

        # Controls
        self.list_btn = QPushButton("List Formats")
        self.sep_chk = QCheckBox("Save selected as separate files (no merge)")
        self.sep_chk.setChecked(True)
        self.parallel_chk = QCheckBox("Download in Parallel")
        # ADD THESE LINES
        self.max_jobs_label = QLabel("Max Jobs:")
        self.max_jobs_spin = QSpinBox()
        self.max_jobs_spin.setRange(1, 16)
        self.max_jobs_spin.setValue(2)        
        # disable by default, enable only when "Download in Parallel" is checked
        #self.max_jobs_spin.setEnabled(False)
        #self.parallel_chk.stateChanged.connect(
        #    lambda state: self.max_jobs_spin.setEnabled(state == QtCore.Qt.Checked)
        #)
        self.max_jobs_spin.setToolTip("Maximum number of parallel downloads (default 2)")        
        #self.debug_chk = QCheckBox("Enable Debug Logs")        
        self.start_btn = QPushButton("Download")
        self.cancel_btn = QPushButton("Cancel All")
        self.clear_btn = QPushButton("Clear Finished")

        # Table of available formats
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Select", "ID", "Ext", "Type", "Res/BR", "Lang"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Active downloads table
        self.active_table = QTableWidget(0, 4)
        self.active_table.setHorizontalHeaderLabels(["Label", "Progress", "Status", "Cancel"])
        # allow text wrapping + flexible column resizing
        self.active_table.setWordWrap(True)
        header = self.active_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)           # Label column fills leftover space
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Progress = fit text width
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.active_table.setColumnWidth(2, 120)  # enough to fit "Downloading…"
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Cancel button = fit widget
        self.active_table.cellDoubleClicked.connect(self._open_file_from_row)

        # Global status + log
        self.progress = QProgressBar()
        self.global_status = QLabel("No downloads yet.")
        #self.log = LogView(debug=self.debug_chk.isChecked())
        self.log = LogView()

        # Layout
        row1 = QHBoxLayout(); row1.addWidget(QLabel("URL")); row1.addWidget(self.url_edit)
        row1b = QHBoxLayout(); row1b.addWidget(QLabel("Entry ID")); row1b.addWidget(self.entry_edit)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Output dir")); row2.addWidget(self.dir_edit); row2.addWidget(self.dir_btn)
        btn_row = QHBoxLayout(); btn_row.addWidget(self.start_btn); btn_row.addWidget(self.cancel_btn); btn_row.addWidget(self.clear_btn)

        # build left_layout as before
        left_layout = QVBoxLayout()
        left_layout.addLayout(row1)
        left_layout.addLayout(row1b)
        left_layout.addLayout(row2)
        #left_layout.addWidget(self.list_btn)
        left_layout.addWidget(self.table)
        left_layout.addWidget(self.sep_chk)

        # build right_layout as before
        right_layout = QVBoxLayout()
        row_parallel = QHBoxLayout()
        row_parallel.addWidget(self.parallel_chk)
        row_parallel.addWidget(self.max_jobs_label)
        row_parallel.addWidget(self.max_jobs_spin)
        row_parallel.addStretch()
        right_layout.addLayout(row_parallel)
        #right_layout.addWidget(self.debug_chk)
        right_layout.addLayout(btn_row)
        right_layout.addWidget(QLabel("Active Downloads"))
        right_layout.addWidget(self.active_table)
        right_layout.addWidget(self.progress)
        right_layout.addWidget(self.global_status)
        right_layout.addWidget(self.log)

        # wrap into widgets
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        # --- Add splitter instead of fixed HBox ---
        splitter = QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)  # left panel wider
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 400])

        # --- Final layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)


        # Wire signals
        self.dir_btn.clicked.connect(self.pick_dir)
        #self.extractor_combo.currentTextChanged.connect(self._on_extractor_changed)
        self.entry_edit.textChanged.connect(self._on_entry_changed)
        #self.list_btn.clicked.connect(self.list_formats)
        self.start_btn.clicked.connect(self.start_download)
        self.cancel_btn.clicked.connect(self._cancel_all)
        self.clear_btn.clicked.connect(self._clear_finished)
        self.dir_edit.textChanged.connect(self._persist_dir)
        #self.debug_chk.stateChanged.connect(self.toggle_debug)

        # State
        self._last_info = None
        self._format_cache = {}   # { url: [formats list] }
        self.active_threads: List[QThread] = []
        self._total = 0
        self._completed = 0
        self._remaining = 0
        self._queue: List[Tuple[str, str, dict]] = []
        self._active_rows: Dict[str, Tuple[int, str, DownloadWorker, QThread]] = {}

    # --- Helper methods ---
    # def toggle_debug(self, state):
        # self.log.debug = bool(state)
        # if self.log.debug:
            # self.log.append_line("Debug logging enabled")
        # else:
            # self.log.append_line("Debug logging disabled")

    def refresh_settings(self):
        self.default_lang = self.settings.data.get("default_lang", "eng")
        last_dir = self.settings.data.get("last_output_dir", {}).get("download", str(Path.cwd()))
        self.dir_edit.setText(last_dir)

    def _persist_dir(self):
        d = self.dir_edit.text().strip()
        if not d:
            return
        self.settings.data.setdefault("last_output_dir", {})
        self.settings.data["last_output_dir"]["download"] = d
        self.output_dir_changed.emit()
        
    def cleanup_on_exit(self):
        """Stop all active downloads and clean up threads when app exits"""
        self._cancel_all()
        for t in list(self.active_threads):
            try:
                t.quit()
                t.wait()
            except Exception:
                pass
        self.active_threads.clear()
        self._active_rows.clear()
        self._queue.clear()

    def _cancel_all(self):
        self.log.append_line("Cancelling all downloads…")
        for label, (row, _, worker, _) in list(self._active_rows.items()):
            worker.cancel()
            self.active_table.setItem(row, 2, QTableWidgetItem("Cancelling…"))
        self._queue.clear()
        self.global_status.setText("Cancel requested for all downloads")

    def _clear_finished(self):
        # Iterate backwards so row indices stay valid when removing
        for row in reversed(range(self.active_table.rowCount())):
            status_item = self.active_table.item(row, 2)
            if status_item and status_item.text() in ("Finished", "Cancelled"):
                self.active_table.removeRow(row)

        self.log.append_line("Cleared finished downloads")
        
    def _resolve_url(self) -> Optional[str]:
        """Smart resolver that detects site type and optimizes resolution."""
        url_in = self.url_edit.text().strip()
        if not url_in:
            QMessageBox.warning(self, "URL", "Please enter a URL.")
            return None

        entry_override = self.entry_edit.text().strip()
        if entry_override:
            return kaltura_embed_url(entry_override)

        # --- Normalize and detect platform ---
        url_lower = url_in.lower()

        # Direct media file shortcut
        if url_lower.endswith((".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm")):
            self.log.append_line("Direct file detected → skipping yt-dlp.")
            return url_in

        # Known platforms (yt-dlp can handle natively)
        platforms = ("youtube.com", "youtu.be", "vimeo.com",
                     "facebook.com", "twitter.com", "x.com",
                     "brightcove.net", "players.brightcove.net",
                     "tiktok.com", "instagram.com", "dailymotion.com")

        if any(p in url_lower for p in platforms):
            self.log.append_line(f"Recognized media platform → handled natively: {url_in}")
            return url_in

        # UN WebTV / Kaltura special handling
        if "webtv.un.org" in url_lower:
            entry_id = derive_entry_id_from_webtv(url_in)
            if entry_id:
                self.entry_edit.setText(entry_id)
                self._lock_entry_field(True)
                return kaltura_embed_url(entry_id)
            self.log.append_line("Could not derive entry_id from webtv.un.org")

        elif url_lower.endswith(".un.org") or ".un.org/" in url_lower:
            resolved = fetch_entry_id_from_html(url_in)
            if resolved:
                self.entry_edit.setText(resolved)
                self._lock_entry_field(True)
                return kaltura_embed_url(resolved)
            self.log.append_line("Could not extract entry_id from UN site HTML")

        elif "news.un.org" in url_lower:
            direct = extract_un_media_file(url_in)
            if direct:
                self.log.append_line(f"Resolved UN media file: {direct}")
                return direct
            self.log.append_line("Could not extract direct file from UN News page")

        # Generic extractor fallback
        direct = extract_direct_media_file(url_in)
        if direct:
            self.log.append_line(f"Resolved direct media file: {direct}")
            return direct

        # yt-dlp cache + fast probe
        if not hasattr(self, "_url_cache"):
            self._url_cache = {}

        if url_in in self._url_cache:
            self.log.append_line("URL resolved from cache.")
            return self._url_cache[url_in]

        try:
            cmd = [YTDLP, "--get-url", "--no-playlist", "--no-warnings", "--socket-timeout", "6", url_in]
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True,
                                          startupinfo=startupinfo, creationflags=creationflags).strip()
            if out:
                resolved = out.splitlines()[0]
                self._url_cache[url_in] = resolved
                self.log.append_line("Resolved via yt-dlp probe.")
                return resolved

        except subprocess.CalledProcessError as e:
            self.log.append_line(f"yt-dlp failed: {e.output.strip() if e.output else e}")
        except Exception as e:
            self.log.append_line(f"Error resolving URL: {e}")

        return None
    
    def _populate_formats(self, url: str, formats: list, err: str = ""):
        """Populate the format table showing all video formats, but filter audio with und/unknown language."""
        if err:
            QMessageBox.critical(self, "Error", f"Could not list formats: {err}")
            return

        self.table.setRowCount(0)
        self._format_cache[url] = formats

        if not formats:
            self.log.append_line("⚠ No formats found.")
            return

        seen_ids = set()
        shown = 0

        for f in formats:
            fid = str(f.get("format_id", "")).strip()
            if not fid or fid in seen_ids:
                continue
            seen_ids.add(fid)

            ext = f.get("ext", "") or "?"
            vcodec = f.get("vcodec", "")
            acodec = f.get("acodec", "")
            res = (
                f.get("resolution")
                or f.get("height")
                or f.get("format_note")
                or f.get("quality")
                or ""
            )
            abr = f.get("abr", "")
            lang = (f.get("language") or f.get("language_preference") or "").strip().lower() or "und"

            # --- Type determination ---
            if vcodec != "none" and acodec == "none":
                ftype = "video"
                info = f"{res or 'video-only'}"
            elif acodec != "none" and (not vcodec or vcodec == "none"):
                # 🎧 Audio track — filter out undefined language
                if lang in ("und", "unknown", ""):
                    continue
                ftype = "audio"
                info = f"{abr} kbps" if abr else "audio-only"
            elif vcodec != "none" and acodec != "none":
                ftype = "av"
                info = f"{res or 'muxed'}"
            else:
                ftype = "other"
                info = "unknown"

            # --- Insert row ---
            row = self.table.rowCount()
            self.table.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            chk.setCheckState(QtCore.Qt.Unchecked)

            self.table.setItem(row, 0, chk)
            self.table.setItem(row, 1, QTableWidgetItem(fid))
            self.table.setItem(row, 2, QTableWidgetItem(ext))
            self.table.setItem(row, 3, QTableWidgetItem(ftype))
            self.table.setItem(row, 4, QTableWidgetItem(str(info)))
            self.table.setItem(row, 5, QTableWidgetItem(lang))

            shown += 1

        self.log.append_line(f"✅ Displayed {shown} of {len(formats)} formats (filtered audio 'und').")   
            
    # TTL cache expiry (optional)
    def _prune_cache(self, ttl_sec=600):
        """Safely remove cached format entries older than ttl_sec (default 10 min)."""
        now = time.time()
        cleaned = 0
        for k, v in list(self._format_cache.items()):
            # Handle both old and new cache formats
            if isinstance(v, tuple) and len(v) == 2:
                formats, t = v
                if now - t > ttl_sec:
                    del self._format_cache[k]
                    cleaned += 1
            elif isinstance(v, list):
                # Old-style (no timestamp): keep as-is
                continue
        if cleaned:
            self.log.append_line(f"🧹 Pruned {cleaned} expired cache entr{'y' if cleaned==1 else 'ies'}.")

    def list_formats(self):
        for exe in (FFMPEG, FFPROBE, YTDLP):
            if not os.path.exists(exe):
                raise FileNotFoundError(
                    f"Required tool not found: {exe}\n"
                    "Make sure the 'bin' folder with ffmpeg.exe, ffprobe.exe, and yt-dlp.exe "
                    "is next to your WebTvMux.exe."
                )
        self._prune_cache()
        """Smarter, faster format listing with caching and async support."""
        url = self._resolve_url()
        if not url:
            return

        # Cached results
        if url in self._format_cache:
            self.log.append_line("Formats served from cache.")
            self._populate_formats(url, self._format_cache[url])
            return

        self.table.setRowCount(0)
        self.log.append_line(f"Listing formats for: {url}")

        # Async format fetcher
        class FormatWorker(QThread):
            done = QtCore.Signal(list, str)

            def __init__(self, url: str):
                super().__init__()
                self.url = url

            def run(self):
                try:
                    cmd = [
                        YTDLP,
                        "-J", "--skip-download", "--no-warnings",
                        "--socket-timeout", "20",
                        "--extractor-args", "youtube:player_client=android,player_skip=dash=False",
                        "--format-sort", "res,ext",
                        "--merge-output-format", "mp4",
                        "--geo-bypass",
                        "--no-check-certificates",
                        "--ignore-errors",
                        "--compat-options", "manifest-filesize-approx",
                        "--add-header", "User-Agent: Mozilla/5.0",
                        self.url
                    ]

                    startupinfo = None
                    creationflags = 0
                    if os.name == "nt":
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        creationflags = subprocess.CREATE_NO_WINDOW

                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        startupinfo=startupinfo,
                        creationflags=creationflags
                    )

                    try:
                        # Increased from 10 → 30 seconds to avoid premature timeout
                        out, err = proc.communicate(timeout=30)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        self.done.emit([], "Timeout fetching formats (first try) — retrying...")
                        try:
                            # Retry once more in case the server was slow
                            proc = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                startupinfo=startupinfo,
                                creationflags=creationflags
                            )
                            out, err = proc.communicate(timeout=30)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            self.done.emit([], "Timeout fetching formats (second try).")
                            return

                    if proc.returncode == 0 and out.strip():
                        import json
                        data = json.loads(out)
                        formats = data.get("formats") or []
                        if not formats and "entries" in data:
                            # playlist or single entry fallback
                            entry = data["entries"][0] if data["entries"] else {}
                            formats = entry.get("formats", [])
                        if formats:
                            self.done.emit(formats, "")
                        else:
                            self.done.emit([], "No downloadable formats found. Try updating yt-dlp.")
                    else:
                        err_msg = err or f"yt-dlp exited with code {proc.returncode}"
                        self.done.emit([], err_msg)
                except subprocess.TimeoutExpired:
                    self.done.emit([], "Timeout fetching formats")
                except Exception as e:
                    self.done.emit([], str(e))

        def on_done(formats: list, err: str):
            if err:
                QMessageBox.critical(self, "Error", f"Could not list formats: {err}")
                return
            self._format_cache[url] = formats
            self._populate_formats(url, formats)
            self.log.append_line(f"Listed {len(formats)} formats successfully.")
        worker = FormatWorker(url)
        worker.done.connect(on_done)
        worker.start()
        self.active_threads.append(worker)

    def _cleanup_thread(self, thread: QThread):
        if thread in self.active_threads:
            self.active_threads.remove(thread)


    def start_download(self):
        url = self._resolve_url()
        if not url:
            return
            
        self.log.append_line("⬇️ Download button clicked → preparing to start download…")
            
        # disable URL editing while downloads run
        self.url_edit.setEnabled(False)
        
        # --- NEW: direct file bypass ---
        if url.lower().endswith((".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm")):
            # Decide folder based on type
            if url.lower().endswith((".mp3", ".m4a", ".ogg", ".wav")):
                subfolder = "audios"
            else:
                subfolder = "videos"

            # Ensure both audios/ and videos/ always exist
            base_dir = Path(self.dir_edit.text())
            (base_dir / "audios").mkdir(parents=True, exist_ok=True)
            (base_dir / "videos").mkdir(parents=True, exist_ok=True)

            # Build output path
            outtmpl = str(base_dir / subfolder / Path(url).name)

            label = Path(url).name
            opts = {"outtmpl": outtmpl, "format": "bestaudio/best"}

            self._queue = [(url, label, opts)]
            self.global_status.setText("Direct file detected → downloading…")
            self.log.append_line(f"Direct file queued: {url} → {subfolder}/")
            self.start_btn.setEnabled(False)
            self._start_worker()
            return
        # --- END bypass ---


        # Ensure formats are listed
        #if self.table.rowCount() == 0:
        #    self.list_formats()
            
        # Auto-remove finished rows before starting new batch
        self._clear_finished()

        selected_formats = []
        for row in range(self.table.rowCount()):
            checkbox = self.table.item(row, 0)
            if checkbox and checkbox.checkState() == QtCore.Qt.Checked:
                fid = self.table.item(row, 1).text()  # ID column
                selected_formats.append((row, fid))

        if not selected_formats:
            QMessageBox.warning(self, "Warning", "Please select at least one format to download.")
            return

        # Queue downloads for each selected format
        self._queue.clear()
        for row, fid in selected_formats:
            outtmpl = self._build_outtmpl_for_row(row)
            if not self._last_info:
                try:
                    cmd = [YTDLP, "--dump-json", url]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    info, _ = proc.communicate(timeout=10)
                    if proc.returncode == 0 and info:
                        import json
                        self._last_info = json.loads(info)
                except Exception:
                    self._last_info = {}
            title = self._last_info.get("title") if self._last_info else None
            if not title:
                title = f"download_{datetime.datetime.now().strftime('%H%M%S')}"
            label = f"{title} | {fid} | row{row}"
            opts = {
                "format": fid,
                "outtmpl": outtmpl,
            }
            self._queue.append((url, label, opts))

        # Start parallel or sequential
        self._completed = 0
        self.global_status.setText(f"Queued {len(self._queue)} downloads")
        self.start_btn.setEnabled(False)
        self._start_worker()


    def _start_worker(self):
        if not self._queue:
            return

        if self.parallel_chk.isChecked():
            max_jobs = self.max_jobs_spin.value()
            while self._queue and len(self._active_rows) < max_jobs:
                url, label, opts = self._queue.pop(0)
                self._launch_worker(url, label, opts)
        else:
            # Only launch one at a time
            # Protect against double-call if already running
            if any(
                status_item and status_item.text() in ("Downloading…", "Starting…")
                for row in range(self.active_table.rowCount())
                for status_item in [self.active_table.item(row, 2)]
            ):
                return  # A worker is still running, don't start again

            if self._queue:  # double-check not empty
                url, label, opts = self._queue.pop(0)
                self._launch_worker(url, label, opts)

    def _launch_worker(self, url, label, opts):
        row = self.active_table.rowCount()
        self.active_table.insertRow(row)
        label_item = QTableWidgetItem(label)
        label_item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)  # align for wrapping
        self.active_table.setItem(row, 0, label_item)
        self.active_table.setItem(row, 1, QTableWidgetItem("0%"))
        self.active_table.setItem(row, 2, QTableWidgetItem("Starting…"))
        # auto-resize row to fit wrapped text
        self.active_table.resizeRowToContents(row)
        self.active_table.resizeRowToContents(row)
        #self.active_table.resizeColumnsToContents()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda _, lbl=label: self._cancel_single(lbl))
        self.active_table.setCellWidget(row, 3, cancel_btn)

        worker = DownloadWorker(opts, url, label)
        thread = QThread()
        worker.moveToThread(thread)

        # wire signals
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress_update)   # (pct, label)
        worker.log.connect(self.log.append_line)
        worker.finished.connect(self._on_worker_finished)   # label
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._active_rows[label] = (row, opts["outtmpl"], worker, thread)
        self.active_threads.append(thread)
        self.log.append_line(f"▶ Download queued: {label}")
        # Safe cleanup when thread finishes
        thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
        thread.start()
        self.log.append_line(f"⬇️ Worker launched for {label} → download about to begin…")

    def _cancel_single(self, label):
        entry = self._active_rows.get(label)
        if not entry:
            return
        row, _filepath, worker, _thread = entry
        worker.cancel()
        self.active_table.setItem(row, 2, QTableWidgetItem("Cancelling…"))
        self.log.append_line(f"⏹ Requested cancel for {label}")

    @QtCore.Slot(int, str)
    def _on_progress_update(self, pct: int, label: str):
        if label in self._active_rows:
            row, *_ = self._active_rows[label]
            self.active_table.setItem(row, 1, QTableWidgetItem(f"{pct}%"))
            self.active_table.setItem(row, 2, QTableWidgetItem("Downloading…"))
            self.active_table.resizeRowToContents(row)

        # --- aggregate overall progress across all active downloads ---
        total_active = self.active_table.rowCount()
        if total_active > 0:
            pct_sum = 0
            for row in range(self.active_table.rowCount()):
                p_item = self.active_table.item(row, 1)
                if p_item:
                    try:
                        val = int(p_item.text().replace("%", ""))
                    except Exception:
                        val = 0
                    pct_sum += val
            self.progress.setValue(int(pct_sum / total_active))
            #self.active_table.resizeColumnsToContents()
            
    @QtCore.Slot(str)
    def _on_worker_cancelled(self, label: str):
        if label in self._active_rows:
            row, outtmpl, worker, _thread = self._active_rows[label]

            # remove partial files at UI level too (backup cleanup)
            if outtmpl:
                base = Path(outtmpl)
                for ext in ("", ".part", ".ytdl", ".temp"):
                    cand = base.with_suffix(base.suffix + ext) if base.suffix else Path(str(base) + ext)
                    if cand.exists():
                        try:
                            cand.unlink()
                            self.log.append_line(f"🗑 Removed partial file: {cand}")
                        except Exception as e:
                            self.log.append_line(f"⚠ Could not remove partial file: {cand} ({e})")

            self.active_table.setItem(row, 2, QTableWidgetItem("Cancelled"))
            self.active_table.resizeRowToContents(row)

            self._progress_map.pop(label, None)

            # remove from active list completely
            del self._active_rows[label]

        self.log.append_line(f"✖ Cancelled: {label}")

        # Trigger next jobs for both serial and parallel modes
        if self._queue:
            if self.parallel_chk.isChecked():
                while self._queue and len(self._active_rows) < self.max_jobs_spin.value():
                    url, label, opts = self._queue.pop(0)
                    self._launch_worker(url, label, opts)
            else:
                self._start_worker()
        
        
    @QtCore.Slot(str, str)
    def _on_worker_error(self, msg: str, label: str):
        if label in self._active_rows:
            row, *_ = self._active_rows[label]
            self.active_table.setItem(row, 2, QTableWidgetItem("Error"))
            self.active_table.resizeRowToContents(row)

            # remove from cache so avg progress is correct
            self._progress_map.pop(label, None)

            # remove entry completely
            del self._active_rows[label]

        self.log.append_line(f"✖ Error: {label} → {msg}")

        # Trigger next jobs for both serial and parallel modes
        if self._queue:
            if self.parallel_chk.isChecked():
                while self._queue and len(self._active_rows) < self.max_jobs_spin.value():
                    url, label, opts = self._queue.pop(0)
                    self._launch_worker(url, label, opts)
            else:
                self._start_worker()

    @QtCore.Slot(str)
    def _on_worker_finished(self, label: str):
        entry = self._active_rows.get(label)
        if entry:
            row, *_ = entry
            last_status = self.active_table.item(row, 2)
            if last_status and "Cancelling" in last_status.text():
                self.active_table.setItem(row, 2, QTableWidgetItem("Cancelled"))
            else:
                self.active_table.setItem(row, 2, QTableWidgetItem("Finished"))
            self.active_table.resizeRowToContents(row)

            # remove entry completely instead of leaving None
            del self._active_rows[label]

        # Update aggregate correctly
        self._completed += 1
        active_count = sum(1 for v in self._active_rows.values() if v)   # only count active
        remaining = active_count + len(self._queue)
        total_done = self._completed
        total = total_done + remaining
        percent = int(total_done / max(1, total) * 100)
        self.progress.setValue(percent)
        self.global_status.setText(f"Completed {total_done}/{total}")

        # NEW: trigger next jobs for both serial and parallel modes
        if self._queue:
            if self.parallel_chk.isChecked():
                while self._queue and len(self._active_rows) < self.max_jobs_spin.value():
                    url, label, opts = self._queue.pop(0)
                    self._launch_worker(url, label, opts)
            else:
                self._start_worker()

        # Re-enable URL if no active downloads left
        if not self._active_rows and not self._queue:
            self.url_edit.setEnabled(True)
            self.start_btn.setEnabled(True)

    def _open_file_from_row(self, row, _col):
        label_item = self.active_table.item(row, 0)
        if not label_item:
            return
        label = label_item.text()
        entry = self._active_rows.get(label)
        # If mapping was removed already, we still try to open the output dir
        outtmpl = None
        if entry:
            _row, outtmpl, *_ = entry
        if not outtmpl:
            # Just fall back to the base output directory
            outtmpl = str(Path(self.dir_edit.text()) / "%(title)s.%(ext)s")

        # We can't know the exact final filename here without parsing info dict again.
        # Open the output directory instead.
        folder = Path(outtmpl).parent
        try:
            if QtCore.QSysInfo.productType().lower().startswith("windows"):
                os.startfile(folder)  # type: ignore
            elif QtCore.QSysInfo.productType().lower() == "osx":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            QMessageBox.critical(self, "Open Error", f"Could not open folder:\n{e}")

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder")
        if d:
            self.dir_edit.setText(d)
            self._persist_dir()

    def _lock_entry_field(self, lock: bool):
        self.entry_edit.setReadOnly(lock)
        if lock:
            # gray background, dimmed text, tooltip
            self.entry_edit.setStyleSheet("background-color: #f0f0f0; color: #555;")
            self.entry_edit.setToolTip("Auto-filled from UN site (read-only)")
        else:
            self.entry_edit.setStyleSheet("")
            self.entry_edit.setToolTip("")

    def _on_extractor_changed(self, text: str):
        if text.lower() != "kaltura":
            self._lock_entry_field(False)

    def _on_entry_changed(self, text: str):
        if not text.strip():
            self._lock_entry_field(False)
            
    def _on_url_changed(self, _text: str):
        # Always clear the format list + active downloads table on new URL
        self.table.setRowCount(0)          # clear format list
        self.active_table.setRowCount(0)   # clear active downloads
        self._last_info = None
        self._queue.clear()
        self._active_rows.clear()
        self._completed = 0
        self.global_status.setText("Ready for new download")

        self.log.append_line("New URL entered → cleared formats and active downloads")

        # Clear Entry ID field (still read-only but reset content)
        self.entry_edit.clear()

        # If downloads were active, ask before cancelling
        if self._active_rows or self._queue:
            reply = QMessageBox.question(
                self,
                "Cancel Downloads?",
                "Changing URL will cancel all active and queued downloads. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self._cancel_all()
            
    def _auto_handle_url(self, _text: str):
        url = self._resolve_url()
        if not url:
            return
            
        # prevent double-call on same URL
        if getattr(self, "_last_resolved_url", None) == url and self.table.rowCount() > 0:
            return
        self._last_resolved_url = url

        # Direct file → start download immediately
        if url.lower().endswith((".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm")):
            self.start_btn.setEnabled(False)   # grey out Download button
            self.start_download()
        else:
            # Not a direct file → auto-list formats
            self.start_btn.setEnabled(True)
            if self.table.rowCount() == 0:
                self.list_formats()

    def _row_type(self, row: int) -> str:
        item = self.table.item(row, 3)
        return (item.text().strip().lower() if item else "video")

    def _build_outtmpl_for_row(self, row: int) -> str:
        base_dir = Path(self.dir_edit.text().strip() or ".")
        ftype = self._row_type(row)

        if ftype == "audio":
            lang_item = self.table.item(row, 5)
            lang = lang_item.text().strip().lower() if lang_item and lang_item.text().strip() else "und"
            sub = "audios"
            pat = f"%(title)s_{lang}_row{row}.%(ext)s"
        else:
            res_item = self.table.item(row, 4)
            res = (res_item.text() if res_item else "").replace(" ", "_").lower()
            sub = "videos"
            pat = f"%(title)s_{res}_row{row}.%(ext)s"
        (base_dir / sub).mkdir(parents=True, exist_ok=True) 
        return str((base_dir / sub / pat).resolve())


# Optional: quick manual test harness
if __name__ == "__main__":
    ensure_ytdlp_latest()  # check for updates once at startup
    app = QtWidgets.QApplication([])
    class DummySettings:
        def __init__(self):
            self.data = {"default_lang": "eng", "last_output_dir": {"download": str(Path.cwd())}}
    w = DownloadTab(DummySettings())
    w.setWindowTitle("DownloadTab Test Harness")
    w.resize(1000, 600)
    w.show()    
    app.exec()