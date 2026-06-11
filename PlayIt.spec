# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs

# El hook automático de PyQt6 no recolecta los plugins de Qt cuando se
# compila bajo Wine/Docker (necesita inicializar Qt para consultarlos y
# falla en silencio); sin plugins/platforms/qwindows.dll el exe muere al
# arrancar con "no Qt platform plugin could be initialized".
# Recolección manual por filesystem, que funciona en cualquier entorno.
_QT_PLUGIN_DIRS = ('platforms', 'styles', 'imageformats', 'iconengines')
qt_plugins = [
    (src, dest) for src, dest in collect_dynamic_libs('PyQt6')
    if any(d in dest.replace('\\', '/').split('/') for d in _QT_PLUGIN_DIRS)
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=qt_plugins,
    datas=[('images', 'images'), ('estilos.css', '.')],
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
    name='PlayIt',
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
    icon='images/main_window/main_icon.ico',
)
