"use client";

// Phase 28: สั่ง agent สืบจากหน้าเว็บ — agentic loop (Phase 13) มีมานานแล้วแต่ยิงได้จาก CLI
// อย่างเดียว หน้านี้เคยแสดงได้แค่ transcript เก่าที่ค้างอยู่ใน DB. ตอนนี้กดปุ่มสืบใหม่ได้ และ
// *เห็นสเต็ปโผล่ทีละอัน* ระหว่างที่ agent กำลังคิด (POST สั่ง -> poll /status ทุก 1.5 วิ)
// ไม่ใช่หมุนรอเฉยๆ แล้วผลโผล่มาทั้งก้อน — ตัวการสืบเองใช้เวลาระดับสิบวินาทีถึงนาที
//
// เตือนโควตา: ปุ่มนี้ยิง Gemini จริงหลายเทิร์นต่อการกด 1 ครั้ง (คู่กับหน้า chat) จึงต้องกดเอง
// เท่านั้น ไม่มี auto-trigger ตอน render และ backend กันกดซ้ำระหว่างที่ยังวิ่งอยู่ (409)

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Investigation, InvestigationJob, InvestigationStep } from "@/lib/types";
import { GlossaryText } from "@/lib/glossary";
import { startInvestigation, getInvestigationStatus } from "@/lib/api";

const POLL_MS = 1500;

function StepList({ steps }: { steps: InvestigationStep[] }) {
  return (
    <ol className="inv-steps">
      {steps.map((st, i) => (
        <li key={i}>
          <div className="inv-tool">
            🔧 <code>{st.tool}</code>
            {Object.keys(st.args).length > 0 && (
              <span className="inv-args">({Object.values(st.args).join(", ")})</span>
            )}
          </div>
          <div className="inv-obs"><GlossaryText text={st.observation} /></div>
        </li>
      ))}
    </ol>
  );
}

export default function InvestigatePanel({
  ticker,
  initial,
}: {
  ticker: string;
  initial: Investigation | null;
}) {
  const router = useRouter();
  const [job, setJob] = useState<InvestigationJob | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [focus, setFocus] = useState("");
  const [showFocus, setShowFocus] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const startedRef = useRef<number>(0);

  const poll = useCallback(async () => {
    try {
      const j = await getInvestigationStatus(ticker);
      if (j) setJob(j);
      if (!j || j.status !== "running") {
        setRunning(false);
        router.refresh(); // ดึง transcript ที่ persist ลง DB แล้วกลับมาเป็นค่า initial รอบหน้า
      }
    } catch (e) {
      setRunning(false);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [ticker, router]);

  // รีเฟรชหน้าระหว่างที่ยังสืบอยู่ (หรือเปิดอีกแท็บ) -> job ยังวิ่งอยู่ฝั่ง API ให้ต่อการ poll เลย
  useEffect(() => {
    getInvestigationStatus(ticker)
      .then((j) => {
        if (!j) return;
        setJob(j);
        if (j.status === "running") {
          startedRef.current = Date.parse(j.started_at) || Date.now();
          setRunning(true);
        }
      })
      .catch(() => {}); // backend ไม่ตอบ = ไม่มีอะไรให้ต่อ ปล่อยผ่าน (หน้าอื่นๆ ยังใช้ได้)
  }, [ticker]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(poll, POLL_MS);
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - startedRef.current) / 1000)), 1000);
    return () => {
      clearInterval(id);
      clearInterval(tick);
    };
  }, [running, poll]);

  async function run() {
    setErr(null);
    startedRef.current = Date.now();
    setElapsed(0);
    try {
      const j = await startInvestigation(ticker, focus.trim());
      setJob(j);
      setRunning(true);
      setShowFocus(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  // ผลของ job รอบนี้มาก่อน transcript เก่าเสมอ (ระหว่างวิ่งก็โชว์สเต็ปสดๆ ของมัน)
  const useJob = job !== null && (running || job.steps.length > 0 || job.status === "error");
  const steps = useJob ? job.steps : initial?.steps ?? [];
  const conclusion = useJob ? job.conclusion : initial?.conclusion ?? "";
  const stopped = useJob ? job.stopped : initial?.stopped ?? "";
  const when = useJob ? (job.finished_at ?? job.started_at).slice(0, 10) : initial?.run_at.slice(0, 10) ?? "";
  const jobError = useJob ? job.error : null;

  return (
    <div className="investigation">
      <div className="section-title" style={{ margin: "0 0 6px", display: "flex", alignItems: "center", gap: 8 }}>
        <span>🔬 การสืบของ agent</span>
        <span className="inv-meta">
          {steps.length > 0 && `${steps.length} สเต็ป`}
          {when && ` · ${when}`}
          {stopped === "max_steps" && " · ชนเพดาน"}
        </span>
        <span style={{ flex: 1 }} />
        {!running && (
          <>
            <button className="btn-sm" onClick={() => setShowFocus((v) => !v)} title="ระบุโจทย์ให้ agent สืบเจาะจง">
              🎯
            </button>{" "}
            <button className="btn-sm" onClick={run}>
              {initial || job ? "สืบใหม่" : "ให้ agent สืบ"}
            </button>
          </>
        )}
      </div>

      {showFocus && !running && (
        <input
          className="input"
          style={{ width: "100%", marginBottom: 8 }}
          placeholder="อยากให้เจาะอะไรเป็นพิเศษ? เช่น ทำไม operating margin ตกสองปีติด (เว้นว่างได้)"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
      )}

      {running && (
        <div className="inv-running">
          <span className="inv-pulse" />
          {steps.length === 0
            ? "กำลังดึงงบ/ข่าว/ไฟล์ SEC มาเตรียมให้ agent…"
            : `agent กำลังคิดสเต็ปที่ ${steps.length + 1}…`}
          <span className="muted"> ({elapsed}s · ยิง Gemini จริง ปิดหน้านี้ได้ ผลถูกบันทึกไว้)</span>
        </div>
      )}

      {err && <div className="notice" style={{ borderColor: "var(--red)", color: "var(--red)", marginTop: 8 }}>{err}</div>}

      {steps.length > 0 && <StepList steps={steps} />}

      {jobError ? (
        <div className="inv-conclusion">
          <span className="inv-brain" style={{ color: "var(--red)" }}>⚠ สืบไม่สำเร็จ</span>
          {jobError}
        </div>
      ) : conclusion ? (
        <div className="inv-conclusion">
          <span className="inv-brain">🧠 สรุป</span>
          <GlossaryText text={conclusion} />
        </div>
      ) : !running && steps.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>
          ยังไม่เคยสืบ {ticker} — กดปุ่มให้ agent วางแผนเอง เรียก tool ดูงบ/ข่าว/ไฟล์ SEC ทีละสเต็ป แล้วสรุปว่าพื้นฐานแข็งหรืออ่อนตรงไหน
        </p>
      ) : null}
    </div>
  );
}