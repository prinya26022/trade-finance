"""สั่ง investigation จากหน้าเว็บได้ (Phase 28) — job registry ในหน่วยความจำ + thread เบื้องหลัง.

ทำไมต้องมีชั้นนี้ ไม่ยิง investigate() ตรงๆ ใน endpoint: การสืบ 1 ครั้ง = Gemini หลายเทิร์น
(ดึง fundamentals/news/XBRL ก่อน แล้ววน tool-calling ได้ถึง MAX_STEPS) ใช้เวลาระดับ *สิบวินาที
ถึงนาที* — ยาวเกินกว่าจะให้ browser ค้างรอใน request เดียว (dev server/proxy ตัดก่อน แถวผู้ใช้
ไม่เห็นอะไรเลยระหว่างรอ). แยกเป็น POST=สั่งเริ่ม (คืน 202 ทันที) + GET status=ถามความคืบหน้า
แทน แล้วให้ frontend poll — ได้ผลพลอยได้ที่ตรงกับจุดขายของโปรเจกต์ด้วย: เห็น agent
คิด/เรียก tool ทีละสเต็ปสดๆ ไม่ใช่โผล่มาทั้งก้อนตอนจบ (ผ่าน on_step callback ของ run_investigation).

ขอบเขตที่ยอมรับโดยตั้งใจ: state อยู่ใน process เดียว (dict + Lock) ไม่ใช่ DB — รีสตาร์ท API
= job ที่ค้างอยู่หายไป. รับได้เพราะ *ผลจริง* ถูก persist ลงตาราง investigations โดย investigate()
อยู่แล้ว (job เป็นแค่ 'สถานะระหว่างทาง') และแอปนี้รันเครื่องเดียวคนเดียว ไม่ได้ scale หลาย worker.

กันยิงซ้ำ: 1 ticker มีได้ job เดียวที่กำลังวิ่ง (กดปุ่มรัวๆ = เผาโควตา Gemini ฟรีๆ) — start()
โยน AlreadyRunning ให้ endpoint แปลงเป็น 409.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class Job:
    """สถานะการสืบ 1 ครั้ง. steps โตขึ้นเรื่อยๆ ระหว่าง running (on_step เติมให้)."""
    ticker: str
    focus: str = ""
    status: str = "running"          # running | done | error
    started_at: str = ""
    finished_at: str | None = None
    steps: list[dict] = field(default_factory=list)
    conclusion: str = ""
    stopped: str = ""                # ค่าจาก Investigation.stopped ตอนจบ (concluded/max_steps/error)
    error: str | None = None
    thread: threading.Thread | None = None   # ไว้ join ในเทสต์ — ไม่ถูก serialize ออก API

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker, "focus": self.focus, "status": self.status,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "steps": list(self.steps), "conclusion": self.conclusion,
            "stopped": self.stopped, "error": self.error,
        }


class AlreadyRunning(Exception):
    """มี investigation ของ ticker นี้วิ่งอยู่แล้ว."""


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get(ticker: str) -> Job | None:
    """job ล่าสุดของ ticker (กำลังวิ่งหรือจบแล้วก็ได้) — None ถ้ายังไม่เคยสั่งใน process นี้."""
    with _LOCK:
        return _JOBS.get(ticker.upper())


def is_running(ticker: str) -> bool:
    job = get(ticker)
    return job is not None and job.status == "running"


def start(ticker: str, focus: str = "", investigate_fn: Callable | None = None) -> Job:
    """เริ่มสืบเบื้องหลังแล้วคืน Job ทันที (ยังไม่มีผล). investigate_fn ฉีดได้เพื่อเทสต์ออฟไลน์
    — โปรดักชันปล่อยเป็น None แล้วมันจะใช้ src.agent.investigate.investigate ตัวจริง."""
    ticker = ticker.upper()
    with _LOCK:
        cur = _JOBS.get(ticker)
        if cur is not None and cur.status == "running":
            raise AlreadyRunning(ticker)
        job = Job(ticker=ticker, focus=focus, started_at=_now())
        _JOBS[ticker] = job

    thread = threading.Thread(target=_run, args=(job, investigate_fn),
                              name=f"investigate-{ticker}", daemon=True)
    job.thread = thread
    thread.start()
    return job


def _run(job: Job, investigate_fn: Callable | None) -> None:
    if investigate_fn is None:
        from src.agent.investigate import investigate as investigate_fn   # noqa: PLW2901

    def on_step(step) -> None:
        with _LOCK:
            job.steps.append({"tool": step.tool, "args": step.args, "observation": step.observation})

    try:
        inv = investigate_fn(job.ticker, context=job.focus, on_step=on_step)
    except Exception as e:
        # โควตา Gemini หมด/ไม่มีคีย์/EDGAR ล่มตอนสร้าง toolbox ฯลฯ — job จบแบบ error
        # (ไม่ให้ thread ตายเงียบๆ ทิ้ง status ค้าง "running" ตลอดกาล)
        with _LOCK:
            job.status, job.stopped = "error", "error"
            job.error = f"{type(e).__name__}: {e}"
            job.finished_at = _now()
        return

    with _LOCK:
        # เอา steps จากผลสุดท้ายเป็นตัวจริง (on_step เป็นแค่ progress ระหว่างทาง — ถ้าพลาดสเต็ปไหน
        # ตรงนี้ทำให้ตรงกับ transcript ที่ persist ลง DB เสมอ)
        job.steps = [{"tool": s.tool, "args": s.args, "observation": s.observation} for s in inv.steps]
        job.conclusion = inv.conclusion
        job.stopped = inv.stopped
        # stopped == "error" = policy (Gemini) พังกลางทาง — run_investigation จับไว้แล้วคืน
        # Investigation สุภาพๆ ไม่ raise จึงต้องแปลงเป็น status error เองตรงนี้
        job.status = "error" if inv.stopped == "error" else "done"
        if inv.stopped == "error":
            job.error = inv.conclusion
        job.finished_at = _now()


def _reset() -> None:
    """ล้าง registry — สำหรับเทสต์เท่านั้น."""
    with _LOCK:
        _JOBS.clear()