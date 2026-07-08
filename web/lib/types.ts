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
export type EdgePosition = {
  ticker: string;
  benchmark: string;
  entry_price: number;
  entry_date: string;
  current_price: number;
  your_return: number; // %
  benchmark_return: number; // %
  edge: number; // % (บวก = ชนะ index)
  holding_days: number;
};

export type Portfolio = {
  benchmark: string;
  positions: EdgePosition[];
  beating_benchmark: number;
  total_positions: number;
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
  facts: Fact[]; // ตัวเลขงบดิบหลายปี (ว่างถ้าแถวเก่าก่อน Phase 3) — ใช้ทำกราฟ trend
  summary: Summary;
};
