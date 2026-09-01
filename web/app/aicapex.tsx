"use client";

/* Phase 49 — เรดาร์ห่วงโซ่การเงิน AI บนหน้าแรก

   คำถามที่ตอบ: **"เงื่อนไขที่ต้องเป็นจริงก่อนฟองสบู่ AI จะแตก ตอนนี้เป็นจริงไปกี่ข้อ"**
   ไม่ใช่ "จะแตกเมื่อไหร่" — อันหลังเดาเอาทั้งนั้น และคนที่เล่าเรื่องฟองสบู่ได้เก่งมักถูก
   แต่เร็วเกินไป 3-5 ปี ซึ่งในทางปฏิบัติแปลว่าผิด

   ลำดับการอ่านที่ตั้งใจ (จากฟีดแบ็ก "อ่านลำบาก ไม่จูงใจ" กับฉบับ Discord แรก):
     1. แถบสี — รู้สถานะก่อนสมองเริ่มอ่านตัวหนังสือ
     2. ตัวชี้ขาด — ถ้าอ่านบรรทัดเดียวต้องเป็นบรรทัดนี้ ไม่ใช่ข้อแรกที่บังเอิญอยู่บนสุด
     3. 4 บท — เรียงตามลำดับที่ความเสียหายจะเดินจริง ไม่ใช่ checklist 7 ข้อน้ำหนักเท่ากัน
     4. รายละเอียดต่อสัญญาณ — ซ่อนไว้หลังคลิก คนที่อยากเจาะค่อยกด

   **ไม่มีคะแนนรวมเป็นเลขเดียว** โดยตั้งใจ: "ความเสี่ยง 63%" เถียงกับมันไม่ได้
   ส่วน "5 ใน 7 ข้อ และนี่คือรายชื่อ" เถียงได้ทีละข้อ */

import { Fragment, useState } from "react";
import type { AicapexHistoryPoint, AicapexResponse, AicapexSignal, AicapexState } from "@/lib/types";
import { Tip } from "@/lib/glossary";

const DOT: Record<AicapexState, string> = {
  alert: "ac-dot-alert", watch: "ac-dot-watch", ok: "ac-dot-ok", unknown: "ac-dot-unknown",
};
const WORD: Record<AicapexState, string> = {
  alert: "เป็นจริงแล้ว", watch: "ต้องจับตา", ok: "ยังปกติ", unknown: "วัดไม่ได้",
};
const ORDER: Record<AicapexState, number> = { alert: 0, watch: 1, unknown: 2, ok: 3 };

function fmt(s: AicapexSignal): string {
  if (s.value == null) return "—";
  return `${s.value}${s.unit ? ` ${s.unit}` : ""}`;
}

/* ห่างเส้นแค่ไหน ในภาษาที่ไม่ต้องรู้ว่า "เส้น" คือเลขอะไร — คนอ่านไม่ได้อยากรู้ว่าเราตั้ง
   เกณฑ์ไว้เท่าไร เขาอยากรู้ว่าใกล้พังหรือยัง ซึ่งเป็นคนละคำถาม */
function distance(s: AicapexSignal): string {
  if (s.margin == null) return "";
  // นับเป็น "ราย" ไม่มีระยะที่มีความหมาย — บริษัทเป็นจำนวนเต็ม เฉียดเส้นครึ่งบริษัทไม่ได้
  if (s.unit === "ราย") return "";
  if (s.borderline) return "เฉียดเส้นมาก";
  return s.margin > 0 ? `เกินเส้นมา ${s.margin}` : `ห่างเส้น ${Math.abs(s.margin)}`;
}

/* ทิศทางเทียบรอบก่อน — "-28.78 pp" ตัวเดียวอ่านแล้วไม่รู้ว่าดีขึ้นหรือแย่ลง ซึ่งเป็นคำถามแรก
   ที่คนถามเสมอ. ต้องรู้ทิศของสัญญาณด้วย เพราะบางตัวยิ่งต่ำยิ่งแย่ */
function Delta({ s }: { s: AicapexSignal }) {
  if (s.delta == null || s.delta === 0) return <span className="ac-flat">ไม่ขยับ</span>;
  const worseWhenHigher = s.alert_at == null || s.watch_at == null || s.alert_at >= s.watch_at;
  const worse = worseWhenHigher ? s.delta > 0 : s.delta < 0;
  return (
    <span className={worse ? "ac-worse" : "ac-better"}>
      {s.delta > 0 ? "▲" : "▼"} {Math.abs(s.delta)} {worse ? "แย่ลง" : "ดีขึ้น"}
    </span>
  );
}

/* เส้นแนวโน้มเล็กๆ — ไม่ใส่แกน ไม่ใส่ตัวเลข เพราะหน้าที่มันคือตอบ "ขึ้นหรือลง" ในครึ่งวินาที
   ไม่ใช่ให้อ่านค่า (ค่าอยู่ข้างๆ อยู่แล้ว) */
function Spark({ points }: { points: AicapexHistoryPoint[] }) {
  const vals = points.map((p) => p.value).filter((v): v is number => v != null);
  // เส้นแนวโน้มสื่อว่า "เวลาผ่านไปแล้วค่าขยับแบบนี้" — ถ้าทุกจุดมาจากวันเดียวกัน (รันซ้ำ
  // หลายรอบในวันเดียว) เส้นแบนจะอ่านเป็น "นิ่งมาตลอด" ทั้งที่จริงคือ "ยังไม่มีเวลาให้ดู"
  // ซึ่งเป็นคนละเรื่อง จึงไม่วาดจนกว่าจะมีอย่างน้อย 3 วันจริง
  const days = new Set(points.map((p) => p.recorded_at.slice(0, 10)));
  if (vals.length < 3 || days.size < 3) return null;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || 1;
  const w = 64, h = 18;
  const d = vals
    .map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - lo) / span) * h}`)
    .join(" ");
  return (
    <svg className="ac-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={d} fill="none" strokeWidth="1.5" />
    </svg>
  );
}

function SignalRow({ s, history }: { s: AicapexSignal; history: AicapexHistoryPoint[] }) {
  const [open, setOpen] = useState(false);
  const dist = distance(s);
  const hasRows = Array.isArray(s.rows) && s.rows.length > 0;

  return (
    <div className={`ac-sig ${open ? "is-open" : ""}`}>
      <button
        className="ac-sig-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        disabled={!hasRows}
      >
        <span className={`ac-dot ${DOT[s.state]}`} aria-label={WORD[s.state]} />
        <span className="ac-sig-label">
          {s.label}
          {s.decisive && <span className="ac-star" title="ตัวชี้ขาด">★</span>}
        </span>
        <span className="ac-sig-val">{fmt(s)}</span>
        <Spark points={history} />
        <span className="ac-sig-meta">
          {dist && <span className={s.borderline ? "ac-close" : ""}>{dist}</span>}
          <Delta s={s} />
        </span>
        {hasRows && <span className={`ac-caret ${open ? "up" : ""}`} aria-hidden="true">⌄</span>}
      </button>
      <p className="ac-sig-why">{s.missing ?? s.detail}</p>
      {open && hasRows && (
        <div className="ac-rows">
          <table>
            <tbody>
              {s.rows.map((r, i) => (
                <tr key={i}>
                  {Object.entries(r)
                    .filter(([k]) => k !== "ticker")
                    .slice(0, 4)
                    .map(([k, v]) => (
                      <td key={k}>
                        <span className="ac-cell-k">{k}</span>
                        <span className="ac-cell-v">{String(v)}</span>
                      </td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Aicapex({ data }: { data: AicapexResponse | null }) {
  const [showBlind, setShowBlind] = useState(false);

  if (!data || !data.available || !data.report) {
    return (
      <section className="ac">
        <h2 className="ac-title">เรดาร์ห่วงโซ่การเงิน AI</h2>
        <p className="ac-empty">
          {data?.reason ?? "ยังไม่มีข้อมูล"}
          {data?.how && <><br /><code>{data.how}</code></>}
        </p>
      </section>
    );
  }

  const r = data.report;
  const decisive = r.signals.find((s) => s.decisive);
  const gauge = [...r.signals].sort((a, b) => ORDER[a.state] - ORDER[b.state]);
  const triggered = r.counts.alert + r.counts.watch;

  return (
    <section className="ac">
      <div className="ac-head">
        <h2 className="ac-title">
          <Tip def="ห่วงโซ่การเงินของการสร้าง AI datacenter: ผู้ใช้จ่ายค่าเช่า → ผู้ให้บริการจ่ายค่าชิป → ผู้ผลิตชิปลงทุน/ค้ำประกันกลับเข้าผู้ให้บริการ → กู้เพิ่มไปซื้อชิปอีก. BIS ใส่เรื่องนี้เป็น 1 ใน 3 ความเสี่ยงใหญ่สุดต่อระบบการเงินโลกในรายงานประจำปี 2026">
            เรดาร์ห่วงโซ่การเงิน AI
          </Tip>
        </h2>
        <span className={`ac-when ${data.stale ? "is-stale" : ""}`}>
          {data.age_days === 0 ? "วันนี้" : data.age_days === 1 ? "เมื่อวาน" : `${data.age_days} วันก่อน`}
        </span>
      </div>

      {/* 1. รู้สถานะก่อนเริ่มอ่าน */}
      <div className="ac-gauge" role="img"
           aria-label={`${triggered} ใน ${r.counts.total} เงื่อนไขเป็นจริง`}>
        {gauge.map((s) => <span key={s.key} className={`ac-pip ${DOT[s.state]}`} />)}
        <b>{triggered} ใน {r.counts.total}</b> เงื่อนไขเป็นจริง
      </div>

      {/* 2. ถ้าอ่านบรรทัดเดียว ต้องเป็นบรรทัดนี้ */}
      {decisive && (
        <div className={`ac-decisive ac-dec-${decisive.state}`}>
          <div className="ac-dec-top">
            ★ ตัวชี้ขาด{decisive.state === "ok" ? "ยังเขียว"
              : decisive.state === "unknown" ? "วัดไม่ได้รอบนี้" : "พลิกแล้ว"}
            {" — "}<b>{decisive.label} {fmt(decisive)}</b>
            {distance(decisive) && <span className="ac-dec-dist"> ({distance(decisive)})</span>}
          </div>
          <p className="ac-dec-why">
            {/* "ไม่รู้" ต้องไม่ถูกอ่านเป็น "ปลอดภัย" — เป็นคนละเรื่องกันในแง่การตัดสินใจ */}
            {decisive.state === "unknown"
              ? `${decisive.missing ?? "ไม่ทราบสาเหตุ"} · ไม่ใช่ "ยังปลอดภัย" แต่คือ "ไม่รู้"`
              : r.decisive_why}
          </p>
        </div>
      )}

      {/* 3. อะไรเปลี่ยน */}
      {r.first_run ? (
        <p className="ac-change">▸ <b>รอบแรก</b> — ยังไม่มีของเมื่อวานให้เทียบ (เงียบไม่ได้แปลว่านิ่ง แปลว่ายังไม่รู้)</p>
      ) : r.changes.length > 0 ? (
        r.changes.map((c) => (
          <p key={c.key} className="ac-change">
            ▸ <b>{c.label}</b>: {WORD[c.before]} → <b>{WORD[c.after]}</b>{" "}
            <span className={c.worsened ? "ac-worse" : "ac-better"}>
              {c.worsened ? "แย่ลง" : "ดีขึ้น"}
            </span>
          </p>
        ))
      ) : (
        <p className="ac-change ac-quiet">▸ ไม่มีข้อไหนเปลี่ยนสถานะจากรอบก่อน</p>
      )}

      {/* 4. เรื่องที่เดินไปข้างหน้า ไม่ใช่ checklist */}
      {r.chapters.map((ch, i) => {
        const members = r.signals.filter((s) => s.chapter === ch.key);
        if (members.length === 0) return null;
        const hit = members.filter((s) => s.state === "alert" || s.state === "watch").length;
        return (
          <Fragment key={ch.key}>
            <h3 className="ac-chapter">
              <span className="ac-chapter-n">{i + 1}</span>
              {ch.title}
              <span className="ac-chapter-hit">{hit}/{members.length} ติด</span>
              {members.some((s) => s.decisive) && <span className="ac-star">★</span>}
            </h3>
            {members.map((s) => (
              <SignalRow key={s.key} s={s} history={data.history?.[s.key] ?? []} />
            ))}
          </Fragment>
        );
      })}

      {/* มุมอับ: ย่อไว้ แต่กดดูได้เสมอ — เรดาร์ที่ไม่บอกว่ามีมุมอับ อันตรายกว่าไม่มีเรดาร์ */}
      <button className="ac-blind-toggle" onClick={() => setShowBlind((v) => !v)}
              aria-expanded={showBlind}>
        {showBlind ? "▾" : "▸"} สิ่งที่เรดาร์นี้มองไม่เห็น ({r.blind_spots.length})
      </button>
      {showBlind && (
        <ul className="ac-blind">
          {r.blind_spots.map((b) => <li key={b}>{b}</li>)}
        </ul>
      )}

      <p className="ac-note">
        นับ<b>เงื่อนไขที่ตรวจสอบได้</b> ไม่ได้ทำนายว่าจะแตกเมื่อไหร่ · เกณฑ์ทุกเส้นเป็นค่าที่เราตั้งเอง
        จึงแสดง &quot;ห่างเส้นแค่ไหน&quot; กำกับทุกข้อ · ไม่ใช่คำแนะนำให้ซื้อ/ขาย
      </p>
    </section>
  );
}
