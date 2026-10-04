"""นำเข้าไม้เก่าจาก Google Sheet (ที่มาจาก Google Form) — ให้สถิติไม้เก่ากับไม้ใหม่ต่อกันได้.

ชีตเดิมไม่มีเวลาเข้าไม้จริง (คอลัมน์ Timestamp คือเวลากรอกฟอร์ม — ทั้ง 15 ไม้กรอกวันเดียวกันภายใน
ไม่กี่นาที) จึงคำนวณบริบทกราฟย้อนหลังให้ไม่ได้: opened_at ว่างไว้ ไม่ใส่เวลากรอกแทน เพราะบริบทที่คิด
จากเวลาผิดดูน่าเชื่อกว่าไม่มีบริบทเลย. ที่ได้ครบคือ ราคาเข้า/stop/TP/ผล และเหตุผลที่ผู้ใช้เขียน
"""
import csv
import io
import urllib.request

TREND = {"ตามเทรนด์": "ตามเทรนด์", "สวนเทรนด์": "สวนเทรนด์"}
PLAN = {"ตามแผน": "ตามแผน", "ด้นสด": "ด้นสด"}
TIME = {"มี": "มีเวลาดู", "ไม่มี": "ไม่มีเวลาดู"}
WAVES = {"1", "2", "3", "4", "5", "A", "B", "C", "ไม่นับ"}


def csv_url(share_url: str) -> str:
    """ลิงก์แชร์ -> ลิงก์ดาวน์โหลด CSV ของแผ่นแรก"""
    sheet_id = share_url.split("/d/")[1].split("/")[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def fetch_csv(share_url: str) -> str:
    with urllib.request.urlopen(csv_url(share_url), timeout=20) as r:
        return r.read().decode("utf-8")


def _num(s: str) -> float | None:
    try:
        return float(s.replace("$", "").replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None


def parse(text: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    out = []
    for i, r in enumerate(rows[1:]):
        d = dict(zip(head, (x.strip() for x in r)))
        if not d.get("ราคาเข้า"):
            continue
        win = d.get("ผล") == "กำไร"
        pnl = _num(d.get("PnL", ""))
        tags: dict = {}
        for col, mapping, key in (("Trend", TREND, "trend"), ("เข้าครบเช็คลิสต์ไหม", PLAN, "plan"),
                                  ("มีเวลาดูไม้นี้จริงไหม", TIME, "time")):
            if d.get(col) in mapping:
                tags[key] = [mapping[d[col]]]
        wave = d.get("Elliott นับเป็นคลื่น", "")
        if wave in WAVES:
            tags["wave"] = [wave]
        why = [x for x in (("divergence" if "divergence" in (d.get("MACD", "") + d.get("RSI", "")) else None),
                           ("นับคลื่น" if wave and wave != "ไม่นับ" else None)) if x]
        if why:
            tags["why"] = why
        out.append({
            "key": f"sheet:{d.get('Timestamp')}:{i}", "source": "sheet",
            "inst": "BTC-USDT-SWAP" if d.get("คู่เทรด") == "BTC" else f"{d.get('คู่เทรด')}-USDT-SWAP",
            "side": "long" if d.get("ทิศ", "").lower() == "long" else "short", "status": "closed",
            "entry": _num(d.get("ราคาเข้า", "")), "sl": _num(d.get("Stoploss", "")), "tp": _num(d.get("TP", "")),
            # ชีตเก็บผลเป็นตัวเลขบวกเสมอ แล้วบอกแพ้/ชนะอีกช่อง
            "pnl": (abs(pnl) if win else -abs(pnl)) if pnl is not None else None,
            "tags": tags, "note": d.get("เหตุผลที่เข้า") or None,
        })
    return out
