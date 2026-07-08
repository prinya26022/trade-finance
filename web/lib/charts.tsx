// กราฟ SVG เขียนเอง — ไม่พึ่ง lib ภายนอก (เบา, ไม่มี bundle บวม, คุมสไตล์ได้เต็ม)
// theme-aware ผ่าน CSS var; เส้นใช้ vector-effect กันเส้นหนาเพี้ยนตอน scale
import React from "react";
import type { SeriesPoint } from "./facts";
import { shortPeriod } from "./facts";

const W = 320;
const PAD = { top: 10, right: 10, bottom: 18, left: 34 };

export type Series = { name: string; color: string; points: SeriesPoint[] };

function bounds(all: number[]) {
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.12; // เผื่อขอบบน/ล่าง ไม่ให้เส้นแตะกรอบ
  return { lo: lo - pad, hi: hi + pad };
}

// กราฟเส้น (รองรับหลายเส้นที่แชร์แกน y เดียวกัน เช่น margins 3 เส้น)
export function LineChart({
  series,
  height = 150,
  fmtY = (v: number) => v.toFixed(0),
}: {
  series: Series[];
  height?: number;
  fmtY?: (v: number) => string;
}) {
  const periods = series[0]?.points.map((p) => p.period) ?? [];
  const n = periods.length;
  if (n < 2) return null;

  const allVals = series.flatMap((s) => s.points.map((p) => p.value));
  const { lo, hi } = bounds(allVals);
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - ((v - lo) / (hi - lo)) * innerH;

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img">
      {/* เส้นแกน y 2 ค่า (บน/ล่าง) */}
      {[hi, lo].map((v, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={y(v)} x2={W - PAD.right} y2={y(v)} className="chart-grid" />
          <text x={PAD.left - 5} y={y(v) + 3} className="chart-axis" textAnchor="end">
            {fmtY(v)}
          </text>
        </g>
      ))}
      {/* label แกน x (ปี) */}
      {periods.map((p, i) => (
        <text key={p} x={x(i)} y={height - 5} className="chart-axis" textAnchor="middle">
          {shortPeriod(p)}
        </text>
      ))}
      {/* เส้นข้อมูล + จุด */}
      {series.map((s) => {
        const d = s.points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
        return (
          <g key={s.name}>
            <path d={d} fill="none" stroke={s.color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {s.points.map((p, i) => (
              <circle key={i} cx={x(i)} cy={y(p.value)} r={2.5} fill={s.color} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// กราฟแท่ง (ค่าเดียว เช่น FCF รายปี / จำนวนหุ้น)
export function BarChart({
  points,
  color,
  height = 150,
  fmtY = (v: number) => v.toFixed(0),
}: {
  points: SeriesPoint[];
  color: string;
  height?: number;
  fmtY?: (v: number) => string;
}) {
  const n = points.length;
  if (n < 1) return null;
  const vals = points.map((p) => p.value);
  const hi = Math.max(...vals, 0);
  const lo = Math.min(...vals, 0);
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const y = (v: number) => PAD.top + innerH - ((v - lo) / (hi - lo || 1)) * innerH;
  const bw = (innerW / n) * 0.6;

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img">
      <text x={PAD.left - 5} y={y(hi) + 3} className="chart-axis" textAnchor="end">
        {fmtY(hi)}
      </text>
      {points.map((p, i) => {
        const cx = PAD.left + (i + 0.5) * (innerW / n);
        const top = y(Math.max(p.value, 0));
        const base = y(0);
        return (
          <g key={p.period}>
            <rect x={cx - bw / 2} y={Math.min(top, base)} width={bw} height={Math.abs(base - top)} rx={2} fill={color} opacity={0.85} />
            <text x={cx} y={height - 5} className="chart-axis" textAnchor="middle">
              {shortPeriod(p.period)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// เส้นจิ๋วในการ์ด (ไม่มีแกน) — โชว์ทิศทาง trend คร่าวๆ
export function Sparkline({ points, color }: { points: SeriesPoint[]; color: string }) {
  const n = points.length;
  if (n < 2) return null;
  const w = 64;
  const h = 18;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const x = (i: number) => (i / (n - 1)) * w;
  const y = (v: number) => h - ((v - lo) / (hi - lo || 1)) * h;
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
  return (
    <svg width={w} height={h} className="spark" role="img" aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
