"""สั่ง investigation จากหน้าเว็บ (Phase 28) — ทดสอบ job runner ล้วน ด้วย investigate ปลอม
(ไม่แตะ Gemini/network/DB). หัวใจที่ต้องพิสูจน์: งานวิ่งเบื้องหลังจริง, สเต็ปโผล่ให้ poll เห็น
*ระหว่างทาง* ไม่ใช่ตอนจบ, กดซ้ำระหว่างวิ่งไม่ได้ (กันเผาโควตา), และ error ไม่ทิ้ง job ค้าง running.
"""
import threading

import pytest

from src.agent import investigate_runner as runner
from src.agent.investigate import Investigation, Step


@pytest.fixture(autouse=True)
def clean_registry():
    runner._reset()
    yield
    runner._reset()


def _join(job, timeout=5.0):
    assert job.thread is not None
    job.thread.join(timeout)
    assert not job.thread.is_alive(), "job thread ไม่จบในเวลาที่กำหนด"


def _fake_investigate(steps=(("get_x", "X=42"),), conclusion="สรุปแล้ว", stopped="concluded",
                      gate: threading.Event | None = None):
    """investigate ปลอม: ยิง on_step ทีละสเต็ป (หยุดรอ gate ได้เพื่อเช็คสถานะระหว่างทาง)."""
    def _fn(ticker, context="", on_step=None):
        made = []
        for tool, obs in steps:
            st = Step(tool, {}, obs)
            made.append(st)
            if on_step:
                on_step(st)
            if gate is not None:
                gate.wait(5)
        return Investigation(ticker, made, conclusion, stopped)
    return _fn


def test_runs_in_background_and_finishes():
    # gate ค้าง fake ไว้ -> พิสูจน์ได้แน่ๆ ว่า start() คืนก่อนสืบเสร็จ (ถ้าไม่ค้างไว้ fake จบเร็ว
    # จนอาจ done ไปแล้วตอน assert = เทสต์ flaky ไม่ได้พิสูจน์อะไร)
    gate = threading.Event()
    job = runner.start("AAPL", investigate_fn=_fake_investigate(gate=gate))
    assert job.status == "running"      # คืนทันที ไม่รอสืบเสร็จ
    gate.set()
    _join(job)

    assert job.status == "done"
    assert job.stopped == "concluded"
    assert job.conclusion == "สรุปแล้ว"
    assert job.steps == [{"tool": "get_x", "args": {}, "observation": "X=42"}]
    assert job.finished_at is not None


def test_steps_visible_while_still_running():
    """จุดขายของ Phase 28: poll แล้วเห็นสเต็ปโผล่ทีละอัน ไม่ใช่รอทั้งก้อนตอนจบ."""
    gate = threading.Event()
    fn = _fake_investigate(steps=(("a", "obs-a"), ("b", "obs-b")), gate=gate)
    job = runner.start("MSFT", investigate_fn=fn)

    # รอให้สเต็ปแรกถูกบันทึก (fake ค้างที่ gate อยู่ = ยังสืบไม่จบแน่ๆ)
    for _ in range(500):
        if runner.get("MSFT").steps:
            break
        threading.Event().wait(0.01)

    live = runner.get("MSFT")
    assert live.status == "running"
    assert live.steps[0]["observation"] == "obs-a"
    assert live.conclusion == ""        # ยังไม่มีข้อสรุประหว่างทาง

    gate.set()
    _join(job)
    assert job.status == "done"
    assert [s["tool"] for s in job.steps] == ["a", "b"]


def test_second_start_while_running_rejected():
    gate = threading.Event()
    job = runner.start("NVDA", investigate_fn=_fake_investigate(gate=gate))
    with pytest.raises(runner.AlreadyRunning):
        runner.start("NVDA", investigate_fn=_fake_investigate())

    gate.set()
    _join(job)
    # จบแล้วสั่งใหม่ได้ตามปกติ
    again = runner.start("NVDA", investigate_fn=_fake_investigate())
    _join(again)
    assert again.status == "done"


def test_other_ticker_can_run_concurrently():
    gate = threading.Event()
    a = runner.start("AAA", investigate_fn=_fake_investigate(gate=gate))
    b = runner.start("BBB", investigate_fn=_fake_investigate())
    _join(b)
    assert b.status == "done"
    assert a.status == "running"
    gate.set()
    _join(a)


def test_exception_marks_error_not_stuck_running():
    def _boom(ticker, context="", on_step=None):
        raise RuntimeError("quota exhausted")

    job = runner.start("TSLA", investigate_fn=_boom)
    _join(job)

    assert job.status == "error"
    assert "quota exhausted" in job.error
    assert job.finished_at is not None
    assert not runner.is_running("TSLA")


def test_policy_failure_inside_loop_becomes_error_status():
    """run_investigation จับ Gemini พังไว้เองแล้วคืน Investigation(stopped='error') ไม่ raise
    — runner ต้องแปลงเป็น status error ให้ UI ไม่ไปโชว์เป็นข้อสรุปจริง."""
    fn = _fake_investigate(steps=(), conclusion="เกิดข้อผิดพลาดระหว่างคุยกับ Gemini", stopped="error")
    job = runner.start("GOOGL", investigate_fn=fn)
    _join(job)

    assert job.status == "error"
    assert "Gemini" in job.error


def test_focus_passed_through_as_context():
    seen = {}

    def _fn(ticker, context="", on_step=None):
        seen["ticker"], seen["context"] = ticker, context
        return Investigation(ticker, [], "ok", "concluded")

    job = runner.start("duol", focus="ทำไม margin ตก", investigate_fn=_fn)
    _join(job)

    assert seen["ticker"] == "DUOL"          # normalize เป็นตัวใหญ่ตั้งแต่ start()
    assert seen["context"] == "ทำไม margin ตก"


def test_as_dict_is_json_serializable():
    import json

    job = runner.start("AAPL", investigate_fn=_fake_investigate())
    _join(job)
    d = job.as_dict()

    assert "thread" not in d                 # thread object ต้องไม่หลุดออก API
    assert json.loads(json.dumps(d, ensure_ascii=False))["status"] == "done"