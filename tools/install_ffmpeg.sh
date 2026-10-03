#!/usr/bin/env bash
# 下载静态 ffmpeg / ffprobe 到 bin/（macOS 与 Linux；Windows 用 install_ffmpeg.ps1）。
# 优先系统包管理器不行——静态包才能随软件一起打包。多源回退，也可用环境变量覆盖 URL。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin"
mkdir -p "$BIN"

ARCH="${FFMPEG_ARCH:-$(uname -m)}"   # arm64 / x86_64；交叉构建（如 Rosetta 出 x64 包）时用环境变量指定目标架构
OS="$(uname -s)"                     # Darwin / Linux

# ---- 按平台/架构选出候选下载源（顺序即优先级，$FFMPEG_URL_BASE 可整体覆盖）----
pick_urls() {
  if [ "$OS" = "Darwin" ]; then
    if [ "$ARCH" = "arm64" ]; then
      echo "https://www.osxexperts.net/ffmpeg9arm.zip https://www.osxexperts.net/ffprobe9arm.zip"
      echo "https://evermeet.cx/ffmpeg/get/ffmpeg/zip https://evermeet.cx/ffmpeg/get/ffprobe/zip"
    else
      echo "https://www.osxexperts.net/ffmpeg80intel.zip https://www.osxexperts.net/ffprobe80intel.zip"
      echo "https://evermeet.cx/ffmpeg/get/ffmpeg/zip https://evermeet.cx/ffmpeg/get/ffprobe/zip"
    fi
  else
    # BtbN 与 CI/Windows 同源，GitHub 直连快（注意 Linux 产物是 tar.xz）；johnvansickle 为回退
    if [ "$ARCH" = "x86_64" ]; then
      echo "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz"
      echo "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    else
      echo "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
      echo "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    fi
  fi
}

fetch() { # fetch <url> <out>
  echo "下载 $1"
  curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 -o "$2" "$1"
}

unzip_pair() { # macOS: 两个 zip，各含一个无扩展名二进制
  local fzip="$1" name="$2"
  local t; t="$(mktemp -d)"
  unzip -oq "$fzip" -d "$t"
  find "$t" -name "$name" -type f -exec cp {} "$BIN/$name" \;
  rm -rf "$t"
}

untar_linux() { # Linux: 单 tar.xz 内含静态 ffmpeg/ffprobe
  local txz="$1"
  local t; t="$(mktemp -d)"
  tar -xJf "$txz" -C "$t"
  find "$t" -name ffmpeg -type f -exec cp {} "$BIN/ffmpeg" \;
  find "$t" -name ffprobe -type f -exec cp {} "$BIN/ffprobe" \;
  rm -rf "$t"
}

ok() {
  chmod +x "$BIN/ffmpeg" "$BIN/ffprobe"
  "$BIN/ffmpeg" -version | head -1
  "$BIN/ffprobe" -version | head -1
  echo "已安装到 $BIN"
}

if [ "$OS" = "Darwin" ]; then
  while read -r furl purl; do
    tf="$(mktemp /tmp/ff_XXXX.zip)"; tp="$(mktemp /tmp/fp_XXXX.zip)"
    if fetch "$furl" "$tf" && fetch "$purl" "$tp"; then
      unzip_pair "$tf" ffmpeg; unzip_pair "$tp" ffprobe
      rm -f "$tf" "$tp"
      ok; exit 0
    fi
    rm -f "$tf" "$tp"
    echo "该源失败，尝试下一个…"
  done < <(pick_urls)
  echo "ERROR: 所有下载源均失败，请手动放置 ffmpeg/ffprobe 到 bin/" >&2
  exit 1
else
  # Linux：逐个试源（BtbN zip 优先，johnvansickle tar.xz 回退），按扩展名解压
  while read -r url; do
    case "$url" in
      *.zip)  t="$(mktemp /tmp/ff_XXXX.zip)";  unpack=zip ;;
      *)      t="$(mktemp /tmp/ff_XXXX.tar.xz)"; unpack=tar ;;
    esac
    if fetch "$url" "$t"; then
      if [ "$unpack" = zip ]; then
        unzip_pair "$t" ffmpeg; unzip_pair "$t" ffprobe
      else
        untar_linux "$t"
      fi
      rm -f "$t"; ok; exit 0
    fi
    rm -f "$t"
    echo "该源失败，尝试下一个…"
  done < <(pick_urls)
  echo "ERROR: 所有下载源均失败，请手动放置 ffmpeg/ffprobe 到 bin/" >&2
  exit 1
fi
