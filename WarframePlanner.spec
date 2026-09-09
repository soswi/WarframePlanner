# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

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
    name="WarframePlanner",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
)
