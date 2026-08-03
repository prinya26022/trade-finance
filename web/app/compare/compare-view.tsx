"use client";

// Phase 33 — เทียบสองสำนัก
//
// ข้อจำกัดที่กำหนดหน้าตาของหน้านี้ทั้งหมด: ฝั่งแชท **ทำนานๆ ครั้ง** (เดือนละหน ใช้แรงคนแปะเอง)
// ส่วนฝั่ง API รันทุกวัน. หน้านี้จึงต้อง:
//   1) บอกให้ชัดว่า "ที่เห็นอยู่นี่ของเมื่อไหร่" — คนเปิดกลางเดือนต้องไม่เข้าใจว่าเป็นของวันนี้
//   2) ไม่ทำหน้าเป็นสีเตือนตอนยังไม่ได้แปะเดือนนี้ — นั่นคือสถานะปกติ ไม่ใช่ความผิดพลาด
//   3) ไม่ไล่นับว่าขาดตัวไหนบ้าง — จะกลายเป็นการทวงงานรายวันกับงานที่ตั้งใจทำปีละไม่กี่ครั้ง

import { useState } from "react";
import Link from "next/link";
import type { CompareResult, CompareRow, CompareSide } from "@/lib/types";

const LABELS: Record<string, string> = {
  fundamental_strength: "พื้นฐาน",
  valuation_view: "ราคา",
  sentiment: "โทน",
};

const TH: Record<string, string> = {
  strong: "แข็ง", mixed: "ปนกัน", weak: "อ่อน",
  cheap: "ถูก", fair: "พอเหมาะ", expensive: "แพง", unclear: "ยังไม่ชัด",
  bullish: "บวก", neutral: "กลาง", bearish: "ลบ",
};

function pct(v: number | null | undefined) {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}

function num(v: number | null | undefined) {
  return typeof v === "number" ? (Number.isInteger(v) ? `${v}` : v.toFixed(1)) : "—";
}

function daysAgo(iso: string | null): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return ms < 0 ? 0 : Math.floor(ms / 86400000);
}

function ageText(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "วันนี้";
  if (days === 1) return "เมื่อวาน";
  return `${days} วันก่อน`;
}

/** ครึ่งหนึ่งของการเทียบ 1 หัวข้อ — ป้ายเดียวกันสองฝั่ง ต่างกันไฮไลต์ */
function LabelPair({ row, field }: { row: CompareRow; field: string }) {
  const c = row.claude[field as keyof CompareSide] as string | null;
  const g = row.gemini ? (row.gemini[field as keyof CompareSide] as string | null) : null;
  const differ = row.agree[field] === false;
  return (
    <td className={differ ? "cmp-differ" : ""}>
      <span className="cmp-val">{c ? TH[c] ?? c : "—"}</span>
      <span className="cmp-vs">{differ ? "≠" : "="}</span>
      <span className="cmp-val cmp-muted">{g ? TH[g] ?? g : "—"}</span>
    </td>
  );
}

function SideColumn({ side, title, tone }: { side: CompareSide | null; title: string; tone: string }) {
  if (!side) return <div className="cmp-col"><div className={`cmp-col-head ${tone}`}>{title}</div><p className="cmp-muted">ไม่มีรอบวิเคราะห์ในงวดนี้</p></div>;
  return (
    <div className="cmp-col">
      <div className={`cmp-col-head ${tone}`}>
        {title}
        <span className="cmp-muted"> · {side.run_at?.slice(0, 10) ?? "—"} · มั่นใจ {num(side.confidence)}</span>
      </div>

      {side.beginner_summary && <p className="cmp-summary">{side.beginner_summary}</p>}

      {side.weak_points.length > 0 && (
        <>
          <div className="section-title">จุดอ่อนที่มองเห็น ({side.weak_points.length})</div>
          <ul className="cmp-list">
            {side.weak_points.map((w, i) => (
              <li key={i}><strong>{w.area}</strong> — {w.detail}</li>
            ))}
          </ul>
        </>
      )}

      {side.strength_reasons.length > 0 && (
        <>
          <div className="section-title">จุดแข็ง ({side.strength_reasons.length})</div>
          <ul className="cmp-list">
            {side.strength_reasons.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </>
      )}

      {side.thesis_assessment && (
        <>
          <div className="section-title">ต่อ thesis ที่เขียนไว้</div>
          <p className="cmp-summary">{side.thesis_assessment}</p>
        </>
      )}
    </div>
  );
}

function Row({ row }: { row: CompareRow }) {
  const [open, setOpen] = useState(false);
  const differs = Object.values(row.agree).filter((a) => a === false).length;

  return (
    <>
      <tr onClick={() => setOpen(!open)}>
        <td>
          <strong>{row.ticker}</strong>
          {row.gemini === null ? (
            <span className="cmp-chip" title="งวดนี้ฝั่งรายวันไม่มีรอบวิเคราะห์เลย จึงไม่มีอะไรให้เทียบ">
              ไม่มีคู่เทียบ
            </span>
          ) : row.data_gap_days !== null && row.data_gap_days >= 2 ? (
            <span className="cmp-chip" title="สองฝั่งอ่านข้อมูลคนละวัน — ราคาและงบที่ได้เห็นอาจไม่เท่ากัน ความเห็นที่ต่างกันจึงอาจไม่ได้มาจากการตีความล้วนๆ">
              ข้อมูลห่าง {row.data_gap_days} วัน
            </span>
          ) : null}
          {row.same_framework === false && (
            <span className="cmp-chip cmp-chip-warn" title="สองฝั่งถูกตัดสินด้วย checklist/TASK คนละเวอร์ชัน = คนละข้อสอบ — ความต่างที่เห็นอ่านเป็น 'ใครเก่งกว่า' ไม่ได้">
              คนละ framework
            </span>
          )}
        </td>
        <LabelPair row={row} field="fundamental_strength" />
        <LabelPair row={row} field="valuation_view" />
        <LabelPair row={row} field="sentiment" />
        <td className="cmp-num">
          {pct(row.claude.facts_grounded_ratio)}
          <span className="cmp-vs">/</span>
          <span className="cmp-muted">{pct(row.gemini?.facts_grounded_ratio)}</span>
        </td>
        <td className="cmp-num">
          {num(row.claude.detail.cited_numbers)}
          <span className="cmp-vs">/</span>
          <span className="cmp-muted">{num(row.gemini?.detail.cited_numbers)}</span>
        </td>
        <td className="cmp-num">{differs > 0 ? `ต่าง ${differs}` : "ตรงกัน"}</td>
      </tr>
      {open && (
        <tr className="cmp-detail">
          <td colSpan={7}>
            <div className="cmp-cols">
              <SideColumn side={row.claude} title={row.model} tone="cmp-head-a" />
              <SideColumn side={row.gemini} title="รอบรายวัน (Gemini)" tone="cmp-head-b" />
            </div>
            <p className="cmp-muted cmp-foot">
              ราคาที่ใช้: {num(row.claude.price)} / {num(row.gemini?.price)} ·
              อ้างข่าวตรง {pct(row.claude.news_grounded_ratio)} / {pct(row.gemini?.news_grounded_ratio)} ·
              จุดที่ต้องจับตา {num(row.claude.detail.what_to_watch)} / {num(row.gemini?.detail.what_to_watch)} ข้อ
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

function Periods({ periods, current }: { periods: string[]; current: string }) {
  if (periods.length < 2) return null;
  return (
    <div className="cmp-periods">
      {periods.map((p) => (
        <Link key={p} href={`/compare?period=${p}`}
              className={`cmp-period ${p === current ? "cmp-period-on" : ""}`}>
          {p}
        </Link>
      ))}
    </div>
  );
}

/** ยังไม่เคยแปะเลย — เป็นสถานะเริ่มต้นที่ถูกต้อง ไม่ใช่ error จึงไม่ใช้สีเตือน */
function Empty() {
  return (
    <div className="card">
      <div className="section-title">ยังไม่มีความเห็นจากแชทให้เทียบ</div>
      <p className="cmp-summary">
        ฟีเจอร์นี้ไม่ได้รันเอง — ตั้งใจให้ทำนานๆ ครั้ง (เดือนละหนก็พอ) เพราะต้องแปะข้อมูลให้โมเดลอ่านเอง
        ไม่ได้ยิงผ่าน API. ขั้นตอนมี 3 คำสั่ง:
      </p>
      <pre className="cmp-code">{`python scripts/claude_handoff.py export
# เปิด data/claude_packs/<งวด>.md -> copy ทั้งไฟล์ -> แปะในแชท
# เซฟ JSON ที่ได้เป็น data/claude_packs/<งวด>.reply.json
python scripts/claude_handoff.py import`}</pre>
      <p className="cmp-muted">
        export ดึงแค่ราคา/ข่าว/งบ ไม่กินโควตา LLM เลย — รันซ้ำได้ตามใจ
      </p>
    </div>
  );
}

export default function CompareView({ data, periods }: { data: CompareResult | null; periods: string[] }) {
  if (!data || data.rows.length === 0) return <Empty />;

  const { totals, rows, disagreements } = data;
  const snapshotAge = daysAgo(data.snapshot_at);
  const agreeCount = Object.values(totals.agree_rate).filter((v) => v === 1).length;

  return (
    <div className="cmp-wrap">
      <Periods periods={periods} current={data.period} />

      <section className="card">
        <div className="cmp-head-row">
          <div className="section-title">📊 งวด {data.period} · {rows.length} ตัว</div>
          <span className="cmp-muted">
            ข้อมูล ณ {data.snapshot_at?.slice(0, 10) ?? "—"} ({ageText(snapshotAge)})
            {data.models.length > 0 && ` · ${data.models.join(", ")}`}
          </span>
        </div>

        <p className="cmp-summary">
          ทั้งสองฝั่งได้ <strong>คำสั่งและกรอบวิเคราะห์ชุดเดียวกัน</strong> และตัวเลขงบชุดเดียวกัน
          (งบรายปีไม่ขยับรายวัน) — ที่ต่างกันได้คือราคากับข่าว ถ้าสองฝั่งดึงข้อมูลคนละวัน
          แถวไหนห่างกันตั้งแต่ 2 วันจะมีป้ายกำกับไว้ ·
          ช่องซ้ายของทุกคู่คือฝั่งแชท ขวาคือรอบรายวัน · กดที่แถวเพื่ออ่านเหตุผลของทั้งคู่วางคู่กัน
        </p>

        <table className="cmp-table">
          <thead>
            <tr>
              <th>ticker</th>
              <th>{LABELS.fundamental_strength}</th>
              <th>{LABELS.valuation_view}</th>
              <th>{LABELS.sentiment}</th>
              <th className="cmp-num" title="สัดส่วนตัวเลขที่ยกมาอ้างแล้วตรงกับตัวเลขงบจริง — ข้อเดียวในหน้านี้ที่ตัดสินถูก/ผิดได้">
                อ้างเลขตรง
              </th>
              <th className="cmp-num" title="จำนวนตัวเลขที่ยกมาอ้างในคำวินิจฉัย — เยอะกว่า = ลงรายละเอียดมากกว่า (แต่ต้องอ่านคู่กับช่องซ้าย)">
                เลขที่ยกมา
              </th>
              <th className="cmp-num">ผล</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => <Row key={r.ticker + r.model} row={r} />)}
          </tbody>
        </table>
      </section>

      <section className="card">
        <div className="section-title">สรุปทั้งงวด</div>
        <table className="cmp-table cmp-totals">
          <thead>
            <tr><th>หัวข้อ</th><th className="cmp-num">ฝั่งแชท</th><th className="cmp-num">รอบรายวัน</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>อ้างตัวเลขตรงกับงบจริง</td>
              <td className="cmp-num">{pct(totals.facts_grounded_avg.claude)}</td>
              <td className="cmp-num">{pct(totals.facts_grounded_avg.gemini)}</td>
            </tr>
            <tr>
              <td>อ้างข่าวตรงกับข่าวที่ให้ไป</td>
              <td className="cmp-num">{pct(totals.news_grounded_avg.claude)}</td>
              <td className="cmp-num">{pct(totals.news_grounded_avg.gemini)}</td>
            </tr>
            <tr>
              <td>ตัวเลขที่ยกมาอ้าง (เฉลี่ย/ตัว)</td>
              <td className="cmp-num">{num(totals.detail_avg.claude.cited_numbers)}</td>
              <td className="cmp-num">{num(totals.detail_avg.gemini.cited_numbers)}</td>
            </tr>
            <tr>
              <td>จุดอ่อนที่ระบุ (เฉลี่ย/ตัว)</td>
              <td className="cmp-num">{num(totals.detail_avg.claude.weak_points)}</td>
              <td className="cmp-num">{num(totals.detail_avg.gemini.weak_points)}</td>
            </tr>
            <tr>
              <td>จุดแข็งที่ระบุ (เฉลี่ย/ตัว)</td>
              <td className="cmp-num">{num(totals.detail_avg.claude.strength_reasons)}</td>
              <td className="cmp-num">{num(totals.detail_avg.gemini.strength_reasons)}</td>
            </tr>
          </tbody>
        </table>

        <p className="cmp-muted cmp-foot">
          ป้ายที่ตรงกันทั้งงวด {agreeCount}/3 หัวข้อ ·{" "}
          {Object.entries(totals.agree_rate)
            .map(([f, v]) => `${LABELS[f]} ${pct(v)}`)
            .join(" · ")}
          {totals.paired < totals.tickers && ` · เทียบได้ ${totals.paired}/${totals.tickers} ตัว`}
        </p>
      </section>

      {disagreements.length > 0 && (
        <section className="card">
          <div className="section-title">🔍 จุดที่เห็นไม่ตรงกัน</div>
          <p className="cmp-summary">
            ไม่ได้แปลว่าฝั่งไหนถูก — แปลว่าตรงนี้มีอะไรให้อ่านเหตุผลของทั้งคู่ก่อนตัดสินเอง
          </p>
          <ul className="cmp-list">
            {disagreements.map((d, i) => (
              <li key={i}>
                <strong>{d.ticker}</strong> · {LABELS[d.field] ?? d.field}:{" "}
                ฝั่งแชทว่า <strong>{d.claude ? TH[d.claude] ?? d.claude : "—"}</strong>{" "}
                รอบรายวันว่า <strong>{d.gemini ? TH[d.gemini] ?? d.gemini : "—"}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="cmp-muted cmp-note">
        หมายเหตุ: คะแนนสุขภาพ (health score) ไม่อยู่ในหน้านี้เพราะไม่ได้มาจาก LLM —
        คำนวณจากตัวเลขงบล้วน ข้อมูลชุดเดียวกันจึงได้คะแนนเท่ากันเสมอไม่ว่าฝั่งไหนตอบ
      </p>
    </div>
  );
}
