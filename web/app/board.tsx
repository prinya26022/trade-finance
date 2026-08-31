"use client";

/* Phase 43/46 — กระดานสรุปบนสุดของหน้าแรก: "ตัวไหนน่าสนใจ ดูเร็วๆ แล้วค่อยเจาะ"

   ทุกอย่างอยู่ในหน่วยเดียว: **ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร** เพราะหน่วยของเครื่องมือ
   ("ส่วนลด −27%", "ช่วง 47pp") อ่านแล้วไม่เห็นภาพ ส่วน "ราคา 100 → 73, ช่วง 26–73" เห็นทันที

   เกณฑ์เดียวที่ต้องจำ: **ช่วงคร่อม 100 หรือเปล่า** — คร่อมเมื่อไหร่แปลว่าบางวิธีวัดบอกถูก
   บางวิธีบอกแพง = ตัวเลขนี้ตัดสินใจแทนไม่ได้ ต้องไปหาคำตอบเรื่องการเติบโตเอง

   Phase 46 (จัดหน้าใหม่): ยุบ "คำนวณได้" กับ "ช่วง" เป็นช่องเดียว (เลขใหญ่ + ช่วงใต้ลงมา)
   ย้ายคำอธิบายลงไปในแผงที่กางออก แล้วให้คลิกได้ทั้งแถว — เดิมมี 7 คอลัมน์แข่งกันดึงสายตา
   และคำอธิบายยาวๆ อยู่ติดกับ chip คำตัดสินจนอ่านทั้งคู่ไม่ทัน */

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import type { BoardResponse, BoardRow, BoardVerdict } from "@/lib/types";
import { Tip } from "@/lib/glossary";

const VERDICT: Record<BoardVerdict, { cls: string; label: string }> = {
  cheap:     { cls: "bv-cheap",  label: "ทุกวิธีบอกว่าถูก" },
  expensive: { cls: "bv-exp",    label: "ทุกวิธีบอกว่าแพง" },
  straddles: { cls: "bv-strad",  label: "พลิกได้ทั้งสองทาง" },
  capped:    { cls: "bv-capped", label: "แน่นเทียม" },
  single:    { cls: "bv-capped", label: "ไม่มีอะไรให้เทียบ" },
  bank:      { cls: "bv-na",     label: "คนละไม้บรรทัด" },
  none:      { cls: "bv-na",     label: "ยังไม่มีราคา" },
};

// ตัวกรอง — ไม่มีตัวเลือก "เรียงลำดับ" โดยตั้งใจ: เรียงตามความถูกเมื่อไหร่ ตารางนี้กลายเป็น
// รายการแนะนำซื้อทันที ส่วนการซ่อนแถวที่ยังไม่มีคำตอบไม่ได้เปลี่ยนความหมายของอะไรเลย
const FILTERS = [
  { key: "all", label: "ทั้งหมด", match: (_r: BoardRow) => true },
  { key: "usable", label: "ตัวเลขใช้ได้", match: (r: BoardRow) => r.verdict === "cheap" || r.verdict === "expensive" },
  { key: "unsure", label: "ยังตัดสินใจแทนไม่ได้", match: (r: BoardRow) => ["straddles", "capped", "single"].includes(r.verdict) },
  { key: "none", label: "ยังไม่มีราคา", match: (r: BoardRow) => r.verdict === "none" || r.verdict === "bank" },
  // กรองได้ ไม่ใช่เรียงได้ — ดูว่าแถวไหนกำลังพูดจากราคาเก่า เป็นคำถามที่ตอบเองไม่ได้ถ้าไม่แยกออกมาดู
  { key: "stale", label: "ข้อมูลเก่า", match: (r: BoardRow) => r.stale && r.at_100 != null },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

// สเกลร่วม 0–250 ทุกแถว ถึงจะเทียบข้ามตัวได้จริง เกินนั้นตัดที่ขอบ
const SCALE = 250;
const pos = (v: number) => `${Math.max(0, Math.min(100, (v / SCALE) * 100))}%`;

/* อายุมาจาก server (age_days) ไม่ใช่คำนวณจาก run_at ฝั่ง client — ไม่งั้นนาฬิกา/timezone
   ของเบราว์เซอร์อาจให้คำตอบคนละอย่างกับตัวเลข stale ที่หัวกระดานนับไว้ แล้วหน้าเดียวกัน
   จะเถียงกันเอง (แถวขึ้น "6 วันก่อน" แต่ถูกนับเป็นเก่า) */
function ago(days: number | null): string {
  if (days == null) return "ไม่รู้วันที่";
  if (days <= 0) return "วันนี้";
  if (days === 1) return "เมื่อวาน";
  return `${days} วันก่อน`;
}

/* "ราคานี้เรียกร้องอะไร" — สองตัวที่ขึ้นว่า margin พอแล้วเหมือนกันยังต้องแยกกันออก
   จึงพ่วง FCF กี่เท่าไว้เสมอ (SBUX ขอ 5.1x ส่วน CVX ขอ 1.9x คนละน้ำหนักกันมาก) */
function Asks({ asks }: { asks: NonNullable<BoardRow["asks"]> }) {
  if (asks.margin_alone_enough) {
    return (
      <Tip def={`ราคานี้ไม่ได้เรียกร้องให้รายได้โตเลย — แค่ margin ที่ถูกกดอยู่ (${asks.margin_today_pct ?? "?"}%) กลับขึ้นไปถึงระดับดีที่สุดที่ธุรกิจแบบนี้ทำได้ (${asks.margin_ceiling_pct}%) ก็พอแล้ว`}>
        <span className="bd-asks bd-asks-easy">
          margin พอแล้ว
          <span className="bd-asks-sub">FCF ×{asks.fcf_multiple.toFixed(1)}</span>
        </span>
      </Tip>
    );
  }
  const heavy = asks.revenue_multiple >= 4;
  return (
    <Tip def={`แม้สมมติให้ทำ FCF margin ได้ ${asks.margin_ceiling_pct}% ซึ่งเป็นระดับดีที่สุดที่บริษัทมหาชนทำได้จริง รายได้ก็ยังต้องโตเป็น ${asks.revenue_multiple.toFixed(1)} เท่าของวันนี้ภายใน ${asks.years} ปี — เอาไปเทียบกับขนาดตลาดรวมของอุตสาหกรรมนั้นได้เลย นั่นคือ check ที่โมเดลทำเองไม่ได้`}>
      <span className={`bd-asks ${heavy ? "bd-asks-heavy" : ""}`}>
        รายได้ ×{asks.revenue_multiple.toFixed(1)}
        <span className="bd-asks-sub">{asks.revenue_cagr_needed_pct.toFixed(1)}%/ปี</span>
      </span>
    </Tip>
  );
}

function Bar({ row }: { row: BoardRow }) {
  if (row.at_100 == null) return <span className="bd-dash">—</span>;
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
  const [filter, setFilter] = useState<FilterKey>("all");
  const { rows, summary } = data;

  const shown = useMemo(
    () => rows.filter(FILTERS.find((f) => f.key === filter)!.match),
    [rows, filter],
  );

  const toggle = (ticker: string) => setOpen((cur) => (cur === ticker ? null : ticker));

  return (
    <section className="bd">
      <div className="bd-head">
        <h2 className="bd-title">
          <Tip def="ราคาที่โมเดลคำนวณได้ของทุกตัวใน watchlist แปลงเป็นหน่วยเดียวกัน: สมมติราคาตลาดวันนี้ของทุกตัว = 100 แล้วดูว่าตัวเลขเราบอกว่าควรเป็นเท่าไร. ไม่ใช่ราคาเป้าหมาย ไม่ใช่สัญญาณซื้อขาย">
            ถ้าราคาวันนี้ 100 เราคำนวณได้เท่าไร
          </Tip>
        </h2>
        <div className="bd-stats">
          {/* เดิมบรรทัดนี้เขียนแค่ "11 ตัวเลขใช้ได้" ซึ่งรวมแถวที่คำนวณจากราคาเมื่อ 27 วันก่อน
              เข้ากับแถวเมื่อวานเป็นเลขเดียว = หัวกระดานอ้างความสดที่ไม่มีจริง. แยกให้เห็น
              แต่ไม่ตัดออกจากยอดรวม — ซ่อนของที่ประเมินยากคือสิ่งที่ Phase 29/34 แก้มาแล้ว */}
          <span><b>{summary.usable_fresh}</b> ตัวเลขใช้ได้</span>
          {summary.stale > 0 && (
            <>
              <span className="bd-sep" />
              <Tip def={`แถวที่มีราคาคำนวณได้ แต่รอบวิเคราะห์ล่าสุดเก่ากว่า ${summary.stale_after_days} วัน — ส่วนใหญ่คือตัวที่พักไว้ (frozen) ซึ่งระบบตั้งใจวิเคราะห์แค่ทุก 30 วันเพื่อประหยัดโควตา ไม่ใช่ความผิดพลาด. นับแยกเพราะราคาก่อนงบออกกับราคาหลังงบออกเปลี่ยนการตัดสินใจคนละแบบ`}>
                <span className="bd-stat-stale"><b>{summary.stale}</b> ข้อมูลเก่า</span>
              </Tip>
            </>
          )}
          <span className="bd-sep" />
          <span><b>{summary.unreliable}</b> ยังตัดสินใจแทนไม่ได้</span>
          <span className="bd-sep" />
          <span><b>{summary.total - summary.priced}</b> ยังไม่มีราคา</span>
        </div>
      </div>

      <div className="bd-filters" role="group" aria-label="กรองแถว">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`bd-chip ${filter === f.key ? "on" : ""}`}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label} <span className="bd-chip-n">{rows.filter(f.match).length}</span>
          </button>
        ))}
      </div>

      <div className="table-scroll bd-wrap">
        <table className="bd-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th className="num">
                <Tip def="พื้นฐานธุรกิจ /8 + ราคาถูกแพง /3 — เอนจิ้นเดียวกับทั้งแอป อ่านจากรอบวิเคราะห์ล่าสุดของตัวนั้น">คะแนน</Tip>
              </th>
              <th className="num bd-div">
                <Tip def="ราคาที่โมเดลคำนวณได้ ถ้าราคาตลาด ณ รอบวิเคราะห์นั้น = 100. เลขเล็กใต้ลงมาคือช่วงที่ได้ถ้าใช้วิธีวัดการเติบโตแบบอื่นที่มีเหตุผลพอกัน. ต่ำกว่า 100 = ตลาดจ่ายแพงกว่าที่ตัวเลขย้อนหลังรองรับ ซึ่งไม่ได้แปลว่าราคาจะลง">
                  คำนวณได้
                </Tip>
              </th>
              <th className="bd-barcol">เทียบราคาตลาด</th>
              <th className="num">
                <Tip def="เดินตัวเลขที่ตลาด price ไว้ไปข้างหน้าจริงๆ แล้วถามว่าบริษัทต้องใหญ่แค่ไหน — สมมติให้ใจกว้างที่สุดว่าทำ FCF margin ได้ระดับดีที่สุดที่บริษัทมหาชนทำได้ (50%). ต่างจากคอลัมน์ซ้ายตรงที่อันนี้เอาไปชนกับขนาดตลาดรวมของอุตสาหกรรมได้ ไม่ต้องเชื่อโมเดลเลย">
                  ราคานี้ขออะไร
                </Tip>
              </th>
              <th className="bd-div">คำตัดสิน</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const isOpen = open === r.ticker;
              return (
                <Fragment key={r.ticker}>
                  <tr
                    className={`bd-row ${isOpen ? "is-open" : ""}`}
                    onClick={() => toggle(r.ticker)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggle(r.ticker);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-expanded={isOpen}
                  >
                    <td>
                      <Link
                        href={`/ticker/${r.ticker}`}
                        className="bd-tk"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.ticker}
                      </Link>
                      {/* ตัวที่แช่แข็ง/รอบเดือนเก่ากว่าตัวอื่นหลายสัปดาห์ ต้องเห็นว่าเลขมาจากวันไหน
                          เก่าจริง = ป้ายที่มีสี ไม่ใช่ตัวเทา 11px ที่แพ้เลขราคา 21px ที่มันกำกับอยู่ */}
                      {r.stale ? (
                        <Tip def={`แถวนี้คำนวณจากราคาและงบของรอบวิเคราะห์เมื่อ ${ago(r.age_days)} ไม่ใช่ราคาวันนี้ — ตัวที่พักไว้ (frozen) ระบบตั้งใจวิเคราะห์แค่ทุก 30 วันเพื่อประหยัดโควตา. อ่านได้ แต่ถ้ามีงบออกหรือราคาวิ่งแรงหลังจากวันนั้น ตัวเลขบรรทัดนี้ยังไม่รู้เรื่องนั้น`}>
                          <span className="bd-stale">⏳ {ago(r.age_days)}</span>
                        </Tip>
                      ) : (
                        <span className="bd-when">{ago(r.age_days)}</span>
                      )}
                    </td>
                    <td className="num">
                      {r.score == null ? (
                        <span className="bd-dash">—</span>
                      ) : (
                        <span>
                          <span className="bd-score">{r.score.toFixed(1)}</span>
                          <span className="bd-of">/{r.max?.toFixed(0)}</span>
                        </span>
                      )}
                      {r.partial && <span className="bd-when">พื้นฐานล้วน</span>}
                    </td>
                    <td className="num bd-div">
                      {r.at_100 == null ? (
                        <span className="bd-dash">—</span>
                      ) : (
                        <>
                          <span className={`bd-main ${r.stale ? "is-stale" : ""}`}>{r.at_100}</span>
                          {r.lo_100 != null && r.hi_100 != null && (
                            <span className="bd-when">
                              {r.lo_100 === r.hi_100 ? `${r.lo_100}` : `${r.lo_100}–${r.hi_100}`}
                            </span>
                          )}
                        </>
                      )}
                    </td>
                    <td className="bd-barcol"><Bar row={r} /></td>
                    <td className="num">
                      {r.asks ? <Asks asks={r.asks} /> : <span className="bd-dash">—</span>}
                    </td>
                    <td className="bd-div">
                      <span className={`bd-verdict ${VERDICT[r.verdict].cls}`}>
                        {VERDICT[r.verdict].label}
                      </span>
                      <span className={`bd-caret ${isOpen ? "up" : ""}`} aria-hidden="true">⌄</span>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bd-panel-row">
                      <td colSpan={6}>
                        <div className="bd-panel">
                          <p className="bd-why">{r.note}</p>
                          {r.stale && (
                            <p className="bd-why bd-why-stale">
                              ตัวเลขทั้งบรรทัดนี้มาจากรอบวิเคราะห์เมื่อ <b>{ago(r.age_days)}</b>
                              {r.run_at ? ` (${r.run_at.slice(0, 10)})` : ""} — ราคาที่ใช้คำนวณคือราคา
                              ของวันนั้น ไม่ใช่วันนี้ ถ้ามีงบออกหรือราคาวิ่งแรงหลังจากนั้น ตัวเลขนี้ยังไม่รู้
                            </p>
                          )}
                          {r.candidates.length > 0 && (
                            <table className="bd-cands">
                              <thead>
                                <tr>
                                  <th>วิธีวัดการเติบโต</th>
                                  <th className="num">โตปีละ</th>
                                  <th className="num">ได้ราคา</th>
                                </tr>
                              </thead>
                              <tbody>
                                {r.candidates.map((c) => (
                                  <tr key={c.label} className={c.used ? "used" : c.rejected ? "dropped" : ""}>
                                    <td>
                                      {c.label}
                                      {c.used && <span className="bd-tag on">ที่ใช้อยู่</span>}
                                      {c.rejected && <span className="bd-tag">ตัดทิ้ง</span>}
                                      {c.capped && <span className="bd-tag">ชนเพดาน</span>}
                                    </td>
                                    <td className="num">{c.growth.toFixed(1)}%</td>
                                    <td className="num">{c.at_100 ?? "—"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          <Link href={`/ticker/${r.ticker}`} className="bd-open-link">
                            ดูรายละเอียด {r.ticker} →
                          </Link>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {shown.length === 0 && <p className="bd-empty">ไม่มีแถวในกลุ่มนี้</p>}

      {/* เตือนซ้ำตรงนี้เพราะเป็นการอ่านผิดที่เกิดขึ้นแน่ถ้าไม่บอก: ตัวเลขส่วนใหญ่ต่ำกว่า 100
          เป็นสมบัติของวิธีคำนวณ (อนุรักษ์นิยมกว่าตลาดอย่างเป็นระบบ) ไม่ใช่คำตัดสินว่าตลาดผิด */}
      <p className="bd-note">
        เรียงตาม<b>คะแนนคุณภาพ ไม่ใช่ความถูก</b> — เรียงตามความถูกเมื่อไหร่ ตารางนี้กลายเป็น
        รายการแนะนำซื้อทันที · ส่วนใหญ่คำนวณได้ต่ำกว่า 100 เพราะวิธีของเราอิงข้อมูลย้อนหลังที่วัดได้จริง
        ส่วนตลาดจ่ายให้อนาคตที่ยังไม่เกิด — <b>อ่านว่า &quot;ตัวไหนต้องเชื่ออนาคตมากกว่ากัน&quot;
        ไม่ใช่ &quot;ตัวไหนควรขาย&quot;</b>
      </p>
    </section>
  );
}
