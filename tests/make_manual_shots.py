"""为《产品操作入门手册》生成 v0.5.0 实况截图（离屏渲染，不弹窗）。

输出 docs\images\manual\01..09 png。全程真 ffmpeg / 真 Pillow 压缩。
"""
import os
import subprocess
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QRect           # noqa: E402
from PySide6.QtWidgets import QApplication # noqa: E402

from core import ffmpeg as ff              # noqa: E402
from main import apply_theme               # noqa: E402
from ui.main_window import MainWindow      # noqa: E402
from ui.widgets import Collapsible         # noqa: E402
from utils.config import Config            # noqa: E402

OUT = os.path.join(ROOT, "docs", "images", "manual")


def settle(app, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.03)


def wait_until(app, cond, timeout):
    end = time.time() + timeout / 1000
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return False


def shoot(win, name):
    p = os.path.join(OUT, name)
    win.grab().save(p)
    print("shot:", name)


def main():
    os.makedirs(OUT, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    win = MainWindow(Config())
    win.resize(1120, 760)
    win.show()

    tmp = tempfile.mkdtemp(prefix="gifkit_manual_")
    ts = os.path.join(tmp, "产品演示视频.ts")
    subprocess.run([ff.tool_path("ffmpeg"), "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1280x720:rate=30:duration=6",
                    "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts", ts],
                   check=True, capture_output=True, creationflags=ff.CREATE_NO_WINDOW)

    # 01 主界面总览（已载入，含目标体积行与粗估估算栏）
    win.gif_tab.load_path(ts)
    ok = wait_until(app, lambda: win.gif_tab.preview.has_image()
                    and win.gif_tab.thumbs.count() == 8, 25000)
    settle(app, 2500)            # 等估算校准出"实测"
    shoot(win, "01_gif_main.png")

    # 02 播放选段
    win.gif_tab.btn_play.click()
    wait_until(app, lambda: win.gif_tab._is_playing(), 20000)
    settle(app, 800)
    shoot(win, "02_gif_play.png")
    win.gif_tab._stop_playback()
    settle(app, 2000)

    # 03 框选裁剪
    win.gif_tab.preview.set_crop(QRect(160, 90, 960, 540))
    settle(app, 500)
    shoot(win, "03_gif_crop.png")

    # 04 高级参数展开（含隔行源）
    adv = win.gif_tab.findChild(Collapsible)
    adv.btn.setChecked(True)
    settle(app, 400)
    shoot(win, "04_gif_adv.png")

    # 05 目标体积勾选
    adv.btn.setChecked(False)
    win.gif_tab.target_chk.setChecked(True)
    settle(app, 400)
    shoot(win, "05_gif_target.png")

    # 06 生成结果卡（目标体积 → 结果含"自动调整"）
    outdir = os.path.join(tmp, "out")
    win.gif_tab.radio_custom.setChecked(True)
    win.gif_tab.out_edit.setText(outdir)
    win.gif_tab.dur_spin.setValue(2.0)
    win.gif_tab.btn_gen.click()
    wait_until(app, lambda: not win.gif_tab.btn_save.isHidden(), 240000)
    settle(app, 1200)
    shoot(win, "06_gif_result.png")
    win.gif_tab.shutdown()

    # 07 图片页空状态（整块拖放区）
    win.tabs.setCurrentIndex(1)
    settle(app, 400)
    shoot(win, "07_img_empty.png")

    # 08 压缩中（取消按钮可见）
    bigs = []
    from PIL import Image
    for i in range(4):
        p = os.path.join(tmp, f"big_{i}.png")
        Image.effect_noise((2400, 1600), 55).convert("RGB").save(p)
        bigs.append(p)
    win.img_tab.add_files(bigs)
    win.img_tab._start()
    settle(app, 600)
    shoot(win, "08_img_running.png")
    win.img_tab._cancel_compress()
    wait_until(app, lambda: win.img_tab.btn_go.isEnabled(), 90000)
    win.img_tab._clear()

    # 09 批量完成态（结果行 + 节省 + 打开输出目录）
    smalls = []
    for i, col in enumerate((120, 400, 640, 700)):
        p = os.path.join(tmp, f"照片_{i}.jpg")
        img = Image.effect_noise((1600, 1100), col).convert("RGB")
        img.save(p, quality=97)
        smalls.append(p)
    win.img_tab.add_files(smalls)
    win.img_tab._start()
    wait_until(app, lambda: win.img_tab.btn_go.isEnabled(), 90000)
    settle(app, 500)
    shoot(win, "09_img_done.png")

    win.gif_tab.shutdown()
    win.img_tab.shutdown()
    print("ALL SHOTS DONE ->", OUT)


if __name__ == "__main__":
    main()
