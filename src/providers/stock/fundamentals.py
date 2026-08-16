import yfinance as yf
import pandas as pd
from dataclasses import dataclass, field
from src.domain.interfaces import Fundamentals, FundamentalsProvider, Fact
from src.domain.series import cagr_pct


# ─────────────────────────────────────────────────────────────────────────────
# DATA SHAPE
# เก็บทั้ง "ค่าล่าสุด/TTM" (สเกลาร์) และ "อนุกรมหลายปี" (series) แยกกัน
# series = list ของ (ป้ายงวด, ค่า) เช่น [("FY2025", 0.32), ("FY2024", 0.31), ...]
# ให้ LLM เห็นตัวเลขรายปีเอง แล้วตัดสิน trend เอง (grounded กว่าให้เราตีป้ายให้)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StockFundamentals(Fundamentals):
    period: str = "N/A"

    # --- fix 2026-08: สกุลเงินของ 'งบ' กับของ 'ราคา' ไม่จำเป็นต้องเป็นตัวเดียวกัน ---
    # หุ้นต่างชาติที่ซื้อขายเป็น ADR ยื่นงบเป็นสกุลบ้านเกิด แต่ราคา/market cap เป็น USD
    # (ASML: EUR/USD, TSM: TWD/USD) — ทุกอัตราส่วนที่เอา 'ฝั่งราคา' หารด้วย 'ฝั่งงบ' จึงไร้
    # ความหมาย และเดิมระบบไม่รู้เรื่องนี้เลย จึงติดป้ายทุกอย่างเป็น USD หมด
    financial_currency: str | None = None   # info['financialCurrency'] — สกุลของงบการเงิน
    price_currency: str | None = None       # info['currency'] — สกุลของราคาที่ซื้อขาย

    # --- ความสามารถทำกำไร / ผลตอบแทนต่อทุน ---
    revenue: float | None = None
    free_cash_flow: float | None = None
    fcf_margin: float | None = None          # FCF / Revenue (%)
    roic: float | None = None                # NOPAT / invested capital (%)
    roe: float | None = None                 # Net Income / equity (%)
    revenue_cagr: float | None = None        # CAGR ตลอดช่วงที่มีข้อมูล (%)

    # --- งบดุล / ความปลอดภัย ---
    net_debt_to_ebitda: float | None = None  # เกิน 3 เท่าเริ่มเสี่ยง
    interest_coverage: float | None = None   # EBIT / ดอกเบี้ย
    current_ratio: float | None = None

    # --- Phase 18: ดิบสำหรับ Piotroski data-gate + reverse-DCF (CAPM/sustainable growth) ---
    net_income: float | None = None          # scoring_spec.md เกณฑ์ #3 (accruals: CFO > Net Income)
    cfo: float | None = None                 # Operating Cash Flow — คู่กับ net_income เช็คคุณภาพกำไร
    net_debt: float | None = None            # ดอลลาร์ดิบ (ไม่ใช่ ratio) — ใช้ผูก EV = Market Cap + Net Debt
    capex: float | None = None               # เข้า reinvestment_rate = (Capex − D&A + ΔNWC) / NOPAT
    depreciation_amortization: float | None = None
    nwc_change: float | None = None          # Change In Working Capital
    nopat: float | None = None               # จาก ROIC calc — เป็นตัวหารของ reinvestment_rate
    invested_capital: float | None = None    # จาก ROIC calc
    beta: float | None = None                # β หุ้น — เข้า CAPM WACC (Rf + β×ERP)

    # --- ธนาคาร (Phase 33.3) — กรอบเดิมอ่านแบงก์ไม่ออกเลย ---
    # ROIC/Operating Margin/FCF/Net Debt-EBITDA/Current Ratio ไม่มีความหมายกับธนาคาร (เงินฝากคือ
    # วัตถุดิบ ไม่ใช่หนี้; การปล่อยสินเชื่อไหลผ่านงบกระแสเงินสดจน FCF ติดลบมหาศาลเป็นเรื่องปกติ)
    # -> JPM คำนวณเกณฑ์ได้แค่ 4/8 แล้วตกด่านข้อมูล กลายเป็น 'ประเมินไม่ได้' ทุกวันตลอดมา.
    # 4 ตัวนี้คือสิ่งที่ 'คำนวณได้จริงจากข้อมูลที่มี' — ไม่ใช่ชุดที่นักวิเคราะห์แบงก์อยากได้ทั้งหมด
    # (CET1 / NPL / provisions ไม่มีใน yfinance) แต่ครอบคลุมสามขาหลัก: คุณภาพกำไร ทุน และต้นทุน
    net_interest_income: float | None = None   # ดอกเบี้ยรับสุทธิ — ตัวชี้ว่าเป็นธุรกิจธนาคารจริง
    tangible_book_value: float | None = None
    rotce: float | None = None            # Net Income / Tangible Book Value (%) — เมตริกคุณภาพหลักของแบงก์
    equity_to_assets: float | None = None  # ทุน/สินทรัพย์ (%) — ตัวแทนหยาบของ CET1 ที่ไม่มีให้ดึง
    nii_to_assets: float | None = None     # NII/สินทรัพย์ (%) — ตัวแทนหยาบของ NIM (ตัวหารควรเป็น
                                           # earning assets แต่ไม่มี จึงใช้สินทรัพย์รวมและตั้งชื่อตามจริง)
    cost_income_ratio: float | None = None  # (รายได้ − กำไรก่อนภาษี)/รายได้ (%) = ต้นทุนรวม+ค่าเผื่อหนี้สูญ
                                            # ต่อรายได้ — ไม่ใช่ efficiency ratio แท้ (ไม่มี non-interest expense)

    # --- Red flags (ด่าน 8) ---
    goodwill: float | None = None            # ถ้าเยอะระวัง write-off
    goodwill_pct_assets: float | None = None # goodwill เป็น % ของสินทรัพย์รวม

    # --- Valuation (ณ ปัจจุบัน, จาก info) ---
    pe: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    peg: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    fcf_yield: float | None = None           # FCF / market cap (%)
    market_cap: float | None = None
    avg_volume: float | None = None          # สภาพคล่อง (ด่าน 0)

    # --- อนุกรมหลายปี (ดู trend) ---
    gross_margin_series: list[tuple[str, float]] = field(default_factory=list)
    operating_margin_series: list[tuple[str, float]] = field(default_factory=list)
    net_margin_series: list[tuple[str, float]] = field(default_factory=list)
    share_count_series: list[tuple[str, float]] = field(default_factory=list)
    fcf_series: list[tuple[str, float]] = field(default_factory=list)          # FCF trend หลายปี
    # Phase 36: CAGR ของ FCF ตลอดประวัติที่ยื่น ก.ล.ต. จริง (ยาวกว่า 4 ปีที่ yfinance ให้มาก) —
    # ส่งเป็น "ค่าเดียวที่คำนวณแล้ว" ไม่ใช่ series ยาว เพราะทุก Fact ถูกแปะเข้า prompt ตรงๆ
    # (data_block) การเพิ่ม 15 บรรทัดต่อหุ้นต่อวันคือการเปลี่ยนโจทย์ที่โมเดลอ่านโดยไม่ตั้งใจ
    fcf_cagr_long: float | None = None            # %/ปี
    fcf_long_window: str | None = None            # "FY2007-FY2025"
    fcf_long_years: int | None = None
    dso_series: list[tuple[str, float]] = field(default_factory=list)          # วันเก็บหนี้ (พุ่ง = red flag)
    inventory_pct_series: list[tuple[str, float]] = field(default_factory=list)  # inventory เทียบยอดขาย (บวม = red flag)

    # --- Phase 18: อนุกรมหลายปีเพิ่ม — scoring_spec.md เกณฑ์ #2/#5/#6 ต้องเช็ค trend YoY ไม่ใช่แค่ level ---
    roe_series: list[tuple[str, float]] = field(default_factory=list)
    net_debt_to_ebitda_series: list[tuple[str, float]] = field(default_factory=list)
    current_ratio_series: list[tuple[str, float]] = field(default_factory=list)

    # --- valuation_guard_growth_lens.md: rev_growth_recent (ปีล่าสุดจริง ไม่ใช่ CAGR หลายปี) ---
    revenue_series: list[tuple[str, float]] = field(default_factory=list)

    # NII ต้องเป็นสัดส่วนที่มีนัยของรายได้ ไม่ใช่แค่ 'มีบรรทัดดอกเบี้ยรับ' — บริษัททั่วไปที่มีเงินสด
    # กองใหญ่ก็รายงานดอกเบี้ยรับได้ แต่ไม่ใช่ธนาคาร
    BANK_NII_SHARE_MIN = 0.20

    @property
    def is_bank(self) -> bool:
        """ใช้กรอบคะแนนของธนาคารไหม — ตัดสินจาก 'มีรายได้ดอกเบี้ยสุทธิเป็นสัดส่วนหลักของรายได้'
        ไม่ใช่จาก sector string เพราะ (1) sector ไม่ได้ติดไปกับ facts ที่เก็บลง DB จึงใช้ตอน
        backfill ไม่ได้ (2) 'Financial Services' รวมประกัน/บลจ./บัตรเครดิต ซึ่งอ่านด้วยกรอบ
        ธนาคารไม่ได้เหมือนกัน. เงื่อนไขนี้ตรวจจาก facts ล้วน = พาธเดียวกันทั้งตอนวิเคราะห์สดและ
        ตอนคำนวณย้อนหลัง (หลักเดียวกับ currency_mismatch)."""
        if self.net_interest_income is None or not self.revenue:
            return False
        return (self.net_interest_income / self.revenue) >= self.BANK_NII_SHARE_MIN

    @property
    def currency_mismatch(self) -> bool:
        """งบกับราคาคนละสกุล — อัตราส่วนข้ามฝั่งทั้งหมดใช้ไม่ได้ (ดู to_facts/reverse_dcf)."""
        return bool(self.financial_currency and self.price_currency
                    and self.financial_currency != self.price_currency)

    def to_facts(self) -> list[Fact]:
        facts: list[Fact] = []
        # ป้ายหน่วยต้องบอกความจริง: ตัวเลขจากงบ = สกุลของงบ, ตัวเลขจากราคา = สกุลที่ซื้อขาย
        # (เดิมฮาร์ดโค้ด 'USD' ทั้งหมด -> DATA บอกว่า TSM มีรายได้ 4.44e12 USD ซึ่งผิดล้วนๆ
        #  และเชิญชวนให้ทั้งคนและ LLM หารกับ Market Cap ที่เป็น USD จริง)
        stmt_ccy = self.financial_currency or "USD"
        price_ccy = self.price_currency or "USD"
        cross_currency = self.currency_mismatch

        # (1) สเกลาร์: (label, value, unit, period) — ข้ามตัวที่เป็น None (ห้ามปลอม 0.0)
        # period ต้องตรงกับ 'ฐานเวลาจริง' ของค่านั้น: Revenue/FCF Margin/FCF Yield คำนวณจาก
        # info['totalRevenue']/info['freeCashflow'] ซึ่งเป็น TTM (ล่าสุด 12 เดือน) ไม่ใช่สิ้นปีงบ
        # (self.period) — ติดป้าย FY ผิดจะทำให้ LLM เห็นค่า TTM (เช่น FCF ติดลบช่วงแย่ล่าสุด)
        # ข้าง ๆ FCF series แบบ FY (เช่น FY2025 บวก) แล้วงงว่าตัวเลขขัดแย้งกันเอง (ลด confidence)
        scalars = [
            ("Revenue", self.revenue, stmt_ccy, "TTM"),
            ("FCF Margin", self.fcf_margin, "%", "TTM"),
            ("ROIC", self.roic, "%", self.period),
            ("ROE", self.roe, "%", self.period),
            ("Revenue CAGR", self.revenue_cagr, "%", self.period),
            ("Net Debt / EBITDA", self.net_debt_to_ebitda, "x", self.period),
            ("Interest Coverage", self.interest_coverage, "x", self.period),
            ("Current Ratio", self.current_ratio, "x", self.period),
            ("P/E", self.pe, "x", self.period),
            ("Forward P/E", self.forward_pe, "x", self.period),
            # อัตราส่วนที่เอา 'ฝั่งราคา' หารด้วย 'ฝั่งงบ' — ไร้ความหมายเมื่อคนละสกุล จึงตัดทิ้ง
            # ทั้งชุด (ค่าที่ผิดแบบดูน่าเชื่อแย่กว่าไม่มีค่า: TSM เคยโชว์ P/S 0.47x = 'ถูกมาก'
            # ทั้งที่เป็นการเอา market cap สกุล USD หารรายได้สกุล TWD). P/E / Forward P/E / PEG
            # ไม่โดนตัด เพราะ Yahoo คิด EPS ให้อยู่ฝั่งเดียวกับราคาแล้ว (ตรวจกับ TSM/ASML จริง)
            ("EV/EBITDA", None if cross_currency else self.ev_ebitda, "x", self.period),
            ("PEG", self.peg, "x", self.period),
            ("P/B", None if cross_currency else self.price_to_book, "x", self.period),
            ("P/S", None if cross_currency else self.price_to_sales, "x", self.period),
            ("FCF Yield", None if cross_currency else self.fcf_yield, "%", "TTM"),
            ("Market Cap", self.market_cap, price_ccy, self.period),
            ("Avg Daily Volume", self.avg_volume, "shares", self.period),
            ("Goodwill", self.goodwill, stmt_ccy, self.period),
            ("Goodwill % Assets", self.goodwill_pct_assets, "%", self.period),
            ("Net Income", self.net_income, stmt_ccy, self.period),
            ("CFO", self.cfo, stmt_ccy, self.period),
            ("Net Debt", self.net_debt, stmt_ccy, self.period),
            ("Capex", self.capex, stmt_ccy, self.period),
            ("D&A", self.depreciation_amortization, stmt_ccy, self.period),
            ("NWC Change", self.nwc_change, stmt_ccy, self.period),
            ("NOPAT", self.nopat, stmt_ccy, self.period),
            ("Invested Capital", self.invested_capital, stmt_ccy, self.period),
            ("Beta", self.beta, "x", self.period),
        ]
        facts += [
            Fact(label, value, unit, period)
            for label, value, unit, period in scalars
            if value is not None
        ]

        # (2) อนุกรม: แตกเป็น 1 Fact ต่อปี (period = ป้ายงวดของปีนั้น)
        series = [
            ("Gross Margin", self.gross_margin_series, "%"),
            ("Operating Margin", self.operating_margin_series, "%"),
            ("Net Margin", self.net_margin_series, "%"),
            ("Diluted Shares", self.share_count_series, "shares"),
            ("Free Cash Flow", self.fcf_series, stmt_ccy),
            ("DSO", self.dso_series, "days"),
            ("Inventory % Revenue", self.inventory_pct_series, "%"),
            ("ROE", self.roe_series, "%"),
            ("Net Debt / EBITDA", self.net_debt_to_ebitda_series, "x"),
            ("Current Ratio", self.current_ratio_series, "x"),
            ("Revenue FY", self.revenue_series, stmt_ccy),
        ]
        for label, points, unit in series:
            for period_label, value in points:
                facts.append(Fact(label, value, unit, period_label))

        # Phase 36: หนึ่งบรรทัด ไม่ใช่ทั้ง series — เพราะ Fact ทุกตัวถูกแปะเข้า prompt ตรงๆ.
        # เก็บเป็น Fact (ไม่ใช่แค่ attribute) เพื่อให้พาธที่ประกอบ duck object จาก facts ที่เก็บใน DB
        # (health.py::_build_duck_fundamentals) เห็นค่าเดียวกันเป๊ะกับพาธที่มี object จริง —
        # สองพาธให้คำตอบต่างกันคือบั๊กที่โปรเจกต์นี้เจอซ้ำแล้วซ้ำอีก (33.3, 34)
        if self.fcf_cagr_long is not None and self.fcf_long_window:
            facts.append(Fact("FCF CAGR (long-run)", self.fcf_cagr_long, "%", self.fcf_long_window))

        # (3) เมตริกของธนาคาร — ใส่เฉพาะเมื่อเป็นธนาคารจริง ไม่งั้นหุ้นทั่วไปจะมีบรรทัดที่ไม่มี
        #     ความหมายโผล่มา และการมีอยู่ของ 'Net Interest Income' คือสัญญาณที่ health ใช้เลือกกรอบ
        if self.is_bank:
            facts += [
                Fact(label, value, unit, self.period)
                for label, value, unit in [
                    ("Net Interest Income", self.net_interest_income, stmt_ccy),
                    ("Tangible Book Value", self.tangible_book_value, stmt_ccy),
                    ("ROTCE", self.rotce, "%"),
                    ("Equity / Assets", self.equity_to_assets, "%"),
                    ("NII / Assets", self.nii_to_assets, "%"),
                    ("Cost+Provision / Revenue", self.cost_income_ratio, "%"),
                ]
                if value is not None
            ]

        facts += self._derived_facts()
        return facts

    def _derived_facts(self) -> list[Fact]:
        """ตัวเลขที่ 'ต้องเอาสองบรรทัดมาชนกันถึงจะเห็น' — คำนวณให้ตรงๆ แทนที่จะหวังว่า LLM จะสังเกตเอง.

        มาจากเคสจริง (DUOL รอบ 2026-08): Net Margin 39.91% แต่ Operating Margin แค่ 13.07% =
        กำไรสุทธิถูกดันด้วยรายการที่ไม่ใช่การดำเนินงาน ทำให้ P/E 15.4x 'ดูถูก' ทั้งที่ธุรกิจไม่ได้
        ทำกำไรขนาดนั้น. ทั้งสองเลขอยู่ใน DATA อยู่แล้ว และ checklist ข้อ 'CFO เทียบ Net Income'
        ก็เขียนไว้ชัดแล้ว — แต่โมเดลที่รันรายวันยังสรุปว่า 'cheap' อยู่ดี. บทเรียนคือ **อย่าฝาก
        ข้อสรุปสำคัญไว้กับการที่ LLM จะเอาสองบรรทัดมาชนกันเอง** ถ้าคำนวณได้ก็คำนวณซะ แล้ววาง
        เป็นบรรทัดเดียวให้เห็นจะๆ (หลักเดียวกับ health/reverse-DCF ที่เป็น deterministic ทั้งหมด).

        ผลพลอยได้ที่สำคัญกว่า: พอเป็น Fact แล้ว health.py เอาไปใช้เป็นเกณฑ์ได้ (ดู
        _criterion_net_margin_level) และ eval ตรวจได้ว่าใครอ้างเลขนี้ตรงไหม — คนละชั้นกับการ
        เติมประโยคใน prompt ซึ่งพิสูจน์แล้วว่าไม่พอ.
        """
        out: list[Fact] = []

        # (1) กำไรสุทธิสูงกว่ากำไรจากการดำเนินงานเท่าไหร่ (บวก = มีตัวช่วยใต้เส้น เช่น ภาษี/รายการพิเศษ,
        #     ลบ = ถูกกดใต้เส้น ซึ่งแปลว่าธุรกิจดีกว่าที่กำไรสุทธิบอก — เจอทั้งสองทางในรอบเดียวกัน:
        #     DUOL +26.84pp, META -11.36pp). เทียบได้เฉพาะเมื่อเป็นงวดเดียวกันจริง
        net_margin = self.net_margin_series[0] if self.net_margin_series else None
        op_margin = self.operating_margin_series[0] if self.operating_margin_series else None
        if net_margin and op_margin and net_margin[0] == op_margin[0]:
            out.append(Fact("Earnings Quality Gap", net_margin[1] - op_margin[1], "pp", net_margin[0]))

        # (2) กำไรกลายเป็นเงินสดจริงกี่ส่วน — ต่ำกว่า 1 = กำไรค้างอยู่ในบัญชี ไม่ใช่ในธนาคาร
        #     (ขาดทุน = อัตราส่วนนี้ไร้ความหมาย ไม่ใส่ดีกว่าใส่แล้วชวนตีความผิด)
        if self.cfo is not None and self.net_income and self.net_income > 0:
            out.append(Fact("CFO / Net Income", self.cfo / self.net_income, "x", self.period))

        # (3) ตลาดคาดกำไรต่อหุ้นงวดหน้า 'ลด' หรือ 'เพิ่ม' — บวก = Forward P/E สูงกว่า trailing
        #     = ตลาดเองก็คาดว่ากำไรจะลดลง (สัญญาณที่ขัดกับการสรุปว่า 'P/E ต่ำ = ถูก' โดยตรง)
        if self.forward_pe is not None and self.pe is not None:
            out.append(Fact("Forward P/E - P/E", self.forward_pe - self.pe, "x", self.period))

        return out


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — ดึงค่าจาก DataFrame ของ yfinance (คอลัมน์ = งวด, ล่าสุดอยู่ซ้ายสุด)
# ─────────────────────────────────────────────────────────────────────────────
# ปีที่ทับกันระหว่าง XBRL กับ yfinance ต้องตรงกันภายใน 2% ถึงจะยอมใช้ประวัติยาว
_LONG_FCF_TOLERANCE = 0.02


def _long_fcf_growth(ticker: str, short_series: list[tuple[str, float]]) -> tuple:
    """CAGR ของ FCF จากประวัติที่ยื่น ก.ล.ต. -> (cagr%, "FY2007-FY2025", จำนวนปี) หรือ (None,)*3.

    ทำไมต้องมี (Phase 36): anchor ของ reverse-DCF คิดจากหน้าต่างที่ yfinance บังเอิญคืนมา ~4 ปี
    เสมอ ถ้าปีแรกของหน้าต่างเป็นปีผิดปกติ 'เทรนด์' ที่วัดได้จะกลายเป็น 'ระยะห่างจากปีนั้น' —
    CVX เริ่มที่ FY2022 ซึ่งเป็นยอดพีคราคาน้ำมัน เลยได้ FCF CAGR ~-24%/ปี ทั้งที่ประวัติ 19 ปี
    บอกคนละเรื่อง (ดู src/evals/check_anchor_window.py)

    เงื่อนไขที่ต้องผ่านครบก่อนยอมใช้ — ผิดข้อไหนก็คืน None แล้วใช้ของเดิม ไม่ใช่ใช้แบบมีเงื่อนไข:
      1) ยาวกว่าหน้าต่างเดิมจริง (ไม่งั้นเปลี่ยนไปก็ไม่ได้อะไร)
      2) ปลายทางทั้งสองฝั่งเป็นบวก (CAGR ไม่มีความหมายถ้าข้ามศูนย์)
      3) **ปีที่ทับกันต้องตรงกับ yfinance** — กันเอาตัวเลขคนละนิยามมาต่อเป็นเทรนด์เดียว
         (ฝั่งรายได้พังข้อนี้จริง: XBRL เลือก 'Revenues' ซึ่งรวมรายได้อื่น ต่างจาก yfinance 3-4%)
    """
    from src.providers.stock.xbrl import MIN_LONG_FCF_YEARS, annual_fcf_series

    try:
        long = annual_fcf_series(ticker)
    except Exception:
        return None, None, None
    if len(long) < MIN_LONG_FCF_YEARS or len(long) <= len(short_series or []):
        return None, None, None

    short = dict(short_series or [])
    overlap = [(p, v) for p, v in long if p in short]
    for period, value in overlap:
        base = abs(short[period])
        if base > 0 and abs(value - short[period]) / base > _LONG_FCF_TOLERANCE:
            return None, None, None          # คนละนิยาม -> ไม่ใช่ประวัติของเส้นเดียวกัน
    if not overlap:
        return None, None, None              # ไม่ทับกันเลย = พิสูจน์ไม่ได้ว่าเป็นชุดเดียวกัน

    # ต้องคิดจาก 'ช่วงปีจริง' ไม่ใช่จำนวนจุด — ประวัติ SEC ขาดปีกลางได้จริง (AAPL ไม่มี FY2014,
    # MSFT ไม่มี FY2014-15) แล้วการหารด้วยจำนวนจุดจะทำให้ CAGR พองขึ้นเงียบๆ (ดู domain/series.py)
    cagr = cagr_pct(long)
    if cagr is None:
        return None, None, None
    return cagr, f"{long[0][0]}-{long[-1][0]}", len(long)


def _period_label(col) -> str:
    """คอลัมน์ (Timestamp) -> 'FY2025'."""
    try:
        return f"FY{col.year}"
    except AttributeError:
        return str(col)


def _find_row(row_names, df):
    """คืน 'ชื่อแถวจริง' ตัวแรกที่มีใน df (รองรับชื่อสำรอง), ไม่เจอคืน None."""
    if df is None or df.empty:
        return None
    for name in row_names:
        if name in df.index:
            return name
    return None


def _compute_bank_metrics(fin, bs, revenue) -> dict:
    """เมตริกธนาคารจาก 'สิ่งที่ดึงได้จริง' — ตัวไหนคำนวณไม่ได้คืน None ไม่ประมาณให้.

    ตัวหารของ NIM ที่ถูกต้องคือ earning assets ซึ่งไม่มีใน yfinance -> ใช้สินทรัพย์รวมแล้วตั้งชื่อ
    ว่า 'NII / Assets' ตามที่คำนวณจริง (ไม่เรียกว่า NIM เพราะมันไม่ใช่ NIM). เช่นเดียวกัน
    efficiency ratio ที่แท้จริงต้องใช้ non-interest expense ซึ่งไม่มี -> ใช้ (รายได้ − กำไรก่อนภาษี)
    ซึ่งรวมค่าเผื่อหนี้สูญเข้าไปด้วย แล้วตั้งชื่อตามนั้น. ตั้งชื่อให้ตรงกับสิ่งที่คำนวณคือส่วนหนึ่ง
    ของความถูกต้อง — ป้ายที่บอกว่าเป็น NIM/efficiency ratio จะทำให้ทั้งคนและ LLM เทียบกับเกณฑ์
    มาตรฐานของอุตสาหกรรมผิดตัว
    """
    nii = _first(["Net Interest Income"], fin)
    if nii is None:
        return {}

    net_income = _first(["Net Income", "Net Income Common Stockholders"], fin)
    pretax = _first(["Pretax Income", "Income Before Tax"], fin)
    equity = _first(["Stockholders Equity", "Total Stockholder Equity"], bs)
    assets = _first(["Total Assets"], bs)
    tbv = _first(["Tangible Book Value"], bs)
    if tbv is None and equity is not None:
        intangibles = _first(["Goodwill And Other Intangible Assets"], bs)
        if intangibles is None:
            goodwill = _first(["Goodwill"], bs) or 0.0
            other = _first(["Other Intangible Assets"], bs) or 0.0
            intangibles = goodwill + other
        tbv = equity - intangibles

    return {
        "net_interest_income": nii,
        "tangible_book_value": tbv,
        "rotce": round(net_income / tbv * 100, 2) if net_income is not None and tbv else None,
        "equity_to_assets": round(equity / assets * 100, 2) if equity is not None and assets else None,
        "nii_to_assets": round(nii / assets * 100, 2) if assets else None,
        "cost_income_ratio": (
            round((revenue - pretax) / revenue * 100, 2)
            if pretax is not None and revenue else None
        ),
    }


# ชื่อแถว CFO ในงบกระแสเงินสดของ yfinance — เรียงจาก 'ชื่อที่ใช้บ่อยสุด' ไปหา 'ชื่อสำรอง'
# (_first ลองตามลำดับ ตัวหลังจึงถูกใช้ต่อเมื่อตัวหน้าไม่มีจริงๆ)
#
# ทำไมต้องมี 'Cash Flow From Continuing Operating Activities' (2026-08-16): ASML คืนเฉพาะชื่อนี้
# บางรอบและคืน 'Operating Cash Flow' บางรอบ ทำให้เกณฑ์ #3 (FCF+คุณภาพกำไร) พลิกคำนวณได้/ไม่ได้
# 6 ครั้งใน 17 วัน = 7 จุดของ 'คะแนนขยับโดยอธิบายไม่ได้' ในสมุดพก ซึ่งเป็นตัวหนักสุดในตาราง
#
# ตรวจก่อนเพิ่มว่าเป็นตัวเลขเดียวกันจริง ไม่ใช่ยอดที่ตัดธุรกิจที่เลิกไปออก (กับดักเดียวกับ
# `Revenues` vs `RevenueFromContract...` ใน Phase 36): **15/15 ตัวที่มีทั้งสองแถว ค่าตรงกันเป๊ะ**
# (ASML เป็นตัวเดียวที่ขาดชื่อแรก). ถ้าวันหนึ่งบริษัทมี discontinued operations จริง ชื่อแรกจะมี
# อยู่แล้วและถูกเลือกก่อนเสมอ — ชื่อนี้จึงเป็นทางออกฉุกเฉิน ไม่ใช่ตัวแทน
#
# 'Total Cash From Operating Activities' คือชื่อยุคเก่าของ yfinance — ตรวจ 16 ตัวแล้วไม่มีใครมี
# เลยสักตัว เก็บไว้เฉยๆ ไม่ได้เสียอะไร แต่อย่านับว่ามันกันอะไรได้
CFO_ROWS = [
    "Operating Cash Flow",
    "Cash Flow From Continuing Operating Activities",
    "Total Cash From Operating Activities",
]


def _first(row_names, df):
    """ค่าล่าสุด (คอลัมน์ซ้ายสุด) ของ 'ชื่อแถวสำรองตัวแรกที่มีค่าจริง', ไม่มีเลยคืน None.

    fix 2026-08: เดิมเลือกชื่อแถวแรกที่ 'มีอยู่' แล้วจบ — ถ้าช่องล่าสุดของแถวนั้นเป็น NaN ก็คืน
    None ทันทีทั้งที่ชื่อสำรองถัดไปมีตัวเลขอยู่. yfinance คืนชุดแถวไม่เหมือนกันทุกครั้งที่เรียก
    (บางรอบมี 'Depreciation And Amortization' บางรอบมีแค่ 'Depreciation') ทำให้ค่าเดียวกันหายๆ
    โผล่ๆ ข้ามวัน — ซึ่งไหลไปเป็นคะแนนที่เด้งไปมาโดยที่ธุรกิจไม่ได้เปลี่ยนอะไรเลย (ดู GOOGL
    ใน valuation.py::valuation_guard). ไล่ทุกชื่อสำรองจนเจอค่าจริงจึงตรงกับเจตนาของ 'ชื่อสำรอง'
    ตั้งแต่แรก.
    """
    if df is None or df.empty:
        return None
    for name in row_names:
        if name in df.index:
            value = df.loc[name, df.columns[0]]
            if pd.notna(value):
                return float(value)
    return None


def _series(row_names, df) -> list[tuple[str, float]]:
    """คืนทั้งอนุกรม [(FYxxxx, ค่า), ...] เรียงล่าสุดก่อน, ข้ามงวดที่เป็น NaN."""
    row = _find_row(row_names, df)
    if row is None:
        return []
    out = []
    for col in df.columns:
        value = df.loc[row, col]
        if pd.notna(value):
            out.append((_period_label(col), float(value)))
    return out


def _ratio_series(numer_names, denom_names, df, pct=True) -> list[tuple[str, float]]:
    """อัตราส่วนรายปี เช่น margin = numerator/denominator ต่อคอลัมน์เดียวกัน."""
    numer_row = _find_row(numer_names, df)
    denom_row = _find_row(denom_names, df)
    if numer_row is None or denom_row is None:
        return []
    out = []
    for col in df.columns:
        n, d = df.loc[numer_row, col], df.loc[denom_row, col]
        if pd.notna(n) and pd.notna(d) and d != 0:
            # cast เป็น native Python float ก่อนคำนวณ (เหมือน _first/_series) — เผื่อไว้ ไม่งั้น
            # ค่าที่ได้เป็น numpy.float64 ซึ่งดู 'เหมือน' float ปกติ (subclass ของ float จริง จึง
            # JSON serialize ผ่านมาตลอดไม่มีปัญหา) แต่พอเอาไปเทียบ <= จะได้ numpy.bool_ ซึ่ง
            # json.dumps() serialize ไม่ได้ (ไม่ใช่ subclass ของ bool) — เจอตอนทำ eval เทียบ tolerance
            ratio = float(n) / float(d)
            out.append((_period_label(col), round(ratio * 100, 2) if pct else round(ratio, 2)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE — เมตริกที่ต้องคำนวณ (ไม่มีตรง ๆ ใน info)
# ─────────────────────────────────────────────────────────────────────────────
def _compute_free_cash_flow(info: dict, cashflow) -> float | None:
    fcf = info.get("freeCashflow")
    if fcf is not None:
        return float(fcf)
    # สำรอง: FCF = OCF + Capex (capex เก็บเป็นเลขติดลบอยู่แล้ว)
    ocf = _first(CFO_ROWS, cashflow)
    capex = _first(["Capital Expenditure", "Capital Expenditures"], cashflow)
    if ocf is not None and capex is not None:
        return ocf + capex
    return None


def _compute_roic(financials, balance_sheet) -> tuple[float | None, float | None, float | None]:
    """คืน (ROIC %, NOPAT ดอลลาร์, Invested Capital ดอลลาร์) — expose NOPAT/invested_capital
    แยกเป็น Fact ของตัวเอง (Phase 18) เพราะ reinvestment_rate ของ reverse-DCF ใหม่ต้องใช้
    NOPAT เป็นตัวหาร (reinvestment_rate = (Capex − D&A + ΔNWC) / NOPAT)."""
    operating_income = _first(["Operating Income", "EBIT"], financials)  # EBIT
    pretax_income = _first(["Pretax Income"], financials)
    tax_provision = _first(["Tax Provision"], financials)

    total_debt = _first(["Total Debt"], balance_sheet)
    total_equity = _first(["Stockholders Equity", "Total Stockholder Equity"], balance_sheet)
    cash = _first(
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
        balance_sheet,
    )
    if operating_income is None or total_debt is None or total_equity is None or cash is None:
        return None, None, None

    # อัตราภาษีจริง (guard หาร 0 / None) แล้วได้ NOPAT = กำไรดำเนินงานหลังภาษี
    tax_rate = tax_provision / pretax_income if pretax_income and tax_provision is not None else 0.0
    nopat = operating_income * (1 - tax_rate)
    invested_capital = total_debt + total_equity - cash  # เงินทั้งหมดที่ใส่ในธุรกิจ (หัก cash กองเฉย ๆ)
    if not invested_capital:
        return None, nopat, invested_capital
    return round((nopat / invested_capital) * 100, 2), nopat, invested_capital


def _compute_roe(financials, balance_sheet) -> float | None:
    net_income = _first(["Net Income", "Net Income Common Stockholders"], financials)
    equity = _first(["Stockholders Equity", "Total Stockholder Equity"], balance_sheet)
    if net_income is None or not equity:
        return None
    return round((net_income / equity) * 100, 2)


def _compute_revenue_cagr(financials) -> float | None:
    """CAGR ตลอดช่วงที่มีข้อมูล (ล่าสุด vs เก่าสุด)."""
    rev = _series(["Total Revenue", "Operating Revenue"], financials)
    if len(rev) < 2:
        return None
    newest, oldest = rev[0][1], rev[-1][1]      # rev เรียงล่าสุดก่อน
    years = len(rev) - 1
    if oldest <= 0 or newest <= 0:
        return None
    cagr = (newest / oldest) ** (1 / years) - 1
    return round(cagr * 100, 2)


def _compute_net_debt(balance_sheet) -> float | None:
    """Net Debt ดอลลาร์ดิบ (ไม่ใช่ ratio) — เดิมคำนวณแล้วทิ้งข้างในเลย (Phase 18: แยก expose
    เป็น Fact ของตัวเองด้วย ใช้ผูก EV = Market Cap + Net Debt ใน reverse-DCF ใหม่)."""
    net_debt = _first(["Net Debt"], balance_sheet)
    if net_debt is not None:
        return net_debt
    total_debt = _first(["Total Debt"], balance_sheet)
    cash = _first(["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], balance_sheet)
    if total_debt is None or cash is None:
        return None
    return total_debt - cash


def _compute_net_debt_to_ebitda(balance_sheet, financials, info) -> float | None:
    net_debt = _compute_net_debt(balance_sheet)
    if net_debt is None:
        return None
    ebitda = _first(["EBITDA", "Normalized EBITDA"], financials) or info.get("ebitda")
    if not ebitda:
        return None
    return round(net_debt / ebitda, 2)


def _net_debt_to_ebitda_series(balance_sheet, financials) -> list[tuple[str, float]]:
    """อนุกรมรายปี — net_debt คำนวณจาก 2 แถวในงบดุลปีเดียวกัน (ไม่ใช่แถวเดียว) จึงคำนวณ
    net_debt ต่อปีก่อน แล้วค่อยจับคู่กับ EBITDA ปีเดียวกันจากงบกำไร (คนละ DataFrame)."""
    debt_row = _find_row(["Total Debt"], balance_sheet)
    cash_row = _find_row(
        ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], balance_sheet
    )
    if debt_row is None or cash_row is None:
        return []
    net_debt_by_year: dict[int, float] = {}
    for col in balance_sheet.columns:
        year = getattr(col, "year", None)
        debt, cash = balance_sheet.loc[debt_row, col], balance_sheet.loc[cash_row, col]
        if year is not None and pd.notna(debt) and pd.notna(cash):
            net_debt_by_year[year] = float(debt) - float(cash)

    ebitda_row = _find_row(["EBITDA", "Normalized EBITDA"], financials)
    if ebitda_row is None:
        return []
    out = []
    for col in financials.columns:
        year = getattr(col, "year", None)
        ebitda = financials.loc[ebitda_row, col]
        net_debt = net_debt_by_year.get(year)
        if year is not None and pd.notna(ebitda) and ebitda and net_debt is not None:
            out.append((f"FY{year}", round(net_debt / float(ebitda), 2)))
    return out


def _latest_common(numer_names, denom_names, df):
    """คู่ (numer, denom) จากคอลัมน์ล่าสุดที่ 'ทั้งคู่' ไม่เป็น NaN (จับคู่ในปีเดียวกัน).
    เผื่อกรณีปีล่าสุดข้อมูลตัวหนึ่งว่าง (เช่น AAPL ไม่รายงาน Interest Expense แล้ว)."""
    numer_row = _find_row(numer_names, df)
    denom_row = _find_row(denom_names, df)
    if numer_row is None or denom_row is None:
        return None
    for col in df.columns:                       # ล่าสุดก่อน
        n, d = df.loc[numer_row, col], df.loc[denom_row, col]
        if pd.notna(n) and pd.notna(d):
            return float(n), float(d)
    return None


def _compute_interest_coverage(financials) -> float | None:
    pair = _latest_common(["EBIT", "Operating Income"], ["Interest Expense", "Interest Expense Non Operating"], financials)
    if pair is None:
        return None
    ebit, interest = pair
    if not interest:
        return None
    return round(ebit / abs(interest), 2)


def _compute_current_ratio(balance_sheet, info) -> float | None:
    cur_assets = _first(["Current Assets"], balance_sheet)
    cur_liab = _first(["Current Liabilities"], balance_sheet)
    if cur_assets is not None and cur_liab:
        return round(cur_assets / cur_liab, 2)
    cr = info.get("currentRatio")
    return float(cr) if cr is not None else None


def _cross_ratio_series(numer_names, numer_df, denom_names, denom_df, mult) -> list[tuple[str, float]]:
    """อัตราส่วนข้ามงบ จับคู่ 'ปีเดียวกัน' เช่น DSO = Receivables(งบดุล)/Revenue(งบกำไร)*365.
    ตัวหาร (revenue) มาจากคนละ DataFrame จึง index ด้วยปีก่อนแล้วค่อยจับคู่."""
    nrow = _find_row(numer_names, numer_df)
    drow = _find_row(denom_names, denom_df)
    if nrow is None or drow is None:
        return []
    denom_by_year: dict[int, float] = {}
    for col in denom_df.columns:
        year = getattr(col, "year", None)
        val = denom_df.loc[drow, col]
        if year is not None and pd.notna(val) and val != 0:
            denom_by_year[year] = float(val)
    out = []
    for col in numer_df.columns:
        year = getattr(col, "year", None)
        num = numer_df.loc[nrow, col]
        den = denom_by_year.get(year)
        if year is not None and pd.notna(num) and den:
            out.append((f"FY{year}", round(float(num) / den * mult, 2)))
    return out


def _compute_goodwill(balance_sheet) -> tuple[float | None, float | None]:
    """คืน (goodwill, goodwill เป็น % ของสินทรัพย์รวม). ถ้าบริษัทไม่มี goodwill -> (None, None)."""
    goodwill = _first(["Goodwill"], balance_sheet)
    if goodwill is None:
        return None, None
    total_assets = _first(["Total Assets"], balance_sheet)
    pct = round(goodwill / total_assets * 100, 2) if total_assets else None
    return goodwill, pct


def _fcf_yield(fcf, market_cap) -> float | None:
    if fcf is None or not market_cap:
        return None
    return round((fcf / market_cap) * 100, 2)


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER
# ─────────────────────────────────────────────────────────────────────────────
class StockFundamentalsProvider(FundamentalsProvider):
    def get_fundamentals(self, ticker: str) -> StockFundamentals:
        t = yf.Ticker(ticker)
        info = t.info
        fin, bs, cf = t.financials, t.balance_sheet, t.cashflow

        revenue = info.get("totalRevenue") or _first(["Total Revenue"], fin)
        revenue = float(revenue) if revenue is not None else None
        fcf = _compute_free_cash_flow(info, cf)
        market_cap = info.get("marketCap")
        # ADR ต่างชาติยื่นงบสกุลบ้านเกิดแต่ราคาเป็น USD (ASML: EUR/USD, TSM: TWD/USD) ->
        # อัตราส่วนที่เอาราคาหารงบไม่มีความหมาย. ไม่แปลงค่าเงินให้ (ไม่รู้แน่ว่า field ไหนของ
        # yfinance อยู่ฝั่งไหน — เดาแล้วผิดจะแย่กว่าไม่มี) แต่ตัดทิ้งพร้อมติดป้ายหน่วยให้ตรงจริง
        financial_currency = info.get("financialCurrency")
        price_currency = info.get("currency")
        goodwill, goodwill_pct = _compute_goodwill(bs)
        bank = _compute_bank_metrics(fin, bs, revenue)
        roic, nopat, invested_capital = _compute_roic(fin, bs)
        # Phase 36: ประวัติ FCF ยาวจาก SEC (cache ดิสก์ 7 วัน — ไม่ใช่ request ใหม่ทุกรอบ)
        # ดึงไม่ได้/ไม่ผ่านเงื่อนไข -> (None, None, None) แล้วทุกอย่างทำงานเหมือนเดิมทุกประการ
        fcf_series = _series(["Free Cash Flow"], cf)
        long_cagr, long_window, long_years = _long_fcf_growth(ticker, fcf_series)

        return StockFundamentals(
            period=_period_label(fin.columns[0]) if fin is not None and not fin.empty else "N/A",
            revenue=revenue,
            free_cash_flow=fcf,
            fcf_margin=round((fcf / revenue) * 100, 2) if fcf is not None and revenue else None,
            roic=roic,
            roe=_compute_roe(fin, bs),
            revenue_cagr=_compute_revenue_cagr(fin),
            net_debt_to_ebitda=_compute_net_debt_to_ebitda(bs, fin, info),
            interest_coverage=_compute_interest_coverage(fin),
            current_ratio=_compute_current_ratio(bs, info),
            goodwill=goodwill,
            goodwill_pct_assets=goodwill_pct,
            financial_currency=financial_currency,
            price_currency=price_currency,
            **bank,
            pe=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            # เก็บค่าดิบไว้ตามที่ yfinance ให้มา — การ 'ตัดอัตราส่วนข้ามสกุลทิ้ง' ทำที่ to_facts()
            # ที่เดียว (ไม่ใช่ตรงนี้) เพื่อให้ object ที่ประกอบเองในเทสต์/สคริปต์อื่นได้กติกาเดียวกัน
            ev_ebitda=info.get("enterpriseToEbitda"),
            peg=info.get("trailingPegRatio") or info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            fcf_yield=_fcf_yield(fcf, market_cap),
            market_cap=float(market_cap) if market_cap is not None else None,
            avg_volume=float(info["averageVolume"]) if info.get("averageVolume") is not None else None,
            net_income=_first(["Net Income", "Net Income Common Stockholders"], fin),
            cfo=_first(CFO_ROWS, cf),
            net_debt=_compute_net_debt(bs),
            capex=_first(["Capital Expenditure", "Capital Expenditures"], cf),
            # ชื่อสำรองเรียงจาก 'ตรงความหมายที่สุด' ไปหา 'กว้างที่สุด' — yfinance สลับชุดแถวที่คืนมา
            # ระหว่างการเรียกแต่ละครั้ง ค่านี้ขาดเมื่อไหร่ reinvestment_rate คำนวณไม่ได้ทั้งก้อน
            depreciation_amortization=_first([
                "Depreciation And Amortization", "Depreciation Amortization Depletion",
                "Reconciled Depreciation", "Depreciation",
            ], cf),
            nwc_change=_first(["Change In Working Capital"], cf),
            nopat=nopat,
            invested_capital=invested_capital,
            beta=float(info["beta"]) if info.get("beta") is not None else None,
            gross_margin_series=_ratio_series(["Gross Profit"], ["Total Revenue"], fin),
            operating_margin_series=_ratio_series(["Operating Income", "EBIT"], ["Total Revenue"], fin),
            net_margin_series=_ratio_series(["Net Income", "Net Income Common Stockholders"], ["Total Revenue"], fin),
            share_count_series=_series(["Diluted Average Shares", "Basic Average Shares"], fin),
            fcf_series=fcf_series,
            fcf_cagr_long=long_cagr,
            fcf_long_window=long_window,
            fcf_long_years=long_years,
            dso_series=_cross_ratio_series(["Receivables", "Accounts Receivable"], bs, ["Total Revenue", "Operating Revenue"], fin, 365),
            inventory_pct_series=_cross_ratio_series(["Inventory"], bs, ["Total Revenue", "Operating Revenue"], fin, 100),
            roe_series=_cross_ratio_series(["Net Income", "Net Income Common Stockholders"], fin, ["Stockholders Equity", "Total Stockholder Equity"], bs, 100),
            net_debt_to_ebitda_series=_net_debt_to_ebitda_series(bs, fin),
            current_ratio_series=_ratio_series(["Current Assets"], ["Current Liabilities"], bs, pct=False),
            revenue_series=_series(["Total Revenue", "Operating Revenue"], fin),
        )


if __name__ == "__main__":
    # เครื่องมือ debug: ดูทุก Fact ของ ticker หนึ่งดิบ ๆ (ไม่เรียก LLM, ไม่กิน quota)
    # ใช้ตอนสงสัยว่า "ทำไม confidence ต่ำ / คำอธิบายดูขัดแย้งกัน" — ไล่ดู label+period+value
    # เทียบกันเองได้ทันที ไม่ต้องเปิด python -c หลายรอบแบบตอนไล่บั๊ก TTM/FY ของ SBUX
    #   ใช้:  python -m src.providers.stock.fundamentals SBUX
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    facts = StockFundamentalsProvider().get_fundamentals(ticker).to_facts()
    facts.sort(key=lambda f: (f.label, f.period))
    print(f"=== {ticker}: {len(facts)} facts ===")
    for f in facts:
        print(f"  {f.label:22} = {f.value:>18,.4f}  {f.unit:8} period={f.period}")