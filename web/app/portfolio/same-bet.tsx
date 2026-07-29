"use client";

// Phase 30: "ถือเดิมพันเดียวกันกี่ชั้น" — บทวิเคราะห์ที่คนเชียร์กันมักเป็นสายเดียวกันโดยไม่รู้ตัว
// (ASML -> TSM -> NVDA -> AMZN คือ AI capex เดิมพันเดียว 4 ชั้น) ถือครบสาย = ไม่ได้กระจายความเสี่ยง
// วัดด้วย correlation ของผลตอบแทนรายวัน (ตัวเลขล้วน ไม่ทำนายทิศทาง ไม่ใช่สัญญาณซื้อขาย)
//
// โหลดตอนกดเท่านั้น: ต้องดึงราคา 1 ปีต่อ ticker จาก yfinance (cache 12 ชม.) รอบแรกของวันช้าหลายวินาที
// จะให้ยิงอัตโนมัติทุกครั้งที่เปิดหน้า portfolio ก็เกินจำเป็น

import { useState } from "react";
import type { CorrelationResponse } from "@/lib/types";
import { getCorrelation } from "@/lib/api";

function corrClass(v: number) {
  if (v >= 0.85) return "corr-same";
  if (v >= 0.7) return "corr-high";
  if (v <= -0.3) return "corr-neg";
  return "";
}

export default function SameBet() {
  const [data, setData] = useState<CorrelationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [extra, setExtra] = useState("");
  const [showAll, setShowAll] = useState(false);

  async function load() {
    setBusy(true);
    setErr(null);
    try {
      const tickers = extra.split(",").map((t) => t.trim()).filter(Boolean);
      setData(await getCorrelation(tickers));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const s = data?.summary;
  const rows = data ? (showAll ? data.pairs : data.pairs.slice(0, 12)) : [];

  return (
    <div className="samebet">
      <div className="section-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span>🎲 ถือเดิมพันเดียวกันกี่ชั้น</span>
        <span style={{ flex: 1 }} />
        <input
          className="input"
          style={{ width: 210 }}
          placeholder="ลองใส่ตัวที่คิดจะซื้อ (TSM,ASML)"
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <button className="btn-sm" onClick={load} disabled={busy}>
          {busy ? "กำลังดึงราคา…" : data ? "คำนวณใหม่" : "คำนวณ"}
        </button>
      </div>

      {!data && !busy && (
        <p className="muted" style={{ margin: 0 }}>
          วัดว่าของที่ถือ/จับตาอยู่ วิ่งไปด้วยกันแค่ไหน — ถ้าหลายตัววิ่งพร้อมกัน แปลว่าเรื่องเล่าเดียว
          ผิดแล้วเจ็บพร้อมกันหมด ไม่ใช่การกระจายความเสี่ยงอย่างที่คิด (ใส่ ticker ที่ยังไม่ได้ซื้อเข้าไป
          ลองก่อนได้ ไม่ต้องเพิ่มเข้า watchlist)
        </p>
      )}

      {err && <div className="notice" style={{ borderColor: "var(--red)", color: "var(--red)" }}>{err}</div>}

      {s && (
        <>
          <div className={`sb-summary${s.n_high_held > 0 ? " sb-alarm" : ""}`}>
            {s.n_tickers} ตัว · <strong>{s.n_high}</strong>/{s.n_pairs} คู่ที่วิ่งด้วยกัน (corr ≥ {s.threshold})
            {s.n_high_held > 0 ? (
              <>
                {" · "}
                <strong>⚠ {s.n_high_held} คู่นั้นคุณถืออยู่จริงทั้งคู่</strong> รวม {s.held_weight_in_high}% ของพอร์ต
              </>
            ) : (
              <span className="muted"> · ไม่มีคู่ไหนที่ถืออยู่จริงพร้อมกัน</span>
            )}
          </div>

          <table className="table sb-table">
            <thead>
              <tr>
                <th>คู่</th>
                <th className="num">90 วัน</th>
                <th className="num">1 ปี</th>
                <th>แปลว่า</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={`${p.a}-${p.b}`} className={p.both_held ? "sb-held" : ""}>
                  <td>
                    {p.a} ~ {p.b}
                    {p.both_held && <span className="sb-tag">ถือทั้งคู่ {p.combined_weight}%</span>}
                  </td>
                  <td className={`num ${p.corr["90d"] != null ? corrClass(p.corr["90d"] as number) : ""}`}>
                    {p.corr["90d"] ?? "—"}
                  </td>
                  <td className="num">{p.corr["1y"] ?? "—"}</td>
                  <td className="muted-sm">{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.pairs.length > 12 && (
            <button className="btn-sm" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "ย่อ" : `ดูทั้งหมด ${data.pairs.length} คู่`}
            </button>
          )}

          <p className="sb-caveat">⚠ {data.caveat}</p>
        </>
      )}
    </div>
  );
}
