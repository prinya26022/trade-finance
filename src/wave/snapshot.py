"""เก็บรายงานคลื่นฉบับที่ส่งจริงไว้ให้หน้าเว็บอ่าน — **หน้าเว็บไม่ดึงราคาเอง** (Phase 49.2):
ถ้าเว็บคำนวณเองคนละรอบกับ Discord ตัวเลขสองที่จะไม่ตรงกันโดยไม่มีใครรู้ว่าอันไหนจริง"""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.wave.analysis import Report
from src.wave.claude import load_view

SNAP_DIR = Path(__file__).parents[2] / "data" / "waves" / "snapshots"


def _auto(counts) -> list[dict]:
    return [{**asdict(c), "hits": c.hits, "score": c.score, "unchecked": c.unchecked} for c in counts]


def to_dict(rep: Report) -> dict:
    d = asdict(rep)
    d["auto"] = _auto(rep.auto)
    d["valid"] = rep.valid
    if rep.parent is not None:
        d["parent"]["auto"] = _auto(rep.parent.auto)
        d["parent"]["valid"] = rep.parent.valid
    return d


def write(stem: str, rep: Report, wave_png: bytes, auto_png: bytes, message: str) -> Path:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{stem}_wave.png").write_bytes(wave_png)
    (SNAP_DIR / f"{stem}_auto.png").write_bytes(auto_png)
    payload = {"stem": stem, "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
               "report": to_dict(rep), "message": message, "claude": load_view(stem)}
    path = SNAP_DIR / f"{stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def read(stem: str) -> dict | None:
    path = SNAP_DIR / f"{stem}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["claude"] = load_view(stem)        # ความเห็นที่แปะทีหลังต้องเห็นได้โดยไม่ต้องรันรายงานใหม่
    return data


def stems() -> list[str]:
    return sorted(p.stem for p in SNAP_DIR.glob("*.json")) if SNAP_DIR.exists() else []
