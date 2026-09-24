# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('providers', 'providers'), ('assets/icon_alert.png', 'assets')],
    hiddenimports=['Crypto.Cipher.AES', 'Crypto.Protocol.KDF', 'certifi'],
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
    [],
    exclude_binaries=True,
    name='Token Telescope',
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
    icon='assets/AppIcon.icns',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Token Telescope',
)
app = BUNDLE(
    coll,
    name='Token Telescope.app',
    icon='assets/AppIcon.icns',
    bundle_identifier='com.oscarzhu.token-telescope',
    info_plist={
        'CFBundleName': 'Token Telescope',
        'CFBundleDisplayName': 'Token Telescope',
        'CFBundleShortVersionString': '2.3.2',
        'CFBundleVersion': '2.3.2',
        'LSUIElement': True,
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSHumanReadableCopyright': 'For personal use.',
    },
)
