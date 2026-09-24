# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

studio_dir = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(studio_dir, 'index.html'), '.'),
    (os.path.join(studio_dir, 'styles.css'), '.'),
    (os.path.join(studio_dir, 'app.js'), '.'),
    (os.path.join(studio_dir, 'frontend'), 'frontend'),
    (os.path.join(studio_dir, 'sample_data'), 'sample_data'),
]

hidden_imports = [
    'backend',
    'backend.io_utils',
    'backend.pipeline',
    'backend.patch_inspector',
    'backend.blending',
    'backend.feature_engine',
    'backend.matcher',
    'backend.global_stitching',
    'backend.manual_export',
    'backend.project_schemas',
    'backend.project_store',
    'cv2',
    'numpy',
    'PIL',
    'PIL.Image',
    'tifffile',
    'psutil',
    'scipy',
    'scipy.spatial',
    'urllib',
    'http.server',
]

a = Analysis(
    ['launcher.py'],
    pathex=[studio_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
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
    name='OmniStitch-Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
