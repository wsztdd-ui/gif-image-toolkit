@echo off
rem ============================================================
rem  GifKit 打包脚本
rem    build.bat          → 单文件版  dist\GifKit.exe
rem    build.bat onedir   → 文件夹版  dist\GifKit\（整个文件夹压缩即绿色版）
rem  前置：已安装 Python 3.10+；建议 bin\ 内已放 ffmpeg.exe/ffprobe.exe
rem ============================================================
setlocal
cd /d %~dp0..

echo [1/3] 安装依赖（PySide6 / Pillow / pyinstaller）...
python -m pip install -r requirements.txt pyinstaller || exit /b 1

set SPEC=build\gifkit.spec
if /i "%~1"=="onedir" set SPEC=build\gifkit_onedir.spec

echo [2/3] PyInstaller 打包（%SPEC%）...
python -m PyInstaller --noconfirm --clean "%SPEC%" || exit /b 1

if not exist bin\ffmpeg.exe echo [!] 提示：bin\ 内没有 ffmpeg.exe，打包产物只能依赖目标机器的 PATH

echo [3/3] 完成。
if /i "%~1"=="onedir" (
  echo   文件夹版输出: dist\GifKit\  —— 压缩整个文件夹即为绿色便携版
) else (
  echo   单文件版输出: dist\GifKit.exe
)
endlocal
