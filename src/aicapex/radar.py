"""ประกอบร่าง — fetch (ข้อมูลดิบ) + signals (ตัดสิน) + store (จำรอบก่อน) เป็นรายงานหนึ่งฉบับ.

โครงเดียวกับ src/macro/radar.py: ทางเข้าสองทาง — `build_report()` สำหรับดูเฉยๆ (เว็บ/รันมือ)
และ `scan()` ที่บันทึกสถานะลง DB ด้วย (สำหรับ cron ที่ต้องรู้ว่า 'อะไรเปลี่ยนตั้งแต่เมื่อวาน')

**สิ่งที่รายงานนี้ตั้งใจไม่ทำ:** ไม่รวมเป็นคะแนนเดียว ไม่ฟันธงว่าจะแตกเมื่อไหร่ ไม่บอกให้
ซื้อ/ขาย — เพราะคนที่เล่าเรื่องฟองสบู่ได้เก่งมักจะถูก แต่เร็วเกินไปหลายปี ซึ่งในทางปฏิบัติ
แปลว่าผิด สิ่งที่ทำได้จริงคือนับเงื่อนไขที่ตรวจสอบได้ แล้วบอกว่าวันนี้ต่างจากเมื่อวานตรงไหน
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.aicapex import signals as sig
from src.aicapex import store
from src.aicapex.fetch import fetch_all
from src.aicapex.universe import ALL

# มุมอับที่ประกาศไว้ตั้งแต่ __init__ — ต้องเดินทางไปกับรายงานทุกฉบับ ไม่ใช่อยู่แค่ใน docstring
# ที่ไม่มีใครเปิดอ่าน. เรดาร์ที่ไม่บอกว่ามีมุมอับ อันตรายกว่าไม่มีเรดาร์
BLIND_SPOTS = (
    "ค่าเช่า GPU รายชั่วโมง — สัญญาณที่ตรงที่สุด แต่ไม่มีแหล่งฟรีที่เชื่อถือได้",
    "อัตราการใช้งานจริงของ neocloud — ไม่เปิดเผยเป็นตัวเลขที่เครื่องอ่านได้",
    "การต่อสัญญาเช่า — เห็นแต่ยอดเซ็นใหม่ ซึ่งโตได้ตลอดขณะที่ของเก่าไม่ต่อ",
    "เงื่อนไขสินเชื่อเอกชน — BIS เองระบุว่าเปิดเผยข้อมูลไม่ดี",
    "GPU ตัวเดียวถูกวางเป็นหลักประกันซ้ำหรือไม่ — แม้แต่ BIS ก็ยกเป็นข้อกังวลที่มองไม่เห็น",
)

_STATE_ORDER = {"alert": 0, "watch": 1, "unknown": 2, "ok": 3}


@dataclass
class Change:
    key: str
    label: str
    before: str
    after: str
    value: float | None

    @property
    def worsened(self) -> bool:
        return _STATE_ORDER[self.after] < _STATE_ORDER[self.before]


@dataclass
class Report:
    run_at: str
    signals: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    first_run: bool = False

    @property
    def overall(self) -> str:
        return sig.worst_state(self.signals)

    @property
    def triggered(self) -> list:
        """เงื่อนไขที่เป็นจริงแล้ว เรียงจากแย่ที่สุด — นี่คือ 'ตัวเลข' ของรายงานนี้
        แทนที่จะเป็นคะแนนรวม: นับได้ ชี้ชื่อได้ เถียงได้ทีละข้อ"""
        return sorted([s for s in self.signals if s.state in ("alert", "watch")],
                      key=lambda s: _STATE_ORDER[s.state])

    @property
    def measurable(self) -> list:
        return [s for s in self.signals if s.state != "unknown"]

    def to_dict(self, previous: dict | None = None) -> dict:
        prev = previous or {}
        return {
            "run_at": self.run_at,
            "overall": self.overall,
            "first_run": self.first_run,
            "summary": self.summary_line(),
            "counts": {
                "total": len(self.signals),
                "triggered": len(self.triggered),
                "alert": sum(1 for s in self.signals if s.state == "alert"),
                "watch": sum(1 for s in self.signals if s.state == "watch"),
                "unknown": sum(1 for s in self.signals if s.state == "unknown"),
            },
            "decisive_key": sig.DECISIVE,
            "decisive_why": sig.DECISIVE_WHY,
            "chapters": [{"key": k, "title": t} for k, t in sig.CHAPTERS],
            "signals": [signal_to_dict(s, (prev.get(s.key) or {}).get("value"))
                        for s in self.signals],
            "changes": [{"key": c.key, "label": c.label, "before": c.before,
                         "after": c.after, "worsened": c.worsened} for c in self.changes],
            "blind_spots": list(BLIND_SPOTS),
        }

    def summary_line(self) -> str:
        n_alert = sum(1 for s in self.signals if s.state == "alert")
        n_watch = sum(1 for s in self.signals if s.state == "watch")
        n_unknown = sum(1 for s in self.signals if s.state == "unknown")
        parts = [f"{n_alert} เป็นจริงแล้ว", f"{n_watch} ต้องจับตา"]
        if n_unknown:
            parts.append(f"{n_unknown} วัดไม่ได้")
        return f"{len(self.signals)} เงื่อนไข: " + " · ".join(parts)


def signal_to_dict(s, previous_value: float | None = None) -> dict:
    """Signal -> dict สำหรับ API/DB. `previous_value` มาจากรอบก่อน เพื่อให้หน้าเว็บตอบ
    'ดีขึ้นหรือแย่ลง' ได้โดยไม่ต้องคำนวณเอง (และไม่ต้องเดาทิศทางของแต่ละสัญญาณ)."""
    delta = None
    if s.value is not None and previous_value is not None:
        delta = round(s.value - previous_value, 2)
    return {
        "key": s.key, "label": s.label, "state": s.state, "value": s.value, "unit": s.unit,
        "watch_at": s.watch_at, "alert_at": s.alert_at, "margin": s.margin,
        "borderline": s.borderline, "detail": s.detail, "missing": s.missing,
        "rows": s.rows, "chapter": sig.CHAPTER_OF.get(s.key),
        "decisive": s.key == sig.DECISIVE,
        "previous_value": previous_value, "delta": delta,
    }


def _diff(current: list, previous: dict[str, dict]) -> list[Change]:
    out = []
    for s in current:
        before = (previous.get(s.key) or {}).get("state")
        if before and before != s.state:
            out.append(Change(s.key, s.label, before, s.state, s.value))
    return out


def build_report(data: dict | None = None, previous: dict | None = None,
                 now: datetime | None = None) -> Report:
    """รายงานหนึ่งฉบับ. `data`/`previous` ฉีดเข้ามาได้เพื่อให้เทสต์ไม่แตะเน็ตและไม่แตะ DB
    (แพตเทิร์นเดียวกับ build_board(rows=...) ของ Phase 43)."""
    data = fetch_all(list(ALL)) if data is None else data
    prev = store.previous_states() if previous is None else previous
    current = [fn(data) for fn in sig.SIGNALS]
    return Report(
        run_at=(now or datetime.now()).isoformat(timespec="seconds"),
        signals=current,
        changes=_diff(current, prev),
        first_run=not prev,
    )


def scan(db_path: Path | None = None) -> Report:
    """รันจริงสำหรับ cron — สร้างรายงานแล้ว **บันทึกสถานะ** เพื่อให้รอบหน้าเทียบได้.

    รอบแรกจะไม่มี changes เลยโดยธรรมชาติ (ไม่มีอะไรให้เทียบ) — ติดธง first_run ไว้เพื่อให้
    ปลายทางไม่ตีความว่า 'ทุกอย่างนิ่ง' ทั้งที่ความจริงคือ 'ยังไม่รู้'"""
    previous = store.previous_states()
    report = build_report(previous=previous)
    store.record(report.signals, db_path=db_path)
    # เก็บฉบับเต็มไว้ให้หน้าเว็บอ่าน — เว็บกับ Discord จะพูดตรงกันเสมอเพราะมาจากรอบเดียวกัน
    store.save_report(report.to_dict(previous), db_path=db_path)
    return report
