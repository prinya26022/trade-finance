"""Phase 12 eval: เทียบเมตริกที่เราคำนวณกับ SEC XBRL (ground truth อิสระจาก yfinance).
ทั้งหมด offline — mock get_annual_series ไม่แตะ EDGAR/network จริง."""
import json
from types import SimpleNamespace

from src.evals.check_xbrl_accuracy import check_xbrl_accuracy, _within_tolerance


def _fake_fundamentals(period="FY2025", roe=25.0,
                        net_margin=None, operating_margin=None):
    return SimpleNamespace(
        period=period,
        roe=roe,
        net_margin_series=net_margin or [("FY2025", 20.0), ("FY2024", 18.0)],
        operating_margin_series=operating_margin or [("FY2025", 25.0), ("FY2024", 22.0)],
    )


def _fake_xbrl_series():
    """Revenue 1000/900, NetIncome 200/162, OperatingIncome 250/198 -> margin 20%/25% (FY25),
    18%/22% (FY24) — ตรงกับ _fake_fundamentals() เป๊ะ (ควรผ่าน tolerance ทุกตัว)."""
    return {
        "Revenues": [("FY2025", 1000.0), ("FY2024", 900.0)],
        "NetIncomeLoss": [("FY2025", 200.0), ("FY2024", 162.0)],
        "OperatingIncomeLoss": [("FY2025", 250.0), ("FY2024", 198.0)],
        "StockholdersEquity": [("FY2025", 800.0), ("FY2024", 700.0)],
    }


def test_within_tolerance_boundaries():
    assert _within_tolerance(20.0, 22.0) is True     # ต่างกัน 2pp < TOLERANCE_ABS (3.0)
    assert _within_tolerance(20.0, -20.0) is False    # ผิดชัดเจน (สลับเครื่องหมาย)


def test_golden_match(monkeypatch):
    """ตัวเลขของเราตรงกับ XBRL เป๊ะ (คำนวณมาให้ตรงกัน) -> accuracy 100%."""
    monkeypatch.setattr(
        "src.evals.check_xbrl_accuracy.get_annual_series",
        lambda ticker: _fake_xbrl_series(),
    )
    # ROE = NetIncome/Equity FY2025 = 200/800*100 = 25.0 -> ตรงกับ roe=25.0 ที่ตั้งไว้
    result = check_xbrl_accuracy(_fake_fundamentals(), "TEST")

    assert result["accuracy"] == 1.0
    assert len(result["checks"]) == 5   # net margin x2 + operating margin x2 + ROE x1
    assert all(c["within_tolerance"] for c in result["checks"])
    json.dumps(result)   # ต้อง serialize ได้ (save_analysis เก็บก้อนนี้ตรงๆ)


def test_flags_mismatch(monkeypatch):
    """ถ้าเมตริกของเราเพี้ยนหนักจาก XBRL จริง -> accuracy ต่ำลง, เห็นตัวที่ fail ชัดเจน."""
    monkeypatch.setattr(
        "src.evals.check_xbrl_accuracy.get_annual_series",
        lambda ticker: _fake_xbrl_series(),
    )
    fund = _fake_fundamentals(net_margin=[("FY2025", 90.0), ("FY2024", 18.0)])  # FY2025 ผิดชัดเจน (จริง 20)
    result = check_xbrl_accuracy(fund, "TEST")

    assert result["accuracy"] < 1.0
    bad = next(c for c in result["checks"] if c["metric"] == "Net Margin (FY2025)")
    assert bad["within_tolerance"] is False


def _fake_xbrl_with_derived():
    """เพิ่ม concept สำหรับ FCF/NOPAT/ROIC ให้คำนวณ reference ได้ (Phase 19.1):
    FCF = CFO(300) − Capex(100) = 200; tax rate = 40/200 = 20%; NOPAT = OpIncome(250)×0.8 = 200;
    invested = debt(300+0) + equity(800) − cash(100) = 1000; ROIC = 200/1000 = 20%."""
    base = _fake_xbrl_series()
    base.update({
        "IncomeTaxExpense": [("FY2025", 40.0)],
        "PretaxIncome": [("FY2025", 200.0)],
        "OperatingCashFlow": [("FY2025", 300.0)],
        "Capex": [("FY2025", 100.0)],
        "CashAndEquivalents": [("FY2025", 100.0)],
        "LongTermDebtNoncurrent": [("FY2025", 300.0)],
    })
    return base


def test_ground_truth_fcf_nopat_roic(monkeypatch):
    """Phase 19.1: FCF/NOPAT/ROIC เทียบ raw XBRL — ค่าที่คำนวณให้ตรงต้องผ่าน tolerance."""
    monkeypatch.setattr(
        "src.evals.check_xbrl_accuracy.get_annual_series",
        lambda ticker: _fake_xbrl_with_derived(),
    )
    fund = _fake_fundamentals()
    fund.fcf_series = [("FY2025", 200.0)]   # = CFO−Capex reference
    fund.nopat = 200.0                       # = OpIncome×(1−taxrate)
    fund.roic = 20.0                         # = NOPAT/invested
    fund.net_debt = 999.0                    # ตั้งใจให้ผิด — ต้อง 'ไม่' ถูกเช็ค (Net Debt ไม่อยู่ใน eval)
    result = check_xbrl_accuracy(fund, "TEST")

    metrics = {c["metric"] for c in result["checks"]}
    assert "FCF (FY2025)" in metrics
    assert "NOPAT (FY2025)" in metrics
    assert "ROIC (FY2025)" in metrics
    assert not any("Net Debt" in m for m in metrics)   # net-debt ถูกกันออกโดยตั้งใจ (definitional)
    assert result["accuracy"] == 1.0                    # ทุกตัวตรง -> 100% (net_debt ผิดไม่นับ)


def test_no_xbrl_data_returns_none_accuracy(monkeypatch):
    """EDGAR ล่ม/ไม่พบ CIK -> get_annual_series คืน {} -> accuracy None ไม่ raise."""
    monkeypatch.setattr("src.evals.check_xbrl_accuracy.get_annual_series", lambda ticker: {})
    result = check_xbrl_accuracy(_fake_fundamentals(), "UNKNOWN")

    assert result["accuracy"] is None
    assert result["checks"] == []


def test_missing_period_overlap_skipped_not_crash(monkeypatch):
    """ปีที่เรามีไม่ตรงกับปีใน XBRL เลย (เช่น ticker ใหม่/เพิ่งเริ่มยื่น) -> ข้ามเงียบๆ ไม่ crash."""
    monkeypatch.setattr(
        "src.evals.check_xbrl_accuracy.get_annual_series",
        lambda ticker: {
            "Revenues": [("FY2020", 1000.0)],
            "NetIncomeLoss": [("FY2020", 200.0)],
            "OperatingIncomeLoss": [("FY2020", 250.0)],
            "StockholdersEquity": [("FY2020", 800.0)],
        },
    )
    result = check_xbrl_accuracy(_fake_fundamentals(period="FY2025"), "TEST")   # ไม่มีปีทับกันเลย
    assert result["accuracy"] is None
    assert result["checks"] == []