"use client";

// Phase 32: สมุดพกของเอเจนต์เอง
//
// สองส่วนนี้ตั้งใจไม่ให้อยู่การ์ดเดียวกัน เพราะ "ตอบได้แล้ว" กับ "ยังตอบไม่ได้" ไม่เท่ากัน —
// การเอามาต่อกันเป็นหน้าเดียวลื่นๆ จะทำให้คนอ่านเหมาว่าตัวเลขทั้งหน้าน่าเชื่อถือเท่ากันหมด
// ซึ่งเป็นวิธีหลอกตัวเองแบบเดียวกับที่ฟีเจอร์นี้พยายามจับ

import { useState } from "react";
import type { Scorecard, StabilityRow, ScoreBuckets } from "@/lib/types";

// business/price = คะแนน "ควร" ขยับตามสองอย่างนี้ (ธุรกิจคือสิ่งที่วัด, ราคาคือสิ่งที่ขา valuation
// ออกแบบมาให้ตอบสนอง) ส่วน data/estimate คือฝั่งเราเปลี่ยนเอง = สัญญาณว่าคะแนนวัดตัวเองอยู่
// method (Phase 37) = เราแก้โค้ดให้คะแนนเอง — อธิบายได้ชัดที่สุด จึงไม่อยู่ใน SUSPECT แต่ต้องเห็น
const BUCKET_ORDER: (keyof ScoreBuckets)[] = ["business", "price", "data", "estimate", "method", "other"];
const SUSPECT: (keyof ScoreBuckets)[] = ["data", "estimate"];

function Bars({ gross, labels }: { gross: ScoreBuckets; labels: Record<string, string> }) {
  const total = BUCKET_ORDER.reduce((s, b) => s + Math.abs(gross[b]), 0);
  if (total <= 0) return <span className="sc-muted">ไม่ขยับเลย</span>;

  return (
    <div className="sc-bars">
      {BUCKET_ORDER.map((b) => {
        const v = Math.abs(gross[b]);
        if (v <= 0.005) return null;
        return (
          <div
            key={b}
            className={`sc-bar sc-bar-${b}`}
            style={{ width: `${(v / total) * 100}%` }}
            title={`${labels[b]}: ${v.toFixed(2)} จุด`}
          />
        );
      })}
    </div>
  );
}

function Row({ row, labels }: { row: StabilityRow; labels: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const suspect = SUSPECT.filter((b) => Math.abs(row.gross[b]) >= 0.05);

  return (
    <>
      <tr className={row.trustworthy ? "" : "sc-flagged"} onClick={() => setOpen(!open)}>
        <td>
          <span className={`sc-dot ${row.trustworthy ? "sc-ok" : "sc-bad"}`} />
          <strong>{row.ticker}</strong>
          <span className="sc-muted"> · {row.points} วัน</span>
        </td>
        <td className="sc-num">
          {row.first_score.toFixed(1)} → {row.last_score.toFixed(1)}
          <span className="sc-muted">/{row.max.toFixed(0)}</span>
        </td>
        <td className="sc-num">{row.swing.toFixed(1)}</td>
        <td className="sc-num">
          <strong className={row.trustworthy ? "" : "sc-bad-text"}>{row.unexplained.toFixed(1)}</strong>
          {row.basis_changes > 0 && (
            <span className="sc-chip" title="พลิกระหว่างคะแนนเต็ม /11 กับคะแนนพื้นฐานล้วน /8 — คนละฐาน เทียบตรงๆ ไม่ได้">
              พลิกฐาน {row.basis_changes}×
            </span>
          )}
          {row.method_changes > 0 && (
            <span className="sc-chip sc-chip-method" title="โค้ดให้คะแนนเปลี่ยนเวอร์ชัน หรือ anchor ของ reverse-DCF เปลี่ยนแหล่ง — เราแก้เอง ไม่ใช่คะแนนไม่นิ่ง แต่ช่วงก่อน/หลังเทียบกันตรงๆ ไม่ได้">
              แก้กติกา {row.method_changes}×
            </span>
          )}
        </td>
        <td style={{ minWidth: 140 }}>
          <Bars gross={row.gross} labels={labels} />
        </td>
      </tr>
      {open && (
        <tr className="sc-detail">
          <td colSpan={5}>
            <div className="sc-legend">
              {BUCKET_ORDER.filter((b) => Math.abs(row.gross[b]) >= 0.005).map((b) => (
                <span key={b}>
                  <i className={`sc-swatch sc-bar-${b}`} />
                  {labels[b]} {Math.abs(row.gross[b]).toFixed(2)}
                </span>
              ))}
            </div>
            {row.notes.length > 0 ? (
              <ul className="sc-notes">
                {row.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            ) : (
              <p className="sc-muted">ไม่มีเหตุการณ์ข้อมูล/วิธีคิดเปลี่ยนในช่วงนี้</p>
            )}
            <p className="sc-muted">
              ช่วง {row.from} → {row.to} · ต่ำสุด {row.low.toFixed(1)} สูงสุด {row.high.toFixed(1)}
              {suspect.length > 0 && (
                <> · ส่วนที่น่าสงสัยมาจาก {suspect.map((b) => labels[b]).join(" + ")}</>
              )}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ScorecardView({ data }: { data: Scorecard }) {
  const { stability, prediction, bucket_labels } = data;
  const clean = stability.total > 0 && stability.flagged === 0;

  return (
    <div className="sc-wrap">
      {/* ---- ด่าน 1: ตอบได้แล้ว ---- */}
      <section className="card">
        <div className="section-title">📓 คะแนนของเรานิ่งพอจะเชื่อได้ไหม</div>
        <p className={`sc-headline ${clean ? "sc-ok-text" : "sc-bad-text"}`}>{stability.headline}</p>
        {stability.method_note && (
          <p className="sc-method-note">
            🔧 {stability.method_note}
          </p>
        )}
        <p className="sc-muted sc-intro">
          คะแนนพื้นฐานของบริษัทเดิมไม่ควรขยับหลายจุดใน 1 เดือนถ้าไม่มีงบใหม่มาคั่น —
          ถ้าขยับ แปลว่ากำลังวัดความพร้อมของข้อมูลฝั่งเรา ไม่ใช่ความแข็งแรงของธุรกิจ.
          คอลัมน์ขวาสุดแยกที่มาของการขยับ กดที่แถวเพื่อดูรายละเอียด.
        </p>

        {stability.rows.length === 0 ? (
          <p className="sc-muted">ยังไม่มีหุ้นตัวไหนถูกวิเคราะห์ซ้ำเกิน 1 วัน</p>
        ) : (
          <table className="sc-table">
            <thead>
              <tr>
                <th>หุ้น</th>
                <th className="sc-num">คะแนน</th>
                <th className="sc-num" title="ต่างระหว่างคะแนนสูงสุดกับต่ำสุดตลอดช่วง">แกว่ง</th>
                <th className="sc-num" title={`ขยับโดยไม่ได้มาจากธุรกิจหรือราคา — เกิน ${data.noise_points} จุดถือว่ายังเชื่อไม่ได้`}>
                  อธิบายไม่ได้
                </th>
                <th>ที่มาของการขยับ</th>
              </tr>
            </thead>
            <tbody>
              {stability.rows.map((r) => (
                <Row key={r.ticker} row={r} labels={bucket_labels} />
              ))}
            </tbody>
          </table>
        )}
        <p className="sc-muted sc-intro">
          กติกาให้คะแนนเวอร์ชันปัจจุบัน <code>{stability.engine_version}</code> — ลายนิ้วมือของโค้ด
          ที่แปลงข้อเท็จจริงเป็นคะแนน บันทึกติดไปกับผลวิเคราะห์ทุกแถว เพื่อให้แยกออกว่า
          &ldquo;บริษัทเปลี่ยน&rdquo; กับ &ldquo;เราเปลี่ยนวิธีให้คะแนน&rdquo; คนละเรื่องกัน.
        </p>
      </section>

      {/* ---- ด่าน 2: ยังตอบไม่ได้ ---- */}
      <section className="card sc-pending">
        <div className="section-title">⏳ คะแนนสูงให้ผลตอบแทนดีกว่าคะแนนต่ำจริงไหม</div>

        {prediction.ready ? (
          <p className="sc-headline">
            มี snapshot ที่แก่พอจะวัดผลได้แล้ว — เปิดหน้านี้ใหม่หลังรอบวิเคราะห์ถัดไปเพื่อดูผล
          </p>
        ) : (
          <p className="sc-headline sc-wait-text">
            ยังตอบไม่ได้ — มีประวัติแค่ {prediction.history_days} วัน ({prediction.snapshots} จุด)
            ยังไม่มี snapshot ไหนแก่พอจะวัดผลล่วงหน้าได้เลย
          </p>
        )}

        <div className="sc-horizons">
          {prediction.horizons.map((h) => (
            <div key={h.days} className={`sc-hz ${h.ready ? "sc-hz-ready" : ""}`}>
              <div className="sc-hz-days">{h.days} วัน</div>
              {h.ready ? (
                <div className="sc-ok-text">พร้อม · {h.eligible} จุด</div>
              ) : (
                <>
                  <div className="sc-wait-text">รออีก {h.days_to_first} วัน</div>
                  <div className="sc-muted">ครบ {h.first_at}</div>
                </>
              )}
            </div>
          ))}
        </div>

        <p className="sc-muted sc-intro">
          เหตุผลที่ยังไม่โชว์ตัวเลข: ถ้าเอาคะแนนทุกจุดมาจับคู่กับ &ldquo;ผลตอบแทนถึงวันนี้&rdquo;
          จุดที่เพิ่งเกิดเมื่อวานจะได้ผลตอบแทน ~0 เสมอ แล้วสถิติจะถูกถ่วงเข้าหาศูนย์จนสรุปว่า
          คะแนนไม่มีความหมาย ทั้งที่จริงคือเรายังไม่ได้รอ.
        </p>
        <ul className="sc-notes">
          {prediction.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      </section>
    </div>
  );
}
