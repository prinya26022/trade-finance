import type { Analysis } from "./types";

// ที่อยู่ FastAPI — override ด้วย NEXT_PUBLIC_API_BASE ได้ ไม่งั้น default localhost:8000
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function getAnalyses(): Promise<Analysis[]> {
  // no-store: ดึงสดทุกครั้ง (dashboard ต้องเห็นผลรันล่าสุด ไม่เอา cache)
  const res = await fetch(`${API_BASE}/api/analyses`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
