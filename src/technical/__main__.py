"""python -m src.technical BTC-USD [--crypto] [--png out.png] [--send]

ดูคะแนน /6 ของตัวเดียวจากข้อมูลจริง. --png เซฟภาพไว้ดูเองก่อน, --send ส่งภาพ+ข้อความเข้า Discord
(ช่อง DISCORD_WEBHOOK_URL_TECHNICAL, ไม่ตั้งจะไปช่องหลัก)
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.technical.fetch import daily_closes
from src.technical.radar import yahoo_symbol
from src.technical.score import evaluate

BENCHMARK = "VT"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")   # console Windows เป็น cp1252 พิมพ์ไทยไม่ได้
    load_dotenv(Path(__file__).parents[2] / ".env")
    p = argparse.ArgumentParser()
    p.add_argument("ticker")
    p.add_argument("--crypto", action="store_true", help="เหรียญ: ต่อ -USD ให้เอง + สัปดาห์ปิดวันอาทิตย์ (เดาเองถ้าลงท้าย -USD)")
    p.add_argument("--png", help="เซฟภาพกราฟลงไฟล์นี้")
    p.add_argument("--send", action="store_true", help="ส่งภาพ+ข้อความเข้า Discord")
    a = p.parse_args()
    ticker = a.ticker.upper()
    asset_type = "crypto" if a.crypto or ticker.endswith("-USD") else "stock"

    daily, bench = daily_closes(yahoo_symbol(ticker, asset_type)), daily_closes(BENCHMARK)
    if daily is None or bench is None:
        print(f"ดึงราคาไม่ได้: {ticker if daily is None else BENCHMARK}")
        sys.exit(1)
    asof = datetime.now(timezone.utc).date()
    week, month, r = evaluate(daily, bench, asof, asset_type, BENCHMARK)

    from src.technical.notify import format_message
    print(format_message(ticker, r))

    if a.png:
        from src.technical.chart import render_png
        Path(a.png).write_bytes(render_png(ticker, week, month, r))
        print(f"\nเซฟภาพ: {a.png}")
    if a.send:
        from src.technical.notify import send
        print("\nส่ง Discord:", "สำเร็จ" if send(ticker, week, month, r) else "ไม่สำเร็จ")


if __name__ == "__main__":
    main()
