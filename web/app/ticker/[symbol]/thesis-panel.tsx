"use client";

// Phase 27: ตั้ง/แก้ thesis + invalidation rules ต่อ ticker — เดิม backend เขียนเสร็จตั้งแต่
// Phase 5 (src/thesis/store.py, src/agent/invalidation.py) แต่ไม่เคยมี UI ให้กรอก ทำให้ theses
// ว่างเปล่ามาตลอดและระบบ "เตือนขาย" ไม่เคยทำงานจริง นี่คือจุดที่อุดช่องนั้น

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Thesis, InvalidationCheck, InvalidationRule, Expectation, ExpectationCheck } from "@/lib/types";
import { setThesis, deleteThesis } from "@/lib/api";

const OPS: InvalidationRule["op"][] = ["<", "<=", ">", ">=", "==", "!="];

function emptyRule(): InvalidationRule {
  return { metric: "", op: "<", value: 0, note: "" };
}

// Phase 30: เส้นตายเริ่มต้น = อีก 1 ปี (ต้องมีเสมอ — ข้ออ้างที่ไม่มีวันหมดอายุคือข้ออ้างที่ไม่มีวันผิด)
function emptyExpectation(): Expectation {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return { claim: "", metric: "", op: ">=", value: 0, by: d.toISOString().slice(0, 10), source: "", note: "" };
}

const STATUS_STYLE: Record<ExpectationCheck["status"], { icon: string; cls: string }> = {
  hit: { icon: "✅", cls: "exp-hit" },
  pending: { icon: "⏳", cls: "exp-pending" },
  missed: { icon: "❌", cls: "exp-missed" },
  unmeasurable: { icon: "❔", cls: "exp-na" },
};

export default function ThesisPanel({
  ticker,
  thesis,
  invalidation,
  expectations,
}: {
  ticker: string;
  thesis: Thesis | null;
  invalidation: InvalidationCheck | null;
  expectations: ExpectationCheck[];
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [text, setText] = useState(thesis?.thesis ?? "");
  const [fairValue, setFairValue] = useState(thesis?.fair_value != null ? String(thesis.fair_value) : "");
  const [rules, setRules] = useState<InvalidationRule[]>(thesis?.invalidation.length ? thesis.invalidation : [emptyRule()]);
  const [expects, setExpects] = useState<Expectation[]>(thesis?.expectations ?? []);

  const breaches = invalidation?.breaches ?? [];
  const hasBreach = breaches.length > 0;
  const missed = expectations.filter((e) => e.status === "missed");

  function startEdit() {
    setText(thesis?.thesis ?? "");
    setFairValue(thesis?.fair_value != null ? String(thesis.fair_value) : "");
    setRules(thesis?.invalidation.length ? thesis.invalidation : [emptyRule()]);
    setExpects(thesis?.expectations ?? []);
    setErr(null);
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const cleanRules = rules
        .filter((r) => r.metric.trim() !== "")
        .map((r) => ({ ...r, value: Number(r.value) }));
      await setThesis(ticker, {
        thesis: text,
        invalidation: cleanRules,
        fair_value: fairValue.trim() === "" ? null : Number(fairValue),
        // ทิ้งแถวที่ยังกรอกไม่ครบ (claim/metric ว่าง) แทนที่จะให้ backend โยน 400 ใส่หน้า
        expectations: expects
          .filter((e) => e.claim.trim() !== "" && e.metric.trim() !== "")
          .map((e) => ({ ...e, value: Number(e.value) })),
      });
      setEditing(false);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`ลบ thesis ของ ${ticker}?`)) return;
    setBusy(true);
    try {
      await deleteThesis(ticker);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="thesis-panel">
      {/* ---- invalidation banner: เด่นที่สุดในกล่องนี้ ต้องเห็นก่อนอย่างอื่น ---- */}
      {hasBreach && (
        <div className="inval-banner">
          <div className="inval-banner-title">🚨 เงื่อนไขออกโดนแตะ — ทบทวน thesis</div>
          <ul className="inval-banner-list">
            {breaches.map((b, i) => (
              <li key={i} className={`inval-item inval-${b.severity}`}>{b.detail}</li>
            ))}
          </ul>
        </div>
      )}

      {/* เลยเส้นตายแล้วไม่ถึงเป้า = เหตุผลที่ซื้อตอนแรกไม่จริง — เตือน แต่คนละระดับกับ breach
          (breach = ธุรกิจแตะเงื่อนไขออก, missed = เรื่องเล่าไม่เกิด ต้องกลับไปทบทวนว่ายังถือทำไม) */}
      {missed.length > 0 && !editing && (
        <div className="exp-banner">
          <div className="exp-banner-title">🔭 เรื่องที่รอไว้ ไม่เกิดตามเส้นตาย ({missed.length})</div>
          <ul className="inval-banner-list">
            {missed.map((e, i) => (
              <li key={i} className="exp-banner-item">
                {e.claim} — ต้องเห็น {e.target} ภายใน {e.by} แต่ได้ {e.actual}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!editing ? (
        <>
          {thesis ? (
            <div className="thesis-box">
              <div className="thesis-box-head">
                <span className="section-title" style={{ margin: 0 }}>Thesis</span>
                <div>
                  <button className="btn-sm" onClick={startEdit} disabled={busy}>แก้ไข</button>{" "}
                  <button className="btn-sm btn-danger" onClick={remove} disabled={busy}>ลบ</button>
                </div>
              </div>
              <p style={{ margin: "6px 0" }}>{thesis.thesis}</p>
              {thesis.fair_value != null && (
                <p className="muted-sm">Fair value: ${thesis.fair_value.toFixed(2)}</p>
              )}
              {thesis.invalidation.length > 0 && (
                <ul className="list" style={{ marginTop: 8 }}>
                  {thesis.invalidation.map((r, i) => (
                    <li key={i} className="muted-sm">
                      {r.metric} {r.op} {r.value} {r.note && `— ${r.note}`}
                    </li>
                  ))}
                </ul>
              )}

              {/* ---- Phase 30: เรื่องเล่าที่รอพิสูจน์ ---- */}
              {expectations.length > 0 && (
                <div className="exp-block">
                  <div className="exp-head">
                    🔭 รอพิสูจน์
                    <span className="muted-sm">
                      {" "}— ข้ออ้างที่ต้องมีตัวเลขมายืนยันภายในเส้นตาย ไม่งั้นถือว่าเป็นแค่เรื่องเล่า
                    </span>
                  </div>
                  {expectations.map((e, i) => {
                    const st = STATUS_STYLE[e.status];
                    return (
                      <div key={i} className={`exp-row ${st.cls}`}>
                        <div className="exp-claim">
                          <span className="exp-icon">{st.icon}</span> {e.claim}
                          {e.source && <span className="muted-sm"> · ที่มา: {e.source}</span>}
                        </div>
                        <div className="exp-detail">
                          ต้องเห็น <code>{e.target}</code> ภายใน {e.by} · ตอนนี้ <strong>{e.actual}</strong>
                          {" · "}
                          <span className="exp-status">{e.status_label}</span>
                          {e.status === "pending" && <span className="muted-sm"> (เหลือ {e.days_left} วัน)</span>}
                        </div>
                        {e.note && <div className="muted-sm">{e.note}</div>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="thesis-box thesis-empty">
              <span className="muted">
                ยังไม่ได้ตั้ง thesis — ไม่มีเงื่อนไขออก และไม่มีข้ออ้างที่รอพิสูจน์สำหรับ {ticker}
              </span>
              <button className="btn-sm" onClick={startEdit}>+ ตั้ง thesis</button>
            </div>
          )}
        </>
      ) : (
        <div className="thesis-box thesis-edit">
          <span className="section-title" style={{ margin: "0 0 6px" }}>Thesis ({ticker})</span>
          <textarea
            className="input textarea"
            placeholder="ทำไมถือ/สนใจตัวนี้..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
          />
          <div style={{ margin: "8px 0" }}>
            <label className="muted-sm">Fair value ($, ไม่บังคับ): </label>
            <input
              className="input"
              style={{ width: 120 }}
              value={fairValue}
              onChange={(e) => setFairValue(e.target.value)}
              inputMode="decimal"
            />
          </div>

          <span className="muted-sm">Invalidation rules — เงื่อนไขที่ถ้าโดนแตะ = thesis ผิด</span>
          {rules.map((r, i) => (
            <div key={i} className="rule-row">
              <input
                className="input"
                placeholder="metric เช่น Operating Margin"
                value={r.metric}
                onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, metric: e.target.value } : x)))}
              />
              <select
                className="input"
                style={{ width: 70 }}
                value={r.op}
                onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, op: e.target.value as InvalidationRule["op"] } : x)))}
              >
                {OPS.map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </select>
              <input
                className="input"
                style={{ width: 90 }}
                placeholder="value"
                value={r.value}
                onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, value: Number(e.target.value) } : x)))}
                inputMode="decimal"
              />
              <input
                className="input"
                placeholder="note (ไม่บังคับ)"
                value={r.note}
                onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)))}
              />
              <button className="chip-x" onClick={() => setRules(rules.filter((_, j) => j !== i))} type="button">✕</button>
            </div>
          ))}
          <button className="btn-sm" onClick={() => setRules([...rules, emptyRule()])} type="button">+ เพิ่ม rule</button>

          {/* ---- Phase 30: แปลงข้ออ้างจากบทวิเคราะห์/คลิป ให้กลายเป็นสิ่งที่ผิดได้ ---- */}
          <div style={{ marginTop: 14 }}>
            <span className="muted-sm">
              🔭 รอพิสูจน์ — เอาข้ออ้างที่ได้ยินมา (&ldquo;สินค้าใหม่จะดัน…&rdquo;) มาแปลงเป็น เมตริก + เป้า + เส้นตาย
              ถ้าแปลงไม่ได้ แปลว่ามันเป็นข้ออ้างที่ไม่มีวันผิด ไม่ควรเอามาใช้ตัดสินใจ
            </span>
          </div>
          {expects.map((e, i) => (
            <div key={i} className="exp-edit">
              <div className="rule-row">
                <input
                  className="input"
                  style={{ flex: 2 }}
                  placeholder='ข้ออ้าง เช่น "Bedrock จะดัน AWS จริง"'
                  value={e.claim}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, claim: ev.target.value } : x)))}
                />
                <button className="chip-x" onClick={() => setExpects(expects.filter((_, j) => j !== i))} type="button">✕</button>
              </div>
              <div className="rule-row">
                <input
                  className="input"
                  placeholder="metric ที่จะวัด เช่น Revenue CAGR"
                  value={e.metric}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, metric: ev.target.value } : x)))}
                />
                <select
                  className="input"
                  style={{ width: 70 }}
                  value={e.op}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, op: ev.target.value as Expectation["op"] } : x)))}
                >
                  {OPS.map((op) => (
                    <option key={op} value={op}>{op}</option>
                  ))}
                </select>
                <input
                  className="input"
                  style={{ width: 90 }}
                  placeholder="เป้า"
                  value={e.value}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, value: Number(ev.target.value) } : x)))}
                  inputMode="decimal"
                />
                <input
                  className="input"
                  style={{ width: 140 }}
                  type="date"
                  value={e.by}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, by: ev.target.value } : x)))}
                />
                <input
                  className="input"
                  placeholder="ที่มา (คลิป/โพสต์/บทวิเคราะห์)"
                  value={e.source}
                  onChange={(ev) => setExpects(expects.map((x, j) => (j === i ? { ...x, source: ev.target.value } : x)))}
                />
              </div>
            </div>
          ))}
          <button className="btn-sm" onClick={() => setExpects([...expects, emptyExpectation()])} type="button">+ เพิ่มข้ออ้างที่รอพิสูจน์</button>

          {err && <div className="notice" style={{ borderColor: "var(--red)", color: "var(--red)" }}>{err}</div>}

          <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
            <button className="btn" onClick={save} disabled={busy || !text.trim()}>บันทึก</button>
            <button className="btn-sm" onClick={() => setEditing(false)} disabled={busy}>ยกเลิก</button>
          </div>
        </div>
      )}
    </div>
  );
}
