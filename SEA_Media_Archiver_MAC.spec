# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['SMA_Pro_MAC.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('logo.png', '.'),
        ('pauly.png', '.'),
        ('scope.png', '.'),
        ('chest.png', '.'),
        ('my_icon.png', '.'),
        ('my_icon.ico', '.')
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'browser_cookie3',
        'yt_dlp',
        'youtube_transcript_api',
        'whisper',
        'requests'
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SEA Media Archiver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='my_icon.icns'
)

app = BUNDLE(
    exe,
    name='SEA Media Archiver.app',
    icon='my_icon.icns',
    bundle_identifier='com.sea.mediaarchiver',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'LSBackgroundOnly': 'False'
    }
)