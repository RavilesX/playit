# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('images/split_dialog/*.png', 'images/split_dialog'),
        ('images/main_window/*.png', 'images/main_window'),
        ('images/main_window/icons01/*.png', 'images/main_window/icons01'),
        ('images/main_window/*.ico', 'images/main_window'),
        ('estilos.css', '.'),
        ('images/main_window/dial_bg.png', 'images/main_window'),
        ('images/main_window/knob.png', 'images/main_window'),
        ('images/main_window/none.png', 'images/main_window'),
        ('images/main_window/default.png', 'images/main_window')
    ],
    hiddenimports=[
        'sounddevice',
        'soundfile',
        'numpy',
        'cffi',          # dependencia interna de sounddevice
        '_sounddevice',  # extensión C de sounddevice
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['demucs', 'torch', 'PySide6', 'PySide2','pygame','pydub',],  
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
    name='Playit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
	icon='images/main_window/main_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True
)