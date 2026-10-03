"""ข้อความ Discord ภาษาคน + ส่งคู่กับภาพกราฟ.

ข้อความเป็นที่ที่ภาษาไทยอยู่ (ภาพเป็นอังกฤษล้วน — ดู chart.py) และใช้กติการายงาน: ไม่ใช้ศัพท์
เครื่องมือ ("SMA40W", "12-1", "pp") แต่แปลงเป็นสิ่งที่คนรู้สึกได้ เช่น "ถือ 100 บาท เหลือ 69"

ส่งมือได้ด้วย `python -m src.technical BTC-USD --send`; รอบอัตโนมัติ (radar.py) ส่งเฉพาะตัวที่เปลี่ยน tier
— ส่งรูปเดิมทุกวันคือวิธีที่ทำให้คนเลิกเปิดดู (Phase 49.1)
"""
import os
from datetime import date

from src.notify import discord

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_TECHNICAL"

PLAIN = {   # ข้อความต่อข้อ: (ตอนผ่าน, ตอนตก)
    "T1": ("ราคาปิดสัปดาห์อยู่เหนือเส้นเฉลี่ย 40 สัปดาห์", "ราคาปิดสัปดาห์อยู่ใต้เส้นเฉลี่ย 40 สัปดาห์"),
    "T2": ("เส้นเฉลี่ย 40 สัปดาห์ยังชี้ขึ้น", "เส้นเฉลี่ย 40 สัปดาห์ยังชี้ลง (ทิศใหญ่ยังไม่กลับ)"),
    "T3": ("ราคาปิดเดือนอยู่เหนือเส้นเฉลี่ย 10 เดือน", "ราคาปิดเดือนอยู่ใต้เส้นเฉลี่ย 10 เดือน"),
    "T4": ("ช่วงปีที่ผ่านมาดีกว่าถือ {b} เฉยๆ", "ช่วงปีที่ผ่านมาแพ้การถือ {b} เฉยๆ"),
    "T5": ("ราคายังไม่ห่างจุดสูงสุดรอบปีเกิน 25%", "ราคาต่ำกว่าจุดสูงสุดรอบปีเกิน 25%"),
    "T6": ("ยังไม่ร้อนเกินไป (RSI รายสัปดาห์ไม่เกิน 75)", "ร้อนเกินไป — ขึ้นแรงติดกันจน RSI รายสัปดาห์เกิน 75"),
}


def _baht(pct: float) -> str:
    """% ผลตอบแทน -> "100 บาท เป็น 69 บาท" — หน่วยที่คนรู้สึกได้"""
    return f"100 บาท เป็น {100 + pct:.0f} บาท"


TIER_LABEL = {"trend_up": "แนวโน้มเป็นใจ", "mixed": "สัญญาณปนกัน", "trend_down": "แนวโน้มไม่เป็นใจ"}


def _change_line(before: dict, result: dict, rule_change: bool) -> str:
    """บรรทัดหัว: เปลี่ยนจากอะไรเป็นอะไร — และถ้าเกณฑ์เปลี่ยนรอบนี้ด้วย ต้องบอกว่าอาจเป็นเพราะเรา"""
    line = (f"🔄 เปลี่ยนจาก **{TIER_LABEL.get(before['tier'], before['tier'])} "
            f"({before['score']}/6)** เป็น **{result['label']} ({result['score']}/6)**")
    if rule_change:
        line += ("\n⚠️ รอบนี้เราแก้เกณฑ์ให้คะแนนด้วย — การเปลี่ยนนี้อาจมาจากเกณฑ์ใหม่ "
                 "ไม่ใช่เพราะราคาขยับ")
    return line


def format_message(ticker: str, result: dict, before: dict | None = None,
                   rule_change: bool = False) -> str:
    bench = result.get("benchmark", "VT")
    if result.get("score") is None:
        return f"**{ticker}** — กราฟ: วัดไม่ได้\nเหตุผล: {result.get('reason')}"

    lines = [f"**{ticker}** — ความเห็นที่สองจากกราฟ: **{result['score']}/6 · {result['label']}**"]
    if before:
        lines.append(_change_line(before, result, rule_change))
    lines += [f"_แท่งสัปดาห์ล่าสุดที่ปิด {result['last_week']} · เดือน {result['last_month']}_", ""]
    for c in result["criteria"]:
        ok_text, bad_text = PLAIN[c["key"]]
        text = (ok_text if c["passed"] else bad_text).format(b=bench)
        edge = " ← เฉียดเส้น" if c["borderline"] else ""
        lines.append(f"{'✅' if c['passed'] else '❌'} {text}{edge}")

    own, other = result["own_return_12_1"], result["bench_return_12_1"]
    lines += ["", f"ถ้าถือ {ticker} ตั้งแต่ 12 เดือนก่อน (ไม่นับเดือนล่าสุด): {_baht(own)} · "
                  f"ถือ {bench}: {_baht(other)}",
              "", "_นับเงื่อนไข ไม่ใช่สัญญาณซื้อขาย — วางคู่กับคะแนนพื้นฐาน ไม่ได้แทนมัน_"]
    return "\n".join(lines)


def send(ticker: str, week, month, result: dict, webhook_url: str | None = None,
         before: dict | None = None, rule_change: bool = False) -> bool:
    from src.technical.chart import render_png   # import ช้า: matplotlib หนัก ใช้เฉพาะตอนส่งจริง

    png = render_png(ticker, week, month, result)
    url = webhook_url or os.environ.get(WEBHOOK_ENV)   # ไม่ตั้ง -> discord.post_image ไปช่องหลักเอง
    name = f"{ticker.replace('-', '_')}_{result.get('asof', date.today().isoformat())}.png"
    return discord.post_image(format_message(ticker, result, before, rule_change), png, name, url)
