"""便携式配置持久化：优先写程序目录 config.json，目录只读时回退到用户目录。"""
import json
import os
import sys

APP_NAME = "GifKit"
APP_VERSION = "0.5.0"

DEFAULTS = {
    "gif": {
        "width_mode": "720", "width_custom": 720, "fps": 12,
        "colors": 128, "dither": "bayer",
        "suffix": "_gif", "outdir_mode": "source", "outdir": "",
    },
    "img": {
        "fmt": "keep", "quality": 80, "max_edge_mode": "0", "max_edge_custom": 1920,
        "quantize_png": True, "skip_larger": True,
        "suffix": "_c", "outdir_mode": "source", "outdir": "",
    },
}


def app_dir() -> str:
    """配置所在目录：Windows 沿用 exe 同目录（绿色便携）；mac 放用户 Application
    Support（.app 包内不便写入）；Linux 优先 AppImage 所在目录，其次解包目录。"""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = os.environ.get("HOME") or os.path.expanduser("~")
            return os.path.join(base, "Library", "Application Support", APP_NAME)
        if sys.platform.startswith("linux"):
            appimage = os.environ.get("APPIMAGE")
            if appimage:
                return os.path.dirname(appimage)
            return os.path.dirname(sys.executable)
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    def __init__(self):
        self.dir = app_dir()
        self.path = os.path.join(self.dir, "config.json")
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def _fallback_path(self) -> str:
        """save 写入失败时的回退路径（与 save 的回退顺序一致）。"""
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME, "config.json")

    def load(self):
        saved = None
        for path in (self.path, self._fallback_path()):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                break
            except (OSError, ValueError):
                continue
        if saved is None:
            return
        if not isinstance(saved, dict):     # 合法 JSON 但顶层不是对象 → 按损坏丢弃
            return
        for sec, vals in saved.items():
            if isinstance(vals, dict):
                self.data.setdefault(sec, {}).update(vals)
            # 非 dict 分区（损坏配置）丢弃，避免后续 .get() AttributeError 崩溃

    def save(self):
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        for path in (self.path, self._fallback_path()):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp_path = path + ".tmp"        # 原子写：防进程被杀留下半截 JSON
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp_path, path)
                return
            except OSError:
                continue
