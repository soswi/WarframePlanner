# -*- mode: python ; coding: utf-8 -*-
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# Read the version straight from the package rather than repeating it here, so
# a release only ever needs planner/__init__.py bumped. Parsed with a regex
# instead of imported, because importing would pull in the app's dependencies
# during the build.
VERSION = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    Path("planner/__init__.py").read_text(encoding="utf-8"),
).group(1)

hiddenimports = collect_submodules("uvicorn") + [
    "anyio._backends._asyncio",
    "multipart",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("planner/static", "planner/static")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f"WarframePlanner-{VERSION}",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
)
