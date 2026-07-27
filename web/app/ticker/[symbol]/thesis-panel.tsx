"use client";

// Phase 27: ตั้ง/แก้ thesis + invalidation rules ต่อ ticker — เดิม backend เขียนเสร็จตั้งแต่
// Phase 5 (src/thesis/store.py, src/agent/invalidation.py) แต่ไม่เคยมี UI ให้กรอก ทำให้ theses
// ว่างเปล่ามาตลอดและระบบ "เตือนขาย" ไม่เคยทำงานจริง นี่คือจุดที่อุดช่องนั้น

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Thesis, InvalidationCheck, InvalidationRule } from "@/lib/types";
import { setThesis, deleteThesis } from "@/lib/api";

const OPS: InvalidationRule["op"][] = ["<", "<=", ">", ">=", "==", "!="];

function emptyRule(): InvalidationRule {
  return { metric: "", op: "<", value: 0, note: "" };
}

export default function ThesisPanel({
  ticker,
  thesis,
  invalidation,
}: {
  ticker: string;
  thesis: Thesis | null;
  invalidation: InvalidationCheck | null;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [text, setText] = useState(thesis?.thesis ?? "");
  const [fairValue, setFairValue] = useState(thesis?.fair_value != null ? String(thesis.fair_value) : "");
  const [rules, setRules] = useState<InvalidationRule[]>(thesis?.invalidation.length ? thesis.invalidation : [emptyRule()]);

  const breaches = invalidation?.breaches ?? [];
  const hasBreach = breaches.length > 0;

  function startEdit() {
    setText(thesis?.thesis ?? "");
    setFairValue(thesis?.fair_value != null ? String(thesis.fair_value) : "");
    setRules(thesis?.invalidation.length ? thesis.invalidation : [emptyRule()]);
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
            </div>
          ) : (
            <div className="thesis-box thesis-empty">
              <span className="muted">ยังไม่ได้ตั้ง thesis — ไม่มีเงื่อนไขออกที่เช็คได้สำหรับ {ticker}</span>
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
