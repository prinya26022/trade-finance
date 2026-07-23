"""Agentic investigation loop (Phase 13) — ทดสอบ *ลูป* ล้วนด้วย policy ปลอม (ไม่แตะ Gemini).
หัวใจที่ต้องพิสูจน์: ลูปรัน tool ตาม decision, ป้อน observation กลับ, จบเมื่อ final,
รับมือ tool ที่ไม่รู้จัก/พังโดยไม่ crash, และบังคับสรุปเมื่อชนเพดาน (stop condition)."""
from src.agent.investigate import run_investigation, Decision, ToolSpec, Investigation


class ScriptedPolicy:
    """policy ปลอม: คืน decision ตามสคริปต์ทีละสเต็ป + จำ observation ที่ลูปป้อนกลับมา."""
    def __init__(self, decisions, conclusion="forced-conclusion"):
        self._decisions = list(decisions)
        self._conclusion = conclusion
        self.observations = []   # เก็บไว้ให้ assert ว่าลูปป้อน observation กลับจริง
        self.i = 0

    def decide(self, observation):
        self.observations.append(observation)
        d = self._decisions[self.i]
        self.i += 1
        return d

    def force_conclude(self):
        return self._conclusion


def _echo_tool(name="get_x", result="observed-value"):
    return ToolSpec(name, "echo", {}, lambda args: result)


def test_runs_tool_then_concludes():
    tools = [_echo_tool("get_x", "X=42")]
    policy = ScriptedPolicy([Decision(name="get_x", args={}), Decision(final="done")])
    inv = run_investigation(policy, tools, ticker="AAPL")

    assert isinstance(inv, Investigation)
    assert inv.stopped == "concluded"
    assert inv.conclusion == "done"
    assert len(inv.steps) == 1
    assert inv.steps[0].tool == "get_x"
    assert inv.steps[0].observation == "X=42"
    # สเต็ปแรก observation=None, สเต็ปสอง = ผลของ tool (ลูปป้อนกลับจริง)
    assert policy.observations == [None, "X=42"]


def test_unknown_tool_reported_not_crash():
    tools = [_echo_tool("real_tool")]
    policy = ScriptedPolicy([Decision(name="ghost_tool", args={}), Decision(final="ok")])
    inv = run_investigation(policy, tools, ticker="X")

    assert len(inv.steps) == 1
    assert "ไม่มี tool" in inv.steps[0].observation   # error ป้อนกลับให้ agent ไม่ raise
    assert inv.conclusion == "ok"


def test_tool_exception_reported_not_crash():
    def _boom(args):
        raise RuntimeError("yfinance down")
    tools = [ToolSpec("flaky", "boom", {}, _boom)]
    policy = ScriptedPolicy([Decision(name="flaky", args={}), Decision(final="handled")])
    inv = run_investigation(policy, tools, ticker="X")

    assert "ERROR" in inv.steps[0].observation
    assert "yfinance down" in inv.steps[0].observation
    assert inv.stopped == "concluded"


def test_max_steps_forces_conclusion():
    tools = [_echo_tool("loop_tool", "again")]
    # policy เรียก tool ไม่หยุด -> ต้องโดนเพดานตัด แล้ว force_conclude
    never_ends = ScriptedPolicy([Decision(name="loop_tool", args={})] * 10, conclusion="ran out of budget")
    inv = run_investigation(never_ends, tools, max_steps=3, ticker="X")

    assert inv.stopped == "max_steps"
    assert len(inv.steps) == 3                 # หยุดที่เพดานพอดี
    assert inv.conclusion == "ran out of budget"


def test_to_dict_is_json_serializable():
    import json
    tools = [_echo_tool()]
    policy = ScriptedPolicy([Decision(name="get_x", args={"k": "v"}), Decision(final="c")])
    inv = run_investigation(policy, tools, ticker="AAPL")
    json.dumps(inv.to_dict())   # เก็บลง DB เป็น JSON ต้อง serialize ได้
    assert inv.to_dict()["steps"][0]["args"] == {"k": "v"}


def test_args_passed_to_tool():
    seen = {}
    tools = [ToolSpec("capture", "capture args", {}, lambda args: seen.update(args) or "ok")]
    policy = ScriptedPolicy([Decision(name="capture", args={"metric": "Operating Margin"}),
                             Decision(final="done")])
    run_investigation(policy, tools, ticker="X")
    assert seen == {"metric": "Operating Margin"}


class _PolicyThatCrashesOnDecide:
    """จำลอง policy ที่เรียก Gemini จริงแล้วพัง (เช่น 503 high demand ที่เจอจริงตอน verify Phase 25) —
    ต่างจาก tool พัง (มี test ข้างบนแล้ว): ตรงนี้ 'สมอง' เองใช้ไม่ได้เลย."""
    def decide(self, observation):
        raise RuntimeError("503 UNAVAILABLE: high demand")

    def force_conclude(self):
        raise AssertionError("ไม่ควรถูกเรียก — policy พังต้องหยุดทันที ไม่ใช่ไปต่อจนชนเพดาน")


def test_policy_crash_returns_graceful_error_not_raise():
    tools = [_echo_tool()]
    inv = run_investigation(_PolicyThatCrashesOnDecide(), tools, ticker="X")

    assert inv.stopped == "error"
    assert inv.steps == []                       # ไม่ทันถึงสเต็ป tool เลย
    assert "Gemini" in inv.conclusion
    assert "RuntimeError" in inv.conclusion       # ชนิด exception โผล่ในข้อความ (ไม่ใช่แค่ raw str)