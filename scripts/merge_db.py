"""รวมไฟล์ DB เวลา git ชน — แทนการเลือกทิ้งข้างใดข้างหนึ่ง.

ติดตั้งครั้งเดียวต่อเครื่อง (เขียน .gitattributes + ตั้ง merge driver ให้ repo นี้):

    python scripts/merge_db.py install

หลังจากนั้น `git pull` / `git rebase` / `git merge` จะรวม data/*.db ให้เองอัตโนมัติ.

ใช้มือได้ด้วย:

    python scripts/merge_db.py resolve            # ตอนที่ conflict ค้างอยู่แล้ว (UU ...)
    python scripts/merge_db.py resolve --dry-run  # ดูก่อนว่าจะได้อะไร ยังไม่แตะไฟล์จริง
    python scripts/merge_db.py merge --ours a.db --theirs b.db --out c.db [--base o.db]

`resolve` คือทางออกตอนที่ยังไม่ได้ install (หรือเครื่องอื่น/CI ไม่มี driver) — มันไปดึง
ทั้งสามเวอร์ชันจาก index ของ git เอง แล้วรวมให้ พร้อม `git add` ปิดงาน.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.merge import merge_db, render_text

ATTR_LINE = "data/*.db -diff merge=sqlitedb"
DRIVER = "sqlitedb"


def _git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} ล้มเหลว:\n{r.stderr.strip()}")
    return r.stdout


def _backup(path: Path) -> Path:
    """สำรองก่อนทับของจริงเสมอ — งานนี้ผิดพลาดแล้วย้อนยากกว่าที่คิด.

    ตั้งชื่อให้ลงท้าย .db เหมือนเดิม เพื่อให้ .gitignore (data/*.db) กลืนไฟล์สำรองไปด้วย
    ไม่งั้นทุกครั้งที่รวม จะมีไฟล์ untracked โผล่มากวน git status
    """
    ts = f"{datetime.now():%Y%m%d-%H%M%S}"
    dest = path.with_name(f"{path.stem}.before-merge-{ts}{path.suffix}")
    shutil.copy2(path, dest)
    return dest


# ---------- install ----------

def cmd_install(args) -> int:
    attrs = ROOT / ".gitattributes"
    lines = attrs.read_text(encoding="utf-8").splitlines() if attrs.exists() else []
    if ATTR_LINE not in lines:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["# DB เป็น binary -> git รวมเองไม่ได้ ต้องใช้ driver ที่รวมทีละแถว",
                  "# (ตั้ง driver ต่อเครื่องด้วย: python scripts/merge_db.py install)",
                  ATTR_LINE]
        attrs.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"เขียน .gitattributes: {ATTR_LINE}")
    else:
        print(".gitattributes มีบรรทัดนี้อยู่แล้ว")

    # %O=base %A=ours(และเป็นไฟล์ผลลัพธ์) %B=theirs %P=ชื่อไฟล์จริง
    cmd = f'"{sys.executable}" "{(ROOT / "scripts" / "merge_db.py").as_posix()}" git-driver %O %A %B %P'
    _git("config", f"merge.{DRIVER}.name", "รวม SQLite ทีละแถว (3-way)")
    _git("config", f"merge.{DRIVER}.driver", cmd)
    print(f"ตั้ง merge driver '{DRIVER}' ใน .git/config แล้ว")
    print()
    print("ลองได้เลย: git pull --rebase   (ไฟล์ DB จะไม่ conflict อีก)")
    print("หมายเหตุ: .gitattributes commit ตามไปได้ แต่ driver เป็นค่าเฉพาะเครื่อง —")
    print("          เครื่องใหม่/CI ต้องรัน install ซ้ำ ไม่งั้นจะกลับไป conflict แบบเดิม")
    return 0


# ---------- git driver ----------

def cmd_git_driver(args) -> int:
    """ถูกเรียกโดย git เอง: รวมแล้วเขียนทับ %A. คืน 0 = สำเร็จ, ไม่ 0 = ปล่อยให้คนแก้."""
    path = args.path or "DB"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "merged.db"
        try:
            report = merge_db(args.base, args.ours, args.theirs, out)
        except Exception as e:                       # noqa: BLE001 — ห้ามพัง git ทั้ง repo
            print(f"[merge_db] รวม {path} ไม่สำเร็จ: {e}", file=sys.stderr)
            print("[merge_db] ปล่อยให้ conflict ตามปกติ แก้มือด้วย "
                  "python scripts/merge_db.py resolve", file=sys.stderr)
            return 1
        shutil.copyfile(out, args.ours)

    print(f"[merge_db] รวม {path} แล้ว", file=sys.stderr)
    print(render_text(report), file=sys.stderr)
    return 0


# ---------- resolve (conflict ค้างอยู่แล้ว) ----------

def _conflicted_dbs() -> list[str]:
    out = _git("diff", "--name-only", "--diff-filter=U")
    return [p for p in out.split() if p.endswith(".db")]


def _stage(path: str, stage: int, dest: Path) -> Path | None:
    r = subprocess.run(["git", "show", f":{stage}:{path}"], cwd=ROOT, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None                                   # ไม่มีสเตจนี้ = ฝั่งนั้นไม่มีไฟล์
    dest.write_bytes(r.stdout)
    return dest


def cmd_resolve(args) -> int:
    targets = args.paths or _conflicted_dbs()
    if not targets:
        print("ไม่มีไฟล์ .db ที่ conflict ค้างอยู่ (git diff --diff-filter=U ว่าง)")
        return 1

    rc = 0
    for path in targets:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            base = _stage(path, 1, d / "base.db")
            ours = _stage(path, 2, d / "ours.db")
            theirs = _stage(path, 3, d / "theirs.db")
            if ours is None or theirs is None:
                print(f"{path}: ไม่มีทั้งสองฝั่งใน index — ไม่ใช่ conflict แบบที่รวมได้")
                rc = 1
                continue
            if base is None:
                print(f"{path}: ไม่มี base ใน index — จะรวมแบบยูเนียน (ไม่ลบอะไรเลย)")

            out = d / "merged.db"
            report = merge_db(base, ours, theirs, out)
            print(f"=== {path} ===")
            print(render_text(report))

            if args.dry_run:
                print("(dry-run — ยังไม่แตะไฟล์จริง)")
                continue

            target = ROOT / path
            if target.exists():
                print(f"สำรองของเดิมไว้ที่ {_backup(target).name}")
            shutil.copyfile(out, target)
            _git("add", "--", path)
            print(f"เขียนทับ {path} และ git add แล้ว")
        print()

    if not args.dry_run and rc == 0:
        print("ทำต่อได้: git rebase --continue   (หรือ git commit ถ้าเป็น merge)")
    return rc


# ---------- merge สองไฟล์ตรงๆ ----------

def cmd_merge(args) -> int:
    report = merge_db(args.base, args.ours, args.theirs, args.out)
    print(render_text(report))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("install", help="ตั้ง merge driver ให้ repo นี้ (ทำครั้งเดียวต่อเครื่อง)")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("git-driver", help="(git เรียกเอง — ไม่ต้องรันมือ)")
    p.add_argument("base")
    p.add_argument("ours")
    p.add_argument("theirs")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_git_driver)

    p = sub.add_parser("resolve", help="รวมไฟล์ .db ที่ conflict ค้างอยู่ใน index")
    p.add_argument("paths", nargs="*", help="ปริยาย = ทุกไฟล์ .db ที่ยัง unmerged")
    p.add_argument("--dry-run", action="store_true", help="แสดงผลอย่างเดียว ไม่เขียนทับ")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("merge", help="รวมสองไฟล์ที่ระบุเอง")
    p.add_argument("--ours", required=True)
    p.add_argument("--theirs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--base", default=None, help="ไม่ใส่ = รวมแบบยูเนียน ไม่ลบอะไรเลย")
    p.set_defaults(func=cmd_merge)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
