"""ข้อความภาษาไทยอ่านง่าย — ลำดับตามที่คนเทรดต้องรู้: ตอนนี้อยู่ไหน → แต่ละทางตายที่ไหน →
หลักฐาน → ระดับที่ต้องจับตา. ไม่มีเปอร์เซ็นต์ความน่าจะเป็น ไม่มีคำว่าซื้อ/ขาย"""
import os

from src.notify import discord
from src.wave.analysis import Report, fmt

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_WAVE"
LEAN = {"A": "→ เข้าทาง A", "B": "→ เข้าทาง B", "-": ""}


def format_message(rep: Report) -> str:
    L = [f"**{rep.name}** · {rep.symbol} ล่าสุด **{fmt(rep.last.close)}** "
         f"({rep.last.ts:%d %b %H:%M} UTC)", "",
         "**จุดที่มาร์ก (ราคาจริงจากแท่ง):** "
         + " · ".join(f"{p.label}={fmt(p.price)}" for p in rep.pivots), ""]

    L.append("**กฎเหล็ก:** " + ("ผ่านครบ ✅" if rep.valid else "ผิด ❌ — count นี้ใช้ไม่ได้"))
    for r in rep.rules:
        if not r.ok or r.text.startswith("คลื่น 4"):     # โชว์ข้อที่ผิด + ข้อที่ใกล้เส้นที่สุดเสมอ
            L.append(f"{'✅' if r.ok else '❌'} {r.text}: {r.detail}")
    L += ["", f"**ตอนนี้:** {rep.state}", ""]

    for sc in rep.scenarios:
        mark = "🟢 ยังเป็นไปได้" if sc.alive else "⚫ ตายแล้ว"
        L.append(f"**ฉาก {sc.key} — {sc.title}** ({mark})")
        L.append(f"  {sc.meaning}")
        L.append(f"  ❌ ผิดเมื่อ: {sc.kill_text}")
        if sc.confirm_text:
            L.append(f"  ✔️ ชัดขึ้นเมื่อ: {sc.confirm_text}")
        if sc.targets:
            L.append("  🎯 " + " · ".join(f"{t} {fmt(x)}" for t, x in sc.targets))
        L.append("")

    if rep.evidence:
        L.append("**หลักฐานตามตำรา** (แนวโน้ม ไม่ใช่กฎ — ไม่ได้รวมเป็นเปอร์เซ็นต์):")
        L += [f"• {e.text} {LEAN.get(e.leans, '')}".rstrip() for e in rep.evidence]
        L.append("")
    if rep.parent_note:
        L += [f"**ภาพใหญ่:** {rep.parent_note}", ""]

    kills = [(sc.kill_level, sc.key) for sc in rep.scenarios if sc.alive and sc.kill_level is not None]
    if len(kills) >= 2:
        lo, hi = min(kills), max(kills)
        L.append(f"**สรุประดับ:** ระหว่าง {fmt(lo[0])} – {fmt(hi[0])} ยังตัดสินไม่ได้ · "
                 f"หลุด {fmt(lo[0])} ฉาก {lo[1]} ตาย · ทะลุ {fmt(hi[0])} ฉาก {hi[1]} ตาย")
    L.append("_เครื่องไม่ได้นับคลื่นแทน — ตรวจ count ที่มาร์กและไล่ทุกทางที่ราคายังไม่ฆ่า_")
    return "\n".join(L)


def send(rep: Report, hourly, webhook_url: str | None = None) -> bool:
    from src.notify.discord import post_chunks
    from src.wave.chart import render_png

    url = webhook_url or os.environ.get(WEBHOOK_ENV)
    msg = format_message(rep)
    # ภาพ + ส่วนหัวใน message แรก ส่วนที่เกิน 2000 ตัวอักษรตามไปเป็นข้อความต่อ (ไม่ตัดทิ้งเงียบๆ)
    head, _, rest = msg.partition("\n\n**หลักฐานตามตำรา**")
    if len(head) > discord.DISCORD_CONTENT_LIMIT:
        head, rest = msg[:0], msg
    ok = discord.post_image(head, render_png(rep, hourly),
                            f"wave_{rep.symbol.replace('-', '_')}.png", url)
    if rest:
        ok = post_chunks("**หลักฐานตามตำรา**" + rest, url) and ok
    return ok
