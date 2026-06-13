# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/web', 'ui/web')],
    hiddenimports=['webview', 'bottle', 'clr_loader', 'pythonnet'],
    hookspath=[],
    hooksconfig={},
    excludes=['PyQt5', 'PySide6', 'PyQt6', 'PySide2', 'matplotlib', 'scipy', 'numpy', 'IPython', 'pygame', 'pkg_resources', 'setuptools'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MVR_PSP_Check',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='MVR_PSP_Check',
)
