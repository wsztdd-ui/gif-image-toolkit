#!/usr/bin/env bash
# ============================================================
#  GifKit mac / Linux 打包脚本
#    macOS : ./build/build.sh          → dist/GifKit.app + GifKit-macos-<arch>.zip
#    Linux : ./build/build.sh          → dist/GifKit/ + AppImage(x86_64) 或 tar.gz(aarch64)
#  前置：python3 -m pip install -r requirements.txt pyinstaller
# ============================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
VERSION="$("$PY" -c "import sys; sys.path.insert(0, 'src'); from utils.config import APP_VERSION; print(APP_VERSION)")"
# 目标架构取自 Python 解释器本身：Rosetta 下交叉构建 x64 包时 uname 仍是 arm64，
# 而 platform.machine() 会如实返回 x86_64
ARCH="$("$PY" -c "import platform; print(platform.machine())")"
export FFMPEG_ARCH="$ARCH"

echo "[1/5] 安装依赖 ..."
"$PY" -m pip install -q -r requirements.txt pyinstaller

echo "[2/5] 准备 ffmpeg（bin/ 为空则自动下载静态版）..."
if [ ! -x bin/ffmpeg ] || [ ! -x bin/ffprobe ]; then
  bash tools/install_ffmpeg.sh
fi

echo "[3/5] 生成图标 ..."
"$PY" tools/make_icon.py

if [ "$(uname -s)" = "Darwin" ]; then
  echo "[4/5] PyInstaller 打包 macOS .app ..."
  # icns 由 png 现场生成
  rm -rf build/icon.iconset build/icon.icns
  mkdir -p build/icon.iconset
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" build/icon.png --out "build/icon.iconset/icon_${s}x${s}.png" >/dev/null
  done
  sips -z 32 32 build/icon.png --out build/icon.iconset/icon_16x16@2x.png >/dev/null
  sips -z 64 64 build/icon.png --out build/icon.iconset/icon_32x32@2x.png >/dev/null
  sips -z 256 256 build/icon.png --out build/icon.iconset/icon_128x128@2x.png >/dev/null
  sips -z 512 512 build/icon.png --out build/icon.iconset/icon_256x256@2x.png >/dev/null
  iconutil -c icns build/icon.iconset -o build/icon.icns
  "$PY" -m PyInstaller --noconfirm --clean build/gifkit_mac.spec

  echo "[5/5] 冒烟 + 压缩 ..."
  GIFKIT_SMOKE=1 QT_QPA_PLATFORM=offscreen dist/GifKit.app/Contents/MacOS/GifKit
  ZIP="GifKit-v${VERSION}-macos-${ARCH}.zip"
  (cd dist && rm -f "$ZIP" && ditto -c -k --sequesterRsrc --keepParent GifKit.app "$ZIP")
  echo "完成: dist/$ZIP"
else
  echo "[4/5] PyInstaller 打包 Linux onedir ..."
  "$PY" -m PyInstaller --noconfirm --clean build/gifkit_onedir.spec

  echo "[5/5] 冒烟 + 成品 ..."
  GIFKIT_SMOKE=1 QT_QPA_PLATFORM=offscreen dist/GifKit/GifKit

  if [ "$ARCH" = "x86_64" ]; then
    # AppImage：AppDir + appimagetool（--appimage-extract-and-run 免 FUSE）
    TOOL="$(mktemp -d)/appimagetool.AppImage"
    curl -fL --retry 3 -o "$TOOL" \
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
    APPDIR="$(mktemp -d)/GifKit.AppDir"
    mkdir -p "$APPDIR/usr/share/gifkit" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
    cp -a dist/GifKit/. "$APPDIR/usr/share/gifkit/"
    cp build/icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/gifkit.png"
    cp build/icon.png "$APPDIR/gifkit.png"
    ln -s gifkit.png "$APPDIR/.DirIcon"
    cat > "$APPDIR/gifkit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GifKit
Comment=GIF 截取 & 图片压缩
Exec=GifKit
Icon=gifkit
Terminal=false
Categories=Graphics;AudioVideo;
EOF
    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/share/gifkit/GifKit" "$@"
EOF
    chmod +x "$APPDIR/AppRun"
    OUT="GifKit-v${VERSION}-linux-x86_64.AppImage"
    "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/$OUT"
    echo "完成: dist/$OUT"
  else
    OUT="GifKit-v${VERSION}-linux-${ARCH}.tar.gz"
    (cd dist && tar -czf "$OUT" GifKit)
    echo "完成: dist/$OUT（aarch64 暂以 tar.gz 分发）"
  fi
fi
