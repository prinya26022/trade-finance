import type { Analysis, WatchlistItem, ChangeReport, Portfolio, Investigation, InvestigationJob, Timeline, ScreenerResponse, HealthTrends, ChatAnswer, MacroResponse, Thesis, InvalidationRule, InvalidationCheck, Decision, DecisionAction, Gate2Status } from "./types";

// ที่อยู่ FastAPI — override ด้วย NEXT_PUBLIC_API_BASE ได้ ไม่งั้น default localhost:8000
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function getAnalyses(): Promise<Analysis[]> {
  // no-store: ดึงสดทุกครั้ง (dashboard ต้องเห็นผลรันล่าสุด ไม่เอา cache)
  const res = await fetch(`${API_BASE}/api/analyses`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const res = await fetch(`${API_BASE}/api/watchlist`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function getChanges(): Promise<ChangeReport[]> {
  const res = await fetch(`${API_BASE}/api/changes`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function getTickerChanges(ticker: string): Promise<ChangeReport> {
  const res = await fetch(`${API_BASE}/api/changes/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// Phase 23: แนวโน้ม health N จุดล่าสุด/ticker (เบา, ไว้วาด sparkline) — ticker ที่ไม่มี key = ยังไม่มี
// รอบวิเคราะห์ที่คำนวณ health ได้ (แถวเก่า/excluded), frontend แสดงไม่ได้ก็แค่ไม่วาด
export async function getHealthTrends(limit = 20): Promise<HealthTrends> {
  const res = await fetch(`${API_BASE}/api/health-trends?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function getPortfolio(): Promise<Portfolio> {
  const res = await fetch(`${API_BASE}/api/portfolio`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// ประวัติวิเคราะห์ของ ticker เดียว (ใหม่ก่อน) — ไว้ทำหน้า detail + กราฟ trend
export async function getHistory(ticker: string): Promise<Analysis[]> {
  const res = await fetch(`${API_BASE}/api/analyses/${ticker}`, { cache: "no-store" });
  if (res.status === 404) return []; // ยังไม่เคยวิเคราะห์ ticker นี้
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// transcript การสืบล่าสุดของ agent (Phase 13) — null ถ้ายังไม่เคยสืบ ticker นี้
export async function getInvestigation(ticker: string): Promise<Investigation | null> {
  const res = await fetch(`${API_BASE}/api/investigation/${ticker}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// Phase 28: สั่ง agent สืบใหม่ — ยิง Gemini จริง (เหมือน askChat) ทำงานเบื้องหลัง คืน job ทันที
// ไม่รอจนสืบเสร็จ แล้วให้ pollInvestigation ตามความคืบหน้าต่อ. 409 = ของเดิมยังวิ่งอยู่
export async function startInvestigation(ticker: string, focus = ""): Promise<InvestigationJob> {
  const res = await fetch(`${API_BASE}/api/investigation/${ticker}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ focus }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

// สถานะงานสืบล่าสุด — null ถ้าไม่มี job ใน process ของ API ตอนนี้ (เช่น เพิ่งรีสตาร์ท backend)
export async function getInvestigationStatus(ticker: string): Promise<InvestigationJob | null> {
  const res = await fetch(`${API_BASE}/api/investigation/${ticker}/status`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// ชีวประวัติบริษัท (Phase 14) — เหตุการณ์ material หลายปี + เรื่องเล่า (narrative อาจ null)
export async function getTimeline(ticker: string): Promise<Timeline | null> {
  const res = await fetch(`${API_BASE}/api/timeline/${ticker}`, { cache: "no-store" });
  if (!res.ok) return null; // timeline ล้ม (EDGAR ล่ม) ไม่ควรทำหน้า detail พังทั้งหน้า
  return res.json();
}

// Phase 21: screener — force=true สแกนใหม่ทั้งก้อน (ช้า, นาทีระดับ) ใช้ตอนกดปุ่ม 'รีเฟรช' เอง
// เท่านั้น — ปกติอ่าน cache (เร็ว) จึงไม่ใช้ no-store (อยากได้ response ตาม cache ฝั่ง backend จริง)
export async function getScreener(force = false): Promise<ScreenerResponse> {
  const res = await fetch(`${API_BASE}/api/screener?force=${force}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// Phase 25: ถามพอร์ตได้เลย — ยิง Gemini จริง (มีโควตา) ทุกครั้งที่เรียก ต่างจาก mutation อื่นด้านล่าง
// history = เทิร์นก่อนหน้าในสนทนาเดียวกัน (state ฝั่ง client เท่านั้น ไม่มี persistence ฝั่ง backend)
export async function askChat(
  question: string,
  history: { role: string; text: string }[]
): Promise<ChatAnswer> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

// --- mutations (เรียกจาก client component) — ไม่ยิง LLM จึงไม่กินโควตา ---
export async function addToWatchlist(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`${res.status}: ${msg}`);
  }
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}

// --- holding management (Phase 11) — แทน CLI hold/add/watch ---
export async function setHolding(
  ticker: string,
  body: { entry_price: number; entry_date?: string | null; shares?: number | null }
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}/holding`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

export async function addShares(
  ticker: string,
  body: { price: number; shares: number }
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}/holding/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

// ขายออก/เลิกถือ -> กลับเป็น watching (ยังอยู่ใน watchlist)
export async function sellHolding(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}/holding`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}

// แช่แข็ง — ขายหมดแล้วแต่อยากดูว่าฟื้นไหม โดยไม่เปลืองโควตา (analyze() รอบเดือนแทนรายวัน)
export async function freezeTicker(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}/freeze`, { method: "PUT" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}

// ยกเลิกแช่แข็ง -> กลับเป็น watching (วิเคราะห์รายวันเหมือนเดิม)
export async function unfreezeTicker(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${ticker}/freeze`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}

// Phase 26: Macro Event Radar — ดึงสด (FRED+yfinance+Google News), ช้ากว่าปกติ ~ไม่กี่วิ ไม่เรียก LLM
export async function getMacro(horizonDays = 1): Promise<MacroResponse> {
  const res = await fetch(`${API_BASE}/api/macro?horizon_days=${horizonDays}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// --- Phase 27: thesis / invalidation ---
export async function getThesis(ticker: string): Promise<Thesis | null> {
  const res = await fetch(`${API_BASE}/api/thesis/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  const data = await res.json();
  return data ?? null; // backend คืน null (200) ถ้ายังไม่เคยตั้ง
}

export async function setThesis(
  ticker: string,
  body: { thesis: string; invalidation: InvalidationRule[]; fair_value: number | null }
): Promise<Thesis> {
  const res = await fetch(`${API_BASE}/api/thesis/${ticker}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function deleteThesis(ticker: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/thesis/${ticker}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}`);
}

export async function getInvalidation(ticker: string): Promise<InvalidationCheck> {
  const res = await fetch(`${API_BASE}/api/invalidation/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

// --- Phase 27: decision journal ---
export async function getDecisions(ticker: string): Promise<Decision[]> {
  const res = await fetch(`${API_BASE}/api/decisions/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function logDecision(
  ticker: string,
  body: { action: DecisionAction; gate2: Gate2Status; gate2_note: string; reason: string; conviction: number | null }
): Promise<Decision> {
  const res = await fetch(`${API_BASE}/api/decisions/${ticker}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}
