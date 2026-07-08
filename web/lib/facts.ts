// ตัวช่วยดึง 'ตัวเลขงบหลายปี' ออกจาก facts ดิบ เพื่อป้อนกราฟ
import type { Fact } from "./types";

export type SeriesPoint = { period: string; value: number };

// จุดข้อมูลรายปี (FY) ของ label หนึ่ง เรียงเก่า -> ใหม่ (เช่น Operating Margin FY2022..FY2025)
export function fySeries(facts: Fact[], label: string): SeriesPoint[] {
  return facts
    .filter((f) => f.label === label && (f.period ?? "").startsWith("FY"))
    .map((f) => ({ period: f.period as string, value: f.value }))
    .sort((a, b) => a.period.localeCompare(b.period));
}

// ค่าเดี่ยวล่าสุดของ label (เอา TTM ก่อน ไม่งั้น FY ล่าสุด) — ไว้โชว์ตัวเลขสรุป
export function latestValue(facts: Fact[], label: string): Fact | undefined {
  const rows = facts.filter((f) => f.label === label);
  if (rows.length === 0) return undefined;
  const ttm = rows.find((f) => f.period === "TTM");
  if (ttm) return ttm;
  return rows.sort((a, b) => (b.period ?? "").localeCompare(a.period ?? ""))[0];
}

// จัดรูปตัวเลขให้อ่านง่าย: เงินก้อนใหญ่ -> $xxxB/M, % -> xx.x%, ที่เหลือ -> ปกติ
export function fmt(value: number, unit: string): string {
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "USD") {
    const abs = Math.abs(value);
    if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return `$${value.toFixed(0)}`;
  }
  // จำนวนหุ้น ฯลฯ (ตัวเลขล้วน)
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  return value.toFixed(2);
}

// FY2025 -> '25 (ย่อแกน x ให้สั้น)
export function shortPeriod(period: string): string {
  const m = period.match(/FY(\d{4})/);
  return m ? `'${m[1].slice(2)}` : period;
}
