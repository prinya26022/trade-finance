import type { Analysis, WatchlistItem, ChangeReport, Portfolio, Investigation, Timeline } from "./types";

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

// ชีวประวัติบริษัท (Phase 14) — เหตุการณ์ material หลายปี + เรื่องเล่า (narrative อาจ null)
export async function getTimeline(ticker: string): Promise<Timeline | null> {
  const res = await fetch(`${API_BASE}/api/timeline/${ticker}`, { cache: "no-store" });
  if (!res.ok) return null; // timeline ล้ม (EDGAR ล่ม) ไม่ควรทำหน้า detail พังทั้งหน้า
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
