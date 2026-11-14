"""Build a standalone AshesQOL.exe with PyInstaller.

    pip install pyinstaller
    python build.py

Output: dist/AshesQOL.exe (single file, no console window). At runtime it keeps its settings,
updated offsets and ashesqol.log next to the exe.
"""
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent


def main() -> int:
    data = ROOT / "ashesqol" / "data"
    sep = ";" if sys.platform == "win32" else ":"
    args = [
        str(ROOT / "main.py"),
        "--name", "AshesQOL",
        "--onefile",
        "--windowed",                                   # no console; logs go to ashesqol.log
        "--icon", str(data / "icon.ico"),
        "--add-data", f"{data / 'offsets.json'}{sep}ashesqol/data",
        "--add-data", f"{data / 'icon.ico'}{sep}ashesqol/data",
        "--hidden-import", "numpy",                     # imported lazily by the offset update
        # Qt pieces AshesQOL doesn't use: keeps the exe smaller.
        "--exclude-module", "PyQt6.QtWebEngineCore", "--exclude-module", "PyQt6.QtMultimedia",
        "--exclude-module", "PyQt6.QtQml", "--exclude-module", "PyQt6.QtQuick", "--exclude-module", "PyQt6.Qt3DCore",
        "--exclude-module", "tkinter",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--noconfirm", "--clean",
    ]
    PyInstaller.__main__.run(args)
    exe = ROOT / "dist" / "AshesQOL.exe"
    print(f"\nBuilt {exe} ({exe.stat().st_size / 1e6:.0f} MB)")
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
