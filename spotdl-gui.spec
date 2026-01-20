# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Assets to include
added_files = [
    ('app/assets/icon.png', 'app/assets'),
    ('README.md', '.'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=['customtkinter', 'PIL', 'PIL._tkinter_finder', 'spotipy', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpotDL-GUI',
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
    icon='app/assets/icon.png',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpotDL-GUI',
)

app = BUNDLE(
    coll,
    name='SpotDL-GUI.app',
    icon='app/assets/icon.png',
    bundle_identifier='com.spotdlgui.app',
)
