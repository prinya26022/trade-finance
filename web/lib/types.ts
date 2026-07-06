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
  summary: Summary;
};
