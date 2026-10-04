# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller single-file build definition."""

import sys

from pathlib import Path

project_root = Path(SPECPATH).parent
source_root = project_root / "src"

a = Analysis(
    [str(source_root / "qserialtool" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (str(project_root / "LICENSE"), "."),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
        (
            str(source_root / "qserialtool" / "ui" / "assets"),
            "qserialtool/ui/assets",
        ),
    ],
    hiddenimports=["serial.tools.list_ports"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_qt", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

icon = (
    str(source_root / "qserialtool" / "ui" / "assets" / "qserialtool.ico")
    if sys.platform == "win32"
    else None
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="QSerialTool",
    icon=icon,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
