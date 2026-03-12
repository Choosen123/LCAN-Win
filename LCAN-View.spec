# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['up2.py'],
    pathex=[],
    binaries=[('gs_usb.cp314-mingw_x86_64_ucrt_gnu.pyd', '.'), ('C:/msys64/ucrt64/bin/libusb-1.0.dll', '.')],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LCAN-View',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['LCAN-View.ico'],
)
