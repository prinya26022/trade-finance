"""ป้ายเวอร์ชันของโค้ดที่ให้คะแนน (Phase 37). Offline ล้วน ไม่แตะ DB/เครือข่าย.

ที่มา: framework_version (33.2) ติดฐานให้ prompt แต่เลข /11 ที่ผู้ใช้อ่านมาจาก health.py/
valuation.py ซึ่งเปลี่ยนไป 4 ครั้งใน 3 เฟสโดยไม่มีอะไรบันทึกไว้ — รอบถัดไป scorecard จะเห็น CVX
ขยับแล้วบอกว่า "ประมาณการของเราเปลี่ยน" ทั้งที่ความจริงคือ "เราเปลี่ยนวิธีคิดเมื่อวาน".

ป้ายแบบนี้ล้มเหลวได้สองทาง และเทสต์ชุดนี้จ่อไว้ทั้งสองทาง:
  (1) ไม่เด้งตอนกติกาเปลี่ยน  -> กติกาเปลี่ยนเงียบๆ = ปัญหาเดิมที่ยังอยู่
  (2) เด้งตอนไม่มีอะไรเปลี่ยน  -> ธงขึ้นทุกวัน = ไม่มีข้อมูลเหมือนไม่มีธง แถมกลบการขยับจริง
"""
import ast

import pytest

from src.agent import engine_version as ev


@pytest.fixture(autouse=True)
def _fresh():
    """ฟังก์ชันจริง cache ไว้ (อ่านไฟล์ทุกครั้งที่บันทึกผลคงเปลืองเปล่า) — เทสต์ต้องเห็นของใหม่เสมอ."""
    ev.clear_cache()
    yield
    ev.clear_cache()


# ---------- ต้องเด้งเมื่อกติกาเปลี่ยน ----------

def test_changing_a_threshold_changes_the_version():
    """เคสรูปธรรมที่สุด: ปรับตัวเลข threshold หนึ่งตัว = หุ้นทุกตัวได้คะแนนใหม่."""
    before = ev.normalize("ROIC_MIN = 8.0\ndef f(x):\n    return x > ROIC_MIN\n")
    after = ev.normalize("ROIC_MIN = 9.0\ndef f(x):\n    return x > ROIC_MIN\n")
    assert before != after


def test_changing_the_logic_changes_the_version():
    """Phase 33.1 เปลี่ยนเกณฑ์ #2 เป็น min(net, operating) — เป็น logic ไม่ใช่ค่าคงที่
    ป้ายที่ hash แค่ค่าคงที่จะมองไม่เห็นการแก้แบบนี้ทั้งดุ้น."""
    before = ev.normalize("def f(n, o):\n    return n\n")
    after = ev.normalize("def f(n, o):\n    return min(n, o)\n")
    assert before != after


def test_deleting_a_criterion_changes_the_version():
    before = ev.normalize("def f():\n    return [a(), b()]\n")
    after = ev.normalize("def f():\n    return [a()]\n")
    assert before != after


# ---------- ต้องไม่เด้งเมื่อไม่มีอะไรเปลี่ยน ----------

def test_editing_a_comment_does_not_change_the_version():
    """ไฟล์พวกนี้มีคำอธิบายภาษาไทยยาวกว่าโค้ดและถูกแก้แทบทุกเฟส — ถ้าคอมเมนต์นับด้วย ป้ายจะเด้ง
    แทบทุกวันจนถังของธุรกิจจริงถูกกลบหมด."""
    before = ev.normalize("# เกณฑ์เดิม\nROIC_MIN = 8.0\n")
    after = ev.normalize("# เกณฑ์นี้มาจาก Piotroski ปรับให้เข้ากับหุ้นเติบโต\nROIC_MIN = 8.0\n")
    assert before == after


def test_rewriting_a_docstring_does_not_change_the_version():
    before = ev.normalize('def f(x):\n    """สั้น"""\n    return x\n')
    after = ev.normalize('def f(x):\n    """ยาวมาก\n\n    หลายย่อหน้า\n    """\n    return x\n')
    assert before == after


def test_a_function_that_is_only_a_docstring_survives_stripping():
    """กันบั๊กที่ลบ docstring แล้ว body ว่างจนพังตอน parse — ของจริงมี stub แบบนี้ได้."""
    assert ev.normalize('def f():\n    """แค่คำอธิบาย"""\n')


def test_reformatting_does_not_change_the_version():
    """ขึ้นบรรทัดใหม่/เว้นวรรคไม่ใช่การเปลี่ยนกติกา."""
    before = ev.normalize("def f(a, b):\n    return a + b\n")
    after = ev.normalize("def f(\n    a,\n    b,\n):\n    return (\n        a + b\n    )\n")
    assert before == after


def test_inserting_a_comment_line_does_not_shift_everything_below_it():
    """เหตุผลที่ต้อง include_attributes=False: ถ้าเลขบรรทัดติดไปด้วย การแทรกคอมเมนต์บรรทัดเดียว
    ข้างบนจะทำให้ทุกอย่างข้างล่างเลื่อน แล้วเวอร์ชันเปลี่ยนทั้งที่โค้ดเหมือนเดิมทุกตัวอักษร."""
    before = ev.normalize("A = 1\nB = 2\n")
    after = ev.normalize("# หมายเหตุ\nA = 1\nB = 2\n")
    assert before == after


# ---------- ตัวเวอร์ชันเอง ----------

def test_the_version_is_stable_across_calls():
    """ต้องไม่สุ่ม/ไม่ผูกกับเวลา — ไม่งั้นทุกแถวจะดูเหมือนคนละเอนจิ้นกันหมด."""
    assert ev.engine_version() == ev.engine_version()
    ev.clear_cache()
    assert ev.engine_version() == ev.engine_version()


def test_the_version_is_short_and_hex():
    v = ev.engine_version()
    assert len(v) == 12 and all(c in "0123456789abcdef" for c in v)


def test_every_scoring_module_is_covered_and_they_all_exist():
    parts = ev.engine_parts()
    assert set(parts) == set(ev.SCORING_MODULES)
    assert len(set(parts.values())) == len(parts)      # ไม่มีไฟล์ไหน hash ชนกัน = ไม่ได้อ่านซ้ำไฟล์เดิม


def test_the_version_changes_when_any_single_part_changes(monkeypatch):
    """เวอร์ชันรวมต้องไวต่อทุกไฟล์ในชุด ไม่ใช่ไวต่อไฟล์แรกไฟล์เดียว."""
    base = ev.engine_version()
    for target in ev.SCORING_MODULES:
        ev.clear_cache()
        real = ev.engine_parts

        def fake(_t=target):
            return {m: ("deadbeef1234" if m == _t else "aaaaaaaaaaaa") for m in ev.SCORING_MODULES}

        monkeypatch.setattr(ev, "engine_parts", fake)
        assert ev.engine_version() != base
        monkeypatch.setattr(ev, "engine_parts", real)


def test_reordering_the_module_list_does_not_change_the_version(monkeypatch):
    """ลำดับในลิสต์เป็นเรื่องความอ่านง่ายของคน ไม่ใช่กติกา — สลับแล้วต้องได้เลขเดิม."""
    base = ev.engine_version()
    ev.clear_cache()
    monkeypatch.setattr(ev, "SCORING_MODULES", tuple(reversed(ev.SCORING_MODULES)))
    assert ev.engine_version() == base


# ---------- เฝ้าขอบเขต ----------

def test_the_module_list_still_covers_everything_the_scoring_code_imports():
    """ป้ายที่ครอบไม่ครบคือป้ายที่โกหก. วันที่ health.py งอก import ไปหาโมดูลคิดเลขตัวใหม่ (แบบที่
    grading.py เคยถูกแยกออกมาใน 19.3) เทสต์นี้ต้องพัง เพื่อบังคับให้ตัดสินใจว่าจะเพิ่มเข้าชุด
    หรือยืนยันว่าไม่ใช่กติกา — ไม่ใช่ปล่อยให้เงียบไปเอง."""
    missing = ev.internal_imports() - set(ev.SCORING_MODULES)
    assert not missing, f"โมดูลเหล่านี้ถูกใช้ให้คะแนนแต่ไม่ได้อยู่ใน SCORING_MODULES: {sorted(missing)}"


def test_the_demo_block_is_not_counted_as_a_scoring_dependency():
    """valuation.py import provider ไว้ในบล็อก __main__ เพื่อเดโมในเทอร์มินอล — ถ้านับด้วยจะต้อง
    ตั้งข้อยกเว้นรายไฟล์ ซึ่งจะกลบ import จริงที่งอกมาทีหลังในไฟล์เดียวกัน."""
    assert not any(p.startswith("src/providers/") for p in ev.internal_imports())


def test_normalize_rejects_broken_source():
    """ป้ายที่คำนวณจากไฟล์พังไม่ควรได้ค่าอะไรออกมาเลย — เงียบแล้วคืนค่ามั่วคือกรณีที่แย่ที่สุด."""
    with pytest.raises(SyntaxError):
        ev.normalize("def f(:\n")


def test_main_guard_detection_is_not_fooled_by_a_lookalike():
    tree = ast.parse('if mode == "__main__":\n    import src.providers.stock.market\n')
    assert not ev._is_main_guard(tree.body[0])


# ---------- สคริปต์ backfill ต้องพูดภาษาเดียวกับโปรดักชัน ----------

def test_the_backfill_and_production_compute_the_version_the_same_way():
    """สคริปต์ backfill คำนวณเวอร์ชันของโค้ด ณ คอมมิตเก่า ถ้ามันลอกสูตรไปไว้เอง วันหลังสูตรฝั่งนี้
    ขยับแล้วประวัติที่เติมไว้จะกลายเป็นคนละสเกลกับแถวใหม่แบบเงียบๆ — ซึ่งจะทำให้ทุกคู่ดูเหมือน
    'แก้กติกา' ตลอดกาล."""
    sources = {m: (ev._ROOT / m).read_text(encoding="utf-8") for m in ev.SCORING_MODULES}

    assert ev.version_from(ev.parts_from(sources)) == ev.engine_version()


def test_a_module_that_did_not_exist_yet_is_a_different_ruleset():
    """grading.py เพิ่งถูกแยกออกมาตอน 19.3 — ชุดที่ยังไม่มีไฟล์นั้น ต้องไม่ได้เวอร์ชันเดียวกับ
    ชุดที่มีไฟล์นั้นเป็นค่าว่าง (สองอย่างนี้คนละกติกากันจริงๆ)."""
    with_it = ev.version_from(ev.parts_from({"a.py": "X = 1", "b.py": ""}))
    without_it = ev.version_from(ev.parts_from({"a.py": "X = 1"}))
    assert with_it != without_it


def test_the_backfill_picks_the_newest_rule_change_at_or_before_the_run():
    """ผิดพลาดข้างเดียวก็มีผล: แถวที่รันตอน 10:00 ของวันที่แก้เกณฑ์ตอน 21:00 ต้องได้กติกา 'ก่อนแก้'
    ไม่ใช่ 'หลังแก้' ไม่งั้นการเปลี่ยนจะถูกบันทึกช้าไปหนึ่งรอบและไปโผล่ผิดวัน."""
    from scripts.backfill_engine_version import _version_for

    tl = [("2026-07-10T00:41:20", "old"), ("2026-07-15T21:00:00", "new")]

    assert _version_for("2026-07-09T23:59:59", tl) is None     # เก่ากว่าคอมมิตแรก = ไม่รู้
    assert _version_for("2026-07-10T00:41:20", tl) == "old"    # ตรงเวลาคอมมิตพอดี = โค้ดใหม่แล้ว
    assert _version_for("2026-07-15T10:00:00", tl) == "old"
    assert _version_for("2026-07-15T21:00:01", tl) == "new"
    assert _version_for("2026-08-01T10:00:00", tl) == "new"
