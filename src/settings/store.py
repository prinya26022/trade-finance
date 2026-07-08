"""Settings store (SQLite) — Phase 5.5.

key-value เล็ก ๆ สำหรับค่าตั้งระดับระบบที่อยากให้เปลี่ยนได้ (เช่น benchmark ที่ใช้วัด edge).
แยกจาก .env เพราะพวกนี้ผู้ใช้ควรแก้ได้จาก UI ทีหลัง (ไม่ใช่ secret) — .env ไว้เก็บ key/secret.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "watchlist.db"

DEFAULTS = {
    "benchmark": "VT",   # กองตลาดรวมโลก — ผู้ใช้เปลี่ยนเป็น SPY/QQQ/อื่น ๆ ได้ (ด่าน 182: วัด edge)
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def get_setting(key: str, default: str | None = None) -> str | None:
    """คืนค่า setting; ถ้ายังไม่ถูกตั้ง -> ใช้ค่าจาก DEFAULTS แล้วจึง default ที่ส่งมา."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["value"]
    return DEFAULTS.get(key, default)


def set_setting(key: str, value: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_benchmark() -> str:
    return get_setting("benchmark", "VT").upper()


def set_benchmark(ticker: str) -> None:
    set_setting("benchmark", ticker.upper())


if __name__ == "__main__":
    # python -m src.settings.store            -> ดูค่าปัจจุบัน
    # python -m src.settings.store SPY         -> ตั้ง benchmark เป็น SPY
    import sys
    if len(sys.argv) > 1:
        set_benchmark(sys.argv[1])
        print(f"ตั้ง benchmark = {get_benchmark()}")
    else:
        print(f"benchmark ปัจจุบัน = {get_benchmark()}")
