"""คำสั่งของส่วนคลื่น:

  python -m src.wave data/waves/btc.json [--png out.png] [--send] [--snapshot]
      รายงาน count ที่มาร์ก + เครื่องนับเอง + เทรนด์หลาย TF. --snapshot = เก็บให้หน้าเว็บ /wave
  python -m src.wave pack data/waves/btc.json
      สร้างไฟล์ให้แปะในแชท Claude เพื่อขอ "มุมมองของ Claude"
  python -m src.wave claude data/waves/btc.json reply.md
      นำคำตอบจากแชทกลับเข้ามาเก็บ (โชว์บนเว็บคู่กับอีกสองฝั่ง)
  python -m src.wave alert data/waves/btc.json
      (รันเองทุกชั่วโมงผ่าน schedule-journal.ps1) แจ้ง Discord เมื่อแท่ง 4H ปิดผ่านเส้นตาย/เส้นยืนยัน
      + อัปเดต snapshot ให้หน้าเว็บ /wave และ /check ใช้ข้อมูลสด

แก้ count = แก้ไฟล์ JSON (วันเวลาโดยประมาณของแต่ละจุด — เครื่องหาราคาจริงรอบนั้นให้เอง)
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.wave.candles import fetch
from src.wave.count import build, load
from src.wave.notify import format_message


def _cached():
    cache: dict = {}

    def get(symbol, interval, period):        # ภาพ รายงาน และ snapshot ต้องใช้แท่งชุดเดียวกัน
        key = (symbol, interval, period)
        if key not in cache:
            cache[key] = fetch(symbol, interval, period)
        return cache[key]
    return get


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).parents[2] / ".env")
    argv = sys.argv[1:]
    cmd = argv[0] if argv and argv[0] in ("pack", "claude", "alert") else "report"
    if cmd != "report":
        argv = argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("count", help="ไฟล์ count เช่น data/waves/btc.json")
    if cmd == "claude":
        p.add_argument("reply", help="ไฟล์คำตอบที่ก๊อปมาจากแชท Claude")
        p.add_argument("--by", default="Claude (แปะจากแชท)")
    p.add_argument("--png", help="เซฟภาพลงไฟล์นี้")
    p.add_argument("--send", action="store_true", help="ส่งภาพ+ข้อความเข้า Discord")
    p.add_argument("--snapshot", action="store_true", help="เก็บรายงาน+ภาพให้หน้าเว็บ /wave")
    a = p.parse_args(argv)

    spec, stem = load(a.count), Path(a.count).stem
    get = _cached()
    rep = build(spec, get)
    hourly = get(spec["symbol"], spec.get("interval", "1h"), spec.get("period", "60d"))
    parent = spec.get("parent") or {}
    daily = get(spec["symbol"], parent.get("interval", "1d"), parent.get("period", "1y"))
    msg = format_message(rep)

    if cmd == "pack":
        from src.wave.claude import make_pack
        print(f"แพ็กสำหรับแปะในแชท Claude: {make_pack(stem, rep, msg)}")
        return
    if cmd == "alert":
        _alert(stem, rep, hourly, daily, msg)
        return
    if cmd == "claude":
        from src.wave.claude import save_view
        text = Path(a.reply).read_text(encoding="utf-8")
        print(f"เก็บมุมมองของ Claude: {save_view(stem, text, rep.last.close, by=a.by)}")
        return

    print(msg)
    if a.png:
        from src.wave.chart import render_png
        Path(a.png).write_bytes(render_png(rep, hourly))
        print(f"\nเซฟภาพ: {a.png}")
    if a.snapshot:
        from src.wave import snapshot
        from src.wave.chart import render_auto_png, render_png
        path = snapshot.write(stem, rep, render_png(rep, hourly), render_auto_png(rep, hourly, daily), msg)
        print(f"\nsnapshot สำหรับหน้าเว็บ: {path}")
    if a.send:
        from src.wave.notify import send
        print("\nส่ง Discord:", "สำเร็จ" if send(rep, hourly, daily=daily) else "ไม่สำเร็จ")


def _alert(stem, rep, hourly, daily, msg) -> None:
    import os
    from datetime import datetime, timezone
    from src.notify import discord
    from src.wave import alerts, snapshot
    from src.wave.candles import resample_4h
    from src.wave.chart import render_auto_png, render_png

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    closed = resample_4h(hourly, now)
    hits = alerts.crossings(alerts.load_state(stem), closed)
    png = render_png(rep, hourly)
    snapshot.write(stem, rep, png, render_auto_png(rep, hourly, daily), msg)     # /wave, /check สดเสมอ
    if hits:
        text = alerts.format_alert(rep.symbol, hits, rep)
        print(text)
        discord.post_image(text, png, f"wave_alert_{stem}.png", os.environ.get("DISCORD_WEBHOOK_URL_WAVE"))
    else:
        print(f"[wave] {stem}: ไม่มีแท่ง 4H ที่ปิดผ่านเส้น")
    alerts.save_state(stem, rep, closed)


if __name__ == "__main__":
    main()
