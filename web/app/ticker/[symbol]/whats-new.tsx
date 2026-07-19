import type { Change } from "@/lib/types";
import { GlossaryText } from "@/lib/glossary";

// Phase 22: "เปลี่ยนแปลงตั้งแต่ครั้งก่อน" ยกขึ้นเป็นสิ่งแรกที่เห็นในหน้า ticker detail — เดิม
// (Phase 3) changes.py คำนวณไว้ครบแล้วแต่ฝังอยู่ท้ายหน้า (ใต้ valuation box) ทำให้ของที่มีค่าที่สุด
// สำหรับการ "กลับมาอ่านซ้ำ" (มีอะไรใหม่ตั้งแต่ครั้งก่อนไหม) ไม่ถูกมองเห็นก่อน
// ความเงียบ = ปกติ (ตามหลักโปรเจกต์ "ข่าวรายวันคือ noise") แต่ในหน้า UI ความเงียบต้อง "ยืนยันตัวเอง"
// (บอกว่าเช็คแล้วไม่มีอะไร ไม่ใช่แค่ไม่แสดงอะไรเฉยๆ ซึ่งดูเหมือนฟีเจอร์พัง) จึงมี calm-state ข้อความ
// ชัดเจนแทนการ render ว่างเปล่า

const SEVERITY_ICON: Record<string, string> = { alert: "🚨", warn: "⚠️", info: "ℹ️" };

function relativeDate(iso: string): string {
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "วันนี้";
  if (days === 1) return "เมื่อวาน";
  if (days < 30) return `${days} วันที่แล้ว`;
  return `${Math.round(days / 30)} เดือนที่แล้ว`;
}

export function WhatsNew({
  changes,
  from,
  to,
  note,
}: {
  changes: Change[];
  from?: string;
  to?: string;
  note?: string;
}) {
  return (
    <div className="whats-new">
      <div className="whats-new-head">
        <span className="whats-new-title">🔎 เปลี่ยนแปลงตั้งแต่ครั้งก่อน</span>
        {from && to ? (
          <span className="whats-new-range">{relativeDate(from)} → {relativeDate(to)}</span>
        ) : note ? (
          <span className="whats-new-range">{note}</span>
        ) : null}
      </div>
      {changes.length === 0 ? (
        <p className="whats-new-calm">✓ ไม่มีอะไรสำคัญเปลี่ยน — พื้นฐาน/ราคา/เงื่อนไขออกยังเหมือนเดิม</p>
      ) : (
        <ul className="whats-new-list">
          {changes.map((c, i) => (
            <li key={i} className={`whats-new-item wn-${c.severity}`}>
              <span className="wn-icon">{SEVERITY_ICON[c.severity] ?? "•"}</span>
              <GlossaryText text={c.detail} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
