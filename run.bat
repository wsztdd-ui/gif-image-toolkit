@echo off
rem 开发模式运行（需先 pip install -r requirements.txt，且 bin\ 内有 ffmpeg 或已加入 PATH）
cd /d %~dp0
python src\main.py
