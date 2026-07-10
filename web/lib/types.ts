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
  status: "watching" | "holding";
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
  your_return: number; // %
  benchmark_return: number; // %
  edge: number; // % (บวก = ชนะ index)
  holding_days: number;
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
export type PersistedHealth = {
  score: number;
  tier: "strong" | "ok" | "weak";
  label: string;
  reasons: string[];
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
  summary: Summary;
};
