"""เติมป้ายเวอร์ชันเอนจิ้นให้แถว analyses ที่บันทึกไว้ก่อน Phase 37 โดยอ่านจากประวัติ git.

ทำไมต้องมี: ป้ายที่เริ่มนับตั้งแต่วันนี้จะอ่านประวัติที่มีอยู่ไม่ได้เลย และประวัติที่มีอยู่คือช่วงที่
เอนจิ้นถูกรื้อหนักที่สุด — 18 คอมมิตแตะ health.py/valuation.py/grading.py ระหว่าง 2026-07-06
ถึง 2026-08-10 ซึ่งเป็นช่วงเดียวกับที่ analyses ทั้ง 357 แถวเกิด. ถ้าไม่เติมย้อนหลัง สมุดพกจะยัง
สรุปว่า "7 จาก 16 ตัวคะแนนขยับโดยอธิบายไม่ได้" ทั้งที่คำอธิบายนอนอยู่ใน git log

วิธี: ไล่คอมมิตที่แตะไฟล์ในชุด -> ดึงซอร์ส ณ คอมมิตนั้นมาคำนวณเวอร์ชันด้วย "สูตรเดียวกับ
โปรดักชัน" (src.agent.engine_version.parts_from/version_from ไม่ใช่โค้ดลอก) -> แถวไหนรันตอนไหน
ก็ได้เวอร์ชันของคอมมิตล่าสุดที่ <= เวลานั้น

ความคลาดเคลื่อนที่ยอมรับ และทิศทางของมัน (สำคัญกว่าตัวเลขความแม่น):
  * รอบ CI รายวันใช้โค้ดที่คอมมิตแล้วเสมอ -> ตรงเป๊ะ
  * รอบที่รันมือระหว่างพัฒนาอาจใช้โค้ดที่ยังไม่ได้คอมมิต -> จะได้ป้ายของคอมมิตก่อนหน้า
    = "มองไม่เห็นการเปลี่ยน" ไม่ใช่ "เห็นการเปลี่ยนที่ไม่มีจริง"
  ความผิดพลาดจึงเอนไปทางรายงานน้อยกว่าความจริงเสมอ ซึ่งเป็นทิศที่ปลอดภัยกว่าสำหรับป้ายที่มีไว้
  บอกว่า "อย่าเพิ่งเชื่อการเทียบช่วงนี้"

แถวที่เก่ากว่าคอมมิตแรกของ health.py จะถูกปล่อยเป็น NULL ต่อไป — NULL แปลว่า "ไม่รู้" ซึ่งเป็น
ความจริง ส่วนการเดาแล้วเขียนลงไปจะทำให้ NULL ที่เหลือแยกไม่ออกระหว่าง "ไม่รู้" กับ "รู้แล้วว่าเก่า"

    python scripts/backfill_engine_version.py            # ดูอย่างเดียว ไม่เขียน
    python scripts/backfill_engine_version.py --apply    # เขียนจริง (แตะเฉพาะแถวที่ยังเป็น NULL)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agent.engine_version import SCORING_MODULES, parts_from, version_from  # noqa: E402
from src.history.store import _connect, init_db  # noqa: E402

ROOT = Path(__file__).parents[1]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def _commits() -> list[tuple[str, str]]:
    """[(committer_date_iso, sha)] เก่า -> ใหม่ ของคอมมิตที่แตะไฟล์ในชุด.

    ใช้ committer date (%cI) ไม่ใช่ author date: rebase/cherry-pick ทำให้ author date ย้อนหลังไป
    ก่อนวันที่โค้ดนั้นมีอยู่บน main จริง แล้วแถวที่รันด้วยโค้ดเก่าจะถูกติดป้ายของโค้ดใหม่.
    """
    out = _git("log", "--reverse", "--format=%cI %H", "--", *SCORING_MODULES)
    rows = []
    for line in out.splitlines():
        when, _, sha = line.partition(" ")
        if sha:
            rows.append((when[:19], sha))     # ตัด timezone ทิ้งให้เทียบกับ run_at (local, ไม่มี tz) ได้
    return rows


def _version_at(sha: str) -> str | None:
    """เวอร์ชันของกติกา ณ คอมมิตนั้น (None ถ้ายังไม่มีไฟล์ในชุดเลยสักไฟล์)."""
    sources: dict[str, str] = {}
    for path in SCORING_MODULES:
        try:
            sources[path] = _git("show", f"{sha}:{path}")
        except subprocess.CalledProcessError:
            pass                              # ไฟล์ยังไม่ถูกสร้างตอนนั้น (เช่น grading.py ก่อน 19.3)
    return version_from(parts_from(sources)) if sources else None


def timeline() -> list[tuple[str, str]]:
    """[(เวลาที่มีผล, เวอร์ชัน)] เก่า -> ใหม่ โดยยุบคอมมิตที่ไม่ได้เปลี่ยนกติกาจริงออก.

    การยุบสำคัญ: คอมมิตส่วนใหญ่ที่แตะไฟล์พวกนี้แก้แต่คอมเมนต์/docstring ซึ่งไม่ใช่การเปลี่ยน
    กติกา ถ้าไม่ยุบ ประวัติจะเต็มไปด้วย "แก้กติกา" ปลอมจนถังนี้ไม่มีความหมาย.
    """
    out: list[tuple[str, str]] = []
    for when, sha in _commits():
        version = _version_at(sha)
        if version and (not out or out[-1][1] != version):
            out.append((when, version))
    return out


def _version_for(run_at: str, tl: list[tuple[str, str]]) -> str | None:
    """เวอร์ชันของคอมมิตล่าสุดที่ <= เวลารัน (None = แถวเก่ากว่าคอมมิตแรก = ไม่รู้จริงๆ)."""
    found = None
    for when, version in tl:
        if when <= run_at:
            found = version
        else:
            break
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="เขียนลง DB จริง (ไม่ใส่ = ดูอย่างเดียว)")
    args = ap.parse_args()

    tl = timeline()
    print(f"กติกาเปลี่ยนจริง {len(tl)} ครั้งตามประวัติ git:")
    for when, version in tl:
        print(f"  {when}  {version}")

    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, ticker, run_at FROM analyses WHERE engine_version IS NULL ORDER BY run_at"
        ).fetchall()

        plan = [(r["id"], _version_for(r["run_at"], tl)) for r in rows]
        filled = [(i, v) for i, v in plan if v]
        counts: dict[str, int] = {}
        for _, v in filled:
            counts[v] = counts.get(v, 0) + 1

        print(f"\nแถวที่ยังไม่มีป้าย {len(rows)} แถว -> เติมได้ {len(filled)} "
              f"(เหลือ {len(rows) - len(filled)} แถวที่เก่ากว่าคอมมิตแรก = ปล่อยเป็น NULL)")
        for version, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {version}  {n} แถว")

        if not args.apply:
            print("\n(ดูอย่างเดียว — ใส่ --apply เพื่อเขียนจริง)")
            return 0

        conn.executemany("UPDATE analyses SET engine_version = ? WHERE id = ?",
                         [(v, i) for i, v in filled])
    print(f"\nเขียนแล้ว {len(filled)} แถว")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
