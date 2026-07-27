# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

_IS_MAC = sys.platform == 'darwin'
# macOS usa .icns; Windows/Linux usan .ico
_ICON = ('images/main_window/main_icon.icns' if _IS_MAC
         else 'images/main_window/main_icon.ico')

# Versión para el Info.plist de macOS (el CI la inyecta en version.py antes de compilar)
_version_ns = {}
with open('version.py', encoding='utf-8') as _f:
    exec(_f.read(), _version_ns)
_VERSION = _version_ns.get('__version__', 'dev')

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
    datas=[('images', 'images'), ('fonts', 'fonts'), ('estilos.css', '.')],
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
    icon=_ICON,
)

# En macOS se empaqueta como bundle PlayIt.app (Finder no lanza binarios sueltos
# con GUI de forma nativa; el bundle además aporta icono e Info.plist)
if _IS_MAC:
    app = BUNDLE(
        exe,
        name='PlayIt.app',
        icon=_ICON,
        bundle_identifier='com.ravilesx.playit',
        info_plist={
            'CFBundleName': 'PlayIt',
            'CFBundleDisplayName': 'PlayIt',
            'CFBundleShortVersionString': _VERSION,
            'NSHighResolutionCapable': True,
        },
    )
