"""เช็กลิสต์ก่อนกดเข้า — โชว์ "ไม้หน้าตาแบบนี้ ในอดีตของคุณเองได้ผลยังไง" ไม่ใช่เกณฑ์ตายตัว.

ทำไมไม่มีเกณฑ์ตายตัว: เกณฑ์แรกที่คิดไว้มาจากชีต 15 ไม้ที่กรอกจากความจำ (R:R เกิน 5 แพ้ 10/10) —
พอได้ไม้จริงจาก OKX กลับกลายเป็น R:R เกิน 5 ชนะ 8/22 และ +317$. ถ้าฝังเกณฑ์จากชีตไว้ เครื่องมือ
จะเตือนผิดทางอย่างมั่นใจ. ที่นี่จึงดึงกลุ่มเดียวกับ stats.py จากสมุดที่อัปเดตทุกชั่วโมง แล้วบอก n
ทุกครั้ง — วันที่ข้อมูลเปลี่ยนใจ หน้าจอก็เปลี่ยนตาม

ไม่ห้ามเข้า ไม่บอกว่าควรเข้าไหม — บันทึกทุกครั้งที่เช็ก แล้วจับคู่กับไม้จริงบน OKX ทีหลัง (link_checks)
เพื่อวัดว่า "ไม้ที่เช็กก่อนเข้า" กับ "ไม้ที่กดเข้าทันที" ต่างกันจริงไหม
"""
from datetime import datetime, timedelta, timezone

from src.journal import context as C
from src.journal import stats as S

LINK_WINDOW = timedelta(hours=3)      # เช็กแล้วกดเข้าภายในเวลานี้ = ไม้เดียวกัน
LINK_PRICE_TOL = 0.01                 # ราคาเข้าห่างจากที่เช็กไม่เกิน 1%
RISK_STEPS = (0.5, 1.0, 2.0)          # % ของพอร์ตที่ใช้คำนวณขนาดไม้ให้ดู (ด่าน 6 ของเช็กลิสต์โปรเจกต์)
CT_VAL = 0.01                         # BTC-USDT-SWAP: 1 สัญญา = 0.01 BTC — หน่วยที่หน้าจอ OKX ใช้


def _wave_lines(side: str, sl: float | None, wave: dict | None) -> list[dict]:
    """ไม้นี้เล่นตามฉากไหน และ stop อยู่ตรงไหนเทียบเส้นตายของฉากนั้น"""
    if not wave:
        return []
    rep = wave.get("report") or {}
    want = "up" if side == "long" else "down"
    out = []
    for sc in rep.get("scenarios", []):
        if not sc.get("alive"):
            continue
        k = sc.get("kill_level")
        row = {"key": sc["key"], "title": sc["title"], "with_trade": sc.get("bias") == want, "kill": k,
               "kill_text": sc.get("kill_text")}
        if row["with_trade"] and sl and k:
            beyond = sl < k if side == "long" else sl > k
            row["stop_vs_kill"] = ("stop อยู่เลยเส้นตายของฉากนี้ — ถ้าโดน stop แปลว่าฉากผิดจริง" if beyond else
                                   "stop อยู่ก่อนถึงเส้นตายของฉากนี้ — โดน stop ได้ทั้งที่ฉากยังไม่ผิด")
            row["stop_beyond_kill"] = beyond
        out.append(row)
    return out


def _history(planned: dict, trades: list[dict], has_time: bool | None) -> list[dict]:
    """กลุ่มที่ไม้นี้จะตกอยู่ + ผลในอดีตของกลุ่มนั้น"""
    groups = S.compute(trades)["groups"]
    out = []
    for title, fn in (("R:R ที่วางไว้", S._rr_bucket), ("stop เทียบระยะแกว่ง", S._stop_bucket),
                      ("เทรนด์จริงตอนเข้า", S._trend_bucket)):
        b = fn(planned)
        if b:
            out.append({"group": title, "bucket": b, **(groups.get(title, {}).get(b) or {"n": 0})})
    if has_time is not None:
        b = "มีเวลาดู" if has_time else "ไม่มีเวลาดู"
        out.append({"group": "มีเวลาดูไม้นี้ไหม", "bucket": b,
                    **(groups.get("มีเวลาดูไม้นี้ไหม", {}).get(b) or {"n": 0})})
    return out


def evaluate(side: str, sl: float | None, tp: float | None, hourly, daily, trades: list[dict],
             entry: float | None = None, margin: float | None = None, lever: float | None = None,
             equity: float | None = None, has_time: bool | None = None, wave: dict | None = None,
             now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    entry = entry or (hourly[-1].close if hourly else None)
    ctx = C.build(hourly, daily, now, side, entry, sl, tp)
    planned = {"side": side, "entry": entry, "sl": sl, "tp": tp, "context": ctx}
    out = {"asof": now.isoformat(timespec="minutes"), "side": side, "entry": entry, "sl": sl, "tp": tp,
           "margin": margin, "lever": lever, "equity": equity, "has_time": has_time, "context": ctx,
           "history": _history(planned, trades, has_time), "wave": _wave_lines(side, sl, wave),
           # เส้นตายมาจากรายงานคลื่นรอบล่าสุด ไม่ใช่ตอนนี้ — ต้องบอกอายุ ไม่งั้นอ่านเหมือนสด (Phase 47)
           "wave_asof": (wave or {}).get("generated_at")}
    if entry and sl:
        per_coin = abs(entry - sl)
        if margin and lever:
            coins = margin * lever / entry
            out["risk_usd"] = round(per_coin * coins, 2)
            if equity:
                out["risk_pct"] = round(per_coin * coins / equity * 100, 2)
        if equity and per_coin:
            # ขนาดไม้ที่ทำให้เสี่ยง x% — ให้เทียบกับที่ตั้งใจจะวาง ไม่ได้บอกว่าควรใช้ข้อไหน
            out["sizing"] = []
            for p in RISK_STEPS:
                coins = equity * p / 100 / per_coin
                out["sizing"].append({"risk_pct": p, "coins": round(coins, 6), "contracts": round(coins / CT_VAL, 2),
                                      "notional": round(coins * entry, 2),
                                      **({"margin": round(coins * entry / lever, 2)} if lever else {})})
    return out


def link_checks(trades: list[dict], checks: list[dict]) -> list[tuple[int, int]]:
    """จับคู่ (check_id, trade_id): ทิศเดียวกัน, กดเข้าภายใน 3 ชม. หลังเช็ก, ราคาเข้าห่างไม่เกิน 1%.
    เช็กหนึ่งครั้งผูกได้ไม้เดียว (ไม้ที่ใกล้ที่สุดหลังเช็ก)"""
    pairs, used = [], set()
    for ch in sorted(checks, key=lambda c: c["created_at"]):
        if ch.get("trade_id"):
            continue
        at = datetime.fromisoformat(ch["created_at"])
        cands = [t for t in trades if t["id"] not in used and t.get("opened_at") and t["side"] == ch["side"]
                 and at <= datetime.fromisoformat(t["opened_at"]) <= at + LINK_WINDOW
                 and t.get("entry") and ch.get("entry")
                 and abs(t["entry"] / ch["entry"] - 1) <= LINK_PRICE_TOL]
        if cands:
            t = min(cands, key=lambda t: t["opened_at"])
            used.add(t["id"])
            pairs.append((ch["id"], t["id"]))
    return pairs
