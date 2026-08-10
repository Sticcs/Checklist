# Build with: pyinstaller checklist.spec (from backend/, desktop venv active)
# Produces dist/ChecklistApp.exe - a single portable file (onefile mode), so
# it's easy to serve as a direct download from the website - see README.md.
from pathlib import Path

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    # The built frontend (frontend/dist, produced by `npm run build`) is
    # bundled read-only alongside the app - app/paths.py's resource_path()
    # resolves it inside sys._MEIPASS at this same relative path when frozen.
    datas=[
        (str(Path("..") / "frontend" / "dist"), str(Path("frontend") / "dist")),
    ],
    hiddenimports=[
        # uvicorn resolves these dynamically at runtime (by string, not a
        # top-level import), so PyInstaller's static analysis misses them
        # unless listed explicitly - the classic first error when freezing
        # an ASGI app is one of these being missing.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ChecklistApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Same artwork as the website's favicon (frontend/public/favicon.png) -
    # regenerate via: python -c "from PIL import Image; Image.open('../frontend/public/favicon.png').save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    icon="icon.ico",
)
