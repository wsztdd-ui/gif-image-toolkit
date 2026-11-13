"""选段预览重播竞态回归测试：播放中改参数，画面不得闪成空状态提示。

背景（修复前实测）：
1. _play_selection 在新一轮抽帧完成前就 rmtree 了正在播放的帧目录，
   且旧翻帧定时器没停 —— 定时器继续用已删除的路径构造 QPixmap →
   空 pixmap → set_live(null) → 预览画成"把视频拖到这里"空状态提示，
   直到新帧抽完才恢复。
2. 停止播放只停定时器、不作废在途抽帧代数 —— 停止后抽帧结果返回，
   播放会被重新拉起来。

场景 A（修复路径）：
  ① 播放中触发 _play_selection（等价改参数防抖重播）→ 抽帧窗口内
     画面必须保持在最后一帧（不闪空提示）；
  ② 新帧到达后恢复播放；
  ③ 再触发一轮抽帧后立刻停止 → 在途结果返回不得复活播放。
场景 B（阴性对照）：屏蔽 _pause_playback（修复点）→ 必须复现画面变空。
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer          # noqa: E402
from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication # noqa: E402

from core import ffmpeg as ff              # noqa: E402
from ui.gif_tab import GifTab              # noqa: E402


def make_frame_png(path, color):
    img = QImage(320, 180, QImage.Format_RGB32)
    img.fill(color)
    assert img.save(path), "测试帧保存失败: " + path


def start_playing(tab, frames):
    """手工搭起 _on_play_frames 完成后的播放状态。"""
    tab._play_frames = list(frames)
    tab._play_idx = 0
    tab.preview.set_live(QPixmap(frames[0]))
    tab._play_timer = QTimer(tab)
    tab._play_timer.setInterval(33)
    tab._play_timer.timeout.connect(tab._advance_playback)
    tab._play_timer.start()
    tab.btn_play.setText("⏹ 停止预览")


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def slow_extract():
    """模拟耗时抽帧：睡 1.2s 后才把新帧写进 ffmpeg 实际收到的输出目录。"""
    def job(*args, **kwargs):
        time.sleep(1.2)
        out_dir = args[1]
        written = []
        for i in (1, 2):
            p = os.path.join(out_dir, f"new_{i}.png")
            make_frame_png(p, 0x0000FF)
            written.append(p)
        return written
    return job


def run_scene(app, scene_dir, disable_fix):
    os.makedirs(scene_dir)
    old_frames = [os.path.join(scene_dir, f"old_{i}.png") for i in (1, 2)]
    for i, p in enumerate(old_frames):
        make_frame_png(p, 0x00FF00 if i == 0 else 0x008800)

    tab = GifTab({})
    tab.video = os.path.join(scene_dir, "fake.mp4")
    tab.info = {"width": 1280, "height": 720, "duration": 30.0}
    tab._sel_dir = scene_dir
    if disable_fix:
        # 阴性对照：同时屏蔽两道修复（先停旧定时器 / 空帧防御），
        # 等价于修复前的行为 —— 旧定时器继续翻已删除的帧
        tab._pause_playback = lambda: None

        def broken_advance(_tab=tab):
            if not _tab._play_frames:
                return
            _tab._play_idx = (_tab._play_idx + 1) % len(_tab._play_frames)
            _tab.preview.set_live(QPixmap(_tab._play_frames[_tab._play_idx]))
        tab._advance_playback = broken_advance
    start_playing(tab, old_frames)
    assert tab.preview.has_image(), "测试前提：播放画面已建立"

    real_extract = ff.extract_frames
    ff.extract_frames = slow_extract()
    try:
        # ① 播放中改参数 → 防抖后重播：抽帧窗口内画面必须保持在最后一帧
        tab._play_selection()
        pump(app, 0.4)          # 让旧定时器在帧目录被删后翻几拍（若有）
        during = tab.preview.has_image() and tab.preview.is_live()

        # ② 新帧到达 → 恢复播放（_play_frames 换成新帧且画面有效）
        def healed():
            return (tab._play_frames and os.path.basename(
                        tab._play_frames[0]) == "new_1.png"
                    and tab.preview.has_image())
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and not healed():
            pump(app, 0.05)
        resumed = healed()

        # ③ 再触发一轮抽帧后立刻停止：在途结果返回不得复活播放
        tab._play_selection()
        pump(app, 0.15)
        tab._stop_playback()
        pump(app, 2.0)          # 覆盖 1.2s 的在途抽帧返回
        stay_stopped = (not tab._is_playing() and not tab.preview.is_live()
                        and tab.btn_play.text() == "▶ 播放选段")
    finally:
        ff.extract_frames = real_extract
        tab.shutdown()          # 等待在途 worker，避免 QThread 销毁崩溃
    return during, resumed, stay_stopped


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="gifkit_replay_")
    try:
        during_a, resumed_a, stay_a = run_scene(app, os.path.join(tmp, "a"), False)
        during_b, _, _ = run_scene(app, os.path.join(tmp, "b"), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok_a = during_a and resumed_a and stay_a
    ok_b = not during_b       # 对照组必须复现"画面变空"
    print("  修复组: 重播窗口保持画面 =", during_a,
          "| 新帧恢复播放 =", resumed_a,
          "| 停止后不复活 =", stay_a)
    print("  对照组: 复现画面变空 =", not during_b)
    print("REPLAY RACE TEST", "PASS" if (ok_a and ok_b) else "FAIL",
          f"(对照组复现原始bug: {ok_b})")
    sys.exit(0 if (ok_a and ok_b) else 1)


if __name__ == "__main__":
    main()
