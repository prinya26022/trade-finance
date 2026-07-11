import { Tip } from "@/lib/glossary";
import type { Health } from "@/lib/health";

// มาตรวัดสุขภาพธุรกิจ -> 5 จุด (สัดส่วนจาก score/max) + ตัวเลข + ป้าย, สีตาม tier
// hover เพื่อดูที่มาของคะแนน (โปร่งใส ไม่ใช่กล่องดำ). score=null (Phase 18 'excluded' — ข้อมูล
// ไม่พอ/ขาดทุน/crypto ไม่เข้าเกณฑ์ screen นี้) -> โชว์ '—' แทนตัวเลข ไม่มี dot ไหนติด
export function HealthMeter({ health, size = "md" }: { health: Health; size?: "sm" | "md" }) {
  const filled = health.score == null ? 0 : Math.round((health.score / health.max) * 5);
  const dots = Array.from({ length: 5 }, (_, i) => i < filled);
  return (
    <Tip def={"คะแนนสุขภาพธุรกิจ (heuristic โปร่งใส ไม่ใช่คำแนะนำซื้อขาย):\n" + health.reasons.join("\n")}>
      <span className={`health health-${health.tier} health-${size}`}>
        <span className="health-dots">
          {dots.map((on, i) => (
            <span key={i} className={`hdot${on ? " on" : ""}`} />
          ))}
        </span>
        <span className="health-num">{health.score == null ? "—" : health.score.toFixed(1)}</span>
        <span className="health-label">{health.label}</span>
      </span>
    </Tip>
  );
}
