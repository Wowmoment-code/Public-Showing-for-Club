# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Stellar PDF."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve()
ASSETS = ROOT / "app" / "assets"
SAMPLE = ROOT / "sample"

datas = [
    (str(ASSETS), "app/assets"),
    (str(SAMPLE), "sample"),
]
binaries = []
hiddenimports = [
    "PySide6.QtSvg",
    "PySide6.QtPrintSupport",
    "pymupdf",
    "docx",
    "openpyxl",
    "pptx",
    "reportlab",
    "reportlab.pdfbase._fontdata",
    "reportlab.graphics.barcode",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "cv2",
    "yaml",
    "shapely",
    "pyclipper",
]

for package in ("rapidocr_onnxruntime", "onnxruntime"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

for package in ("docx", "pptx", "reportlab"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

for package in ("pymupdf", "onnxruntime"):
    try:
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "launch.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtNetworkAuth",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "tkinter",
        "matplotlib",
        "pandas",
        "scipy",
        "notebook",
        "IPython",
        "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="星澜PDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "app.ico"),
    version=str(ROOT / "version_info.txt"),
)
