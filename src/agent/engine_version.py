"""ลายนิ้วมือของ "เอนจิ้นที่ให้คะแนน" (Phase 37).

Phase 33.2 ติดฐานให้ **prompt** ไปแล้ว (summarize.framework_version) ด้วยเหตุผลว่า ถ้าไม่บันทึก
ไว้ว่ารอบนั้นใช้กรอบไหน การเทียบข้ามงวดจะปนกันระหว่าง "โมเดลเปลี่ยน" กับ "เราเปลี่ยนโจทย์".
แต่เลขที่ผู้ใช้อ่านจริงทุกวัน — คะแนน /11 — ไม่ได้มาจาก prompt เลย มันมาจากโค้ด deterministic
ใน health.py/valuation.py ซึ่งเปลี่ยนไป 4 ครั้งภายในสามเฟสล่าสุดโดยไม่มีอะไรในข้อมูลบันทึกไว้:

    33.1  เกณฑ์ #2 เปลี่ยนนิยามเป็น min(Net Margin, Operating Margin)
    33.2  ตัดอัตราส่วนข้ามสกุลเงิน -> ASML/TSM ย้ายฐาน /11 เป็น /8
    33.3  เพิ่มกรอบธนาคาร      -> JPM จาก excluded เป็นมีคะแนน
    36    ย้าย anchor ของ reverse-DCF ไปใช้ประวัติ FCF ที่ยื่น ก.ล.ต. -> CVX realistic growth
          -11.09% เป็น +3.21%

รอบวิเคราะห์ถัดจากนั้น scorecard.py จะเห็น CVX ขยับ แล้วโยนเข้าถัง `estimate` = "ประมาณการของเรา
เปลี่ยน" ซึ่งถูกตามตัวอักษรแต่แยกไม่ออกเลยว่าเป็น "ข้อมูลใหม่ทำให้ประมาณการขยับ" หรือ "เราแก้วิธี
คิดเมื่อวาน" — ปัญหาเดียวกับที่ framework_version ถูกสร้างมาแก้ วิธีแก้ก็อันเดิม: **ติดฐานไปกับ
ข้อมูล** แล้วให้ชั้นที่เปรียบเทียบเห็นเองว่าคนละฐาน.

ทำไม hash ไม่ใช่เลขเวอร์ชันที่พิมพ์เอง: เลขที่ต้องอัปเดตด้วยมือคือเลขที่ลืมอัปเดต — และวันที่ลืม
คือวันที่กติกาเปลี่ยนพอดี ซึ่งเป็นวันเดียวที่ป้ายนี้มีค่า.

ทำไมต้องตัดคอมเมนต์/docstring ทิ้งก่อน hash: สามไฟล์นี้มีคำอธิบายภาษาไทยยาวกว่าตัวโค้ดหลายเท่า
และถูกแก้แทบทุกเฟส. ถ้า hash ซอร์สดิบ การแก้คำผิดในคอมเมนต์จะกลายเป็น "เราเปลี่ยนกติกา" แล้ว
การขยับจริงของธุรกิจวันนั้นจะถูกกลบไปอยู่ถัง method ทั้งก้อน. ธงที่ขึ้นทุกครั้งไม่ต่างจากไม่มีธง
(บทเรียนเดิมจาก macro grace window). ตัด comment/docstring ออก = เหลือเฉพาะสิ่งที่มีผลต่อตัวเลข.

ทำไมเลือกทางที่ "เตือนเกิน" มากกว่า "เตือนขาด": อีกทางที่คิดไว้คือรันเอนจิ้นกับข้อมูลตัวอย่างคงที่
แล้ว hash ผลลัพธ์ ซึ่งจะไม่เด้งเลยเวลาแก้เรื่องที่ไม่กระทบตัวอย่าง — แต่มันก็จะเงียบสนิทตอนเพิ่ม
กรอบธนาคาร (ตัวอย่างไม่ใช่แบงก์) ทั้งที่ JPM ขยับทั้งกระดาน. งานนี้มีไว้จับ "การเปลี่ยนกติกาแบบ
เงียบๆ" การพลาดฝั่งเงียบจึงแย่กว่าการเด้งเกินจำเป็นเป็นครั้งคราว.

ขอบเขต = โมดูลที่แปลง "ข้อเท็จจริง -> คะแนน" เท่านั้น. ฝั่ง provider (yfinance/XBRL) ไม่นับ
เพราะมันผลิต *ข้อเท็จจริง* ซึ่งการเปลี่ยนของมันปรากฏเป็นเกณฑ์พลิก null<->ตัวเลขอยู่แล้ว และถูกจับ
เข้าถัง `data` โดย _fundamental_delta. ส่วนกรณีที่ provider เปลี่ยนแหล่ง anchor ของ reverse-DCF
(เช่น NVDA ที่วันหนึ่งประวัติ XBRL จะยาวพอ) จับด้วย anchor_window.source ใน scorecard แยกต่างหาก
— hash ตัวนี้เป็นป้ายระดับ "ทั้งระบบ" มันไม่มีทางรู้ว่าหุ้นตัวไหนเปลี่ยนแหล่งข้อมูลวันไหน.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

_ROOT = Path(__file__).parents[2]

# ไฟล์ที่ประกอบกันเป็น "กติกาให้คะแนน" — ครบตาม import closure ของ health.py พอดี
# (health -> grading, valuation; valuation -> grading) ซึ่ง test_engine_version บังคับให้ยังจริงอยู่
SCORING_MODULES: tuple[str, ...] = (
    "src/agent/health.py",       # เกณฑ์พื้นฐาน 8 ข้อ + gate + comparable_score
    "src/agent/valuation.py",    # reverse-DCF: implied vs realistic growth -> คะแนนขาราคา /3
    "src/agent/grading.py",      # การไล่ระดับรอบ threshold ที่ทั้งสองขาใช้ร่วมกัน
)

_HASH_LEN = 12


def _strip_docs(tree: ast.AST) -> ast.AST:
    """ลบ docstring ของ module/class/function ออกจาก AST (คอมเมนต์หายไปตั้งแต่ ast.parse แล้ว)."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            # ฟังก์ชันที่มีแต่ docstring จะเหลือ body ว่างซึ่ง ast.dump รับได้ แต่ใส่ Pass ไว้ให้
            # เป็นโครงที่ถูกต้องตามไวยากรณ์ เผื่อวันหลังมีใครเอา tree นี้ไป unparse ต่อ
            node.body = body[1:] or [ast.Pass()]
    return tree


def normalize(source: str) -> str:
    """ซอร์ส -> รูปแบบมาตรฐานที่เหลือเฉพาะสิ่งที่มีผลต่อตัวเลข (ไม่มีคอมเมนต์/docstring/ช่องว่าง).

    include_attributes=False สำคัญ: ไม่งั้นเลขบรรทัด/คอลัมน์จะติดไปด้วย แล้วการแทรกคอมเมนต์
    หนึ่งบรรทัดจะเลื่อนทุกอย่างที่อยู่ข้างล่างจนเวอร์ชันเปลี่ยน ซึ่งคือสิ่งที่ตั้งใจเลี่ยง.

    ตั้งใจ **ไม่** ตัดบล็อก `if __name__ == "__main__"` ทิ้ง (ต่างจาก internal_imports ที่ตัด):
    การแก้เดโมในเทอร์มินอลจะทำให้เวอร์ชันเด้งโดยไม่จำเป็นก็จริง แต่การเริ่มยกเว้นโค้ดบางส่วน
    ออกจาก hash คือจุดเริ่มของช่องที่กติกาจริงหลุดออกไปได้ — เตือนเกินดีกว่าเตือนขาด.
    """
    return ast.dump(_strip_docs(ast.parse(source)), include_attributes=False)


def _is_main_guard(node: ast.stmt) -> bool:
    """node นี้คือ `if __name__ == "__main__":` หรือไม่."""
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_LEN]


_cache: tuple[tuple[str, str], ...] | None = None


def clear_cache() -> None:
    """ให้เทสต์ (และการแก้ไฟล์ระหว่างรัน) เห็นซอร์สใหม่ — โปรดักชันไม่ต้องเรียก."""
    global _cache
    _cache = None


def parts_from(sources: dict[str, str]) -> dict[str, str]:
    """{path: ซอร์ส} -> {path: hash}. ไฟล์ที่ยังไม่มีตัวตนในตอนนั้นให้ไม่ต้องส่งมา (ไม่ใช่ส่ง "")
    — ชุดที่ยังไม่มี grading.py คือคนละกติกากับชุดที่มี grading.py ว่างเปล่าจริงๆ."""
    return {m: _digest(normalize(src)) for m, src in sources.items()}


def version_from(parts: dict[str, str]) -> str:
    """{path: hash} -> เวอร์ชันรวม. แยกออกมาเป็นฟังก์ชันสาธารณะเพราะสคริปต์ backfill ต้องคำนวณ
    เวอร์ชันของโค้ด ณ คอมมิตเก่า ถ้าให้มันลอกสูตรไปไว้เอง วันหลังสูตรฝั่งนี้ขยับแล้วประวัติที่
    backfill ไว้จะกลายเป็นคนละสเกลกับแถวใหม่เงียบๆ."""
    return _digest("\n".join(f"{m}:{h}" for m, h in sorted(parts.items())))


def engine_parts() -> dict[str, str]:
    """{path: hash} รายไฟล์ของโค้ดที่ใช้อยู่จริงตอนนี้ — ตอบคำถาม "เวอร์ชันเปลี่ยนเพราะไฟล์ไหน"
    ได้โดยไม่ต้องไล่ diff."""
    global _cache
    if _cache is None:
        _cache = tuple(parts_from(
            {m: (_ROOT / m).read_text(encoding="utf-8") for m in SCORING_MODULES}
        ).items())
    return dict(_cache)


def engine_version() -> str:
    """ลายนิ้วมือสั้นๆ ของกติกาให้คะแนนทั้งชุด — คู่ขนานของ summarize.framework_version.

    hash ของ hash รายไฟล์ (ไม่ใช่ hash ของซอร์สที่ต่อกัน) เพื่อให้ engine_parts() ที่เก็บไว้ตอน
    debug ประกอบกลับเป็นเวอร์ชันเดิมได้ตรงๆ และการสลับลำดับไฟล์ในลิสต์ไม่ทำให้เวอร์ชันเปลี่ยน.
    """
    return version_from(engine_parts())


def internal_imports() -> set[str]:
    """โมดูลใน src/ ที่ไฟล์ในชุดนี้ import (เป็น path แบบเดียวกับ SCORING_MODULES).

    มีไว้ให้เทสต์เฝ้าขอบเขต: วันที่ health.py งอก import ใหม่ไปหาโมดูลคิดเลขอีกตัว ป้ายนี้จะหยุด
    ครอบคลุมกติกาทั้งหมดเงียบๆ — ซึ่งคือความล้มเหลวแบบเดียวกับเลขเวอร์ชันที่ลืมอัปเดตด้วยมือ.
    """
    found: set[str] = set()
    for m in SCORING_MODULES:
        tree = ast.parse((_ROOT / m).read_text(encoding="utf-8"))
        # บล็อก `if __name__ == "__main__"` ไม่ใช่เส้นทางให้คะแนน — valuation.py import provider
        # ตรงนั้นไว้เดโมในเทอร์มินอล ถ้านับด้วยจะต้องตั้งข้อยกเว้นรายไฟล์ ซึ่งจะกลบ import จริง
        # ที่งอกมาทีหลังในไฟล์เดียวกัน
        tree.body = [n for n in tree.body if not _is_main_guard(n)]
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src."):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names if a.name.startswith("src.")]
            for name in names:
                path = name.replace(".", "/") + ".py"
                if (_ROOT / path).exists():
                    found.add(path)
                else:
                    # `from src.pkg import mod` -> ตัว mod เองต่างหากที่เป็นไฟล์
                    found.update(
                        f"{name.replace('.', '/')}/{a.name}.py"
                        for a in getattr(node, "names", [])
                        if (_ROOT / f"{name.replace('.', '/')}/{a.name}.py").exists()
                    )
    return found


if __name__ == "__main__":       # python -m src.agent.engine_version
    print(f"engine_version = {engine_version()}")
    for path, digest in engine_parts().items():
        print(f"  {digest}  {path}")