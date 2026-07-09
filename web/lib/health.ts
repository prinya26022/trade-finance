// Health score 0–10 — สรุป 'สุขภาพธุรกิจโดยรวม' จากสัญญาณที่ AI/eval สรุปมาแล้ว
// เป็น heuristic แบบ deterministic + โปร่งใส (โชว์ที่มาได้ทาง tooltip) — ไม่เรียก LLM ซ้ำ
// ไม่ใช่คำแนะนำซื้อขาย: เป็นแค่ 'ภาพรวมคุณภาพ' ให้ triage ง่ายขึ้น
//
// Phase 10: Python (src/agent/health.py) เป็น source of truth แล้ว — คำนวณตอน analyze()
// และเก็บทุกแถวประวัติ (ดู trend + debug คะแนนเด้งผิดปกติได้). ฟังก์ชัน healthScore() ที่นี่
// เหลือไว้เป็น fallback สำหรับแถวเก่าก่อน Phase 10 เท่านั้น (a.health เป็น null) — สูตรต้องตรง
// กับฝั่ง Python เป๊ะ ถ้าแก้ที่นี่ต้องแก้ src/agent/health.py ด้วย.
import type { Analysis, Change } from "./types";

export type Health = {
  score: number; // 0–10 (ปัด 1 ตำแหน่ง)
  tier: "strong" | "ok" | "weak"; // ไว้เลือกสี
  label: string; // ป้ายไทยสั้นๆ
  reasons: string[]; // ที่มาของคะแนน (โชว์ใน tooltip)
};

const STRENGTH_PTS: Record<string, number> = { strong: 4, mixed: 2, weak: 0 };
const VALUATION_PTS: Record<string, number> = { cheap: 3, fair: 2, unclear: 1.5, expensive: 0.5 };
const SENTIMENT_PTS: Record<string, number> = { bullish: 2, neutral: 1, bearish: 0 };

export function healthScore(a: Analysis, changes: Change[] = []): Health {
  const s = a.summary;
  const reasons: string[] = [];

  const strength = STRENGTH_PTS[s.fundamental_strength] ?? 2;
  reasons.push(`พื้นฐาน ${s.fundamental_strength} (+${strength}/4)`);

  const valuation = VALUATION_PTS[s.valuation_view] ?? 1.5;
  reasons.push(`ราคา ${s.valuation_view} (+${valuation}/3)`);

  const sentiment = SENTIMENT_PTS[s.sentiment] ?? 1;
  reasons.push(`มุมมอง ${s.sentiment} (+${sentiment}/2)`);

  const confPts = Math.max(0, Math.min(1, a.confidence)); // 0–1 ตามความมั่นใจ AI
  reasons.push(`ความมั่นใจข้อมูล ${a.confidence} (+${confPts.toFixed(1)}/1)`);

  let score = strength + valuation + sentiment + confPts; // เต็ม 10

  // เงื่อนไขออก (invalidation breach) โดนแตะ = หักหนัก เพราะ thesis สั่น
  const hasBreach = changes.some((c) => c.severity === "alert");
  if (hasBreach) {
    score -= 3;
    reasons.push("เงื่อนไขออกโดนแตะ (−3)");
  }

  score = Math.max(0, Math.min(10, score));
  const rounded = Math.round(score * 10) / 10;
  const tier = rounded >= 7 ? "strong" : rounded >= 4.5 ? "ok" : "weak";
  const label = tier === "strong" ? "แข็งแรง" : tier === "ok" ? "พอใช้" : "อ่อน";

  return { score: rounded, tier, label, reasons };
}

// ใช้ค่าที่ persist มาจาก Python ถ้ามี (แถวใหม่ทุกแถวหลัง Phase 10) ไม่งั้น fallback คำนวณสด
// (แถวเก่า) — เรียกอันนี้แทน healthScore() ตรงๆ ในหน้า UI ทั้งหมด
export function resolveHealth(a: Analysis, changes: Change[] = []): Health {
  if (a.health) return a.health;
  return healthScore(a, changes);
}
