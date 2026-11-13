本目录放入 ffmpeg 与 ffprobe（对应平台版本），构建时会随软件一起打包（构建脚本自动收录）。

下载地址（任选其一）：
- Windows: gyan.dev 完整版 https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
  或 BtbN 自动构建 https://github.com/BtbN/FFmpeg-Builds/releases （ffmpeg-master-latest-win64-gpl.zip）
- macOS / Linux: 运行 `bash tools/install_ffmpeg.sh` 一键下载静态版到本目录；
  或 brew install ffmpeg / sudo apt install ffmpeg 装入系统 PATH

解压后把对应平台的 ffmpeg、ffprobe 复制到这里（Windows 为 ffmpeg.exe / ffprobe.exe，
macOS / Linux 为 ffmpeg / ffprobe，注意保留可执行权限）。
未放入时，程序会尝试使用系统 PATH 中的 ffmpeg；打包便携版必须放入，否则产物在别的机器不可用。
