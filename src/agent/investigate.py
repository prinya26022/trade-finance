"""Agentic investigation loop (Phase 13) — ตัว 'agent' จริงของโปรเจกต์.

ต่างจาก summarize() ที่ยิง LLM ครั้งเดียวจบ (pipeline เส้นตรง): อันนี้ให้ LLM **วางแผน +
เรียก tool เองเป็นสเต็ป** จนพอใจแล้วสรุป — โชว์ครบ 4 อย่างที่ AGENT_PROJECT.md บอกว่าทำให้
เป็น 'agent' ไม่ใช่ script: planning, tool-calling, tool-failure handling, loop + stop condition.

ดีไซน์แยก 2 ชั้นเพื่อให้ test offline ได้ (ไม่แตะ Gemini/network):
  - run_investigation(policy, tools, ...) : *ลูป* ล้วน — รับ 'policy' (สมองที่ตัดสินใจ) แบบ
    inject ได้ จึงทดสอบด้วย policy ปลอมที่คืน decision ตามสคริปต์ได้
  - GeminiPolicy : สมองจริงที่ห่อ google-genai function-calling (manual, คุม loop เอง)

ทุกสเต็ปถูก log (tool + args + observation) -> เป็นทั้ง demo ('agent คิดยังไง') และ eval
artifact ('agent ตัดสินใจดีไหม') — เก็บลง DB ได้ (investigations table).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Protocol

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

MAX_STEPS = 6   # เพดาน tool call ต่อ 1 investigation — กัน loop ไม่รู้จบ + คุม Gemini quota


# ─────────────────────────────────────────────────────────────────────────────
# DATA SHAPES
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Decision:
    """สิ่งที่ 'สมอง' (policy) ตัดสินใจในแต่ละสเต็ป: เรียก tool (name+args) หรือ จบ (final)."""
    name: str | None = None
    args: dict | None = None
    final: str | None = None

    @property
    def is_final(self) -> bool:
        return self.final is not None


@dataclass
class Step:
    tool: str
    args: dict
    observation: str


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict            # {argname: {"type": "STRING", "description": "...", "required": bool}}
    fn: Callable[[dict], str]   # รับ args -> คืน observation (string ที่ป้อนกลับให้ LLM)


@dataclass
class Investigation:
    ticker: str
    steps: list[Step] = field(default_factory=list)
    conclusion: str = ""
    stopped: str = "concluded"   # "concluded" (agent จบเอง) | "max_steps" (ชนเพดาน) | "error"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "steps": [asdict(s) for s in self.steps],
            "conclusion": self.conclusion,
            "stopped": self.stopped,
        }


class Policy(Protocol):
    """สมองของ agent — ตัดสินใจสเต็ปถัดไปจาก observation ล่าสุด (None = สเต็ปแรก)."""
    def decide(self, observation: str | None) -> Decision: ...
    def force_conclude(self) -> str: ...


# ─────────────────────────────────────────────────────────────────────────────
# THE LOOP (pure — ไม่รู้จักว่า policy เป็น Gemini หรือของปลอม)
# ─────────────────────────────────────────────────────────────────────────────
def run_investigation(policy: Policy, tools: list[ToolSpec], max_steps: int = MAX_STEPS,
                      ticker: str = "") -> Investigation:
    """ขับ loop: policy ตัดสินใจ -> ถ้าเรียก tool ก็รัน แล้วป้อน observation กลับ -> วนจน
    policy จบเอง หรือชนเพดาน (แล้วบังคับให้สรุป). tool ที่ไม่รู้จัก/พัง-> ส่ง error กลับให้ agent
    รับมือเอง (tool-failure handling) ไม่ทำ loop ล่ม."""
    by_name = {t.name: t for t in tools}
    steps: list[Step] = []
    observation: str | None = None

    for _ in range(max_steps):
        decision = policy.decide(observation)
        if decision.is_final:
            return Investigation(ticker, steps, decision.final or "", "concluded")

        tool = by_name.get(decision.name or "")
        args = decision.args or {}
        if tool is None:
            observation = f"ERROR: ไม่มี tool ชื่อ '{decision.name}' — เลือกจาก: {', '.join(by_name)}"
        else:
            try:
                observation = tool.fn(args)
            except Exception as e:                       # tool พัง -> บอก agent ไม่ใช่ crash
                observation = f"ERROR ตอนเรียก {decision.name}: {e}"
        steps.append(Step(decision.name or "", args, observation))

    # ชนเพดานแล้วยังไม่จบ -> บังคับให้สรุปจากสิ่งที่รู้ (stop condition)
    return Investigation(ticker, steps, policy.force_conclude(), "max_steps")


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS — backed by data ที่มีอยู่แล้ว (facts/news) + XBRL (cache) ไม่ใช่ endpoint ใหม่
# ─────────────────────────────────────────────────────────────────────────────
def build_toolbox(ticker: str) -> list[ToolSpec]:
    """สร้างชุด tool สำหรับ ticker หนึ่ง — ดึง facts/news/xbrl ครั้งเดียวแล้ว closure ไว้
    (tool เรียกซ้ำได้ไม่ยิง network เพิ่ม; XBRL มี cache ในตัวอยู่แล้ว)."""
    from src.providers.registry import get_providers
    from src.providers.stock.xbrl import get_annual_series

    bundle = get_providers("stock")
    try:
        facts = bundle.fundamentals.get_fundamentals(ticker).to_facts()
    except Exception:
        facts = []
    try:
        news = bundle.news.get_news(ticker, limit=6)
    except Exception:
        news = []
    xbrl = get_annual_series(ticker)

    # facts จัดกลุ่มตาม label -> [(period, value, unit), ...]
    by_label: dict[str, list] = {}
    for f in facts:
        by_label.setdefault(f.label, []).append((f.period, f.value, f.unit))

    def _list_metrics(args: dict) -> str:
        if not by_label:
            return "ไม่มีข้อมูลงบ (fundamentals ดึงไม่ได้)"
        return "เมตริกที่ดูได้: " + ", ".join(sorted(by_label))

    def _get_metric_trend(args: dict) -> str:
        metric = (args.get("metric") or "").strip()
        # จับคู่แบบ case-insensitive + partial กัน LLM สะกดเพี้ยน
        match = next((k for k in by_label if k.lower() == metric.lower()), None) \
            or next((k for k in by_label if metric.lower() in k.lower()), None)
        if match is None:
            return f"ไม่มีเมตริก '{metric}'. {_list_metrics({})}"
        pts = sorted(by_label[match])
        unit = pts[0][2] if pts else ""
        return f"{match}: " + ", ".join(f"{p} = {v:g}{unit}" for p, v, _ in pts)

    def _get_recent_news(args: dict) -> str:
        if not news:
            return "ไม่มีข่าวล่าสุด"
        return "\n".join(
            (f"[SEC 8-K material] {n.title}" if getattr(n, "material", False) else f"- {n.title}")
            for n in news
        )

    def _check_sec_filing(args: dict) -> str:
        concept = (args.get("concept") or "").strip()
        match = next((k for k in xbrl if k.lower() == concept.lower()), None) \
            or next((k for k in xbrl if concept.lower() in k.lower()), None)
        if match is None:
            avail = ", ".join(xbrl) if xbrl else "(ดึง XBRL ไม่ได้)"
            return f"ไม่มี concept '{concept}' ใน SEC XBRL. มีให้ดู: {avail}"
        pts = xbrl[match]
        return f"{match} (จาก 10-K จริง): " + ", ".join(f"{p} = {v:,.0f}" for p, v in pts)

    def _get_event_timeline(args: dict) -> str:
        # Phase 14: เหตุการณ์ material หลายปี (8-K + จุดพลิกพื้นฐาน) — ไว้เข้าใจ 'เรื่องราว'
        from src.agent.timeline import build_timeline
        events = build_timeline(ticker)[:20]
        if not events:
            return "ไม่มี timeline (ดึง EDGAR/XBRL ไม่ได้)"
        return "\n".join(f"{e['date']} [{e['kind']}] {e['detail']}" for e in events)

    return [
        ToolSpec("list_metrics", "List all financial metrics available for this company (call this first to see what you can inspect).",
                 {}, _list_metrics),
        ToolSpec("get_metric_trend", "Get the multi-year trend of one specific metric (e.g. 'Operating Margin', 'Revenue CAGR', 'ROIC'). Use exact names from list_metrics.",
                 {"metric": {"type": "STRING", "description": "metric label", "required": True}}, _get_metric_trend),
        ToolSpec("get_recent_news", "Get recent news headlines, including SEC 8-K material events (leadership change, M&A, earnings, restructuring).",
                 {}, _get_recent_news),
        ToolSpec("check_sec_filing", "Cross-check a raw figure straight from the company's SEC 10-K filing (e.g. 'Revenues', 'NetIncomeLoss', 'OperatingIncomeLoss', 'StockholdersEquity', 'Assets') — the authoritative source.",
                 {"concept": {"type": "STRING", "description": "us-gaap concept", "required": True}}, _check_sec_filing),
        ToolSpec("get_event_timeline", "Get the multi-year timeline of material events (SEC 8-K filings: leadership changes, restructuring, M&A) interleaved with fundamental inflection points (margin/revenue/cash-flow turns). Use this to understand how the business got to where it is.",
                 {}, _get_event_timeline),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI POLICY — สมองจริง (manual function-calling, คุม loop เอง)
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM = """You are a fundamental equity analyst investigating a company for a LONG-TERM
investor (holds for years, exits only when the thesis breaks — not on daily moves).

You have tools to inspect financial metrics, news, and raw SEC filings. INVESTIGATE like a real
analyst: start broad (what metrics exist?), then DRILL into whatever looks weak, surprising, or
thesis-relevant. Follow the evidence — if margins are falling, dig into why; cross-check a
suspicious number against the SEC filing. Call tools one at a time; use what you learn to decide
what to look at next. Do not call a tool just to fill space — stop investigating once you can
justify a conclusion.

When done, write your conclusion in THAI (2-5 sentences): is the business fundamentally strong or
weakening and WHERE, citing the specific numbers you found. This is RESEARCH to help the investor
decide — never a buy/sell or timing call."""


def _to_schema(params: dict):
    from google.genai import types
    if not params:
        return None
    props = {name: types.Schema(type=spec["type"], description=spec.get("description", ""))
             for name, spec in params.items()}
    required = [name for name, spec in params.items() if spec.get("required")]
    return types.Schema(type="OBJECT", properties=props, required=required)


class GeminiPolicy:
    """ห่อ google-genai function-calling แบบ manual — เก็บ conversation state ไว้เอง แล้ว
    แปลเป็น Decision ให้ loop. ไม่รู้จัก loop เลย (loop เป็นคนเรียก decide/force_conclude)."""

    def __init__(self, ticker: str, tools: list[ToolSpec], context: str = "",
                 model: str = "gemini-2.5-flash"):
        from google.genai import types
        self._types = types
        self._client = __import__("google.genai", fromlist=["Client"]).Client(
            api_key=os.environ["GEMINI_API_KEY"])
        self._model = model

        decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                           parameters=_to_schema(t.params)) for t in tools]
        self._tools = [types.Tool(function_declarations=decls)]
        self._cfg = types.GenerateContentConfig(
            tools=self._tools, system_instruction=_SYSTEM,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        prompt = f"Investigate {ticker}." + (f"\n\nContext:\n{context}" if context else "")
        self._contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        self._last_call: str | None = None

    def decide(self, observation: str | None) -> Decision:
        types = self._types
        if observation is not None and self._last_call is not None:
            # ป้อนผลของ tool ก่อนหน้ากลับเข้าไป (role=user, function_response part)
            self._contents.append(types.Content(role="user", parts=[types.Part(
                function_response=types.FunctionResponse(name=self._last_call,
                                                         response={"result": observation}))]))
        resp = self._client.models.generate_content(model=self._model, contents=self._contents,
                                                     config=self._cfg)
        self._contents.append(resp.candidates[0].content)   # เก็บ model turn ไว้ต่อบทสนทนา
        fcs = resp.function_calls
        if fcs:
            fc = fcs[0]
            self._last_call = fc.name
            return Decision(name=fc.name, args=dict(fc.args or {}))
        self._last_call = None
        return Decision(final=(resp.text or "").strip())

    def force_conclude(self) -> str:
        types = self._types
        self._contents.append(types.Content(role="user", parts=[types.Part(
            text="You have used your investigation budget. Give your THAI conclusion NOW from what you found.")]))
        # ปิด tool ในรอบสรุป -> บังคับให้ตอบเป็น text ไม่ใช่เรียก tool อีก
        cfg = types.GenerateContentConfig(system_instruction=_SYSTEM)
        resp = self._client.models.generate_content(model=self._model, contents=self._contents, config=cfg)
        return (resp.text or "").strip()


def investigate(ticker: str, context: str = "", max_steps: int = MAX_STEPS,
                persist: bool = True) -> Investigation:
    """สะดวก: สร้าง toolbox + GeminiPolicy แล้วขับ loop ให้เลย (ใช้จริง — ยิง Gemini).
    persist=True -> เก็บ transcript ล่าสุดลง DB (ไว้โชว์บนหน้า detail)."""
    ticker = ticker.upper()
    tools = build_toolbox(ticker)
    policy = GeminiPolicy(ticker, tools, context)
    inv = run_investigation(policy, tools, max_steps=max_steps, ticker=ticker)
    if persist:
        from src.agent.investigate_store import save_investigation
        save_investigation(inv)
    return inv


if __name__ == "__main__":
    # python -m src.agent.investigate SBUX   -> ให้ agent สืบเองแล้ว print transcript + ข้อสรุป
    import sys

    tk = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    inv = investigate(tk)
    print(f"=== Investigation: {tk} (stopped: {inv.stopped}, {len(inv.steps)} steps) ===\n")
    for i, s in enumerate(inv.steps, 1):
        print(f"[{i}] 🔧 {s.tool}({s.args})")
        obs = s.observation if len(s.observation) < 400 else s.observation[:400] + "..."
        print(f"    → {obs}\n")
    print("🧠 สรุป:")
    print(inv.conclusion)