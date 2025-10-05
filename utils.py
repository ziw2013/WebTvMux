import os, sys, json, re, subprocess
from pathlib import Path

# ---------- Base Directories ----------
def get_base_dir() -> Path:
    """
    Return the correct base directory for both development and frozen builds.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent  # EXE mode
    else:
        return Path(__file__).resolve().parent  # ✅ dev mode = same folder as utils.py

BASE_DIR = get_base_dir()
BIN_DIR = BASE_DIR / "bin"
CONFIG_DIR = BASE_DIR / "config"

# ---------- Executable Resolution ----------
def get_bin_path(tool: str) -> str:
    """
    Locate ffmpeg/ffprobe/yt-dlp executables from the bin folder.
    Works in both dev and app modes, and falls back to PATH if missing.
    """
    exe_name = f"{tool}.exe" if os.name == "nt" else tool
    exe_path = BIN_DIR / exe_name
    if exe_path.exists():
        return str(exe_path)
    return tool  # fallback to PATH if not found

FFMPEG = get_bin_path("ffmpeg")
FFPROBE = get_bin_path("ffprobe")
YTDLP = get_bin_path("yt-dlp")

# ---------- Hide Console for Subprocesses ----------
def no_console_flags():
    """Return startupinfo + creationflags that suppress console windows on Windows."""
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW
    return {"startupinfo": startupinfo, "creationflags": creationflags}

# ---------- Verify Tool Presence ----------
def verify_tools():
    """
    Ensure required executables exist.
    Works in both development and EXE environments.
    """
    missing = [exe for exe in (FFMPEG, FFPROBE, YTDLP) if not os.path.exists(exe)]
    if missing:
        missing_list = "\n".join(missing)
        raise FileNotFoundError(
            f"Missing required tools:\n{missing_list}\n\n"
            f"Make sure a 'bin' folder exists at:\n{BIN_DIR}\n"
            f"and contains ffmpeg.exe, ffprobe.exe, yt-dlp.exe."
        )

# ---------- Filename and Format Helpers ----------
def build_path_with_suffix(base: str, suffix: str) -> str:
    """
    Return a new file path by adding suffix before the extension.
    Example: 'video.mp4' + '_1080p' -> 'video_1080p.mp4'
    """
    p = Path(base)
    return str(p.with_name(p.stem + suffix + p.suffix))


def pick_video_suffix_from_format(fmt: dict) -> str:
    """
    Return a suffix (e.g. '_1080p') from yt-dlp format dictionary.
    """
    if not fmt:
        return ""
    res = fmt.get("height") or fmt.get("resolution") or fmt.get("format_note")
    if res:
        return f"_{res}"
    return ""


# ---------- Language Helpers ----------
def lang_for_mux(norm_code: str) -> str:
    """Convert 'floor' → 'ina' and pass through others unchanged."""
    if norm_code == "floor":
        return "ina"
    return norm_code


def load_languages(lang_file: str = None) -> dict:
    """
    Load language codes from config/languages.json.
    Works for both dev and frozen builds (EXE).
    Falls back to built-in defaults if missing or invalid.
    """
    # Default lookup priority:
    # 1. Explicitly passed path
    # 2. config/ next to executable or project root
    # 3. _MEIPASS (PyInstaller temp folder)
    if lang_file is None:
        if getattr(sys, "frozen", False):
            # ✅ Use actual executable directory first
            base_dir = Path(sys.executable).parent / "config"
        else:
            # ✅ Use project root during development
            base_dir = Path(__file__).resolve().parent / "config"

        lang_file = base_dir / "languages.json"

    # Fallback: PyInstaller's unpacked directory (as a last resort)
    if not lang_file.exists() and getattr(sys, "_MEIPASS", None):
        lang_file = Path(sys._MEIPASS) / "config" / "languages.json"

    try:
        with open(lang_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[load_languages] warning: {e}")

    # Final fallback
    return {}



# ---------- Default Settings ----------
DEFAULT_SETTINGS = {
    "overwrite_policy": {"download": "safe", "mux": "safe", "demux": "safe"},
    "last_output_dir": {
        "download": str(Path.cwd()),
        "mux": str(Path.cwd()),
        "demux": str(Path.cwd()),
    },
    "default_lang": "eng",
}


# ---------- Settings Manager ----------
class SettingsManager:
    def __init__(self, filename: str = "settings.json"):
        self.filename = Path(filename)
        self.data = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        """Load settings, or use defaults if missing/corrupt."""
        if self.filename.exists():
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.data = json.load(f)

                # --- Migration from old configs ---
                if "remux" in self.data.get("overwrite_policy", {}):
                    self.data["overwrite_policy"]["demux"] = self.data["overwrite_policy"].pop("remux")
                if "remux" in self.data.get("last_output_dir", {}):
                    self.data["last_output_dir"]["demux"] = self.data["last_output_dir"].pop("remux")

                # Fill defaults for missing keys
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in self.data:
                        self.data[k] = v
                    elif isinstance(v, dict):
                        for kk, vv in v.items():
                            self.data[k].setdefault(kk, vv)
            except Exception as e:
                print(f"Failed to load settings ({e}), using defaults.")
                self.data = DEFAULT_SETTINGS.copy()
        else:
            self.data = DEFAULT_SETTINGS.copy()

    def save(self):
        """Save settings safely."""
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")


# ---------- Utility: Ensure Unique Path ----------
def ensure_unique_path(filepath: Path) -> Path:
    """Append (1), (2)... until unique filename is found."""
    filepath = Path(filepath)
    if not filepath.exists():
        return filepath
    stem, suffix = filepath.stem, filepath.suffix
    parent = filepath.parent
    i = 1
    while True:
        new_path = parent / f"{stem} ({i}){suffix}"
        if not new_path.exists():
            return new_path
        i += 1


# ---------- Language Mapping ----------
_LANGS_DEFAULT = {
    "ara": "Arabic", "zho": "Chinese", "eng": "English", "fra": "French",
    "rus": "Russian", "spa": "Spanish", "ina": "Floor", "floor": "Floor",
    "ben": "Bangla", "deu": "German", "ell": "Greek", "hin": "Hindi",
    "ind": "Indonesian", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
    "pol": "Polish", "por": "Portuguese", "fas": "Persian", "swa": "Kiswahili",
    "tur": "Turkish", "tuk": "Turkmen", "vie": "Vietnamese", "urd": "Urdu",
    "ukr": "Ukrainian", "aze": "Azerbaijani",
}

_MAPPING_2TO3 = {
    "ar": "ara", "zh": "zho", "en": "eng", "fr": "fra", "ru": "rus", "es": "spa",
    "bn": "ben", "de": "deu", "el": "ell", "hi": "hin", "id": "ind", "it": "ita",
    "ja": "jpn", "jp": "jpn", "ko": "kor", "pl": "pol", "pt": "por", "fa": "fas",
    "sw": "swa", "tr": "tur", "tk": "tuk", "vi": "vie", "ur": "urd",
    "uk": "ukr", "az": "aze",
}

LANGS_639_2 = {**_LANGS_DEFAULT, **load_languages()}


def normalize_lang_code(code: str, fallback: str = "eng") -> str:
    """Normalize language codes (e.g. en-us -> eng, jp -> jpn, ia -> floor)."""
    if not code:
        return fallback
    code = code.strip().lower()
    if code in ("ia", "ina"):
        return "floor"
    match = re.search(r'[_\-\.]([a-z]{2,3})(?=[_\-\.])', code)
    if match:
        short = match.group(1)
        if short in ("ia", "ina"):
            return "floor"
        return _MAPPING_2TO3.get(short, fallback)
    if code in _MAPPING_2TO3:
        return _MAPPING_2TO3[code]
    if "-" in code:
        base = code.split("-")[0]
        return _MAPPING_2TO3.get(base, fallback)
    if code in LANGS_639_2:
        return code
    return fallback
