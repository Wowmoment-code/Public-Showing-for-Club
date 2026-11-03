"""Persistent, workspace-local settings and recent-document list."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR, RECENT_FILE, SETTINGS_FILE, SIGNATURE_FILE, ensure_dirs

DEFAULT_SETTINGS: dict[str, Any] = {
    "view_mode": "continuous",
    "zoom": 1.0,
    "last_dir": "",
    "recent_limit": 12,
    "show_welcome": True,
    "theme": "light",
    "author": "星澜 PDF 用户",
    "ocr_dpi": 200,
}


class Store:
    def __init__(self) -> None:
        ensure_dirs()
        self.settings = dict(DEFAULT_SETTINGS)
        self.recent: list[dict[str, Any]] = []
        self._thumbs = DATA_DIR / "thumbs"
        self._thumbs.mkdir(parents=True, exist_ok=True)
        self.load()

    # ------------------------------------------------------------------ json
    @staticmethod
    def _read(path: Path, fallback: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return fallback

    def load(self) -> None:
        data = self._read(SETTINGS_FILE, {})
        if isinstance(data, dict):
            self.settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        recent = self._read(RECENT_FILE, [])
        if isinstance(recent, list):
            self.recent = [r for r in recent if isinstance(r, dict) and r.get("path")]
        self.recent = self.recent[: int(self.settings.get("recent_limit", 12))]

    def save_settings(self) -> None:
        ensure_dirs()
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.settings, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)

    def save_recent(self) -> None:
        ensure_dirs()
        tmp = RECENT_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.recent, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, RECENT_FILE)

    # ---------------------------------------------------------------- recent
    def touch_recent(
        self,
        path: str,
        title: str | None = None,
        page: int = 0,
        thumbnail_png: bytes | None = None,
    ) -> None:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return
        entry = next((r for r in self.recent if os.path.abspath(r["path"]) == path), None)
        if entry is None:
            entry = {"path": path, "title": title or os.path.basename(path)}
            self.recent.insert(0, entry)
        entry["title"] = title or entry.get("title") or os.path.basename(path)
        entry["opened"] = time.time()
        entry["page"] = max(0, int(page))
        entry["size"] = os.path.getsize(path) if os.path.exists(path) else 0
        if thumbnail_png:
            digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]
            thumb_path = self._thumbs / f"{digest}.png"
            try:
                thumb_path.write_bytes(thumbnail_png)
                entry["thumb"] = str(thumb_path)
            except OSError:
                pass
        self.recent = [r for r in self.recent if os.path.exists(r.get("path", ""))]
        self.recent.sort(key=lambda r: r.get("opened", 0), reverse=True)
        limit = int(self.settings.get("recent_limit", 12))
        self.recent = self.recent[:limit]
        self.save_recent()

    def remove_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        self.recent = [r for r in self.recent if os.path.abspath(r.get("path", "")) != path]
        self.save_recent()

    def clear_recent(self) -> None:
        self.recent.clear()
        self.save_recent()

    # -------------------------------------------------------------- signature
    def save_signature(self, png_bytes: bytes) -> None:
        payload = {"png": base64.b64encode(png_bytes).decode("ascii"), "saved": time.time()}
        tmp = SIGNATURE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, SIGNATURE_FILE)

    def load_signature(self) -> bytes | None:
        data = self._read(SIGNATURE_FILE, {})
        if isinstance(data, dict) and data.get("png"):
            try:
                return base64.b64decode(data["png"])
            except Exception:
                return None
        return None


STORE: Store | None = None


def store() -> Store:
    global STORE
    if STORE is None:
        STORE = Store()
    return STORE
