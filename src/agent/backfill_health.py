"""Backfill script (one-time, Phase 17): recompute health_score/health_reasons_json
สำหรับทุกแถวประวัติที่มีอยู่แล้ว ด้วยสูตรใหม่ (Piotroski strength + reverse-DCF valuation)
แทนสูตร Phase 10 เดิม (bucket lookup ล้วนๆ) — ให้คะแนนย้อนหลังทั้งหมดยืนอยู่บนพื้นฐานเดียวกัน
ไม่ใช่ครึ่งนึงสูตรเก่าครึ่งนึงสูตรใหม่ (ถ้าไม่ backfill กราฟ health trend จะมีรอยต่อหลอกๆ
ตรงวันที่ deploy สูตรใหม่ ทั้งที่ธุรกิจไม่ได้เปลี่ยนอะไรเลย).

ไม่เรียก LLM/network เลย — facts/summary ของแต่ละแถวถูกเก็บไว้แล้วตอน analyze() ครั้งนั้นๆ
(point-in-time ถูกต้อง: ใช้ตัวเลข ณ เวลานั้นจริง ไม่ใช่ดึงข้อมูลปัจจุบันมาคำนวณย้อนหลังซึ่งจะผิดเวลา).

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


def _had_breach(old_health: dict | None) -> bool:
    if not old_health:
        return False
    return any("โดนแตะ" in r for r in old_health.get("reasons", []))


def backfill(apply: bool = False) -> None:
    rows = all_rows()
    changed = 0
    skipped = 0
    for row in rows:
        try:
            summary = SimpleNamespace(**row["summary"])
            facts = row.get("facts") or []
            breaches = [{"severity": "alert"}] if _had_breach(row.get("health")) else []
            new_health = compute_health(summary, breaches, facts)
        except Exception as e:   # แถวเก่าผิดปกติ/schema เก่าจนขาด field -> ข้าม ไม่ให้ตัวเดียวล้มทั้ง batch
            print(f"[skip] {row.get('ticker')} id={row.get('id')}: {e}")
            skipped += 1
            continue

        old_score = row.get("health_score")
        new_score = new_health["score"]
        if old_score != new_score:
            changed += 1
            old_str = f"{old_score:.1f}" if old_score is not None else "N/A"
            print(f"{row['ticker']:6} {row['run_at']}  {old_str:>5} -> {new_score:.1f}")

        if apply:
            update_health(row["id"], new_health)

    mode = "APPLIED" if apply else "DRY-RUN (ไม่เขียน DB — รันด้วย --apply เพื่อเขียนจริง)"
    print(f"\n{mode}: {changed}/{len(rows)} แถวคะแนนเปลี่ยน, {skipped} แถวข้าม (error)")


if __name__ == "__main__":
    backfill(apply="--apply" in sys.argv)