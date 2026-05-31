# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Invoice Generator App
Creates a windowed exe (no console) with all required files included
Updated to support:
- PySide6 with QCalendarWidget for date pickers
- ReportLab with Unicode font support for Rupee symbol (₹)
- Config and data persistence
"""

import os
from pathlib import Path

block_cipher = None

# Get the absolute path to the project (spec file directory)
project_root = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        # Include logo from invoice_app folder
        (os.path.join(project_root, 'invoice_app', 'logo.png'), 'invoice_app'),
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtSvg',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.lib.enums',
        'reportlab.lib.colors',
        'reportlab.lib.units',
        'reportlab.lib.utils',
        'reportlab.platypus',
        'reportlab.pdfbase',
        'reportlab.pdfbase.ttfonts',
        'sqlite3',
        'json',
        'decimal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Invoice Generator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # This creates a windowed app without console
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'invoice_app', 'logo.png'),  # Use logo as icon
)
