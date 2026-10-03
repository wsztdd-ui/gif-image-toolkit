"""时间与体积的格式化工具。"""


def fmt_seconds(sec: float) -> str:
    sec = max(0.0, float(sec))
    m, s = divmod(sec, 60)
    if m >= 60:
        h, m = divmod(int(m), 60)
        return f"{h}:{int(m):02d}:{s:04.1f}"
    return f"{int(m):02d}:{s:04.1f}"


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"
