"""build_quality_report (Phase 4 extraction + Phase 12 xbrl + Phase 38 ความนิ่งของข้อมูล) —
alert-only: เงียบถ้าปกติ, flag แต่ละชั้น eval แยกกันถ้าต่ำกว่าเกณฑ์. offline ล้วน.

rows=[] ทุกที่ที่ไม่ได้ทดสอบชั้นความนิ่ง — ไม่ใช่แค่ให้ผ่าน แต่เพราะ default ของมันคือ all_rows()
ซึ่งอ่าน data/watchlist.db ของจริง เทสต์ที่ปล่อยไว้จะขึ้น/ลงตามข้อมูลจริงของเจ้าของ."""
from src.agent.report import build_quality_report


def _row(ticker, extraction=None, xbrl=None):
    return {"ticker": ticker, "extraction": extraction, "xbrl": xbrl}


def _eval(accuracy, metric="ROE", ours=10.0, ref=50.0, ok=False):
    return {"accuracy": accuracy, "checks": [{"metric": metric, "ours": ours, "reference": ref, "within_tolerance": ok}]}


def test_silent_when_all_healthy(monkeypatch):
    rows = [_row("AAPL", extraction=_eval(1.0, ok=True), xbrl=_eval(1.0, ok=True))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    assert build_quality_report(rows=[]) is None


def test_silent_when_no_eval_data(monkeypatch):
    # ticker ที่ไม่มี extraction/xbrl เลย (เช่น crypto) -> ไม่ error, ไม่ flag
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: [_row("BTC")])
    assert build_quality_report(rows=[]) is None


def test_flags_low_extraction_accuracy(monkeypatch):
    rows = [_row("SBUX", extraction=_eval(0.5))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report(rows=[])
    assert report is not None
    assert "SBUX" in report
    assert "extraction accuracy 50%" in report


def test_flags_low_xbrl_accuracy_separately_labeled(monkeypatch):
    """xbrl ต้องมีป้ายบอกว่าเป็น 'SEC ground truth' แยกจาก extraction ธรรมดา."""
    rows = [_row("MSFT", xbrl=_eval(0.4))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report(rows=[])
    assert report is not None
    assert "MSFT" in report
    assert "SEC ground truth" in report


def test_flags_both_layers_for_same_ticker(monkeypatch):
    rows = [_row("NVDA", extraction=_eval(0.6), xbrl=_eval(0.5))]
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: rows)
    report = build_quality_report(rows=[])
    assert report.count("NVDA") == 2   # 1 บรรทัดต่อชั้น eval

def test_flags_a_metric_that_keeps_vanishing(monkeypatch):
    """Phase 38: ค่าที่ได้มา *ถูก* ทุกครั้ง (accuracy ผ่าน) แต่บางวันไม่ได้มาเลย — คนละอาการกับ
    accuracy ต่ำ แต่ปลายทางเดียวกันคือคะแนนขยับโดยที่บริษัทไม่ได้เปลี่ยน (ASML CFO ของจริง)."""
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: [])

    def _hist(day, labels, computable):
        return {"ticker": "ASML", "run_at": f"{day}T17:00:00",
                "facts": [{"label": n, "value": 1.0, "unit": "x", "period": "FY2025"} for n in labels],
                "health": {"score": 7.0, "max": 11.0,
                           "fundamental": {"computable": computable, "criteria": []},
                           "valuation": {"score": 1.0}}}

    rows = [_hist("2026-08-10", ["Revenue", "CFO"], 8),
            _hist("2026-08-11", ["Revenue"], 7),
            _hist("2026-08-12", ["Revenue", "CFO"], 8)]

    report = build_quality_report(rows=rows)

    assert report is not None
    assert "ASML" in report and "CFO" in report


def test_stays_silent_when_the_gap_never_reached_the_score(monkeypatch):
    """'หายจาก DATA เฉยๆ' ไม่คุ้มกับการรบกวนทุกวัน — ช่องนี้เป็น alert-only ตามหลักของโปรเจกต์."""
    monkeypatch.setattr("src.agent.report.latest_per_ticker", lambda: [])

    def _hist(day, labels):
        return {"ticker": "A", "run_at": f"{day}T17:00:00",
                "facts": [{"label": n, "value": 1.0, "unit": "x", "period": "FY2025"} for n in labels],
                "health": {"score": 9.0, "max": 11.0,
                           "fundamental": {"computable": 8, "criteria": []},
                           "valuation": {"score": 2.0}}}

    rows = [_hist("2026-08-10", ["Revenue", "P/S"]),
            _hist("2026-08-11", ["Revenue"]),
            _hist("2026-08-12", ["Revenue", "P/S"])]

    assert build_quality_report(rows=rows) is None
