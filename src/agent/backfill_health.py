"""Backfill script (Phase 17 -> Phase 18): recompute health_score/health_reasons_json
สำหรับทุกแถวประวัติที่มีอยู่แล้ว ด้วยสูตรปัจจุบัน (ตอนนี้คือ Phase 18: Piotroski fixed-/8 +
reverse-DCF /3 + news /1, ตาม scoring_spec.md) แทนสูตรเก่า — ให้คะแนนย้อนหลังทั้งหมดยืนอยู่บน
พื้นฐานเดียวกัน ไม่ใช่ครึ่งนึงสูตรเก่าครึ่งนึงสูตรใหม่ (ถ้าไม่ backfill กราฟ health trend จะมีรอยต่อ
หลอกๆ ตรงวันที่ deploy สูตรใหม่ ทั้งที่ธุรกิจไม่ได้เปลี่ยนอะไรเลย).

ไม่เรียก LLM เลย — facts/summary ของแต่ละแถวถูกเก็บไว้แล้วตอน analyze() ครั้งนั้นๆ (point-in-time
ถูกต้อง: ใช้ตัวเลข ณ เวลานั้นจริง ไม่ใช่ดึงข้อมูลปัจจุบันมาคำนวณย้อนหลังซึ่งจะผิดเวลา). เรียก
get_risk_free_rate_pct() ครั้งเดียว (เครือข่าย 1 ครั้ง, cache 1 วัน) ใช้ร่วมกันทุกแถว — Rf ปัจจุบัน
ใกล้เคียงกว่าค่า fallback ตายตัว แม้จะไม่ใช่ Rf ณ วันที่วิเคราะห์จริงเป๊ะๆ (ไม่มี snapshot ย้อนหลัง).

สำคัญ (Phase 18): แถวเก่าจำนวนมาก 'จะกลายเป็น excluded' หลัง backfill นี้ — ไม่ใช่ bug แต่เพราะ
Piotroski เกณฑ์ใหม่ต้องการ Fact ที่เพิ่งเพิ่ม (CFO, Net Income, Beta, ROE/leverage/liquidity
series) ซึ่ง facts_json ของแถวเก่า (ก่อน Phase 18) ไม่มีเก็บไว้ — คำนวณย้อนหลังให้ไม่ได้จริงๆ
(ข้อมูลไม่มีอยู่จริง ไม่ใช่คำนวณผิด) จะกลับมาสมบูรณ์เองเมื่อ analyze() รอบใหม่บันทึก facts ชุดใหม่.

breach_penalty ของแต่ละแถวเก่า 'คงสภาพเดิมไว้' ไม่ recompute ใหม่ เพราะ invalidation เช็ค
กับ thesis/rule ปัจจุบัน ไม่มี snapshot ของ thesis ณ เวลานั้นเก็บไว้ (recompute จะผิดเวลาได้ ถ้า
thesis เปลี่ยนไปแล้ว) — จึงอ่านจาก reasons เดิมว่าตอนนั้นโดน breach ไหม แล้วส่งต่อให้สูตรใหม่
คำนวณ penalty ให้เหมือนเดิม.

ใช้:  python -m src.agent.backfill_health          (dry-run, แค่ print diff ไม่เขียน DB)
      python -m src.agent.backfill_health --apply  (เขียนจริง)
"""
import sys
from types import SimpleNamespace

from src.agent.health import compute_health
from src.history.store import all_rows, update_health
from src.providers.stock.market import get_risk_free_rate_pct


def _had_breach(old_health: dict | None) -> bool:
    if not old_health:
        return False
    return any("โดนแตะ" in r for r in old_health.get("reasons", []))


def _fmt(score) -> str:
    return f"{score:.1f}" if score is not None else "excluded"


def backfill(apply: bool = False) -> None:
    risk_free_pct = get_risk_free_rate_pct()
    rows = all_rows()
    changed = 0
    skipped = 0
    for row in rows:
        try:
            summary = SimpleNamespace(**row["summary"])
            facts = row.get("facts") or []
            breaches = [{"severity": "alert"}] if _had_breach(row.get("health")) else []
            new_health = compute_health(summary, breaches, facts, risk_free_pct)
        except Exception as e:   # แถวเก่าผิดปกติ/schema เก่าจนขาด field -> ข้าม ไม่ให้ตัวเดียวล้มทั้ง batch
            print(f"[skip] {row.get('ticker')} id={row.get('id')}: {e}")
            skipped += 1
            continue

        old_score = row.get("health_score")
        new_score = new_health["score"]
        if old_score != new_score:
            changed += 1
            print(f"{row['ticker']:6} {row['run_at']}  {_fmt(old_score):>9} -> {_fmt(new_score)}")

        if apply:
            update_health(row["id"], new_health)

    mode = "APPLIED" if apply else "DRY-RUN (ไม่เขียน DB — รันด้วย --apply เพื่อเขียนจริง)"
    print(f"\n{mode} (Rf={risk_free_pct:.2f}%): {changed}/{len(rows)} แถวคะแนนเปลี่ยน, {skipped} แถวข้าม (error)")


if __name__ == "__main__":
    backfill(apply="--apply" in sys.argv)