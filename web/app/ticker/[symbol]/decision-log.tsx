"use client";

// Phase 27: จด "ตัดสินใจอะไรวันนี้" ต่อ ticker — รวมถึงตอน "ผ่าน" ซึ่งเดิมไม่เคยมีที่บันทึกเลย
// gate2 = ผลเช็คกราฟ/EW ตอนนั้น (free-form, Elliott Wave เองแยกเป็นโปรเจกต์ต่างหาก) เก็บไว้
// ย้อนวัดทีหลังว่าการรอ "ทรงกราฟ" บนตัวที่ health สูงอยู่แล้ว ช่วยจริงไหม

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Decision, DecisionAction, Gate2Status } from "@/lib/types";
import { logDecision } from "@/lib/api";

const ACTIONS: { value: DecisionAction; label: string }[] = [
  { value: "buy", label: "ซื้อ" },
  { value: "pass", label: "ผ่าน" },
  { value: "wait", label: "รอ" },
  { value: "sell", label: "ขาย" },
  { value: "trim", label: "ลดสัดส่วน" },
];

const GATE2: { value: Gate2Status; label: string }[] = [
  { value: "n/a", label: "ไม่เช็ค" },
  { value: "ready", label: "กราฟพร้อม" },
  { value: "not_ready", label: "กราฟยังไม่ส่ง" },
];

function relDate(iso: string): string {
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "วันนี้";
  if (days === 1) return "เมื่อวาน";
  return `${days} วันที่แล้ว`;
}

export default function DecisionLog({ ticker, decisions }: { ticker: string; decisions: Decision[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [action, setAction] = useState<DecisionAction>("wait");
  const [gate2, setGate2] = useState<Gate2Status>("n/a");
  const [gate2Note, setGate2Note] = useState("");
  const [reason, setReason] = useState("");
  const [conviction, setConviction] = useState("");

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await logDecision(ticker, {
        action,
        gate2,
        gate2_note: gate2Note,
        reason,
        conviction: conviction ? Number(conviction) : null,
      });
      setGate2Note("");
      setReason("");
      setConviction("");
      setOpen(false);
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decision-log">
      <div className="thesis-box-head">
        <span className="section-title" style={{ margin: 0 }}>Decision journal</span>
        <button className="btn-sm" onClick={() => setOpen(!open)}>{open ? "ยกเลิก" : "+ จดการตัดสินใจ"}</button>
      </div>

      {open && (
        <div className="decision-form">
          <div className="decision-form-row">
            <label className="muted-sm">การตัดสินใจ</label>
            <select className="input" value={action} onChange={(e) => setAction(e.target.value as DecisionAction)}>
              {ACTIONS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
            <label className="muted-sm">กราฟ/gate 2</label>
            <select className="input" value={gate2} onChange={(e) => setGate2(e.target.value as Gate2Status)}>
              {GATE2.map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
            <label className="muted-sm">conviction</label>
            <select className="input" style={{ width: 70 }} value={conviction} onChange={(e) => setConviction(e.target.value)}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <input
            className="input"
            style={{ width: "100%", marginTop: 8 }}
            placeholder="gate2 note เช่น 'wave 4 ยังไม่จบ' / 'หลุด trendline'"
            value={gate2Note}
            onChange={(e) => setGate2Note(e.target.value)}
          />
          <textarea
            className="input textarea"
            style={{ marginTop: 8 }}
            placeholder="เหตุผล"
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          {err && <div className="notice" style={{ borderColor: "var(--red)", color: "var(--red)" }}>{err}</div>}
          <button className="btn" style={{ marginTop: 8 }} disabled={busy} onClick={submit}>บันทึก</button>
        </div>
      )}

      {decisions.length > 0 && (
        <div className="table-scroll" style={{ marginTop: 10 }}>
          <table className="pf-table decision-table">
            <thead>
              <tr>
                <th>เมื่อไหร่</th>
                <th>action</th>
                <th className="num">health</th>
                <th className="num">price</th>
                <th>gate2</th>
                <th>reason</th>
                <th className="num">conv</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id}>
                  <td className="muted-sm">{relDate(d.decided_at)}</td>
                  <td><span className={`badge b-${d.action === "buy" ? "cheap" : d.action === "sell" ? "expensive" : "fair"}`}>{d.action}</span></td>
                  <td className="num">{d.health_score != null ? d.health_score.toFixed(1) : "—"}</td>
                  <td className="num">{d.price != null ? `$${d.price.toFixed(2)}` : "—"}</td>
                  <td className="muted-sm">
                    {d.gate2 !== "n/a" && <span>{d.gate2 === "ready" ? "✓ " : "✗ "}</span>}
                    {d.gate2_note || (d.gate2 !== "n/a" ? d.gate2 : "—")}
                  </td>
                  <td className="muted-sm">{d.reason || "—"}</td>
                  <td className="num">{d.conviction ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
