# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata

datas = [('templates', 'templates'), ('static', 'static'), ('best.pt', '.'), ('classes.txt', '.'), ('PCB_remake\\test\\images\\01_missing_hole_04.jpg', 'PCB_remake\\test\\images'), ('PCB_remake\\test\\images\\01_mouse_bite_12.jpg', 'PCB_remake\\test\\images'), ('PCB_remake\\test\\images\\01_open_circuit_04_create_5.jpg', 'PCB_remake\\test\\images')]
datas += copy_metadata('ultralytics')
datas += copy_metadata('timm')


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['gradio', 'tensorboard'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PCBDefectStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PCBDefectStudio',
)
