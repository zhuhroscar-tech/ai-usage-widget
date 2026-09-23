# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('providers', 'providers')],
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
    name='AI Usage',
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
    name='AI Usage',
)
app = BUNDLE(
    coll,
    name='AI Usage.app',
    icon='assets/AppIcon.icns',
    bundle_identifier='com.oscarzhu.ai-usage-widget',
    info_plist={
        'CFBundleName': 'AI Usage',
        'CFBundleDisplayName': 'AI Usage',
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion': '1',
        'LSUIElement': True,
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSHumanReadableCopyright': 'For personal use.',
    },
)
