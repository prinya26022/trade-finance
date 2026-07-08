import type { Analysis, WatchlistItem, ChangeReport, Portfolio } from "./types";

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
