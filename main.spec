# -*- mode: python ; coding: utf-8 -*-
# ScriptShaper.app 번들 빌드 (onedir → 첫 실행 빠름, zip 배포로 실행 권한 보존)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
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
    [],
    exclude_binaries=True,  # onedir: 자가 압축해제 없음 → 실행 속도 개선
    name='ScriptShaper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 앱 — 터미널 창 없이 실행
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
    name='ScriptShaper',
)

app = BUNDLE(
    coll,
    name='ScriptShaper.app',
    icon=None,
    bundle_identifier='com.sora9z.scriptshaper',
    info_plist={
        'CFBundleName': 'ScriptShaper',
        'CFBundleDisplayName': 'ScriptShaper',
        'NSHighResolutionCapable': True,
    },
)
