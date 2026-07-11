import { Tip } from "@/lib/glossary";
import type { Health } from "@/lib/health";

// มาตรวัดสุขภาพธุรกิจ 0–10 -> 5 จุด (แต่ละจุด = 2 คะแนน) + ตัวเลข + ป้าย, สีตาม tier
// hover เพื่อดูที่มาของคะแนน (โปร่งใส ไม่ใช่กล่องดำ)
export function HealthMeter({ health, size = "md" }: { health: Health; size?: "sm" | "md" }) {
  const filled = Math.round(health.score / 2); // 0–5
  const dots = Array.from({ length: 5 }, (_, i) => i < filled);
  return (
    <Tip def={"คะแนนสุขภาพธุรกิจ (heuristic โปร่งใส ไม่ใช่คำแนะนำซื้อขาย):\n" + health.reasons.join("\n")}>
      <span className={`health health-${health.tier} health-${size}`}>
        <span className="health-dots">
          {dots.map((on, i) => (
            <span key={i} className={`hdot${on ? " on" : ""}`} />
          ))}
        </span>
        <span className="health-num">{health.score.toFixed(1)}</span>
        <span className="health-label">{health.label}</span>
      </span>
    </Tip>
  );
}
