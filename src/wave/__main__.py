"""python -m src.wave data/waves/btc.json [--png out.png] [--send]

แก้ count = แก้ไฟล์ JSON (วันเวลาโดยประมาณของแต่ละจุด — เครื่องหาราคาจริงรอบนั้นให้เอง)
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.wave.candles import fetch
from src.wave.count import build, load
from src.wave.notify import format_message


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).parents[2] / ".env")
    p = argparse.ArgumentParser()
    p.add_argument("count", help="ไฟล์ count เช่น data/waves/btc.json")
    p.add_argument("--png", help="เซฟภาพลงไฟล์นี้")
    p.add_argument("--send", action="store_true", help="ส่งภาพ+ข้อความเข้า Discord")
    a = p.parse_args()

    spec = load(a.count)
    cache: dict = {}

    def cached(symbol, interval, period):        # ภาพกับรายงานต้องใช้แท่งชุดเดียวกัน
        key = (symbol, interval, period)
        if key not in cache:
            cache[key] = fetch(symbol, interval, period)
        return cache[key]

    rep = build(spec, cached)
    hourly = cached(spec["symbol"], spec.get("interval", "1h"), spec.get("period", "60d"))
    print(format_message(rep))
    if a.png:
        from src.wave.chart import render_png
        Path(a.png).write_bytes(render_png(rep, hourly))
        print(f"\nเซฟภาพ: {a.png}")
    if a.send:
        from src.wave.notify import send
        print("\nส่ง Discord:", "สำเร็จ" if send(rep, hourly) else "ไม่สำเร็จ")


if __name__ == "__main__":
    main()
