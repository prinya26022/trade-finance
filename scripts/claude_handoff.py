"""CLI ของ Phase 33 — ยกงานวิเคราะห์ไปให้โมเดลในแชททำ แล้วเอาผลกลับเข้าระบบ.

    python scripts/claude_handoff.py export                  # ทุกตัวใน watchlist ที่ยัง active
    python scripts/claude_handoff.py export --tickers DUOL,NVDA
    python scripts/claude_handoff.py export --period 2026-08 --include-frozen
    python scripts/claude_handoff.py import                  # อ่าน data/claude_packs/<งวด>.reply.json
    python scripts/claude_handoff.py import --file path.json --model claude-opus-5
    python scripts/claude_handoff.py compare                 # เทียบกับผลของ Gemini งวดเดียวกัน
    python scripts/claude_handoff.py invariance              # พิสูจน์ว่าผลลัพธ์ไม่ขึ้นกับว่าใครตอบ

export ไม่กินโควตา Gemini เลย (ดึงราคา/ข่าว/งบอย่างเดียว) — รันซ้ำได้ตามใจ.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import handoff
from src.agent.compare import compare_period, render_text
from src.evals.check_model_invariance import check_period, render_text as render_invariance

DEFAULT_MODEL = "claude-opus-5"


def cmd_export(args) -> int:
    result = handoff.export(
        tickers=[t.strip() for t in args.tickers.split(",")] if args.tickers else None,
        period=args.period,
        include_frozen=args.include_frozen,
    )
    pack, paths = result["pack"], result["paths"]
    if not pack["items"]:
        print("ไม่มี ticker ให้ export (watchlist ว่าง หรือถูก frozen ทั้งหมด — ใช้ --include-frozen)")
        return 1
    size_kb = paths["markdown"].stat().st_size / 1024
    print(f"งวด {pack['period']}: {len(pack['items'])} ตัว "
          f"({', '.join(i['ticker'] for i in pack['items'])})")
    print(f"  ไฟล์ที่เอาไปแปะในแชท : {paths['markdown']}  ({size_kb:.0f} KB)")
    print(f"  snapshot ข้อมูล      : {paths['data']}")
    print()
    print("ขั้นถัดไป: เปิดไฟล์ .md -> copy ทั้งไฟล์ -> แปะในแชท -> เอา JSON ที่ได้กลับมาเซฟเป็น")
    print(f"  {paths['reply']}")
    print(f"แล้วรัน:  python scripts/claude_handoff.py import --period {pack['period']}")
    return 0


def cmd_import(args) -> int:
    period = args.period or handoff.current_period()
    path = Path(args.file) if args.file else handoff.pack_paths(period)["reply"]
    if not path.exists():
        print(f"ไม่พบไฟล์คำตอบ: {path}")
        return 1

    results = handoff.ingest(period, path.read_text(encoding="utf-8"), model=args.model)
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]

    for r in ok:
        s = r["summary"]
        g = r["grounding"]
        warn = f"  [scrub] {r['warning']}" if r["warning"] else ""
        print(f"{r['ticker']:6} | {s.fundamental_strength:6}/{s.valuation_view:9} | "
              f"conf {s.confidence} | price_ok={g['price_ok']} "
              f"news={g['news_grounded_ratio']:.0%} "
              f"facts={g['facts']['facts_grounded_ratio']:.0%}{warn}")
    for r in bad:
        print(f"{r['ticker']:6} | ข้าม — {r['error']}")

    print(f"\nบันทึกแล้ว {len(ok)} ตัว (งวด {period}, model={args.model})")
    if bad:
        print(f"ยังขาด/ผิดรูป {len(bad)} ตัว — แก้ไฟล์คำตอบแล้วรัน import ซ้ำได้ (ทับของเดิม ไม่เพิ่มแถว)")
    print(f"ดูผลเทียบ:  python scripts/claude_handoff.py compare --period {period}")
    return 0 if ok else 1


def cmd_compare(args) -> int:
    period = args.period or handoff.current_period()
    result = compare_period(period, model=None if args.all_models else args.model)
    if not result["rows"]:
        print(f"งวด {period} ยังไม่มีผลจากแชทให้เทียบ (รัน export -> import ก่อน)")
        return 1
    print(render_text(result))
    return 0


def cmd_invariance(args) -> int:
    """พิสูจน์ว่าเปลี่ยนโมเดลแล้วตัวเลขที่ระบบใช้ตัดสินไม่เปลี่ยน (ไม่เรียก LLM)."""
    period = args.period or handoff.current_period()
    report = check_period(period, model=args.model)
    if not report["compared"]:
        print(f"งวด {period} ยังไม่มีคู่ที่เทียบได้ (ต้องมีทั้งผลจากแชทและรอบรายวันที่ผูกกันไว้)")
        return 1
    print(render_invariance(report))
    return 0 if report["identical"] == report["compared"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="สร้างไฟล์ข้อมูลไปแปะในแชท")
    p_export.add_argument("--tickers", help="ระบุเอง คั่นด้วย , (ปริยาย = watchlist ที่ active)")
    p_export.add_argument("--period", help="งวด YYYY-MM (ปริยาย = เดือนนี้)")
    p_export.add_argument("--include-frozen", action="store_true",
                          help="รวมตัวที่ frozen ด้วย")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="นำคำตอบ JSON กลับเข้า DB")
    p_import.add_argument("--period", help="งวด YYYY-MM (ปริยาย = เดือนนี้)")
    p_import.add_argument("--file", help="ไฟล์คำตอบ (ปริยาย = data/claude_packs/<งวด>.reply.json)")
    p_import.add_argument("--model", default=DEFAULT_MODEL, help=f"ชื่อโมเดลที่ตอบ (ปริยาย {DEFAULT_MODEL})")
    p_import.set_defaults(func=cmd_import)

    p_compare = sub.add_parser("compare", help="เทียบกับผลของ Gemini งวดเดียวกัน")
    p_compare.add_argument("--period", help="งวด YYYY-MM (ปริยาย = เดือนนี้)")
    p_compare.add_argument("--model", default=DEFAULT_MODEL)
    p_compare.add_argument("--all-models", action="store_true",
                           help="รวมทุกโมเดลในงวดนั้น ไม่กรองด้วย --model")
    p_compare.set_defaults(func=cmd_compare)

    p_inv = sub.add_parser("invariance", help="เช็คว่าผลลัพธ์ไม่ขึ้นกับว่าโมเดลไหนตอบ")
    p_inv.add_argument("--period", help="งวด YYYY-MM (ปริยาย = เดือนนี้)")
    p_inv.add_argument("--model", default=None)
    p_inv.set_defaults(func=cmd_invariance)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
