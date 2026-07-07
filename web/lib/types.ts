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
  beginner_summary?: string; // optional: แถวเก่าก่อน Phase 2.5 จะไม่มี field นี้
};

export type WatchlistItem = {
  ticker: string;
  asset_type: string;
  added_at: string;
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
  summary: Summary;
};
