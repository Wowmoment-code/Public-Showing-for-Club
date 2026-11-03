"""Global configuration and paths for Stellar PDF."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_NAME = "星澜 PDF"
APP_NAME_EN = "StellarPDF"
APP_VERSION = "1.0.0"
APP_VENDOR = "Stellar Studio"
APP_SLOGAN = "像编辑文档一样编辑 PDF"


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


APP_DIR = _app_dir()
PROJECT_DIR = Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
    return base / "app" / "assets"


def asset_path(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


# Runtime data deliberately lives inside the project folder so the application
# remains self-contained and never scatters files around the host.
DATA_DIR = Path(os.environ.get("STELLAR_DATA_DIR", str(APP_DIR / "StellarPDF" / "runtime")))
RECENT_FILE = DATA_DIR / "recent.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
SIGNATURE_FILE = DATA_DIR / "signature.json"
UNDO_DIR = DATA_DIR / "undo"
TEMP_DIR = DATA_DIR / "temp"
EXPORT_DIR = Path(os.path.expanduser("~")) / "Documents"


def ensure_dirs() -> None:
    for folder in (DATA_DIR, UNDO_DIR, TEMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)


FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
]


def cjk_font_file() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


# Windows fonts that closely match the families commonly embedded in Chinese
# office PDFs.  Editing a paragraph with the *same* family is what keeps the
# document from suddenly switching to a generic sans-serif face.
_PDF_FONT_FAMILIES = {
    "microsoftyahei": ("Microsoft YaHei", ("msyh.ttc", "msyhbd.ttc", "msyh.ttc")),
    "microsoftyaheiui": ("Microsoft YaHei UI", ("msyh.ttc", "msyhbd.ttc", "msyh.ttc")),
    "微软雅黑": ("Microsoft YaHei", ("msyh.ttc", "msyhbd.ttc", "msyh.ttc")),
    "simsun": ("SimSun", ("simsun.ttc", "simsun.ttc", "simsun.ttc")),
    "songti": ("SimSun", ("simsun.ttc", "simsun.ttc", "simsun.ttc")),
    "宋体": ("SimSun", ("simsun.ttc", "simsun.ttc", "simsun.ttc")),
    "nsimsun": ("NSimSun", ("simsun.ttc", "simsun.ttc", "simsun.ttc")),
    "simhei": ("SimHei", ("simhei.ttf", "simhei.ttf", "simhei.ttf")),
    "黑体": ("SimHei", ("simhei.ttf", "simhei.ttf", "simhei.ttf")),
    "kaiti": ("KaiTi", ("simkai.ttf", "simkai.ttf", "simkai.ttf")),
    "楷体": ("KaiTi", ("simkai.ttf", "simkai.ttf", "simkai.ttf")),
    "fangsong": ("FangSong", ("simfang.ttf", "simfang.ttf", "simfang.ttf")),
    "仿宋": ("FangSong", ("simfang.ttf", "simfang.ttf", "simfang.ttf")),
    "dengxian": ("DengXian", ("Deng.ttf", "Dengb.ttf", "Deng.ttf")),
    "等线": ("DengXian", ("Deng.ttf", "Dengb.ttf", "Deng.ttf")),
    "arial": ("Arial", ("arial.ttf", "arialbd.ttf", "ariali.ttf")),
    "arialnarrow": ("Arial Narrow", ("ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF")),
    "timesnewroman": ("Times New Roman", ("times.ttf", "timesbd.ttf", "timesi.ttf")),
    "times": ("Times New Roman", ("times.ttf", "timesbd.ttf", "timesi.ttf")),
    "calibri": ("Calibri", ("calibri.ttf", "calibrib.ttf", "calibrii.ttf")),
    "cambria": ("Cambria", ("cambria.ttc", "cambriab.ttf", "cambriai.ttf")),
    "georgia": ("Georgia", ("georgia.ttf", "georgiab.ttf", "georgiai.ttf")),
    "verdana": ("Verdana", ("verdana.ttf", "verdanab.ttf", "verdanai.ttf")),
    "tahoma": ("Tahoma", ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf")),
    "segoeui": ("Segoe UI", ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf")),
    "consolas": ("Consolas", ("consola.ttf", "consolab.ttf", "consolai.ttf")),
    "couriernew": ("Courier New", ("cour.ttf", "courbd.ttf", "couri.ttf")),
}


def normalize_font_name(name: str) -> str:
    value = re.sub(r"^[A-Z]{6}\+", "", str(name or ""))
    value = value.split(",")[0]
    value = re.sub(
        r"(?i)(regular|bold|italic|oblique|medium|light|semibold|black|mt|ps)$",
        "",
        value,
    )
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def pdf_font_family_and_file(font_name: str, *, bold: bool = False, italic: bool = False) -> tuple[str, str | None]:
    """Return (family, file) matching an embedded PDF font.

    Using the same Windows family for replacement text avoids the most common
    WPS-parity complaint: “only one sentence was edited, but the whole
    paragraph changed its font”.
    """
    normalized = normalize_font_name(font_name)
    entry = _PDF_FONT_FAMILIES.get(normalized)
    if entry is None:
        # Try a prefix match for names such as "MicrosoftYaHeiBold".
        for key, value in _PDF_FONT_FAMILIES.items():
            if normalized.startswith(key):
                entry = value
                break
    if entry is None:
        path = cjk_font_file()
        return (ui_font_family(), path)
    family, filenames = entry
    if italic:
        candidate = filenames[2]
    elif bold:
        candidate = filenames[1]
    else:
        candidate = filenames[0]
    path = str(Path(r"C:\Windows\Fonts") / candidate)
    if not Path(path).exists():
        path = str(Path(r"C:\Windows\Fonts") / filenames[0])
    return family, (path if Path(path).exists() else cjk_font_file())


def ui_font_family() -> str:
    if os.name == "nt":
        return "Microsoft YaHei UI"
    return "Noto Sans CJK SC"


SUPPORTED_OPEN = "PDF 文件 (*.pdf);;所有文件 (*.*)"
SUPPORTED_IMAGES = "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
