"""取消路径单测：生成中途取消 → ffmpeg 进程必须被杀死，不残留、不卡死。"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core import ffmpeg as ff
from core.workers import GifWorker


def ffmpeg_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"],
                         capture_output=True).stdout.decode("gbk", errors="replace")
    return out.lower().count("ffmpeg.exe")


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="gifkit_cancel_")
    src = os.path.join(tmp, "long.ts")
    subprocess.run(
        [ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
         "-i", "testsrc2=size=1280x720:rate=30:duration=30",
         "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts", src],
        check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)

    out = os.path.join(tmp, "out.gif")
    wk = GifWorker(dict(video=src, out_path=out, start=0.0, duration=30.0,
                        crop=None, width=720, fps=12, colors=128, dither="bayer"))
    t0 = time.time()
    result = {}

    def on_failed(msg):
        result["msg"] = msg
        result["secs"] = time.time() - t0
        result["ffmpeg_left"] = ffmpeg_running()
        app.quit()

    def on_ok(path, secs):
        result["msg"] = "意外完成"
        app.quit()

    wk.failed.connect(on_failed)      # QThread 信号 → 绑定方法，主线程回调
    wk.ok.connect(on_ok)
    wk.start()

    def do_cancel():
        print("cancel at %.1fs" % (time.time() - t0))
        wk.cancel()

    QTimer.singleShot(3000, do_cancel)
    QTimer.singleShot(30000, app.quit)    # 兜底超时
    app.exec()

    wk.wait(5000)
    time.sleep(1.0)                       # 给系统一点时间回收进程表
    left = ffmpeg_running()
    print("result:", result)
    print("ffmpeg processes after cancel:", left)
    ok = result.get("msg") == "已取消" and result.get("secs", 99) < 8 and left == 0
    print("CANCEL TEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
