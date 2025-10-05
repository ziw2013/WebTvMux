from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QMessageBox
)
from utils import SettingsManager, DEFAULT_SETTINGS
import sys
INSTALL_DIR = str(Path(sys.argv[0]).resolve().parent)

class PreferencesDialog(QDialog):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings

        # --- Policies ---
        self.dl_policy = QComboBox()
        self.dl_policy.addItems(["safe", "overwrite"])
        self.dl_policy.setToolTip(
            "Download overwrite policy:\n"
            "• safe = avoid overwriting files (auto-rename if needed)\n"
            "• overwrite = replace existing files"
        )

        self.mux_policy = QComboBox()
        self.mux_policy.addItems(["safe", "overwrite"])
        self.mux_policy.setToolTip(
            "Mux overwrite policy:\n"
            "• safe = avoid overwriting files (auto-rename if needed)\n"
            "• overwrite = replace existing files"
        )

        self.demux_policy = QComboBox()
        self.demux_policy.addItems(["safe", "overwrite"])
        self.demux_policy.setToolTip(
            "Demux overwrite policy:\n"
            "• safe = avoid overwriting files (auto-rename if needed)\n"
            "• overwrite = replace existing files"
        )

        # --- Directories ---
        self.dl_dir = QLineEdit()
        self.dl_dir.setToolTip("Path to save downloaded files (hover to see full path)")
        self.mux_dir = QLineEdit()
        self.mux_dir.setToolTip("Path to save muxed files (hover to see full path)")
        self.demux_dir = QLineEdit()
        self.demux_dir.setToolTip("Path to save demuxed files (hover to see full path)")

        # Browse buttons
        b1 = QPushButton("Browse")
        b1.setToolTip("Select download output directory")
        b2 = QPushButton("Browse")
        b2.setToolTip("Select mux output directory")
        b3 = QPushButton("Browse")
        b3.setToolTip("Select demux output directory")

        # Restore buttons
        self.restore_dl_btn = QPushButton("Restore")
        self.restore_dl_btn.setToolTip("Restore the last used download directory")
        self.restore_mux_btn = QPushButton("Restore")
        self.restore_mux_btn.setToolTip("Restore the last used mux directory")
        self.restore_demux_btn = QPushButton("Restore")
        self.restore_demux_btn.setToolTip("Restore the last used demux directory")

        # --- Buttons ---
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setToolTip("Reset all settings to default values (not saved until you click OK)")
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setToolTip("Save changes and close the preferences dialog")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Discard changes and close the preferences dialog")

        # --- Layout ---
        layout = QVBoxLayout()

        # Policies
        for title, widget in [
            ("Download overwrite policy", self.dl_policy),
            ("Mux overwrite policy", self.mux_policy),
            ("Demux overwrite policy", self.demux_policy),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            row.addWidget(widget)
            layout.addLayout(row)

        # Dirs
        for title, edit, browse_btn, restore_btn in [
            ("Download output dir", self.dl_dir, b1, self.restore_dl_btn),
            ("Mux output dir", self.mux_dir, b2, self.restore_mux_btn),
            ("Demux output dir", self.demux_dir, b3, self.restore_demux_btn),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            row.addWidget(edit)
            row.addWidget(browse_btn)
            row.addWidget(restore_btn)
            layout.addLayout(row)

        # Action buttons
        buttons = QHBoxLayout()
        buttons.addWidget(self.reset_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.ok_btn)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

        self.setLayout(layout)

        # --- Connections ---
        self.reset_btn.clicked.connect(self.reset_defaults)
        self.ok_btn.clicked.connect(self.accept_and_save)
        self.cancel_btn.clicked.connect(self.reject)

        b1.clicked.connect(lambda: self._pick_dir(self.dl_dir, "download", self.restore_dl_btn))
        b2.clicked.connect(lambda: self._pick_dir(self.mux_dir, "mux", self.restore_mux_btn))
        b3.clicked.connect(lambda: self._pick_dir(self.demux_dir, "demux", self.restore_demux_btn))

        self.restore_dl_btn.clicked.connect(lambda: self._restore_dir("download", self.dl_dir, self.restore_dl_btn))
        self.restore_mux_btn.clicked.connect(lambda: self._restore_dir("mux", self.mux_dir, self.restore_mux_btn))
        self.restore_demux_btn.clicked.connect(lambda: self._restore_dir("demux", self.demux_dir, self.restore_demux_btn))

        self.dl_dir.textChanged.connect(lambda: self._check_restore_button("download", self.dl_dir, self.restore_dl_btn))
        self.mux_dir.textChanged.connect(lambda: self._check_restore_button("mux", self.mux_dir, self.restore_mux_btn))
        self.demux_dir.textChanged.connect(lambda: self._check_restore_button("demux", self.demux_dir, self.restore_demux_btn))

        # Load settings into UI
        self._load_into_ui()

    # --- Helpers ---
    def _pick_dir(self, edit: QLineEdit, key: str, btn: QPushButton):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            edit.setText(d)
            edit.setToolTip(f"{key.capitalize()} output directory:\n{d}")
            self._check_restore_button(key, edit, btn)

    def _restore_dir(self, key: str, widget: QLineEdit, btn: QPushButton):
        lod = self.settings.data.get("last_output_dir", {})
        default_path = str(Path.cwd())
        saved_path = lod.get(key, default_path)
        widget.setText(saved_path)
        widget.setToolTip(f"{key.capitalize()} output directory:\n{saved_path}")
        btn.setEnabled(False)

    def _check_restore_button(self, key: str, widget: QLineEdit, btn: QPushButton):
        lod = self.settings.data.get("last_output_dir", {})
        default_path = str(Path.cwd())
        saved_path = lod.get(key, default_path)
        btn.setEnabled(widget.text() != saved_path)

    def _load_into_ui(self):
        pol = self.settings.data.get("overwrite_policy", {})
        self.dl_policy.setCurrentText(pol.get("download", "safe"))
        self.mux_policy.setCurrentText(pol.get("mux", "safe"))
        self.demux_policy.setCurrentText(pol.get("demux", "safe"))

        lod = self.settings.data.get("last_output_dir", {})
        default_path = str(Path.cwd())

        dl_path = lod.get("download", default_path)
        mux_path = lod.get("mux", default_path)
        demux_path = lod.get("demux", default_path)

        self.dl_dir.setText(dl_path)
        self.mux_dir.setText(mux_path)
        self.demux_dir.setText(demux_path)

        self.dl_dir.setToolTip(f"Download output directory:\n{dl_path}")
        self.mux_dir.setToolTip(f"Mux output directory:\n{mux_path}")
        self.demux_dir.setToolTip(f"Demux output directory:\n{demux_path}")

        self.restore_dl_btn.setEnabled(self.dl_dir.text() != dl_path)
        self.restore_mux_btn.setEnabled(self.mux_dir.text() != mux_path)
        self.restore_demux_btn.setEnabled(self.demux_dir.text() != demux_path)

    def reset_defaults(self):
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.settings.data = DEFAULT_SETTINGS.copy()
            self._load_into_ui()

    def accept_and_save(self):
        self.settings.data["overwrite_policy"] = {
            "download": self.dl_policy.currentText(),
            "mux": self.mux_policy.currentText(),
            "demux": self.demux_policy.currentText(),
        }
        self.settings.data["last_output_dir"] = {
            "download": self.dl_dir.text() or INSTALL_DIR,
            "mux": self.mux_dir.text() or INSTALL_DIR,
            "demux": self.demux_dir.text() or INSTALL_DIR,
        }
        self.settings.save()
        self.done(QDialog.Accepted)

