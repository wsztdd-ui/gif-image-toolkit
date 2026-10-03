"""便携式配置持久化：优先写程序目录 config.json，目录只读时回退到用户目录。"""
import json
import os
import sys

APP_NAME = "GifKit"
APP_VERSION = "0.2.0"

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
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    def __init__(self):
        self.dir = app_dir()
        self.path = os.path.join(self.dir, "config.json")
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for sec, vals in saved.items():
                if isinstance(vals, dict):
                    self.data.setdefault(sec, {}).update(vals)
                else:
                    self.data[sec] = vals
        except (OSError, ValueError):
            pass

    def save(self):
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(payload)
        except OSError:
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            alt = os.path.join(base, APP_NAME)
            try:
                os.makedirs(alt, exist_ok=True)
                with open(os.path.join(alt, "config.json"), "w", encoding="utf-8") as f:
                    f.write(payload)
            except OSError:
                pass
