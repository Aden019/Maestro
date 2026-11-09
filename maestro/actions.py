"""Finding and opening apps on this Mac."""

import subprocess
from pathlib import Path

APP_FOLDERS = (
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
)


def installed_apps():
    names = {path.stem for folder in APP_FOLDERS if folder.is_dir() for path in folder.glob("*.app")}
    return sorted(names, key=str.casefold)


def open_app(name):
    """Opens an app by name. Returns None on success, or a short reason it failed."""
    try:
        result = subprocess.run(["open", "-a", name], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "macOS didn't respond in time"
    return None if result.returncode == 0 else "macOS couldn't find it"
