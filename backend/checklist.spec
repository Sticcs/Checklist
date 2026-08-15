# Build with: pyinstaller checklist.spec (from backend/, desktop venv active)
#
# Windows: dist/ChecklistApp.exe - a single portable file (onefile mode).
#
# macOS: dist/ChecklistApp.app - PyInstaller deprecates onefile+BUNDLE()
# together ("a .app bundle can not be a single file and clashes with
# macOS's security" - confirmed by a real build: it works today but warns
# this becomes a hard error in PyInstaller v7), so macOS instead uses the
# onedir + COLLECT() + BUNDLE() path it actually recommends: EXE() here
# builds just the bootloader (exclude_binaries=True), COLLECT() gathers it
# plus every dependency into dist/ChecklistApp/, and BUNDLE() wraps that
# directory into the final .app package.
#
# Either way, the result is meant to be served as a direct download from the
# website - see README.md.
import sys
from pathlib import Path

block_cipher = None
is_macos = sys.platform == "darwin"

# The built frontend (frontend/dist, produced by `npm run build`) is bundled
# read-only alongside the app - app/paths.py's resource_path() resolves it
# inside sys._MEIPASS at this same relative path when frozen. Built file-by-
# file (skipping frontend/dist/downloads) rather than as a single directory
# tuple: Vite copies frontend/public/ verbatim into dist/, and public/
# holds the website's downloadable ChecklistApp.exe / ChecklistApp-mac.zip -
# bundling those into the desktop app itself is pure dead weight (the app
# never needs to serve its own installer to itself), and worse, compounds on
# every rebuild: build once with a mac.zip already in public/downloads/ and
# the next app embeds a copy of the previous one, growing without bound.
_frontend_dist_src = Path("..") / "frontend" / "dist"
_frontend_datas = [
    (str(f), str(Path("frontend") / "dist" / f.relative_to(_frontend_dist_src).parent))
    for f in _frontend_dist_src.rglob("*")
    if f.is_file() and "downloads" not in f.relative_to(_frontend_dist_src).parts[:-1]
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=_frontend_datas,
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
        # plyer.notification (desktop.py) picks its backend module by
        # platform string at runtime, not a static top-level import, so
        # PyInstaller's analysis misses it the same way it misses uvicorn's
        # dynamic imports above - only the current platform's module exists
        # to even scan.
        "plyer.platforms.macosx.notification" if is_macos else "plyer.platforms.win.notification",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Same artwork as the website's favicon (frontend/public/favicon.png).
# Windows wants .ico; regenerate via:
#   python -c "from PIL import Image; Image.open('../frontend/public/favicon.png').save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
# macOS wants .icns; regenerate via (from backend/, macOS only):
#   rm -rf icon.iconset && mkdir icon.iconset && SRC=../frontend/public/favicon.png && \
#   for s in 16 32 128 256; do sips -z $s $s "$SRC" --out icon.iconset/icon_${s}x${s}.png; \
#   sips -z $((s*2)) $((s*2)) "$SRC" --out icon.iconset/icon_${s}x${s}@2x.png; done && \
#   iconutil -c icns icon.iconset -o icon.icns && rm -rf icon.iconset
icon_file = "icon.icns" if is_macos else "icon.ico"

if is_macos:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ChecklistApp",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        # Standard, low-risk entitlements for any codesigned app embedding
        # WKWebView (see entitlements.plist) - disables a few hardened-
        # runtime restrictions (library validation, JIT, unsigned executable
        # memory) that WebKit's own helper processes can need. Not required
        # to fix the actual blank-white-window bug this build hit (that
        # turned out to be a symlink-resolution bug in app/paths.py's
        # resource_path(), unrelated to code signing - see its docstring),
        # but harmless and worth keeping as a defensive default.
        entitlements_file="entitlements.plist",
        icon=icon_file,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="ChecklistApp",
    )
    app = BUNDLE(
        coll,
        name="ChecklistApp.app",
        icon=icon_file,
        bundle_identifier="com.debayanm.checklist",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            # desktop.py loads http://127.0.0.1:<port> (plain HTTP, an IP
            # literal rather than the hostname "localhost") into the native
            # WKWebView window. App Transport Security blocks non-HTTPS
            # loads by default and doesn't automatically exempt IP-literal
            # loopback addresses the way it does a browser tab, so this key
            # is needed for the load to be allowed at all.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
else:
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
        icon=icon_file,
    )
