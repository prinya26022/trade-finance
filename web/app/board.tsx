"use client";

/* Phase 43 — กระดานสรุปบนสุดของหน้าแรก: "ตัวไหนน่าสนใจ ดูเร็วๆ แล้วค่อยเจาะ"

   ทุกอย่างอยู่ในหน่วยเดียว: **ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร** เพราะหน่วยของเครื่องมือ
   ("ส่วนลด −27%", "ช่วง 47pp") อ่านแล้วไม่เห็นภาพ ส่วน "ราคา 100 → 73, ช่วง 26–73" เห็นทันที

   เกณฑ์เดียวที่ต้องจำ: **ช่วงคร่อม 100 หรือเปล่า** — คร่อมเมื่อไหร่แปลว่าบางวิธีวัดบอกถูก
   บางวิธีบอกแพง = ตัวเลขนี้ตัดสินใจแทนไม่ได้ ต้องไปหาคำตอบเรื่องการเติบโตเอง */

import { useState } from "react";
import Link from "next/link";
import type { BoardResponse, BoardRow, BoardVerdict } from "@/lib/types";
import { Tip } from "@/lib/glossary";

const VERDICT: Record<BoardVerdict, { cls: string; label: string }> = {
  cheap:     { cls: "bv-cheap",  label: "ทุกวิธีบอกว่าถูก" },
  expensive: { cls: "bv-exp",    label: "ทุกวิธีบอกว่าแพง" },
  straddles: { cls: "bv-strad",  label: "พลิกได้ทั้งสองทาง" },
  capped:    { cls: "bv-capped", label: "แน่นเทียม (ชนเพดาน)" },
  single:    { cls: "bv-capped", label: "ไม่มีอะไรให้เทียบ" },
  bank:      { cls: "bv-na",     label: "คนละไม้บรรทัด" },
  none:      { cls: "bv-na",     label: "ยังไม่มีราคา" },
};

// สเกลร่วม 0–250 ทุกแถว ถึงจะเทียบข้ามตัวได้จริง เกินนั้นตัดที่ขอบ (DUOL 216 ยังอยู่ในสเกล)
const SCALE = 250;
const pos = (v: number) => `${Math.max(0, Math.min(100, (v / SCALE) * 100))}%`;

function ago(runAt: string | null): string {
  if (!runAt) return "";
  const days = Math.floor((Date.now() - new Date(runAt).getTime()) / 86400000);
  if (days <= 0) return "วันนี้";
  if (days === 1) return "เมื่อวาน";
  return `${days} วันก่อน`;
}

function Bar({ row }: { row: BoardRow }) {
  if (row.at_100 == null) return <span className="muted-sm">—</span>;
  const lo = row.lo_100 ?? row.at_100;
  const hi = row.hi_100 ?? row.at_100;
  return (
    <div className="bd-bar">
      <div className="bd-track" />
      <div
        className={`bd-span ${row.verdict === "straddles" ? "cross" : ""}`}
        style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }}
      />
      <div className="bd-mark" style={{ left: pos(row.at_100) }} />
      {/* เส้นราคาตลาด: ทุกอย่างในกระดานนี้อ่านเทียบเส้นนี้เส้นเดียว */}
      <div className="bd-now" />
    </div>
  );
}

export default function Board({ data }: { data: BoardResponse }) {
  const [open, setOpen] = useState<string | null>(null);
  const { rows, summary } = data;

  return (
    <section className="bd">
      <div className="bd-head">
        <span className="section-title" style={{ margin: 0 }}>
          <Tip def="ราคาที่โมเดลคำนวณได้ของทุกตัวใน watchlist แปลงเป็นหน่วยเดียวกัน: สมมติราคาตลาดวันนี้ของทุกตัว = 100 แล้วดูว่าตัวเลขเราบอกว่าควรเป็นเท่าไร. ไม่ใช่ราคาเป้าหมาย ไม่ใช่สัญญาณซื้อขาย">
            ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร
          </Tip>
        </span>
        <span className="muted-sm">
          {summary.priced}/{summary.total} ตัวคำนวณราคาได้ ·{" "}
          <b>{summary.usable} ตัวที่ทุกวิธีวัดเห็นตรงกัน</b> ·{" "}
          {summary.unreliable} ตัวที่ตัวเลขยังตัดสินใจแทนไม่ได้
        </span>
      </div>

      <div className="table-scroll">
        <table className="pf-table bd-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th className="num">
                <Tip def="พื้นฐานธุรกิจ /8 + ราคาถูกแพง /3 — เอนจิ้นเดียวกับทั้งแอป อ่านจากรอบวิเคราะห์ล่าสุดของตัวนั้น">
                  คะแนน
                </Tip>
              </th>
              <th className="num">
                <Tip def="ราคาที่โมเดลคำนวณได้ ถ้าราคาตลาด ณ รอบวิเคราะห์นั้น = 100. ต่ำกว่า 100 = ตลาดจ่ายแพงกว่าที่ตัวเลขย้อนหลังรองรับ ซึ่งไม่ได้แปลว่าราคาจะลง">
                  คำนวณได้
                </Tip>
              </th>
              <th className="num">
                <Tip def="ช่วงที่ได้ถ้าใช้วิธีวัดการเติบโตแบบอื่นที่มีเหตุผลพอกัน (นับเฉพาะวิธีที่ระบบไม่ได้ตัดทิ้ง) — ช่วงแคบ = ทุกมุมมองเห็นตรงกัน เชื่อตัวเลขได้; ช่วงคร่อม 100 = ตัดสินใจแทนไม่ได้">
                  ช่วงตามวิธีวัด
                </Tip>
              </th>
              <th style={{ minWidth: 170 }}>เทียบราคาตลาด</th>
              <th>ตัวเลขนี้ใช้ได้ไหม</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker} className={open === r.ticker ? "bd-open" : ""}>
                <td>
                  <Link href={`/ticker/${r.ticker}`} className="ticker-link">{r.ticker}</Link>
                  {/* ตัวที่แช่แข็ง/รอบเดือนจะเก่ากว่าตัวอื่นมาก ต้องเห็นว่าเลขมาจากวันไหน */}
                  <div className="muted-sm">{ago(r.run_at)}</div>
                </td>
                <td className="num">
                  {r.score == null ? "—" : `${r.score.toFixed(1)}/${r.max?.toFixed(0)}`}
                  {r.partial && <div className="muted-sm">พื้นฐานล้วน</div>}
                </td>
                <td className="num bd-main">{r.at_100 ?? "—"}</td>
                <td className="num">
                  {r.lo_100 != null && r.hi_100 != null
                    ? (r.lo_100 === r.hi_100 ? `${r.lo_100}` : `${r.lo_100}–${r.hi_100}`)
                    : <span className="muted-sm">—</span>}
                </td>
                <td><Bar row={r} /></td>
                <td>
                  <span className={`bd-verdict ${VERDICT[r.verdict].cls}`}>
                    {VERDICT[r.verdict].label}
                  </span>
                  {r.candidates.length > 0 && (
                    <button
                      className="bd-more"
                      onClick={() => setOpen(open === r.ticker ? null : r.ticker)}
                      aria-expanded={open === r.ticker}
                    >
                      {open === r.ticker ? "ซ่อน" : "ทำไม"}
                    </button>
                  )}
                  <div className="muted-sm">{r.note}</div>
                  {open === r.ticker && (
                    <table className="bd-cands">
                      <tbody>
                        {r.candidates.map((c) => (
                          <tr
                            key={c.label}
                            className={c.used ? "used" : c.rejected ? "dropped" : ""}
                          >
                            <td>
                              {c.label}
                              {c.rejected && <span className="bd-chip">ตัดทิ้ง</span>}
                              {c.capped && <span className="bd-chip">ชนเพดาน</span>}
                            </td>
                            <td className="num">โตปีละ {c.growth.toFixed(1)}%</td>
                            <td className="num">→ {c.at_100 ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* เตือนซ้ำตรงนี้เพราะเป็นการอ่านผิดที่เกิดขึ้นแน่ถ้าไม่บอก: ตัวเลขส่วนใหญ่ต่ำกว่า 100
          เป็นสมบัติของวิธีคำนวณ (อนุรักษ์นิยมกว่าตลาดอย่างเป็นระบบ) ไม่ใช่คำตัดสินว่าตลาดผิด */}
      <p className="bd-note">
        เรียงตาม<b>คะแนนคุณภาพ ไม่ใช่ความถูก</b> — เรียงตามความถูกเมื่อไหร่ ตารางนี้กลายเป็น
        รายการแนะนำซื้อทันที. ส่วนใหญ่คำนวณได้ต่ำกว่า 100 เพราะวิธีของเราอิงข้อมูลย้อนหลังที่วัดได้จริง
        ส่วนตลาดจ่ายให้อนาคตที่ยังไม่เกิด — <b>อ่านว่า &quot;ตัวไหนต้องเชื่ออนาคตมากกว่ากัน&quot;
        ไม่ใช่ &quot;ตัวไหนควรขาย&quot;</b>
      </p>
    </section>
  );
}
