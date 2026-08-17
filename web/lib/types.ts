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
  // Phase 35: หน้าต่างข้อมูลที่ realistic_growth ถูกคำนวณมา — metadata ล้วน ไม่เข้าคะแนน.
  // มีเพราะ yfinance คืนมา 4 ปีเสมอ และถ้าปีแรกบังเอิญเป็นปีผิดปกติ (CVX เริ่มที่พีคน้ำมัน 2022)
  // "เทรนด์" ที่วัดได้จะกลายเป็น "ระยะห่างจากปีนั้น" แทน โดยไม่มีอะไรบนหน้าจอบอกเลย
  anchor_window?: {
    source: string; // fcf | revenue | revenue_cagr | sustainable
    years: number | null;
    start: string | null;
    end: string | null;
    starts_at_max: boolean;
    starts_at_min: boolean;
    flags: string[];
  } | null;
  // Phase 40: gap เดิมในหน่วยราคา — ไม่ใช่ราคาเป้าหมายและไม่ใช่สัญญาณซื้อ (โปรเจกต์นี้ไม่ฟันธง
  // จังหวะ) แต่คือ "ตลาดขอราคาสูง/ต่ำกว่าที่ประมาณการของเรารองรับกี่ %" ซึ่งเป็นข้อมูลเดียวกับ
  // gap ที่โชว์อยู่แล้ว แค่อยู่ในหน่วยที่เจ้าของใช้ซื้อขายจริง
  fair?: {
    market_cap: number | null; // null สำหรับเลนส์ธนาคาร (ให้สัดส่วน ไม่ได้ให้ตัวเงิน)
    discount_pct: number | null; // ลบ = ราคาวันนี้แพงกว่าที่ประมาณการรองรับ
    at_growth: number | null;
    at_rotce?: number | null; // เลนส์ธนาคารใช้ ROTCE เป็นแกนแทน growth
    band_pp: number;
    band: { growth?: number; rotce?: number; discount_pct: number | null }[];
    // ราคาขยับกี่ % ต่อ growth (หรือ ROTCE) 1pp — ตัวเลขที่บอกว่าควรเชื่อเลขข้างบนแค่ไหน
    pct_per_pp: number | null;
    lens?: string;
  } | null;
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

// Phase 28: สั่งสืบจากหน้าเว็บ — งานเบื้องหลังที่ poll ดูความคืบหน้าได้ (steps โตทีละสเต็ป
// ระหว่าง status='running'). state อยู่ในหน่วยความจำฝั่ง API เท่านั้น รีสตาร์ท API แล้วหาย
// (transcript ที่จบแล้ว persist ลง DB ตามปกติ อ่านผ่าน getInvestigation)
export type InvestigationJob = {
  ticker: string;
  focus: string;
  status: "running" | "done" | "error";
  started_at: string;
  finished_at: string | null;
  steps: InvestigationStep[];
  conclusion: string;
  stopped: "" | "concluded" | "max_steps" | "error";
  error: string | null;
};

// Phase 25: portfolio chat — ถามคำถามภาษาคนเกี่ยวกับ watchlist/portfolio ของตัวเอง agent ไปดึง
// ข้อมูลที่คำนวณเก็บไว้แล้ว (ไม่ fetch สด) มาตอบ พร้อม step trace ให้เห็นว่าอ้างอิงอะไร
export type ChatMessage = { role: "user" | "assistant"; text: string; steps?: InvestigationStep[] };

export type ChatAnswer = {
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
  // Phase 34: ประเมินราคาไม่ได้ -> คะแนน 'พื้นฐานล้วน' max=8 (partial) แทนการหายไปทั้งตัว
  // ห้ามเอา score ของ partial ไปเทียบกับตัวที่ได้เต็ม /11 ตรงๆ — คนละมาตรวัด
  partial: boolean;
  partial_reason: string | null;
  // Phase 39: true = ดึงข้อมูลไม่สำเร็จรอบนี้ (ไม่ใช่ข้อสรุปว่าบริษัทประเมินไม่ได้) — สองอย่างนี้
  // ต่างกันที่ผู้อ่านควรทำอะไรต่อ จึงต้องแยกให้เห็น ไม่ใช่ให้เดาจากข้อความ
  data_gap?: boolean;
  // Phase 40: gap ในหน่วยราคา + ความไวของมัน — ตั้งใจไม่ใช้เรียงลำดับ (นั่นคือการทำสัญญาณซื้อ)
  fair_discount_pct?: number | null;
  fair_pct_per_pp?: number | null;
  valuation_score: number | null;
  implied_growth: number | null;
  realistic_growth: number | null;
  gap: number | null;
  lens: "standard" | "growth" | "NA" | "bank_pb";   // bank_pb = ธนาคาร (justified P/B)
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
  // Phase 29: true = คะแนน 'พื้นฐานล้วน' /8 (ประเมินราคาไม่ได้ เช่นบริษัทที่ยัง burn cash ->
  // reverse-DCF ใช้ไม่ได้) — ห้ามเอาไปเทียบ/จัดอันดับกับคะแนนเต็ม /11 ตรงๆ. คอลัมน์
  // analyses.health_score ของแถวพวกนี้เป็น null โดยตั้งใจ (sparkline/health-at-entry จึงข้ามไปเอง)
  partial?: boolean;
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

// Phase 26: Macro Event Radar — ตัวเลขเศรษฐกิจ + base-rate ผลตอบสนองย้อนหลัง + ธงข่าวภูมิรัฐศาสตร์
export type MacroReaction = {
  asset: string;        // ชื่อไทยของสินทรัพย์ (BTC/ETH/ทองคำ/หุ้นสหรัฐ)
  n: number;            // จำนวนครั้งย้อนหลัง
  mean_pct: number;     // % เปลี่ยนแปลงเฉลี่ยหลังประกาศ
  min_pct: number;
  max_pct: number;
  share_up: number;     // สัดส่วนครั้งที่ขึ้น (0..1)
  horizon_days: number;
};

export type MacroRelease = {
  key: string;
  label: string;
  ref_date: string;     // เดือนอ้างอิง (YYYY-MM-DD)
  value: number;
  unit: string;
  direction: "up" | "down" | "flat";
  desc: string;         // อธิบายทิศ (เช่น 'เงินเฟ้อเร่งตัวขึ้น')
  signal: number;       // สัญญาณล่าสุด (YoY% / งานเพิ่ม / ระดับ)
  prev_signal: number;
  approx: boolean;      // true = วันประกาศประมาณ (ไม่มี FRED_API_KEY)
  reactions: MacroReaction[];
};

export type GeoNews = { title: string; source: string; published: string; url: string };

// Alt vs BTC — โมเมนตัม ETH/BTC ratio (บรรยายตอนนี้ ไม่ทำนาย alt season)
export type AltSeason = {
  eth_btc_ratio: number;
  change_30d: number;   // % ขยับของ ratio ใน 30 วัน (+ = ETH นำ)
  change_90d: number;
  eth_30d: number;      // ผลตอบแทน ETH/BTC 30 วัน (context)
  btc_30d: number;
  state: "alt" | "btc" | "neutral";
  label: string;
};

// สถานะของเรดาร์เอง — "ยังไม่มีข่าว" กับ "ดึงข้อมูลไม่ได้" หน้าตาเหมือนกันหมดถ้าไม่มีอันนี้
export type MacroStatus = {
  key: string;
  label: string;
  state: "ok" | "unreported" | "overdue" | "fetch_failed";
  fetched: boolean;
  latest_ref: string | null;
  seen_ref: string | null;
  due_on: string | null;
  overdue_days: number;
};

export type MacroResponse = {
  releases: MacroRelease[];
  geopolitical: GeoNews[];
  altseason: AltSeason | null;
  status: MacroStatus[];
};

// Phase 27: thesis + invalidation — เดิมเขียนไว้ตั้งแต่ Phase 5 แต่ไม่เคยมี endpoint ให้ frontend
// เรียก (theses ว่างเปล่ามาตลอด) นี่คือระบบ "เตือนขาย": ตั้งเงื่อนไขที่พิสูจน์ว่าคิดผิดไว้ล่วงหน้า
// แล้วให้เครื่องเช็คแบบ deterministic ทุกรอบวิเคราะห์ — ต่างจาก LLM sentiment ตรงที่เป็นกฎที่
// *คุณ* กำหนดเอง ไม่ใช่เครื่องเดา
export type InvalidationRule = { metric: string; op: "<" | "<=" | ">" | ">=" | "==" | "!="; value: number; note: string };

// Phase 30: "เรื่องเล่าที่รอพิสูจน์" — ข้ออ้างจากบทวิเคราะห์/คลิป (เช่น "Bedrock จะดัน AWS")
// ที่ถูกบังคับให้แปลงเป็น เมตริก + เป้า + เส้นตาย ก่อนถึงจะเก็บได้ ข้ออ้างที่ไม่มีวันหมดอายุ =
// ไม่มีวันผิด = ไม่ใช่ thesis (นั่นคือสิ่งที่ฟีเจอร์นี้ตั้งใจกรองออก)
export type Expectation = {
  claim: string;
  metric: string;
  op: InvalidationRule["op"];
  value: number;
  by: string;       // YYYY-MM-DD
  source: string;   // มาจากไหน — ไว้ย้อนดูว่าแหล่งไหนพูดถูกบ่อย
  note: string;
};

export type ExpectationStatus = "hit" | "pending" | "missed" | "unmeasurable";

export type ExpectationCheck = {
  claim: string;
  metric: string;
  target: string;   // "Revenue CAGR >= 20"
  actual: string;   // "11.7 (FY2026)" หรือ "—"
  value: number | null;
  period: string | null;
  by: string;
  days_left: number;
  status: ExpectationStatus;
  status_label: string;
  source: string;
  note: string;
  severity: "warn" | "info";
};

export type ExpectationsResponse = { ticker: string; expectations: ExpectationCheck[]; note: string };

// Phase 31: ตัวแปลข้ออ้าง — วางบทวิเคราะห์ดิบ -> แยกเป็นข้ออ้างย่อย + จัดชั้นว่าอันไหนตรวจได้จริง
// metric ที่เสนอถูกบังคับ (ฝั่ง backend) ให้มาจาก facts จริงของ ticker นั้นเท่านั้น
export type ClaimKind = "checkable" | "needs_data" | "unfalsifiable" | "timing" | "factual";

export type ClaimProposal = {
  claim: string;
  kind: ClaimKind;
  why: string;
  metric: string;
  op: InvalidationRule["op"] | "";
  value: number | null;
  by: string;
  deadline_defaulted: boolean;   // true = เราเติมเส้นตายให้เอง ผู้ใช้ควรยืนยัน
};

export type ClaimExtraction = {
  ticker: string;
  proposals: ClaimProposal[];
  counts: Partial<Record<ClaimKind, number>>;
  kind_labels: Record<ClaimKind, string>;
  n_metrics_available: number;
};

export type Thesis = {
  ticker: string;
  thesis: string;
  invalidation: InvalidationRule[];
  expectations: Expectation[];
  fair_value: number | null;
  created_at: string;
  updated_at: string;
};

// Phase 30: ถือเดิมพันเดียวกันกี่ชั้น — correlation ของผลตอบแทนรายวัน (วัดจริง ไม่ใช่ความเห็น)
export type CorrelationPair = {
  a: string;
  b: string;
  corr: Record<string, number | null>;   // {"90d": 0.74, "1y": 0.71}
  days: Record<string, number>;
  primary: number;
  note: string;
  high: boolean;
  both_held: boolean;                    // ถืออยู่จริงทั้งคู่ = เคสที่ต้องเตือนแรงสุด
  combined_weight: number | null;        // % ของพอร์ตที่คู่นี้กินรวมกัน
};

export type CorrelationResponse = {
  tickers: string[];
  pairs: CorrelationPair[];
  high_pairs: CorrelationPair[];
  summary: {
    n_tickers: number;
    n_pairs: number;
    n_high: number;
    n_high_held: number;
    threshold: number;
    held_weight_in_high: number;
  };
  weights: Record<string, number>;
  caveat: string;
};

export type InvalidationBreach = { type: string; metric: string; detail: string; severity: "alert" | "warn" };

export type InvalidationCheck = {
  ticker: string;
  breaches: InvalidationBreach[];
  no_margin_safety: boolean;
  note: string;
};

// Phase 27: decision journal — จดทุกครั้งที่ตัดสินใจ ซื้อ/ผ่าน/รอ/ขาย รวมถึงตอน "ผ่าน" (เดิมไม่มี
// ที่จดเลย) พร้อม gate2 = ผลเช็คกราฟ/EW ตอนนั้น (free-form note, EW เองแยกเป็นอีกโปรเจกต์) ไว้ย้อน
// วัดทีหลังว่า gate ที่สองนี้ช่วยจริงไหม เทียบกับซื้อทันทีที่ health ถึงเกณฑ์
export type DecisionAction = "buy" | "pass" | "wait" | "sell" | "trim";
export type Gate2Status = "ready" | "not_ready" | "n/a";

export type Decision = {
  id: number;
  ticker: string;
  decided_at: string;
  action: DecisionAction;
  health_score: number | null;
  price: number | null;
  gate2: Gate2Status;
  gate2_note: string;
  reason: string;
  conviction: number | null;
};

// Phase 32: สมุดพกของเอเจนต์เอง — เอาเกณฑ์ที่ใช้จับข้ออ้างคนอื่น (Phase 31) มาจับคะแนนของเราเอง
// gross = ผลรวมของ |การขยับ| ทีละคู่วัน (จับอาการเด้งไปมา), net = หัวถึงท้าย (เด้งกลับแล้วหักล้างกัน)
export type ScoreBuckets = {
  business: number;
  data: number;
  estimate: number;
  price: number;
  method: number;           // Phase 37: โค้ดให้คะแนนคนละเวอร์ชัน / anchor เปลี่ยนแหล่ง
  other: number;
};

export type StabilityRow = {
  ticker: string;
  points: number;
  from: string;
  to: string;
  first_score: number;
  last_score: number;
  max: number;
  low: number;
  high: number;
  swing: number;
  gross: ScoreBuckets;
  net: ScoreBuckets;
  unexplained: number;      // จุดที่ขยับโดยไม่ได้มาจากธุรกิจหรือราคา
  trustworthy: boolean;
  basis_changes: number;    // จำนวนครั้งที่พลิกฐาน /8 <-> /11 (เทียบตรงๆ ไม่ได้)
  method_changes: number;   // จำนวนครั้งที่กติกาให้คะแนนเปลี่ยน — ไม่นับเป็นความไม่นิ่ง แต่ต้องเห็น
  notes: string[];
};

export type ScorecardHorizon = {
  days: number;
  eligible: number;
  ready: boolean;
  days_to_first: number | null;
  first_at: string | null;
};

export type Scorecard = {
  stability: {
    headline: string;
    flagged: number;
    total: number;
    rows: StabilityRow[];
    method_note: string | null;   // null = ไม่มีการแก้กติกาในช่วงที่มีข้อมูล
    engine_version: string;
  };
  prediction: {
    oldest: string | null;
    history_days: number;
    snapshots: number;
    horizons: ScorecardHorizon[];
    ready: boolean;
    caveats: string[];
  };
  bucket_labels: Record<string, string>;
  noise_points: number;
  generated_at: string;
};

// --- Phase 33: เทียบสองสำนัก (Gemini รายวัน vs โมเดลที่แปะในแชทเดือนละครั้ง) ---
// side เดียวกันทั้งสองฝั่งโดยตั้งใจ: ถ้าโครงต่างกัน หน้าเว็บจะเผลอแสดงคนละอย่างให้คนละฝั่ง
// แล้วการ "เทียบ" จะกลายเป็นการเปรียบคนละหน่วยโดยไม่มีใครสังเกต
export type CompareDetail = {
  strength_reasons: number | null;
  weak_points: number | null;
  what_to_watch: number | null;
  thesis_relevant_news: number | null;
  cited_numbers: number | null;
  beginner_summary_chars: number | null;
  thesis_assessment_chars: number | null;
};

export type CompareSide = {
  fundamental_strength: string | null;
  valuation_view: string | null;
  sentiment: string | null;
  confidence: number | null;
  price: number | null;
  price_ok: boolean;
  news_grounded_ratio: number | null;
  facts_grounded_ratio: number | null;
  detail: CompareDetail;
  beginner_summary: string;
  strength_reasons: string[];
  weak_points: { area: string; detail: string }[];
  what_to_watch: string[];
  thesis_assessment: string;
  run_at: string | null;
};

export type CompareRow = {
  ticker: string;
  model: string;
  linked: boolean;                 // จับคู่กับแถวที่ผูกไว้ตอน export (ไม่ได้แปลว่าข้อมูลชุดเดียวกัน)
  data_gap_days: number | null;    // ข้อมูลสองฝั่งห่างกันกี่วัน — null = ไม่มีคู่เทียบ
  same_framework: boolean | null;  // กรอบที่ใช้ตัดสินเวอร์ชันเดียวกันไหม (null = แถวเก่า ไม่รู้)
  claude: CompareSide;
  gemini: CompareSide | null;      // null = เดือนนั้นฝั่งรายวันไม่มีรอบไหนเลย
  agree: Record<string, boolean | null>;
};

export type CompareResult = {
  period: string;
  model: string | null;
  models: string[];
  snapshot_at: string | null;      // เวลาที่ export ข้อมูลออกไป = 'ของเมื่อไหร่'
  imported_at: string | null;
  rows: CompareRow[];
  totals: {
    tickers: number;
    paired: number;
    agree_rate: Record<string, number | null>;
    facts_grounded_avg: { claude: number | null; gemini: number | null };
    news_grounded_avg: { claude: number | null; gemini: number | null };
    detail_avg: { claude: Record<string, number | null>; gemini: Record<string, number | null> };
  };
  disagreements: { ticker: string; field: string; claude: string | null; gemini: string | null }[];
};
