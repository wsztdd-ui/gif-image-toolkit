#!/usr/bin/env bash
# 开发模式运行（macOS / Linux；Windows 用 run.bat）
# 前置：python3 -m pip install -r requirements.txt，且 bin/ 内有 ffmpeg 或已加入 PATH
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x bin/ffmpeg ] && ! command -v ffmpeg >/dev/null 2>&1; then
  echo "未找到 ffmpeg：brew install ffmpeg（mac）/ sudo apt install ffmpeg（Linux），"
  echo "或运行 bash tools/install_ffmpeg.sh 下载静态版到 bin/"
  exit 1
fi
exec "${PYTHON:-python3}" src/main.py "$@"
