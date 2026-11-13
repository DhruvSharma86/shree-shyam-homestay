# PyInstaller spec for the Shree Shyam Home Stay packaged desktop backend.
# Build from the backend directory:
#   cd backend && pyinstaller packaging/desktop_entry.spec --noconfirm
# Output: dist/ShreeShyamBackend/ShreeShyamBackend.exe (onedir, Windows x64).

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

BACKEND_DIR = os.path.dirname(SPECPATH)  # backend/
PACKAGING_DIR = SPECPATH

hiddenimports = []
datas = [(os.path.join(BACKEND_DIR, "alembic"), "alembic")]
binaries = []

# uvicorn loads "app.main:app" dynamically — PyInstaller cannot infer it, so
# include the entire application package explicitly.
hiddenimports += collect_submodules("app")

for package in ("psycopg", "reportlab", "uvicorn", "argon2", "pydantic_core"):
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hiddenimports
    except Exception:
        hiddenimports += collect_submodules(package)

hiddenimports += [
    "psycopg",
    "psycopg.rows",
    "psycopg_binary",
    "alembic",
    "reportlab.pdfgen.canvas",
    "reportlab.lib.pagesizes",
    "argon2.low_level",
]

a = Analysis(
    [os.path.join(PACKAGING_DIR, "desktop_entry.py")],
    pathex=[BACKEND_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "httpx.testclient", "mypy", "ruff", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShreeShyamBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # spawned with windowsHide by Electron — no visible window
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ShreeShyamBackend",
)
