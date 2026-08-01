"use client";

// Phase 31: วางบทวิเคราะห์ของคนอื่น (คลิป/โพสต์/บทวิเคราะห์) -> แยกเป็นข้ออ้างย่อยแล้วจัดชั้นว่า
// อันไหนตรวจได้จริง อันไหน "ผิดไม่ได้" -> ติ๊กเลือกเฉพาะที่ตรวจได้ บันทึกเข้า thesis เป็น expectation
//
// ทำไมต้องมี: Phase 30 ทำที่เก็บ+ตัวตรวจไว้แล้ว แต่คนที่ไม่ใช่สายการเงินแปลเองไม่ได้ว่า
// "Bedrock จะดัน AWS" ต้องกลายเป็น metric อะไร เท่าไหร่ ภายในเมื่อไหร่ — ถ้าไม่มีตัวช่วยตรงนี้
// ช่อง expectations จะถูกทิ้งว่างเหมือนที่ thesis เคยว่างมา 22 เฟส
//
// ยิง Gemini จริงตอนกดปุ่มเท่านั้น (ไม่มี auto-trigger) และ metric ที่เสนอถูกบังคับฝั่ง backend
// ให้มาจาก facts จริงของ ticker นี้เท่านั้น — LLM แต่งชื่อเมตริกไม่ได้

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ClaimProposal, Thesis } from "@/lib/types";
import { extractClaims, setThesis } from "@/lib/api";

const KIND_STYLE: Record<ClaimProposal["kind"], { icon: string; cls: string }> = {
  checkable: { icon: "✅", cls: "cp-checkable" },
  needs_data: { icon: "📭", cls: "cp-needsdata" },
  unfalsifiable: { icon: "🚫", cls: "cp-unfalsifiable" },
  timing: { icon: "⏱", cls: "cp-timing" },
  factual: { icon: "📌", cls: "cp-factual" },
};

const ORDER: ClaimProposal["kind"][] = ["checkable", "needs_data", "unfalsifiable", "timing", "factual"];

export default function ClaimParser({ ticker, thesis }: { ticker: string; thesis: Thesis | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<ClaimProposal[] | null>(null);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<Set<number>>(new Set());

  async function parse() {
    setBusy(true);
    setErr(null);
    try {
      const out = await extractClaims(ticker, text);
      setResult(out.proposals);
      setLabels(out.kind_labels);
      // ติ๊กให้เฉพาะข้อที่ตรวจได้ไว้ก่อน (ที่เหลือเลือกเองไม่ได้อยู่แล้ว)
      setPicked(new Set(out.proposals.map((p, i) => (p.kind === "checkable" ? i : -1)).filter((i) => i >= 0)));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!result) return;
    setBusy(true);
    setErr(null);
    try {
      const chosen = result.filter((p, i) => picked.has(i) && p.kind === "checkable");
      await setThesis(ticker, {
        // ต่อท้ายของเดิม ไม่เขียนทับ — thesis/rules ที่เขียนไว้เองต้องไม่หาย
        thesis: thesis?.thesis ?? `(ยังไม่ได้เขียน thesis — สร้างจากข้ออ้างที่วางเข้ามา)`,
        invalidation: thesis?.invalidation ?? [],
        fair_value: thesis?.fair_value ?? null,
        expectations: [
          ...(thesis?.expectations ?? []),
          ...chosen.map((p) => ({
            claim: p.claim,
            metric: p.metric,
            op: p.op as Exclude<ClaimProposal["op"], "">,
            value: p.value as number,
            by: p.by,
            source: source.trim(),
            note: p.why,
          })),
        ],
      });
      setResult(null);
      setText("");
      setOpen(false);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const nCheckable = result?.filter((p) => p.kind === "checkable").length ?? 0;
  const nUseless = result?.filter((p) => p.kind === "unfalsifiable" || p.kind === "timing").length ?? 0;

  return (
    <div className="claim-parser">
      <div className="section-title" style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 6px" }}>
        <span>🧪 วางบทวิเคราะห์ที่ได้ยินมา</span>
        <span style={{ flex: 1 }} />
        <button className="btn-sm" onClick={() => setOpen((v) => !v)}>{open ? "ปิด" : "เปิด"}</button>
      </div>

      {open && (
        <>
          <p className="muted-sm" style={{ marginTop: 0 }}>
            วางข้อความจากคลิป/โพสต์/บทวิเคราะห์ → agent จะแยกเป็นข้ออ้างทีละข้อ แล้วบอกว่าข้อไหน
            <strong> พิสูจน์ผิดได้ด้วยตัวเลขจริง</strong> ข้อไหนเป็นแค่ความเชื่อที่ไม่มีวันผิด
          </p>
          <textarea
            className="input textarea"
            rows={5}
            placeholder={`เช่น "${ticker} ดีเพราะสินค้าใหม่กำลังจะออก รายได้น่าจะโตแรง ลงไปก็ไม่ขาดทุน ระยะสั้นน่าจะขึ้น"`}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="ที่มา (ชื่อคลิป/เพจ/วันที่) — เก็บไว้ดูทีหลังว่าแหล่งไหนพูดถูกบ่อย"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
            <button className="btn" onClick={parse} disabled={busy || !text.trim()}>
              {busy ? "กำลังแยกข้ออ้าง…" : "แยกข้ออ้าง"}
            </button>
          </div>

          {err && <div className="notice" style={{ borderColor: "var(--red)", color: "var(--red)", marginTop: 8 }}>{err}</div>}

          {result && (
            <>
              <div className="cp-summary">
                แยกได้ {result.length} ข้ออ้าง — <strong>{nCheckable} ข้อตรวจได้ด้วยตัวเลขจริง</strong>
                {nUseless > 0 && <> · {nUseless} ข้อเป็นความเชื่อ/การเดาจังหวะที่พิสูจน์ผิดไม่ได้</>}
              </div>

              {ORDER.map((kind) => {
                const rows = result.map((p, i) => ({ p, i })).filter((x) => x.p.kind === kind);
                if (rows.length === 0) return null;
                const st = KIND_STYLE[kind];
                return (
                  <div key={kind} className="cp-group">
                    <div className="cp-group-head">{st.icon} {labels[kind] ?? kind} ({rows.length})</div>
                    {rows.map(({ p, i }) => (
                      <div key={i} className={`cp-row ${st.cls}`}>
                        {kind === "checkable" && (
                          <input
                            type="checkbox"
                            checked={picked.has(i)}
                            onChange={(e) => {
                              const next = new Set(picked);
                              e.target.checked ? next.add(i) : next.delete(i);
                              setPicked(next);
                            }}
                          />
                        )}
                        <div>
                          <div className="cp-claim">{p.claim}</div>
                          {kind === "checkable" ? (
                            <div className="cp-detail">
                              ต้องเห็น <code>{p.metric} {p.op} {p.value}</code> ภายใน {p.by}
                              {p.deadline_defaulted && (
                                <span className="cp-warn"> · เส้นตายนี้ระบบเติมให้เอง ควรแก้ให้ตรงกับที่เขาพูด</span>
                              )}
                            </div>
                          ) : (
                            <div className="cp-detail">{p.why}</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}

              <button className="btn" onClick={save} disabled={busy || picked.size === 0} style={{ marginTop: 10 }}>
                บันทึก {picked.size} ข้อที่เลือกเข้า thesis
              </button>
              <span className="muted-sm"> — ข้อที่ตรวจไม่ได้จะไม่ถูกบันทึก (ตั้งใจ)</span>
            </>
          )}
        </>
      )}
    </div>
  );
}