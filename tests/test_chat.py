"""Portfolio chat toolbox (Phase 25) — offline, ไม่แตะ Gemini/network เลย. ทดสอบแค่ layer ที่
ประกอบข้อความจาก DB ที่คำนวณไว้แล้ว (เหมือน tools ที่ agent จะเรียก) — ไม่ทดสอบ GeminiPolicy/ask()
ตรงๆ (ต้องใช้ GEMINI_API_KEY จริง, อยู่นอกขอบเขต offline test).
"""
from src.agent.chat import build_portfolio_toolbox, _fmt_health, _render_history


def _tool(name):
    tools = build_portfolio_toolbox()
    return next(t for t in tools if t.name == name)


def _analysis(ticker, price=100.0, health=None, valuation=None, thesis_summary=""):
    return {
        "ticker": ticker,
        "price": price,
        "summary": {
            "fundamental_strength": "strong", "valuation_view": "fair", "sentiment": "neutral",
            "beginner_summary": thesis_summary,
        },
        "health": health,
        "valuation": valuation,
    }


# --- _fmt_health ---

def test_fmt_health_none():
    assert "ไม่ได้" in _fmt_health(None)


def test_fmt_health_excluded_shows_reason():
    out = _fmt_health({"score": None, "reasons": ["ข้อมูลไม่พอ"]})
    assert "ข้อมูลไม่พอ" in out


def test_fmt_health_scored():
    out = _fmt_health({"score": 7.9, "max": 11.0, "tier": "strong"})
    assert "7.9/11" in out and "strong" in out


# --- _render_history ---

def test_render_history_empty():
    assert _render_history([]) == ""


def test_render_history_formats_turns():
    out = _render_history([{"role": "user", "text": "Q1"}, {"role": "assistant", "text": "A1"}])
    assert "คุณ: Q1" in out
    assert "ผู้ช่วย: A1" in out


# --- list_portfolio ---

def test_list_portfolio_empty(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [])
    assert "ว่าง" in _tool("list_portfolio").fn({})


def test_list_portfolio_shows_status_and_health(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [
        {"ticker": "AAPL", "status": "holding"},
        {"ticker": "SBUX", "status": "watching"},
    ])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [
        _analysis("AAPL", health={"score": 7.0, "max": 11.0, "tier": "ok"}),
    ])
    out = _tool("list_portfolio").fn({})
    assert "AAPL: ถืออยู่, health 7.0/11" in out
    assert "SBUX: จับตา, ยังไม่เคยวิเคราะห์" in out


# --- get_ticker_summary ---

def test_get_ticker_summary_unknown_ticker(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [])
    out = _tool("get_ticker_summary").fn({"ticker": "ZZZZ"})
    assert "ไม่มีผลวิเคราะห์" in out


def test_get_ticker_summary_includes_thesis_and_valuation(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [{"ticker": "DUOL", "status": "holding"}])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [
        _analysis("DUOL", price=350.0,
                  health={"score": 9.9, "max": 11.0, "tier": "strong", "reasons": ["พื้นฐานแข็งมาก"]},
                  valuation={"implied_growth": 3.6, "realistic_growth": 6.2, "gap": -2.6},
                  thesis_summary="ธุรกิจแข็งแรง"),
    ])
    monkeypatch.setattr("src.thesis.store.get_thesis", lambda t: {"thesis": "ถือเพราะ moat แข็ง"})
    out = _tool("get_ticker_summary").fn({"ticker": "duol"})   # lowercase -> ต้อง upper เอง
    assert "DUOL @ $350.0" in out
    assert "9.9/11" in out
    assert "พื้นฐานแข็งมาก" in out
    assert "gap -2.6pp" in out
    assert "ถือเพราะ moat แข็ง" in out
    assert "ธุรกิจแข็งแรง" in out


# --- get_ticker_changes ---

def test_get_ticker_changes_none(monkeypatch):
    monkeypatch.setattr("src.agent.changes.detect_changes", lambda t: {"ticker": t, "changes": []})
    out = _tool("get_ticker_changes").fn({"ticker": "AAPL"})
    assert "ไม่มีอะไรสำคัญเปลี่ยน" in out


def test_get_ticker_changes_with_items(monkeypatch):
    monkeypatch.setattr("src.agent.changes.detect_changes", lambda t: {
        "ticker": t, "changes": [{"type": "strength_flip", "detail": "พื้นฐานเปลี่ยน: strong -> mixed", "severity": "alert"}],
    })
    out = _tool("get_ticker_changes").fn({"ticker": "AAPL"})
    assert "[alert]" in out and "พื้นฐานเปลี่ยน" in out


# --- compare_tickers ---

def test_compare_tickers_requires_two():
    out = _tool("compare_tickers").fn({"tickers": "AAPL"})
    assert "อย่างน้อย 2" in out


def test_compare_tickers_side_by_side(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [
        _analysis("MSFT", health={"score": 7.9, "max": 11.0, "tier": "strong"}, valuation={"gap": 9.6}),
        _analysis("GOOGL", health={"score": 8.1, "max": 11.0, "tier": "strong"}, valuation={"gap": 9.3}),
    ])
    out = _tool("compare_tickers").fn({"tickers": "MSFT, GOOGL"})
    assert "MSFT: health 7.9/11" in out and "gap +9.6pp" in out
    assert "GOOGL: health 8.1/11" in out and "gap +9.3pp" in out


def test_compare_tickers_missing_one(monkeypatch):
    monkeypatch.setattr("src.watchlist.store.list_all", lambda: [])
    monkeypatch.setattr("src.history.store.latest_per_ticker", lambda: [])
    out = _tool("compare_tickers").fn({"tickers": "MSFT,ZZZZ"})
    assert "ZZZZ: ไม่มีข้อมูล" in out


# --- get_performance ---

def test_get_performance_no_holdings(monkeypatch):
    monkeypatch.setattr("src.agent.performance.portfolio_edge", lambda: {
        "total_positions": 0, "positions": [], "beating_benchmark": 0, "benchmark": "VT", "total_return": None,
    })
    out = _tool("get_performance").fn({})
    assert "ยังไม่มี holding" in out


def test_get_performance_with_holdings(monkeypatch):
    monkeypatch.setattr("src.agent.performance.portfolio_edge", lambda: {
        "total_positions": 1, "beating_benchmark": 1, "benchmark": "VT", "total_return": 12.5,
        "positions": [{"ticker": "DUOL", "your_return": 15.0, "benchmark": "VT",
                       "benchmark_return": 8.0, "edge": 7.0, "holding_days": 60}],
    })
    out = _tool("get_performance").fn({})
    assert "ชนะ VT 1/1 ตัว" in out
    assert "DUOL: คุณ +15.0% vs VT +8.0% (edge +7.0pp), ถือมา 60 วัน" in out