"""สมุดเทรด — ปกติไม่ต้องพิมพ์คำสั่งเอง (schedule-journal.ps1 ตั้งให้รันทุกชั่วโมง)

  python -m src.journal sync            ดึงไม้จาก OKX + แจ้ง Discord ไม้ที่เพิ่งเปิด/ปิด
  python -m src.journal stats [--send]  สรุปสถิติ (--send = ส่ง Discord)
  python -m src.journal import-sheet <ลิงก์ Google Sheet>   นำเข้าไม้เก่าจากชีต (ทำครั้งเดียว)
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(Path(__file__).parents[2] / ".env")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    st = sub.add_parser("stats")
    st.add_argument("--send", action="store_true")
    im = sub.add_parser("import-sheet")
    im.add_argument("url")
    a = p.parse_args()

    from src.journal import store
    if a.cmd == "sync":
        from src.journal import okx, sync
        creds = okx.credentials()
        if creds is None:
            print("ยังไม่ได้ตั้ง OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE ใน .env — ข้าม")
            return
        try:
            rep = sync.sync(okx.Client(creds))
        except okx.OkxError as e:
            print(f"[journal] {e}")
            sys.exit(1)
        print(f"[journal] ไม้ใหม่ที่เปิด {len(rep.opened)} · เพิ่งปิด {len(rep.closed)}")
        sync.notify(rep)
    elif a.cmd == "stats":
        from src.journal.stats import compute, format_report
        text = format_report(compute(store.all_trades()))
        print(text)
        if a.send:
            import os
            from src.notify.discord import post_chunks
            post_chunks(text, os.environ.get("DISCORD_WEBHOOK_URL_JOURNAL"))
    elif a.cmd == "import-sheet":
        from src.journal import sheet
        rows = sheet.parse(sheet.fetch_csv(a.url))
        states = [store.upsert(t)[1] for t in rows]
        print(f"นำเข้า {states.count('new')} ไม้ใหม่ · มีอยู่แล้ว {len(states) - states.count('new')} ไม้")


if __name__ == "__main__":
    main()
