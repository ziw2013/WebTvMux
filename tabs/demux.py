import json, os
import subprocess, sys
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QComboBox, QCheckBox, QSpinBox
)

from utils import ensure_unique_path, FFMPEG, FFPROBE
from workers import FfmpegWorker
from utils import verify_tools
verify_tools()

INSTALL_DIR = str(Path(sys.argv[0]).resolve().parent)

# --- Suppress console windows on Windows ---
CREATE_NO_WINDOW = 0
STARTUPINFO = None
if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
# ---- ffprobe cache ----
_ffprobe_cache: dict[str, dict] = {}

def probe_file(path: str) -> dict:
    for exe in (FFMPEG, FFPROBE):
        if not os.path.exists(exe):
            raise FileNotFoundError(
                f"Required tool not found: {exe}\n"
                "Make sure the 'bin' folder with ffmpeg.exe, ffprobe.exe, and yt-dlp.exe "
                "is next to your WebTvMux.exe."
            )
    """Probe a media file with ffprobe and cache results in memory."""
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

class _ProbeThread(QtCore.QThread):
    done = QtCore.Signal(list, str)  # (jobs, error)

    def __init__(self, files, audio_ext, video_ext, force_reencode, out_dir):
        super().__init__()
        self.files = files
        self.audio_ext = audio_ext
        self.video_ext = video_ext
        self.force_reencode = force_reencode
        self.out_dir = out_dir
        self._stopped = False
        
    def stop(self):
        """Signal the thread to stop gracefully"""
        self._stopped = True

    def run(self):
        jobs = []
        try:
            for infile in self.files:
                if self._stopped:
                    break
                info = probe_file(infile)
                streams = info.get("streams", [])
                duration = float(info.get("format", {}).get("duration") or 0.0)
                video_added = False
                for s in streams:
                    if self._stopped:
                        break
                    if s.get("codec_type") not in ("audio", "video"):
                        continue

                    idx = s.get("index")
                    codec = s.get("codec_name", "")
                    lang = s.get("tags", {}).get("language", "unknown")

                    # --- VIDEO handling ---
                    if s["codec_type"] == "video":
                        # only include the default video stream
                        if not s.get("disposition", {}).get("default", 0):
                            continue
                        if video_added:
                            continue
                        video_added = True
                        ext = self.video_ext
                        if self.force_reencode:
                            codec_opt = ["-c:v", "libx264"]
                        else:
                            # allow copy only if codec is h264/h265 and container supports it
                            if codec in ("h264", "hevc") and ext in ("mp4", "mkv", "mov"):
                                codec_opt = ["-c:v", "copy"]
                            else:
                                codec_opt = ["-c:v", "libx264"]

                    # --- AUDIO handling ---
                    else:
                        if self.audio_ext == "aac":
                            ext = "m4a"  # safer container for AAC
                            if self.force_reencode:
                                codec_opt = ["-c:a", "aac"]
                            else:
                                codec_opt = ["-c:a", "copy"] if codec == "aac" else ["-c:a", "aac"]

                        elif self.audio_ext == "mp3":
                            ext = "mp3"
                            if self.force_reencode:
                                codec_opt = ["-c:a", "libmp3lame"]
                            else:
                                codec_opt = ["-c:a", "copy"] if codec == "mp3" else ["-c:a", "libmp3lame"]

                        elif self.audio_ext == "flac":
                            ext = "flac"
                            if self.force_reencode:
                                codec_opt = ["-c:a", "flac"]
                            else:
                                codec_opt = ["-c:a", "copy"] if codec == "flac" else ["-c:a", "flac"]

                        elif self.audio_ext == "opus":
                            ext = "opus"
                            if self.force_reencode:
                                codec_opt = ["-c:a", "libopus"]
                            else:
                                codec_opt = ["-c:a", "copy"] if codec == "opus" else ["-c:a", "libopus"]

                        elif self.audio_ext == "wav":
                            ext = "wav"
                            if self.force_reencode:
                                codec_opt = ["-c:a", "pcm_s16le"]
                            else:
                                codec_opt = ["-c:a", "copy"] if codec.startswith("pcm") else ["-c:a", "pcm_s16le"]

                        else:
                            # fallback — use requested extension with reencode
                            ext = self.audio_ext
                            codec_opt = ["-c:a", self.audio_ext]

                    # --- Output file path ---
                    outfile = ensure_unique_path(
                        Path(self.out_dir) / f"{Path(infile).stem}_{lang}.{ext}"
                    )

                    # --- Build ffmpeg command ---
                    cmd = [FFMPEG, "-y", "-i", infile, "-map", f"0:{idx}", *codec_opt, str(outfile)]
                    jobs.append((cmd, outfile, duration))

            self.done.emit(jobs, "")
        except Exception as e:
            self.done.emit([], str(e))



class DemuxTab(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.files = []
        self.jobs = []
        self.active_jobs = []   # keep worker references alive
        self.max_parallel = 1

        self._build_layout()
        
    def refresh_settings(self):
        lod = self.settings.data.get("last_output_dir", {})
        out_dir = lod.get("demux") or INSTALL_DIR
        self.out_dir.setText(out_dir)


    def _build_layout(self):
        layout = QVBoxLayout(self)

        # File selection row
        row1 = QHBoxLayout()
        self.add_btn = QPushButton("Add Files")
        self.add_btn.setToolTip("Add media files to the demux queue")
        self.add_btn.clicked.connect(self.add_files)
        row1.addWidget(self.add_btn)

        # Remove Selected button
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setToolTip("Remove selected file(s) from the table")
        self.remove_btn.clicked.connect(self.remove_selected)
        row1.addWidget(self.remove_btn)
        # Clear All button
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setToolTip("Clear all files from the list")
        self.clear_btn.clicked.connect(self.clear_all)
        row1.addWidget(self.clear_btn)

        self.out_dir_label = QLabel("Output Dir:")
        row1.addWidget(self.out_dir_label)

        self.out_dir = QtWidgets.QLineEdit()
        row1.addWidget(self.out_dir)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setToolTip("Choose an output directory")
        self.browse_btn.clicked.connect(self.choose_out_dir)
        row1.addWidget(self.browse_btn)

        layout.addLayout(row1)

        # Table
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["File", "Status"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)          # File column expands
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents) # Status auto-size
        layout.addWidget(self.table, stretch=1)  # let table grow with window
        layout.addWidget(self.table)


        # Options row
        row3 = QHBoxLayout()

        self.audio_format_label = QLabel("Audio Format:")
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["aac", "mp3", "flac", "opus", "mka", "wav"])

        self.video_format_label = QLabel("Video Format:")
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItems(["mp4", "mkv", "mov"])

        self.force_reencode = QCheckBox("Force Re-encode")
        self.parallel_chk = QCheckBox("Run in Parallel")
        self.max_jobs_label = QLabel("Max Jobs:")
        self.max_jobs_spin = QSpinBox()
        self.max_jobs_spin.setRange(1, 16)
        self.max_jobs_spin.setValue(1)

        self.start_btn = QPushButton("Start Demux")
        self.start_btn.clicked.connect(self.do_demux)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_jobs)

        row3.addWidget(self.audio_format_label)
        row3.addWidget(self.audio_format_combo)
        row3.addWidget(self.video_format_label)
        row3.addWidget(self.video_format_combo)
        row3.addWidget(self.force_reencode)
        row3.addWidget(self.parallel_chk)
        row3.addWidget(self.max_jobs_label)
        row3.addWidget(self.max_jobs_spin)
        row3.addWidget(self.start_btn)
        row3.addWidget(self.stop_btn)

        layout.addLayout(row3)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    def add_files(self):
        """Add new files to the table, skipping duplicates by name."""
        self.clean_finished_rows()

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select media files",
            "",
            "Media files (*.mp4 *.mkv *.ts *.m4a *.mp3 *.aac *.wav)"
        )

        if not files:
            return

        added = 0
        skipped = 0
        existing_basenames = {Path(x).name.lower() for x in self.files}

        for f in files:
            base_name = Path(f).name.lower()
            if base_name in existing_basenames:
                skipped += 1
                self.log.append(f"⚠️ Skipped duplicate file: {Path(f).name}")
                continue

            self.files.append(f)
            existing_basenames.add(base_name)

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(f))
            self.table.setItem(row, 1, QTableWidgetItem("Pending"))
            added += 1

        self.log.append(f"✅ Added {added} file(s), skipped {skipped} duplicate(s).")


    def remove_selected(self):
        """Remove selected file(s) from the table and internal list."""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Remove Selected", "No rows selected.")
            return

        count = 0
        for idx in sorted(selected, key=lambda x: x.row(), reverse=True):
            row = idx.row()
            if row < len(self.files):
                del self.files[row]
            self.table.removeRow(row)
            count += 1

        self.log.append(f"🗑️ Removed {count} selected file(s).")


    def clear_all(self):
        """Clear all files from the table and reset the list."""
        if not self.files:
            QMessageBox.information(self, "Clear All", "No files to clear.")
            return

        confirm = QMessageBox.question(
            self,
            "Clear All",
            "Are you sure you want to remove all files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.table.setRowCount(0)
        self.files.clear()
        self.log.append("🧹 Cleared all files.")

                
    def clean_finished_rows(self):
        """Remove rows already marked Done or Error before adding new files"""
        for row in reversed(range(self.table.rowCount())):
            status_item = self.table.item(row, 1)
            if status_item and status_item.text() in ("Done", "Error"):
                self.table.removeRow(row)
                if row < len(self.files):
                    del self.files[row]
                    
    def cleanup_on_exit(self):
        """Stop all jobs and clean up workers when app exits"""
        self.stop_jobs()
        for worker in list(self.active_jobs):
            try:
                if hasattr(worker, "stop"):
                    worker.stop()
            except Exception:
                pass
            worker.deleteLater()
        self.active_jobs.clear()

    def choose_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select output directory")
        if d:
            self.out_dir.setText(d)

    def probe_duration(self, infile: str) -> float:
        try:
            info = probe_file(infile)
            dur = info.get("format", {}).get("duration")
            return float(dur) if dur else 0.0
        except Exception as e:
            self.log.append(f"probe_duration error for {infile}: {e}")
            return 0.0



    def do_demux(self):
        if not self.files:
            QMessageBox.warning(self, "Demux", "Add input files")
            return

        base_dir = Path(self.out_dir.text() or Path.cwd())
        demux_dir = base_dir / "demux"
        demux_dir.mkdir(parents=True, exist_ok=True)

        # disable button while probing
        self.start_btn.setEnabled(False)
        self.log.append("Probing input files… (non-blocking)")

        # launch probe thread
        t = _ProbeThread(
            self.files,
            self.audio_format_combo.currentText(),
            self.video_format_combo.currentText(),
            self.force_reencode.isChecked(),
            demux_dir,
        )

        def _on_done(jobs, err):
            self._file_job_counts = {}  # total jobs per input file
            self._file_jobs_done = {}   # completed jobs per input file

            self.start_btn.setEnabled(True)
            if err:
                QMessageBox.critical(self, "Demux", f"Probe error: {err}")
                return
            if not jobs:
                QMessageBox.warning(self, "Demux", "No valid streams found")
                return

            # turn job list into workers
            self._job_queue = []
            start_row = self.table.rowCount()   # append after existing rows
            for i, (cmd, outfile, duration) in enumerate(jobs):
                # Default to mapping each job to its own row
                row = self.table.rowCount()

                # Always map jobs to the input file row from add_files
                infile = Path(cmd[2]).name if len(cmd) > 2 else None
                if str(outfile).endswith((".mp4", ".mkv", ".mov")):
                    # Video → reuse the input file row
                    try:
                        row = self.files.index(infile)
                    except Exception:
                        row = 0
                    self.table.setItem(row, 1, QTableWidgetItem("Pending"))
                    self.log.append(f"Queued video stream: {outfile}")
                else:
                    # Audio → add new row
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    self.table.setItem(row, 0, QTableWidgetItem(str(outfile)))
                    self.table.setItem(row, 1, QTableWidgetItem("Pending"))
                    self.log.append(f"Queued audio stream: {outfile}")
                # Initialize job counters per row
                self._file_job_counts.setdefault(row, 0)
                self._file_job_counts[row] += 1
                self._file_jobs_done.setdefault(row, 0)
                # create worker bound to chosen row
                worker = FfmpegWorker(cmd, str(outfile), duration)
                worker.progress.connect(self.progress.setValue)
                worker.finished.connect(lambda f=outfile, r=row, w=worker: self._on_job_finished(f, r, w))
                worker.error.connect(lambda msg, r=row, w=worker: self._on_job_error(msg, r, w))
                self._job_queue.append((worker, row))



            # start jobs depending on parallel mode
            slots = self.max_jobs_spin.value() if self.parallel_chk.isChecked() else 1
            for _ in range(min(slots, len(self._job_queue))):
                self._launch_next_job()

        t.done.connect(_on_done)
        self.active_jobs.append(t)  # keep reference alive
        t.start()

    def stop_jobs(self):
        for worker in self.active_jobs:
            worker.stop()
        self.active_jobs.clear()
        self.jobs.clear()

    def _launch_next_job(self):
        if not getattr(self, "_job_queue", None):
            return
        worker, row = self._job_queue.pop(0)
        self.table.setItem(row, 1, QTableWidgetItem("Running"))
        self.active_jobs.append(worker)
        worker.start()

    def _on_job_finished(self, outfile, row, worker):
        # Mark one job finished for this row
        self._file_jobs_done[row] += 1

        if self._file_jobs_done[row] >= self._file_job_counts[row]:
            # All jobs for this file done
            self.table.setItem(row, 1, QTableWidgetItem("Done"))
            self.log.append(f"All streams finished for row {row}")
        else:
            # Still waiting on other streams
            self.table.setItem(row, 1, QTableWidgetItem("Running"))

        self.log.append(f"Finished: {outfile}")
        if worker in self.active_jobs:
            self.active_jobs.remove(worker)
        worker.deleteLater()

        # refill slots
        if self.parallel_chk.isChecked():
            # parallel: fill until active < max_jobs
            slots = self.max_jobs_spin.value()
            while len(self.active_jobs) < slots and getattr(self, "_job_queue", []):
                self._launch_next_job()
        else:
            # sequential: run next only when previous finished
            if getattr(self, "_job_queue", []):
                self._launch_next_job()


    def _on_job_error(self, msg, row, worker):
        self.table.setItem(row, 1, QTableWidgetItem("Error"))
        self.log.append(f"Error: {msg}")
        try:
            self.log.append(f"Command failed: {' '.join(worker.cmd)}")
        except Exception:
            pass
        if worker in self.active_jobs:
            self.active_jobs.remove(worker)
        worker.deleteLater()

        # refill like in finished
        if self.parallel_chk.isChecked():
            slots = self.max_jobs_spin.value()
            while len(self.active_jobs) < slots and getattr(self, "_job_queue", []):
                self._launch_next_job()
        else:
            if getattr(self, "_job_queue", []):
                self._launch_next_job()



