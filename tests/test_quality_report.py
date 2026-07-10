"""build_quality_report (Phase 4 extraction + Phase 12 xbrl) — alert-only: เงียบถ้าปกติ,
flag ทั้ง 2 ชั้น eval แยกกันถ้าต่ำกว่าเกณฑ์. offline ล้วน (monkeypatch latest_per_ticker)."""
from src.agent.report import build_quality_report


def _row(ticker, extraction=None, xbrl=None):
    return {"ticker": ticker, "extraction": extraction, "xbrl": xbrl}


def _eval(accuracy, metric="ROE", ours=10.0, ref=50.0, ok=False):
    return {"accuracy": accuracy, "checks": [{"metric": metric, "ours": ours, "reference": ref, "within_tolerance": ok}]}


def test_silent_when_all_healthy(monkeypatch):
    rows = [_row("AAPL", extraction=_eval(1.0, ok=True), xbrl=_eval(1.0, ok=True))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    assert build_quality_report() is None


def test_silent_when_no_eval_data(monkeypatch):
    # ticker ที่ไม่มี extraction/xbrl เลย (เช่น crypto) -> ไม่ error, ไม่ flag
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: [_row("BTC")])
    assert build_quality_report() is None


def test_flags_low_extraction_accuracy(monkeypatch):
    rows = [_row("SBUX", extraction=_eval(0.5))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report()
    assert report is not None
    assert "SBUX" in report
    assert "extraction accuracy 50%" in report


def test_flags_low_xbrl_accuracy_separately_labeled(monkeypatch):
    """xbrl ต้องมีป้ายบอกว่าเป็น 'SEC ground truth' แยกจาก extraction ธรรมดา."""
    rows = [_row("MSFT", xbrl=_eval(0.4))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report()
    assert report is not None
    assert "MSFT" in report
    assert "SEC ground truth" in report


def test_flags_both_layers_for_same_ticker(monkeypatch):
    rows = [_row("NVDA", extraction=_eval(0.6), xbrl=_eval(0.5))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report()
    assert report.count("NVDA") == 2   # 1 บรรทัดต่อชั้น eval