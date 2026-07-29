import { Tip } from "@/lib/glossary";
import type { Health } from "@/lib/health";

// มาตรวัดสุขภาพธุรกิจ -> 5 จุด (สัดส่วนจาก score/max) + ตัวเลข + ป้าย, สีตาม tier
// hover เพื่อดูที่มาของคะแนน (โปร่งใส ไม่ใช่กล่องดำ). score=null (Phase 18 'excluded' — ข้อมูล
// ไม่พอ/crypto ไม่เข้าเกณฑ์ screen นี้) -> โชว์ '—' แทนตัวเลข ไม่มี dot ไหนติด
//
// Phase 29: คะแนน partial (พื้นฐานล้วน /8 เพราะประเมินราคาไม่ได้) ต้อง **โชว์ตัวหารเสมอ** —
// สัดส่วน dot ถูกอยู่แล้วเพราะหารด้วย max จริง แต่ตัวเลขลอยๆ '6.5' จะถูกอ่านว่า 6.5/11 ทันที
// ถ้าไม่บอก (นี่คือจุดที่ทำให้ 'มีคะแนนดีกว่าว่างเปล่า' ไม่กลายเป็น 'ตัวเลขที่หลอกตัวเอง')
export function HealthMeter({ health, size = "md" }: { health: Health; size?: "sm" | "md" }) {
  const filled = health.score == null ? 0 : Math.round((health.score / health.max) * 5);
  const dots = Array.from({ length: 5 }, (_, i) => i < filled);
  const tip = health.partial
    ? "คะแนนพื้นฐานล้วน (ไม่มีขาราคา — ประเมิน reverse-DCF ไม่ได้):\n" + health.reasons.join("\n")
    : "คะแนนสุขภาพธุรกิจ (heuristic โปร่งใส ไม่ใช่คำแนะนำซื้อขาย):\n" + health.reasons.join("\n");
  return (
    <Tip def={tip}>
      <span className={`health health-${health.tier} health-${size}${health.partial ? " health-partial" : ""}`}>
        <span className="health-dots">
          {dots.map((on, i) => (
            <span key={i} className={`hdot${on ? " on" : ""}`} />
          ))}
        </span>
        <span className="health-num">
          {health.score == null ? "—" : health.score.toFixed(1)}
          {health.partial && <span className="health-den">/{health.max}</span>}
        </span>
        <span className="health-label">{health.partial ? "พื้นฐานล้วน" : health.label}</span>
      </span>
    </Tip>
  );
}
