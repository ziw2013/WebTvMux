# workers.py
import subprocess
import re
from PySide6.QtCore import QThread, Signal


class FfmpegWorker(QThread):
    progress = Signal(float)   # Emits progress in %
    finished = Signal(str)     # Emits the output file path when done
    error = Signal(str)        # Emits an error message if ffmpeg fails

    def __init__(self, cmd, outfile, duration=0.0):
        super().__init__()
        self.cmd = cmd
        self.outfile = outfile
        self.duration = duration
        self._running = True
        self._proc = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
                bufsize=1
            )

            for line in self._proc.stderr:
                if not self._running:
                    self._proc.terminate()
                    break

                if "time=" in line and self.duration > 0:
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match:
                        h, m, s = match.groups()
                        sec = int(h) * 3600 + int(m) * 60 + float(s)
                        progress = min(100.0, sec / self.duration * 100)
                        self.progress.emit(progress)

            self._proc.wait()

            if self._proc.returncode == 0:
                self.progress.emit(100.0)
                self.finished.emit(self.outfile)
            else:
                self.error.emit(f"ffmpeg failed with code {self._proc.returncode}")

        except Exception as e:
            self.error.emit(f"Worker error: {e}")

    def stop(self):
        self._running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
