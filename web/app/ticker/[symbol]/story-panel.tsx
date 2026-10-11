"use client";

// Phase 56: เรื่องอนาคต 3 ข้อ (วิธีคิดแบบ CK Cheong ทำให้ตรวจได้) — พื้นฐานของทุกตัวใน watchlist
// ร่างของ Claude โชว์ป้ายชัดๆ: เป็นจุดเริ่มให้แก้เป็นคำของผู้ใช้ ไม่ใช่ความเชื่อของผู้ใช้เอง

import { useEffect, useState } from "react";
import { getStory, saveStory, type Story } from "@/lib/api";

const QUESTIONS: { key: "future" | "signals" | "wrong_if"; label: string; hint: string }[] = [
  { key: "future", label: "1. สินค้า/บริการนี้อีก 5–10 ปีจะดีขึ้นเพราะอะไร", hint: "มองที่สินค้า ไม่ใช่ราคาหุ้น" },
  { key: "signals", label: "2. ถ้าข้อ 1 จริง ตัวเลขอะไรต้องเกิดตามมา", hint: "สิ่งที่เทียบกับผลวิเคราะห์แต่ละรอบได้" },
  { key: "wrong_if", label: "3. เห็นอะไรแล้วจะยอมรับว่าคิดผิด", hint: "ราคาลงแต่ยังไม่เห็นข้อนี้ = ยังไม่ผิด" },
];

export default function StoryPanel({ ticker }: { ticker: string }) {
  const [story, setStory] = useState<Story | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ future: "", signals: "", wrong_if: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getStory(ticker)
      .then((s) => setStory(s))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoaded(true));
  }, [ticker]);

  function startEdit() {
    setDraft({ future: story?.future ?? "", signals: story?.signals ?? "", wrong_if: story?.wrong_if ?? "" });
    setEditing(true);
  }

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      setStory(await saveStory(ticker, draft));
      setEditing(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // วิธีของโช๊ค โชกุล: ให้ AI แย้ง thesis — เติมโจทย์ให้กล่อง "การสืบของ agent" แล้วผู้ใช้กดสืบเอง
  function challenge() {
    if (!story) return;
    const brief =
      `ทำหน้าที่ฝ่ายค้าน: หาหลักฐานจากข้อมูลจริงที่ขัดกับเรื่องอนาคตของ ${ticker} 3 ข้อนี้ ` +
      `(1) ${story.future} (2) ตัวเลขที่ต้องเกิด: ${story.signals} (3) ผิดเมื่อ: ${story.wrong_if}. ` +
      `ตอบทีละข้อว่ามีหลักฐานแย้งไหม ตัวเลขในข้อ 2 ตอนนี้เป็นยังไงจริง และเงื่อนไขข้อ 3 เข้าใกล้แค่ไหน ` +
      `แยกให้ชัดว่าส่วนไหนเป็นข้อมูล ส่วนไหนเป็นการตีความ`;
    window.dispatchEvent(new CustomEvent("investigate-focus", { detail: brief }));
  }

  if (!loaded) return null;

  return (
    <div className="decision-log">
      <div className="thesis-box-head">
        <span className="section-title" style={{ margin: 0 }}>เรื่องอนาคต 3 ข้อ</span>
        {story && !editing && (
          <button className="btn-sm" onClick={challenge}
                  title="เติมโจทย์ให้ agent หาหลักฐานแย้ง 3 ข้อนี้ — กดสืบเองในกล่องการสืบ (ใช้โควตา Gemini)">
            ให้ AI แย้ง
          </button>
        )}
        <button className="btn-sm" onClick={() => (editing ? setEditing(false) : startEdit())}>
          {editing ? "ยกเลิก" : story ? "แก้" : "+ เขียน"}
        </button>
      </div>

      {story?.author === "claude-draft" && !editing && (
        <p className="muted-sm">
          ร่างโดย Claude ({story.updated_at.slice(0, 10)}) จากผลวิเคราะห์ในระบบ — ยังไม่ใช่ความเห็นของคุณ
          กด &quot;แก้&quot; แล้วเขียนเป็นคำของตัวเอง
        </p>
      )}

      {editing ? (
        <div className="decision-form">
          {QUESTIONS.map((q) => (
            <div className="decision-form-row" key={q.key}>
              <label className="muted-sm">
                {q.label} <span style={{ opacity: 0.7 }}>· {q.hint}</span>
              </label>
              <textarea
                className="input"
                rows={3}
                value={draft[q.key]}
                onChange={(e) => setDraft({ ...draft, [q.key]: e.target.value })}
              />
            </div>
          ))}
          <button className="btn-sm" disabled={busy} onClick={submit}>
            {busy ? "กำลังบันทึก…" : "บันทึก"}
          </button>
        </div>
      ) : story ? (
        QUESTIONS.map((q) => (
          <div key={q.key} style={{ marginTop: 8 }}>
            <div className="muted-sm">{q.label}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{story[q.key]}</div>
          </div>
        ))
      ) : (
        <p className="muted-sm">ยังไม่ได้เขียน — ตอบ 3 ข้อนี้ก่อนตัดสินใจซื้อ จะได้รู้ว่าราคาลงเมื่อไหร่คือโอกาส และเมื่อไหร่คือคิดผิด</p>
      )}
      {err && <div className="error">{err}</div>}
    </div>
  );
}
