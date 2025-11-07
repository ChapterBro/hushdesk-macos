# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

_HUSH_DESK_SUBMODULES = collect_submodules('hushdesk')


a = Analysis(
    ['src/hushdesk/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('hushdesk/config', 'config'),
        ('src/hushdesk', 'hushdesk'),
        ('src/sitecustomize.py', '.'),
    ],
    hiddenimports=_HUSH_DESK_SUBMODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyinstaller_runtime_hook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HushDesk',
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
    icon=['/Users/hushdesk/Projects/hushdesk-macos/assets/icons/hushdesk.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HushDesk',
)
app = BUNDLE(
    coll,
    name='HushDesk.app',
    icon='/Users/hushdesk/Projects/hushdesk-macos/assets/icons/hushdesk.icns',
    bundle_identifier='com.nottingham.hushdesk',
)
