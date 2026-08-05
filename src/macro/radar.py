"""Macro Event Radar — orchestration.

รวม fred (ข้อมูลดิบ) + baserate (สถิติย้อนหลัง) + store (กันแจ้งซ้ำ) เป็น 2 ทางเข้า:

  latest_release_view(key)  : สแนปช็อต read-only ของตัวเลขล่าสุด + base-rate — ใช้โชว์บนเว็บ.
  scan_for_alerts()         : ตรวจว่ามี 'ตัวเลขเดือนใหม่' โผล่ไหม -> คืน alert + mark_seen — ใช้กับ cron/loop ยิง Discord.

ปรัชญาเดิม: บอก 'ข้อเท็จจริง + การกระจายย้อนหลัง' ไม่ 'ฟันธงว่าจะขึ้น/ลง'.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.macro import baserate, fred, store

# ตัวเลขจริงเลื่อนได้ไม่กี่วัน และ approx_lag_days เองก็เป็นค่าประมาณ — ให้เวลาผ่อนก่อนจะบอกว่า
# 'เกินกำหนด' ไม่งั้นจะเตือนหมาป่ามาทุกเดือนจนไม่มีใครเชื่อตอนที่พังจริง
OVERDUE_GRACE_DAYS = 7


@dataclass
class ReleaseView:
    key: str
    label: str                 # ชื่อไทยของ series
    ref_date: str              # เดือนอ้างอิง (YYYY-MM-DD)
    value: float               # ค่าดิบล่าสุด
    unit: str
    direction: str             # 'up' | 'down' | 'flat'
    desc: str                  # อธิบายทิศ (เช่น 'เงินเฟ้อเร่งตัวขึ้น')
    signal: float              # สัญญาณล่าสุด (YoY% / งานเพิ่ม / ระดับ)
    prev_signal: float
    stats: list = field(default_factory=list)   # list[baserate.ReactionStats]
    approx: bool = True        # base-rate ใช้วันประกาศประมาณหรือไม่

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "ref_date": self.ref_date,
            "value": self.value,
            "unit": self.unit,
            "direction": self.direction,
            "desc": self.desc,
            "signal": round(self.signal, 2),
            "prev_signal": round(self.prev_signal, 2),
            "approx": self.approx,
            "reactions": [
                {
                    "asset": r.asset,
                    "n": r.n,
                    "mean_pct": round(r.mean_pct, 2),
                    "min_pct": round(r.min_pct, 2),
                    "max_pct": round(r.max_pct, 2),
                    "share_up": round(r.share_up, 3),
                    "horizon_days": r.horizon_days,
                }
                for r in self.stats
            ],
        }


def latest_release_view(key: str, horizon_days: int = 1) -> ReleaseView | None:
    """ตัวเลขล่าสุดของ series + สถิติผลตอบสนองย้อนหลังของทิศทางนั้น. ข้อมูลไม่พอ -> None."""
    ls = baserate.latest_signal(key)
    if ls is None:
        return None
    stats = [] if ls.direction == "flat" else baserate.reaction_stats(key, ls.direction, horizon_days)
    return ReleaseView(
        key=key,
        label=fred.SERIES[key].label_th,
        ref_date=ls.ref_date.isoformat(),
        value=ls.value,
        unit=fred.SERIES[key].unit,
        direction=ls.direction,
        desc=ls.desc,
        signal=ls.signal,
        prev_signal=ls.prev_signal,
        stats=stats,
        approx=stats[0].approx if stats else not fred.has_api_key(),
    )


def dashboard(horizon_days: int = 1) -> list[ReleaseView]:
    """ทุก series (สำหรับหน้าเว็บ). ข้าม series ที่ดึงข้อมูลไม่ได้เงียบๆ."""
    out = []
    for key in fred.SERIES:
        v = latest_release_view(key, horizon_days)
        if v is not None:
            out.append(v)
    return out


def scan_for_alerts(mark: bool = True) -> list[ReleaseView]:
    """ตรวจทุก series ว่ามี 'ตัวเลขเดือนใหม่' โผล่หลังจากครั้งก่อนที่แจ้งไหม.

    - ครั้งแรกสุด (ยังไม่เคย seen) -> mark เงียบๆ ไม่แจ้ง (bootstrap กันสแปมย้อนหลัง).
    - ถ้า ref_date ล่าสุด != ที่เคยแจ้ง -> คืน view เป็น alert แล้ว mark_seen.
    """
    alerts: list[ReleaseView] = []
    for key in fred.SERIES:
        pair = fred.latest_two(key)
        if pair is None:
            continue
        latest = pair[1]
        latest_ref = latest.ref_date.isoformat()
        seen = store.get_seen(key)

        if seen is None:                        # bootstrap: จำไว้เฉยๆ ไม่แจ้ง
            if mark:
                store.mark_seen(key, latest_ref, latest.value)
            continue
        if seen == latest_ref:                  # ไม่มีอะไรใหม่
            continue

        view = latest_release_view(key)         # มีของใหม่ -> สร้าง alert เต็ม
        if view is not None:
            alerts.append(view)
        if mark:
            store.mark_seen(key, latest_ref, latest.value)
    return alerts


@dataclass
class SeriesStatus:
    """สถานะของ series หนึ่งตัว — มีไว้ตอบคำถามเดียว: 'ที่มันเงียบอยู่ ปกติหรือพัง'."""
    key: str
    label: str
    fetched: bool              # ดึงจาก FRED สำเร็จไหม (ล้มเหลว = เงียบเพราะพัง)
    latest_ref: str | None     # เดือนอ้างอิงล่าสุดที่ FRED มี
    seen_ref: str | None       # เดือนที่เราแจ้งไปแล้ว
    due_on: str | None         # วันที่คาดว่าเดือนถัดไปจะประกาศ
    overdue_days: int          # เลยกำหนด(+ผ่อนผัน)มากี่วัน — 0 คือยังไม่ถึงคิว

    @property
    def state(self) -> str:
        if not self.fetched:
            return "fetch_failed"    # พัง: ดึงข้อมูลไม่ได้เลย
        if self.overdue_days > 0:
            return "overdue"         # น่าสงสัย: เลยกำหนดประกาศแล้วยังไม่มีของใหม่
        if self.seen_ref != self.latest_ref:
            return "unreported"      # มีของใหม่ที่ยังไม่ได้แจ้ง (รอบถัดไปจะยิง)
        return "ok"                  # ปกติ: ตามทันแล้ว รอรอบหน้า

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "state": self.state,
                "fetched": self.fetched, "latest_ref": self.latest_ref,
                "seen_ref": self.seen_ref, "due_on": self.due_on,
                "overdue_days": self.overdue_days}


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def status(today: date | None = None) -> list[SeriesStatus]:
    """สถานะทุก series — ไม่แตะ store.mark_seen (อ่านอย่างเดียว เรียกกี่ครั้งก็ได้).

    ทำไมต้องมี: ผลลัพธ์ปกติของ radar คือ 'เงียบ' และผลลัพธ์ตอนพังก็คือ 'เงียบ' เหมือนกันเป๊ะ
    (FRED เคยบล็อก IP ของ runner มาแล้วรอบหนึ่ง — ตอนนั้นไม่มีอะไรบอกเลย). ตัวนี้ทำให้ความเงียบ
    สองแบบแยกออกจากกันได้ โดยไม่ต้องรอให้ตัวเลขออกจริงเพื่อจะรู้ว่าระบบยังทำงานอยู่ไหม
    """
    today = today or date.today()
    out: list[SeriesStatus] = []
    for key, meta in fred.SERIES.items():
        seen = store.get_seen(key)
        pair = fred.latest_two(key)
        if pair is None:
            out.append(SeriesStatus(key, meta.label_th, False, None, seen, None, 0))
            continue
        latest = pair[1].ref_date
        due = _next_month(latest) + timedelta(days=meta.approx_lag_days)
        out.append(SeriesStatus(
            key, meta.label_th, True, latest.isoformat(), seen, due.isoformat(),
            max(0, (today - due).days - OVERDUE_GRACE_DAYS),
        ))
    return out


_STATE_TH = {
    "ok": "ปกติ",
    "unreported": "มีของใหม่ ยังไม่ได้แจ้ง",
    "overdue": "เลยกำหนดแล้วยังไม่มีของใหม่",
    "fetch_failed": "ดึง FRED ไม่ได้",
}


def render_status(rows: list[SeriesStatus], today: date | None = None) -> str:
    today = today or date.today()
    lines = [f'{"series":8} {"FRED ล่าสุด":>12} {"แจ้งไปแล้ว":>12} {"คาดว่าออก":>12}  สถานะ']
    for r in rows:
        due = r.due_on or "-"
        if r.due_on and r.overdue_days == 0:
            days = (date.fromisoformat(r.due_on) - today).days
            due += f" (อีก {days} วัน)" if days > 0 else " (ถึงคิวแล้ว)"
        elif r.overdue_days:
            due += f" (เลยมา {r.overdue_days} วัน)"
        lines.append(f'{r.key:8} {r.latest_ref or "-":>12} {r.seen_ref or "-":>12} '
                     f'{due:>12}  {_STATE_TH[r.state]}')
    return "\n".join(lines)


def format_alert(view: ReleaseView) -> str:
    """แปลง ReleaseView เป็นข้อความ Discord/markdown (ข้อเท็จจริง + base-rate + คำเตือน)."""
    arrow = {"up": "🔺", "down": "🔻", "flat": "➖"}.get(view.direction, "•")
    lines = [
        f"📊 **{view.label}** ออกใหม่ (เดือนอ้างอิง {view.ref_date[:7]})",
        f"{arrow} {view.desc}: {view.prev_signal:g} → {view.signal:g} {view.unit}",
    ]
    if view.stats:
        lines.append("")
        lines.append("_ครั้งก่อนๆ ที่สัญญาณแบบนี้ ตลาดขยับยังไง (ย้อนหลัง — ไม่ใช่การทำนาย):_")
        for r in view.stats:
            lines.append("• " + r.as_text())
    lines.append("")
    lines.append("_ข้อมูลย้อนหลังเพื่อประกอบการมองภาพ ไม่ใช่คำแนะนำซื้อ/ขาย_")
    return "\n".join(lines)


if __name__ == "__main__":  # เดโม read-only (แตะเน็ต): python -m src.macro.radar
    for v in dashboard():
        print(format_alert(v))
        print("-" * 60)
