# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['freetv.py'],
    pathex=[],
    binaries=[],
    datas=[('lib', 'lib'],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    name='FreeTV',
    console=False,
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='freetv',
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
    name='freetv',
)