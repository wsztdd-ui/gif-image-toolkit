"""全量功能测试：GifTab + ImageTab 全部功能端到端（离屏 + 真 ffmpeg）。

GIF 页：载入 TS/动图、时间联动（滑块↔输入框、钳制、选整段、缩略图起点）、
选段播放/停止/播放中改参数、裁剪（框/比例/重置/估算联动）、质量预设、
宽度模式、生成（两遍调色板）→ QMovie 预览 → 保存（源目录/自定义目录/后缀）、
动图再压缩对比、生成取消、拖放路由、非法输出目录报错、设置持久化、shutdown 清理。
图片页：添加去重、移除/清空、keep/jpeg/webp/png 压缩、最长边缩放（含调色板图）、
PNG 量化、跳过变大文件、错误行、自定义输出目录、拖放过滤非图片、压缩中按钮禁用、
设置持久化。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QRect, QUrl          # noqa: E402
from PySide6.QtGui import QMovie                # noqa: E402
from PySide6.QtWidgets import QApplication      # noqa: E402

from core import ffmpeg as ff                   # noqa: E402
from core import imglib                         # noqa: E402
from ui.gif_tab import GifTab                   # noqa: E402
from ui.image_tab import ImageTab               # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  ({detail})" if detail and not cond else ""))


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_until(app, cond, timeout, what=""):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    print(f"    [超时] {what}")
    return False


def run_ff(args):
    subprocess.run([ff.tool_path("ffmpeg"), *args], check=True, capture_output=True,
                   creationflags=ff.CREATE_NO_WINDOW)


# ======================= GIF 页 =======================

def scene_gif_load(app, tmp):
    print("— GIF 页：载入与信息 —")
    tab = GifTab({})
    src = os.path.join(tmp, "demo.ts")           # 640x360 6s，由 make_media 生成
    tab.load_path(src)
    check("载入后 file_line 显示源信息", "demo.ts" in tab.file_line.text()
          and "640×360" in tab.file_line.text() and not tab.file_line.isHidden())
    check("滑块范围=总长(0.1s步进)", tab.range_slider.selection() == (0, 60),
          str(tab.range_slider.selection()))
    check("时长默认=整段(≤10s)", tab.dur_spin.value() == 6.0)
    check("估算标签含 720×405", "720×405" in tab.estimate.text(), tab.estimate.text())
    ok = wait_until(app, lambda: tab.preview.has_image(), 20, "静态帧")
    check("静态预览帧生成", ok)
    ok = wait_until(app, lambda: tab.thumbs.count() > 0, 25, "缩略图")
    check("缩略图条生成 8 张", ok and tab.thumbs.count() == 8, str(tab.thumbs.count()))
    return tab


def scene_gif_time_sync(app, tab):
    print("— GIF 页：时间选取联动 —")
    tab.range_slider.set_selection(20, 50)
    check("滑块→输入框", tab.start_spin.value() == 2.0 and tab.dur_spin.value() == 3.0)
    tab.start_spin.setValue(5.0)
    check("起点钳制挤压时长", abs(tab.dur_spin.value() - 1.0) < 0.001,
          str(tab.dur_spin.value()))
    check("输入框→滑块", tab.range_slider.selection() == (50, 60),
          str(tab.range_slider.selection()))
    tab.dur_spin.setValue(100.0)
    check("时长钳制不超尾", abs(tab.dur_spin.value() - 1.0) < 0.001)
    tab.btn_full.click()
    check("选整段", tab.start_spin.value() == 0.0 and abs(tab.dur_spin.value() - 6.0) < 0.01)
    t = tab.thumbs.item(3).data(0x0100)          # Qt.UserRole
    tab.thumbs.itemClicked.emit(tab.thumbs.item(3))
    check("点缩略图设起点", abs(tab.start_spin.value() - t) < 0.011,
          f"{tab.start_spin.value()} vs {t}")
    tab.start_spin.setValue(0.0)
    tab.dur_spin.setValue(2.0)


def scene_gif_play(app, tab):
    print("— GIF 页：选段播放 —")
    tab.btn_play.click()
    ok = wait_until(app, lambda: tab._is_playing(), 20, "播放开始")
    check("播放态（定时器+live+按钮⏹）", ok and tab.preview.is_live()
          and tab.btn_play.text() == "⏹ 停止预览")
    gen0 = tab._play_gen
    tab.start_spin.setValue(2.0)                 # 播放中改参数 → 防抖重播（代数+1）
    ok = wait_until(app, lambda: tab._play_gen > gen0 and tab._is_playing(),
                    15, "按新参数重播")
    check("改参数后按新参数重播", ok)
    tab._toggle_play()                           # 停止
    ok = wait_until(app, lambda: not tab._is_playing() and not tab.preview.is_live(),
                    10, "停止播放")
    check("停止后回编辑态", ok and tab.btn_play.text() == "▶ 播放选段")
    ok = wait_until(app, lambda: tab.preview.has_image(), 15, "停止后刷新静态帧")
    check("停止后静态帧已刷新", ok)


def scene_gif_crop(app, tab):
    print("— GIF 页：裁剪 —")
    tab.preview.set_crop(QRect(20, 20, 320, 160))
    check("框选后标签更新", "320 × 160" in tab.crop_label.text(), tab.crop_label.text())
    w, h = ff.output_dims(640, 360, (20, 20, 320, 160), 720)
    check("估算随裁剪联动", f"{w}×{h}" in tab.estimate.text(), tab.estimate.text())
    tab.ratio_combo.setCurrentIndex(2)           # 1:1
    c = tab.preview.get_crop()
    check("比例锁定 1:1", abs(c.width() / c.height() - 1.0) < 0.05,
          f"{c.width()}x{c.height()}")
    tab.btn_crop_reset.click()
    check("重置回全画面", tab.preview.get_crop() is None
          and "全画面" in tab.crop_label.text())


def scene_gif_params(app, tab):
    print("— GIF 页：参数与预设 —")
    tab.preset_combo.setCurrentIndex(2)          # 高质量
    check("预设→高级参数", tab.fps_spin.value() == 15
          and tab.colors_combo.currentText() == "256"
          and tab.dither_combo.currentData() == "floyd")
    tab.fps_spin.setValue(10)
    check("改细节→预设显示自定义", tab.preset_combo.currentIndex() == 0)
    tab.preset_combo.setCurrentIndex(3)          # 高压缩
    check("高压缩预设", tab.fps_spin.value() == 8
          and tab.colors_combo.currentText() == "64"
          and tab.dither_combo.currentData() == "none")
    tab.width_combo.setCurrentIndex(1)           # 原始宽度
    check("宽度=原始", tab._out_width() == 0)
    tab.width_combo.setCurrentIndex(6)           # 自定义
    check("自定义宽度输入框出现", not tab.width_spin.isHidden())
    tab.width_spin.setValue(500)
    check("自定义宽度生效", tab._out_width() == 500)
    tab.width_combo.setCurrentIndex(0)           # 720
    tab.preset_combo.setCurrentIndex(1)          # 均衡


def scene_gif_generate_save(app, tmp):
    print("— GIF 页：生成 → 预览 → 保存 —")
    tab = GifTab({})
    tab.load_path(os.path.join(tmp, "demo.ts"))
    wait_until(app, lambda: tab.preview.has_image(), 20)
    outdir = os.path.join(tmp, "自动建目录", "子层")
    tab.radio_custom.setChecked(True)
    tab.out_edit.setText(outdir)
    tab.suffix_edit.setText("_t")
    tab.dur_spin.setValue(1.5)
    tab.btn_gen.click()
    ok = wait_until(app, lambda: not tab.btn_save.isHidden(), 120, "生成完成")
    check("生成完成出保存按钮", ok)
    check("成品预览动画播放中", tab.preview_stack.currentIndex() == 1
          and isinstance(tab._movie, QMovie)
          and tab._movie.state() == QMovie.Running)
    check("体积对比标签可见", not tab.cmp_label.isHidden()
          and tab.cmp_label.text().strip() != "")
    check("meta 行含输出尺寸 720×405", "720×405" in tab.pv_meta.text(),
          tab.pv_meta.text())
    check("自定义输出目录已自动创建", os.path.isdir(outdir))
    tab.btn_save.click()
    pump(app, 0.5)
    dst = os.path.join(outdir, "demo_t.gif")
    check("保存成功（自定义目录+后缀）", os.path.isfile(dst)
          and os.path.getsize(dst) > 0)
    check("临时预览产物已移走", not os.path.exists(tab._preview_file))
    check("保存后出“打开目录”", not tab.btn_open.isHidden())
    check("状态栏已保存", tab.status.text().startswith("已保存"))
    # 非法输出目录：指向一个已存在的文件 → 报错不崩溃
    tab._back_to_edit()
    tab.out_edit.setText(os.path.join(tmp, "demo.ts"))
    tab.btn_save.setVisible(True)                # 模拟仍有产物可保存的状态
    scratch = os.path.join(tmp, "scratch_preview.gif")
    shutil.copy(dst, scratch)                    # 用一次性副本当预览产物，
    tab._preview_file = scratch                  # shutdown 的临时清理不会波及成品
    tab._save_preview()
    check("非法输出目录报错不崩溃", tab.status.text().startswith("保存失败")
          and tab.btn_gen.isEnabled())
    tab.shutdown()
    return dst


def scene_gif_recompress(app, tmp, gif_path):
    print("— GIF 页：动图再压缩 —")
    tab = GifTab({})
    tab.load_path(gif_path)
    check("识别为动图模式", tab.gif_mode and "动图" in tab.file_line.text())
    wait_until(app, lambda: tab.preview.has_image(), 20)
    tab.dur_spin.setValue(1.0)
    tab.btn_gen.click()
    ok = wait_until(app, lambda: not tab.btn_save.isHidden(), 120, "再压缩完成")
    check("动图再压缩完成", ok)
    check("对比标签为 原→新 格式", tab.cmp_label.text().startswith("原 "),
          tab.cmp_label.text())
    tab.shutdown()


def scene_gif_cancel(app, tmp):
    print("— GIF 页：生成取消 —")
    tab = GifTab({})
    tab.load_path(os.path.join(tmp, "long.ts"))  # 1280x720 30s
    wait_until(app, lambda: tab.preview.has_image(), 25)
    tab.fps_spin.setValue(30)
    tab.dur_spin.setValue(30.0)
    tab.btn_gen.click()
    pump(app, 1.2)
    tab._cancel_gen()
    ok = wait_until(app, lambda: tab.status.text() in ("已取消生成", "生成完成，请确认后保存"),
                    30, "取消返回")
    check("取消生效", ok and tab.status.text() == "已取消生成", tab.status.text())
    check("取消后按钮恢复", tab.btn_gen.isEnabled() and tab.btn_cancel.isHidden())
    tab.shutdown()


def scene_gif_target_size(app, tmp):
    print("— GIF 页：目标体积模式 —")
    tab = GifTab({})
    tab.load_path(os.path.join(tmp, "demo.ts"))
    wait_until(app, lambda: tab.preview.has_image(), 20)
    outdir = os.path.join(tmp, "target_out")
    tab.radio_custom.setChecked(True)
    tab.out_edit.setText(outdir)
    tab.suffix_edit.setText("_s")
    tab.target_chk.setChecked(True)              # 打开目标体积模式
    tab.target_spin.setValue(0.5)
    check("目标模式估算标签", "目标 ≤ 0.5 MB" in tab.estimate.text(),
          tab.estimate.text())
    tab.btn_gen.click()
    ok = wait_until(app, lambda: not tab.btn_save.isHidden(), 240, "目标体积生成完成")
    check("目标体积生成完成", ok)
    check("结果含自动调整说明", "自动调整" in tab.pv_meta.text(), tab.pv_meta.text())
    tab.btn_save.click()
    pump(app, 0.5)
    dst = os.path.join(outdir, "demo_s.gif")
    check("产物 ≤ 0.5MB", os.path.isfile(dst)
          and os.path.getsize(dst) <= int(0.5 * 1024 * 1024),
          str(os.path.getsize(dst)) if os.path.isfile(dst) else "missing")
    check("命中目标（非下限警告）", not tab.status.text().startswith("已用最小参数"))
    tab.shutdown()


def scene_gif_deinterlace(app, tmp):
    print("— GIF 页：隔行源自动去隔行 —")
    tab = GifTab({})
    check("隔行模式默认自动", tab._deint_mode() == "auto")
    tab.load_path(os.path.join(tmp, "il.ts"))    # 合成的隔行 TS
    check("probe 识别隔行", tab.info["field_order"] in ff.INTERLACED_ORDERS,
          tab.info["field_order"])
    ok = wait_until(app, lambda: tab.preview.has_image(), 20)
    check("隔行源静态帧生成（已去隔行）", ok)
    outdir = os.path.join(tmp, "deint_out")
    tab.radio_custom.setChecked(True)
    tab.out_edit.setText(outdir)
    tab.dur_spin.setValue(1.0)
    tab.btn_gen.click()
    ok = wait_until(app, lambda: not tab.btn_save.isHidden(), 120, "隔行源生成完成")
    check("隔行源生成完成", ok)
    tab.shutdown()


def scene_gif_estimate(app, tmp):
    print("— GIF 页：估算试编校准 —")
    tab = GifTab({})
    tab.load_path(os.path.join(tmp, "demo.ts"))
    wait_until(app, lambda: tab.preview.has_image(), 20)
    check("先显示公式粗估", "粗估" in tab.estimate.text(), tab.estimate.text())
    ok = wait_until(app, lambda: "（实测）" in tab.estimate.text(), 40, "试编校准")
    check("后台试编校准替换为实测", ok, tab.estimate.text())
    if ok:
        check("实测标签含分辨率", "720×405" in tab.estimate.text(),
              tab.estimate.text())
    tab.fps_spin.setValue(6)                     # 改参数 → 重新校准
    ok = wait_until(app, lambda: "（实测）" in tab.estimate.text()
                    and "720×405" in tab.estimate.text(), 40, "参数变化后重新校准")
    check("改参数后重新校准", ok)
    tab.target_chk.setChecked(True)              # 目标模式下不跑校准
    pump(app, 0.3)
    check("目标模式显示目标标签", "目标 ≤" in tab.estimate.text())
    tab.shutdown()


def scene_gif_routing(app, tmp):
    print("— GIF 页：拖放路由 —")
    tab = GifTab({})
    got = []
    tab.imageDropped.connect(got.append)
    tab._route_drop(os.path.join(tmp, "pic.jpg"))
    pump(app, 0.3)
    check("图片拖入→切图片页信号", len(got) == 1 and got[0].endswith("pic.jpg"))
    tab._route_drop(os.path.join(tmp, "note.txt"))
    check("未知类型→警告", "不支持" in tab.status.text())
    tab.shutdown()


def scene_gif_settings(app):
    print("— GIF 页：设置持久化 —")
    cfg = {"gif": {}}
    t1 = GifTab(cfg["gif"])
    t1.width_combo.setCurrentIndex(3)            # 480
    t1.fps_spin.setValue(20)
    t1.colors_combo.setCurrentText("32")
    t1.dither_combo.setCurrentIndex(2)
    t1.suffix_edit.setText("_x")
    t1.radio_custom.setChecked(True)
    out_path = os.path.join(tempfile.gettempdir(), "gifkit_out_test_dir")
    t1.out_edit.setText(out_path)
    t1.save_settings()
    t2 = GifTab(cfg["gif"])
    check("设置往返还原", t2.width_combo.currentData() == "480"
          and t2.fps_spin.value() == 20
          and t2.colors_combo.currentText() == "32"
          and t2.dither_combo.currentData() == "none"
          and t2.suffix_edit.text() == "_x"
          and t2.radio_custom.isChecked()
          and t2.out_edit.text() == out_path)
    t1.shutdown()
    t2.shutdown()


# ======================= 图片页 =======================

def scene_img_add_remove(app, tab, tmp):
    print("— 图片页：添加/移除/清空 —")
    tab.add_files([os.path.join(tmp, "pic.jpg"), os.path.join(tmp, "missing.jpg"),
                   os.path.join(tmp, "pal.png"), os.path.join(tmp, "pic.jpg")])
    check("添加去重+忽略不存在", len(tab.files) == 2 and tab.table.rowCount() == 2)
    check("空状态已切列表", tab.stack.currentIndex() == 1)
    check("汇总计数", tab.summary.text() == "共 2 个文件")
    tab.table.selectRow(1)
    tab._remove_selected()
    check("移除选中", len(tab.files) == 1 and tab.table.rowCount() == 1)
    tab._clear()
    check("清空回空状态", len(tab.files) == 0 and tab.stack.currentIndex() == 0)
    tab._handle_drop([QUrl.fromLocalFile(os.path.join(tmp, "pic.jpg")),
                      QUrl.fromLocalFile(os.path.join(tmp, "note.txt"))])
    check("拖放过滤非图片并提示", len(tab.files) == 1 and "已忽略 1" in tab.status.text())


def scene_img_compress(app, tmp):
    print("— 图片页：批量压缩（keep/png + 缩放 + 量化）—")
    tab = ImageTab({})
    outdir = os.path.join(tmp, "img_out")
    tab.add_files([os.path.join(tmp, "pic.jpg"), os.path.join(tmp, "pal.png")])
    tab.fmt_combo.setCurrentIndex(0)             # 保持原格式
    tab.edge_combo.setCurrentIndex(5)            # 自定义（EDGES 共 6 项）
    tab.edge_spin.setValue(600)                  # 1200x800 → 600x400、1600x900 → 600x338
    tab.q_slider.setValue(70)
    tab.suffix_edit.setText("_c")
    tab.radio_custom.setChecked(True)
    tab.out_edit.setText(outdir)
    tab._start()
    check("压缩中按钮禁用", not tab.btn_go.isEnabled() and not tab.btn_add.isEnabled())
    ok = wait_until(app, lambda: tab.status.text().startswith("完成"), 60, "压缩完成")
    check("批量压缩完成", ok, tab.status.text())
    check("按钮恢复可用", tab.btn_go.isEnabled() and tab.btn_add.isEnabled())
    for name, w in (("pic_c.jpg", 600), ("pal_c.png", 600)):
        p = os.path.join(outdir, name)
        exists = os.path.isfile(p)
        check(f"产物 {name}", exists)
        if exists:
            with imglib.Image.open(p) as im:
                check(f"{name} 最长边=600", max(im.size) == 600, str(im.size))
    check("结果行状态为完成", "完成" in tab.table.item(0, 4).text())
    check("节省列给出百分比", "%" in tab.table.item(0, 3).text())
    check("汇总含节省", "共节省" in tab.summary.text(), tab.summary.text())
    tab.shutdown()
    return outdir


def scene_img_fmt_webp(app, tmp):
    print("— 图片页：格式转换 WebP —")
    tab = ImageTab({})
    tab.add_files([os.path.join(tmp, "pic.jpg")])
    tab.fmt_combo.setCurrentIndex(2)             # WebP
    tab.edge_combo.setCurrentIndex(0)            # 保持原始尺寸
    tab._start()
    ok = wait_until(app, lambda: tab.status.text().startswith("完成"), 60)
    check("WebP 转换完成", ok)
    p = os.path.join(tmp, "pic_c.webp")          # 默认输出到源目录
    check("WebP 产物生成", os.path.isfile(p)
          and os.path.getsize(p) < os.path.getsize(os.path.join(tmp, "pic.jpg")))
    tab.shutdown()


def scene_img_skip_larger(app, tmp):
    print("— 图片页：跳过变大文件 —")
    tab = ImageTab({})
    tab.add_files([os.path.join(tmp, "pal.png")])
    real = imglib.compress_one

    def fake(src, dst, **kw):
        with open(dst, "wb") as f:
            f.write(b"x" * 9999)
        return 1000, 9999, "png"
    imglib.compress_one = fake
    try:
        tab._start()
        ok = wait_until(app, lambda: tab.status.text().startswith("完成"), 30)
    finally:
        imglib.compress_one = real
    check("跳过流程完成", ok)
    check("行状态=已跳过", "已跳过" in tab.table.item(0, 4).text(),
          tab.table.item(0, 4).text())
    check("变大产物已删除", not os.path.exists(
        os.path.join(os.path.dirname(list(tab.files)[0]), "pal_c.png")))
    tab.shutdown()


def scene_img_error_row(app, tmp):
    print("— 图片页：坏文件错误行 —")
    tab = ImageTab({})
    bad = os.path.join(tmp, "bad.jpg")
    with open(bad, "wb") as f:
        f.write(b"not an image at all")
    tab.add_files([bad])
    tab._start()
    ok = wait_until(app, lambda: tab.status.text().startswith("完成"), 30)
    check("坏文件不中断批次", ok)
    check("错误行提示", tab.table.item(0, 4).text().startswith("失败"))
    os.remove(bad)
    tab.shutdown()


def scene_img_cancel(app, tmp):
    print("— 图片页：并行压缩与取消 —")
    tab = ImageTab({})
    bigs = [os.path.join(tmp, f"big_{i}.png") for i in range(9)]
    tab.add_files(bigs)
    tab.fmt_combo.setCurrentIndex(1)             # JPEG
    tab.edge_combo.setCurrentIndex(0)            # 保持原始尺寸
    tab._start()
    pump(app, 0.15)
    check("压缩中出取消按钮", not tab.btn_cancel.isHidden())
    tab._cancel_compress()                       # 6 并发下后 3 张应被跳过
    ok = wait_until(app, lambda: tab.status.text().startswith(("已取消", "完成"))
                    and tab.btn_go.isEnabled(), 90, "取消收敛")
    check("取消后状态收敛", ok, tab.status.text())
    check("取消按钮隐藏", tab.btn_cancel.isHidden())
    done_rows = sum(1 for r in range(tab.table.rowCount())
                    if tab.table.item(r, 4) and tab.table.item(r, 4).text() != "待处理")
    check("结果行与状态一致（无串行）", done_rows == tab.table.rowCount()
          or tab.status.text().startswith("已取消"))
    tab.shutdown()


def scene_img_settings(app):
    print("— 图片页：设置持久化 —")
    cfg = {"img": {}}
    t1 = ImageTab(cfg["img"])
    t1.fmt_combo.setCurrentIndex(2)
    t1.q_slider.setValue(55)
    t1.edge_combo.setCurrentIndex(5)             # 自定义
    t1.edge_spin.setValue(1600)
    t1.quant_chk.setChecked(False)
    t1.skip_chk.setChecked(False)
    t1.suffix_edit.setText("_z")
    t1.save_settings()
    t2 = ImageTab(cfg["img"])
    check("设置往返还原", t2.fmt_combo.currentData() == "webp"
          and t2.q_slider.value() == 55
          and t2.edge_spin.value() == 1600
          and not t2.quant_chk.isChecked()
          and not t2.skip_chk.isChecked()
          and t2.suffix_edit.text() == "_z")
    t1.shutdown()
    t2.shutdown()


# ======================= 主流程 =======================

def make_media(tmp):
    run_ff(["-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
            "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts",
            os.path.join(tmp, "demo.ts")])
    run_ff(["-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=30",
            "-c:v", "mpeg2video", "-q:v", "4", "-f", "mpegts",
            os.path.join(tmp, "long.ts")])
    run_ff(["-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=2",
            "-c:v", "mpeg2video", "-q:v", "4", "-flags", "+ilme+ildct",
            "-vf", "setparams=tff",   # ffmpeg 9 起移除编码选项 -top，用滤镜设场序
            "-f", "mpegts", os.path.join(tmp, "il.ts")])
    from PIL import Image
    Image.effect_noise((1600, 900), 60).resize((1600, 900)).convert("RGB").save(
        os.path.join(tmp, "pic.jpg"), quality=95)
    p = os.path.join(tmp, "pal.png")
    img = Image.new("P", (1200, 800))
    palette = []
    for i in range(256):
        palette += [i, (i * 3) % 256, (255 - i) % 256]
    img.putpalette(palette)
    img.putdata([(x * y) % 256 for y in range(800) for x in range(1200)])
    img.save(p, optimize=True)
    for i in range(9):                       # 取消场景用：大图让压缩池跑得足够久
        big = Image.effect_noise((2000, 1300), 50).convert("RGB")
        big.save(os.path.join(tmp, f"big_{i}.png"))
    with open(os.path.join(tmp, "note.txt"), "w") as f:
        f.write("txt")


def main():
    app = QApplication([])
    tmp = tempfile.mkdtemp(prefix="gifkit_full_")
    print("临时目录:", tmp)
    try:
        ok, msg = ff.available()
        if not ok:
            print("ffmpeg 不可用:", msg)
            return 1
        make_media(tmp)

        tab = scene_gif_load(app, tmp)
        scene_gif_time_sync(app, tab)
        scene_gif_play(app, tab)
        scene_gif_crop(app, tab)
        scene_gif_params(app, tab)
        tab.shutdown()
        gif_out = scene_gif_generate_save(app, tmp)
        scene_gif_recompress(app, tmp, gif_out)
        scene_gif_target_size(app, tmp)
        scene_gif_deinterlace(app, tmp)
        scene_gif_estimate(app, tmp)
        scene_gif_cancel(app, tmp)
        scene_gif_routing(app, tmp)
        scene_gif_settings(app)

        itab = ImageTab({})
        scene_img_add_remove(app, itab, tmp)
        scene_img_compress(app, tmp)
        scene_img_fmt_webp(app, tmp)
        scene_img_cancel(app, tmp)
        scene_img_skip_larger(app, tmp)
        scene_img_error_row(app, tmp)
        scene_img_settings(app)
        itab.shutdown()
    finally:
        time.sleep(0.3)
        shutil.rmtree(tmp, ignore_errors=True)

    n_pass = sum(1 for r in RESULTS if r)
    n_fail = len(RESULTS) - n_pass
    print(f"\n共 {len(RESULTS)} 项断言，通过 {n_pass}，失败 {n_fail}")
    print("FULL FEATURES TEST", "PASS" if n_fail == 0 else "FAIL")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
