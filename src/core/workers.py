"""Qt 后台工作者：所有耗时操作都不在主线程执行。"""
import shutil
import os
import time

from PySide6.QtCore import QThread, Signal

from core import ffmpeg as ff
from core import imglib


class Cancelled(Exception):
    pass


class FnWorker(QThread):
    """运行任意无参函数，结果/异常通过信号返回（取帧、缩略图等）。

    结果同时存在 self.result / self.error 上，供接收槽用 sender() 读取；
    外部槽必须是接收者对象（QObject）的绑定方法，保证回调在主线程执行。
    """
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._fn()
            self.done.emit(self.result)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            self.failed.emit(str(e))


class GifWorker(QThread):
    """GIF 生成（也用于动图再压缩）。progress: 0-100。"""
    progress = Signal(int)
    ok = Signal(str, float)          # 产物路径, 用时(秒)
    failed = Signal(str)

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self._params = params
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _on_progress(self, p):
        if self._cancelled:
            raise Cancelled()
        self.progress.emit(int(p * 100))

    def run(self):
        t0 = time.time()
        try:
            path = ff.make_gif(progress=self._on_progress,
                               cancel_check=lambda: self._cancelled, **self._params)
            self.ok.emit(path, time.time() - t0)
        except (Cancelled, ff.FfmpegCancelled):
            self.failed.emit("已取消")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ImgWorker(QThread):
    """批量图片压缩。每个文件完成发一条 row 信号。"""
    row = Signal(int, dict)          # 行号, {orig,new,kind,dst,skipped} 或 {"error":...}
    progress = Signal(int)
    done = Signal(int, int)          # 成功数, 跳过数
    failed = Signal(str)

    def __init__(self, files, options, parent=None):
        super().__init__(parent)
        self._files = list(files)
        self._opt = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _dst_for(self, src):
        if self._opt["outdir_mode"] == "custom" and self._opt["outdir"]:
            outdir = self._opt["outdir"]
            os.makedirs(outdir, exist_ok=True)
        else:
            outdir = os.path.dirname(src)
        kind = imglib.target_kind(src, self._opt["fmt"])
        base = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(outdir, base + self._opt["suffix"] + imglib.EXT_BY_KIND[kind])
        return dst

    def run(self):
        ok_n = skip_n = 0
        try:
            for i, src in enumerate(self._files):
                if self._cancelled:
                    break
                dst = self._dst_for(src)
                try:
                    orig, new, kind = imglib.compress_one(
                        src, dst,
                        fmt=self._opt["fmt"], quality=self._opt["quality"],
                        max_edge=self._opt["max_edge"],
                        quantize_png=self._opt["quantize_png"])
                    skipped = False
                    if self._opt["skip_larger"] and self._opt["fmt"] == "keep" \
                            and new >= orig and os.path.splitext(src)[1].lower() == \
                            imglib.EXT_BY_KIND[kind]:
                        os.remove(dst)
                        skipped = True
                        skip_n += 1
                    else:
                        ok_n += 1
                    self.row.emit(i, {"orig": orig, "new": new, "kind": kind,
                                      "dst": dst, "skipped": skipped})
                except Exception as e:  # noqa: BLE001
                    self.row.emit(i, {"error": str(e)})
                self.progress.emit(int((i + 1) * 100 / max(1, len(self._files))))
            self.done.emit(ok_n, skip_n)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def install_preview(src, dst):
    """把临时预览产物保存到输出目录（跨盘移动兼容）。"""
    dst = shutil.move(src, dst)
    return dst
