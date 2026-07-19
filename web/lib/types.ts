// รูปข้อมูลที่ API ส่งมา — สะท้อน Summary (Pydantic) ฝั่ง Python + คอลัมน์ denormalize

export type WeakPoint = { area: string; detail: string };

export type Summary = {
  ticker: string;
  price: number;
  fundamental_strength: "strong" | "mixed" | "weak";
  strength_reasons: string[];
  weak_points: WeakPoint[];
  valuation_view: "cheap" | "fair" | "expensive" | "unclear";
  thesis_relevant_news: string[];
  key_news: string[];
  what_to_watch: string[];
  sentiment: "bullish" | "neutral" | "bearish";
  confidence: number;
  thesis_assessment?: string; // Phase 5: AI ประเมินว่าข้อมูลวันนี้ยังหนุน thesis เดิมไหม ("" ถ้าไม่ได้ตั้ง thesis)
  beginner_summary?: string; // optional: แถวเก่าก่อน Phase 2.5 จะไม่มี field นี้
};

// ตัวเลขงบดิบ 1 จุด (label เช่น "Operating Margin", period เช่น "FY2024" | "TTM")
export type Fact = {
  label: string;
  value: number;
  unit: string;
  period: string | null;
};

export type WatchlistItem = {
  ticker: string;
  asset_type: string;
  added_at: string;
  // Phase 5.5: สถานะถือครอง — 'watching' (แค่จับตา) | 'holding' (ถืออยู่จริง)
  // Phase: 'frozen' (ขายหมดแล้วแต่อยากดูว่าฟื้นไหม — analyze() รอบเดือนแทนรายวัน ประหยัดโควตา)
  status: "watching" | "holding" | "frozen";
  entry_price: number | null;
  entry_date: string | null;
  shares: number | null;
};

// Phase 5.5: edge ของโพซิชันที่ถืออยู่ vs benchmark ตั้งแต่วันซื้อ
// Phase 11: + dollar figures (null ถ้าไม่ได้ใส่ shares)
export type EdgePosition = {
  ticker: string;
  benchmark: string;
  entry_price: number;
  entry_date: string;
  current_price: number;
  shares: number | null;
  cost_basis: number | null;      // เงินต้น ($)
  market_value: number | null;    // มูลค่าตอนนี้ ($)
  unrealized_pnl: number | null;  // กำไร/ขาดทุน $ ที่ยังไม่ realize
  weight: number | null;          // % ของพอร์ต
  // Phase 20.3: คะแนน health ณ วันที่ซื้อ (point-in-time, ดึงจาก history store ที่มีอยู่แล้ว) —
  // ตอบคำถาม 'เลือกหุ้น health สูงเองชนะ VT จริงไหม' ไม่ใช่แค่ 'ราคาขึ้นกว่า VT ไหม'
  entry_health: number | null;       // null = ไม่มี analysis ที่มี health เลย
  entry_health_exact: boolean;       // false = ไม่มีรอบวิเคราะห์ก่อนวันซื้อจริง (fallback เป็นค่าประมาณ ห้ามอ้างว่าคือคะแนนจริง ณ วันซื้อ)
  your_return: number; // %
  benchmark_return: number; // %
  edge: number; // % (บวก = ชนะ index)
  holding_days: number;
};

// Phase 14: company biography timeline — เหตุการณ์ material หลายปี + จุดพลิกพื้นฐาน
export type TimelineEvent = {
  date: string;
  period: string;
  kind: "8-K" | "fundamental";
  label: string;
  detail: string;
  url?: string;
};

export type Timeline = {
  ticker: string;
  events: TimelineEvent[];
  narrative: string | null;
};

// Phase 15: reverse-DCF — growth rate ที่ราคาตลาดปัจจุบัน 'price ไว้' เทียบกับ historical CAGR จริง
// Phase 18: CAPM WACC (company-specific, ไม่ใช่ค่าคงที่เดิม), EV = Market Cap + Net Debt,
// realistic_growth = sustainable growth (reinvestment×ROIC, capped) แทน raw historical CAGR,
// score = 0-3 step-function จาก gap band (ตาม scoring_spec.md)
// valuation_guard_growth_lens.md: sustainable_growth (reinvestment_rate × ROIC) พังกับหุ้น
// asset-light + deferred-revenue (เช่น DUOL — ΔNWC บวกมากจากลูกค้าจ่ายล่วงหน้า ทำให้
// reinvestment ติดลบทั้งที่บริษัทโตจริง) valuation_guard ตรวจจับแล้ว route ไป 'growth lens'
// (ใช้ growth จริงล่าสุดที่ fade ลง terminal แทน) — lens ต้องแยกกลุ่มตอนวิเคราะห์ ห้ามปนกัน
export type Valuation = {
  implied_growth: number | null; // % ต่อปี — null ถ้าคำนวณไม่ได้ (FCF ติดลบ/นอกขอบเขตโมเดล)
  realistic_growth: number | null; // % ต่อปี — anchor ที่ใช้เทียบ gap จริง (มาจาก lens ไหนดู field lens)
  historical_cagr: number | null; // % ต่อปีที่บริษัทโตจริงในอดีต (อ้างอิง/cross-check เท่านั้น)
  gap: number | null; // implied - realistic (บวก = ตลาดคาดหวังมากกว่าที่ทำได้)
  score: number | null; // 0-3, step function จาก gap band (ปรับด้วย Rule of 40 ถ้า lens='growth')
  lens: "standard" | "growth" | "NA"; // ใช้ sustainable_growth ตรงๆ | ใช้ growth lens แทน | คำนวณไม่ได้เลย
  flags: string[]; // เหตุผลที่ route (FCF_NONPOSITIVE/NOPAT_UNSTABLE/NEGATIVE_REINVESTMENT/SUSTAINABLE_DIVERGES)
  rule_of_40: number | null; // rev_growth_recent% + fcf_margin% (เฉพาะ lens='growth')
  wacc: number; // % CAPM (Rf + β×ERP) ที่ใช้จริง
  beta_used: number; // β หลัง clamp [0.7, 1.6]
  terminal_growth: number;
  years: number;
  ev: number | null; // Market Cap + Net Debt ที่ใช้เป็นเป้าหมายแก้สมการ
  fcf_base: number | null; // ค่าเฉลี่ย FCF 3 ปีที่ใช้เป็นฐานโมเดล
  note: string | null;
};

// Phase 13: agentic investigation transcript — ทุกสเต็ปที่ agent ตัดสินใจ+เรียก tool เอง
export type InvestigationStep = {
  tool: string;
  args: Record<string, unknown>;
  observation: string;
};

export type Investigation = {
  ticker: string;
  run_at: string;
  steps: InvestigationStep[];
  conclusion: string;
  stopped: "concluded" | "max_steps" | "error";
};

// Phase 21: screener — สแกน UNIVERSE คัดมือ (large/liquid US stocks, ไม่ใช่ S&P 500 เต็มรูปแบบ)
// หาหุ้นพื้นฐานแข็ง+ราคาถูก โดยใช้เอนจิ้นเดียวกับ health score (Piotroski/8 + reverse-DCF/3)
// แต่ไม่เรียก LLM เลย — ผลลัพธ์ cache ไว้ฝั่ง backend (นาทีระดับต่อการสแกนใหม่ทั้งก้อน)
export type ScreenerResult = {
  ticker: string;
  score: number;
  max: number;
  tier: "strong" | "ok" | "weak";
  label: string;
  fundamental_score: number;
  valuation_score: number;
  implied_growth: number | null;
  realistic_growth: number | null;
  gap: number | null;
  lens: "standard" | "growth" | "NA";
  pe: number | null;
  roic: number | null;
  market_cap: number | null;
  already_watching: boolean;
};

export type ScreenerResponse = {
  computed_at: number; // unix epoch (วินาที) — ตอนสแกนล่าสุด
  results: ScreenerResult[];
};

// Phase 23: แนวโน้ม health score N จุดล่าสุด/ticker (เบา, ไม่มี summary/facts) ไว้วาด sparkline
export type HealthTrendPoint = { period: string; value: number };
export type HealthTrends = Record<string, HealthTrendPoint[]>;

export type Portfolio = {
  benchmark: string;
  positions: EdgePosition[];
  beating_benchmark: number;
  total_positions: number;
  total_value: number | null;   // มูลค่าพอร์ตรวม ($)
  total_cost: number | null;    // เงินต้นรวม ($)
  total_pnl: number | null;     // กำไร/ขาดทุนรวม ($)
  total_return: number | null;  // % ผลตอบแทนรวมของพอร์ต
};

export type Change = {
  type: string;
  detail: string;
  severity: "alert" | "warn" | "info";
  metric?: string;
};

export type ChangeReport = {
  ticker: string;
  from?: string;
  to?: string;
  changes: Change[];
  note?: string;
};

export type ExtractionCheck = {
  metric: string;
  ours: number;
  reference: number;
  within_tolerance: boolean;
};

// Phase 4: ความแม่นของ 'การคำนวณของเราเอง' เทียบกับ yfinance's own ratios (ไม่ใช่ LLM)
export type ExtractionResult = {
  ticker: string;
  checks: ExtractionCheck[];
  accuracy: number | null;
};

// Phase 10: health score ที่คำนวณ+เก็บตอน analyze() (Python เป็น source of truth) — เก็บทุก
// แถวประวัติ ต่างจากเดิมที่คำนวณสดฝั่ง frontend อย่างเดียว จึงย้อนดู trend/เหตุผลได้
// Phase 18: score/tier เป็น null/"excluded" ได้ — ticker ที่ข้อมูลไม่พอ (data gate <6/8 เกณฑ์),
// ขาดทุน (reverse-DCF หาคำตอบไม่ได้), หรือ crypto (ไม่มี Fact ที่เกี่ยวข้องเลย) จะถูกตัดออกจาก
// screen นี้แทนการ fallback ไปใช้ label ของ LLM แบบ Phase 17 เดิม
// Phase 20.2: แตกคะแนนให้อ่านออก — components/fundamental มีอยู่ใน health JSON ที่ backend เก็บ
// อยู่แล้ว (health.py) แค่เดิม type ไม่ได้ประกาศไว้ frontend เลยใช้ไม่ได้ (โชว์แต่เลขรวม)
export type HealthComponents = {
  strength: number | null;   // /8 (Piotroski) — null เมื่อ excluded
  valuation: number | null;  // /3 (reverse-DCF) — null เมื่อ excluded
  sentiment: number;         // metadata เท่านั้นตั้งแต่ 19.3.1 (ไม่รวมในคะแนน)
  breach_penalty: number | null;
};

// (label เกณฑ์, degree 0-1 | null=คำนวณไม่ได้/ข้อมูลไม่พอ) — ไล่ระดับตั้งแต่ 19.3
export type HealthCriterion = [string, number | null];

export type HealthFundamental = {
  score: number | null;
  computable: number;
  passed: number;
  criteria: HealthCriterion[];   // 8 เกณฑ์ Piotroski พร้อม degree รายข้อ
  disqualified: boolean;
  reason: string;
};

export type PersistedHealth = {
  score: number | null;
  max?: number; // Phase 18+ เท่านั้น (11 ตั้งแต่ 19.3.1 — เดิม 12 ก่อนตัด sentiment ออกจากผลรวม)
                // แถวเก่า Phase 10-17 ไม่มี field นี้ (undefined = /10)
  tier: "strong" | "ok" | "weak" | "excluded";
  label: string;
  reasons: string[];
  components?: HealthComponents;   // Phase 18+ (แถวเก่ากว่านั้นไม่มี -> breakdown ไม่ render)
  fundamental?: HealthFundamental; // Phase 18+
};

export type Analysis = {
  id: number;
  ticker: string;
  run_at: string;
  fundamental_strength: string;
  valuation_view: string;
  sentiment: string;
  price: number;
  confidence: number;
  price_ok: boolean;
  news_grounded_ratio: number;
  facts_grounded_ratio: number;
  extraction_accuracy: number | null;
  extraction: ExtractionResult | null;
  xbrl_accuracy: number | null; // Phase 12: เทียบกับ SEC XBRL จริง (ground truth อิสระจาก yfinance)
  xbrl: ExtractionResult | null;
  facts: Fact[]; // ตัวเลขงบดิบหลายปี (ว่างถ้าแถวเก่าก่อน Phase 3) — ใช้ทำกราฟ trend
  health_score: number | null; // denormalized ไว้ query/sort เร็ว (เหมือน extraction_accuracy)
  health: PersistedHealth | null; // None = แถวเก่าก่อน Phase 10 -> frontend fallback คำนวณสด
  valuation: Valuation | null; // Phase 15: null = แถวเก่าก่อน Phase 15 หรือคำนวณไม่ได้
  summary: Summary;
};
