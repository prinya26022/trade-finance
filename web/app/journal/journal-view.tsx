"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";

type Group = { key: string; label: string; single: boolean; options: string[] };
type Summary = { n: number; wins: number; win_rate: number | null; net: number; thin: boolean };
type Ctx = {
  trend?: Record<string, string>; against_trend?: string[]; stop_pct?: number; noise_pct_4h?: number;
  stop_inside_noise?: boolean; rr?: number; ema_4h?: { aligned: number; of: number };
  "4H"?: { rsi?: number; macd_hist?: string }; "1H"?: { rsi?: number; macd_hist?: string };
} | null;
type Trade = {
  id: number; source: string; inst: string; side: string; status: string; opened_at: string | null;
  closed_at: string | null; entry: number | null; exit: number | null; pnl: number | null; sl: number | null;
  tp: number | null; liquidated: boolean; context: Ctx; tags: Record<string, string[]>; note: string | null;
  risk_usd?: number; risk_pct?: number;
};
export type JournalData = {
  trades: Trade[]; tag_groups: Group[];
  stats: { overall: Summary & { avg_win: number | null; avg_loss: number | null; avg_risk_pct: number | null };
           groups: Record<string, Record<string, Summary>>; untagged: number };
};

const TREND: Record<string, string> = { up: "🟢", down: "🔴", mixed: "🟡", unknown: "⚪" };
const n0 = (x: number | null | undefined, d = 0) =>
  typeof x === "number" ? x.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }) : "—";
const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);

function Stats({ s }: { s: JournalData["stats"] }) {
  const o = s.overall;
  if (!o.n) return <div className="card">ยังไม่มีไม้ที่ปิดแล้ว</div>;
  return (
    <section className="card jn-stats">
      <div className="jn-big">
        ปิดแล้ว <b>{o.n}</b> ไม้ · ชนะ <b>{o.wins}</b> ({pct(o.win_rate)}) · สุทธิ{" "}
        <b className={o.net >= 0 ? "jn-pos" : "jn-neg"}>{o.net >= 0 ? "+" : ""}{n0(o.net, 2)}$</b>
      </div>
      {o.avg_win !== null && o.avg_loss !== null && (
        <div className="wv-muted">
          ชนะเฉลี่ย {n0(o.avg_win, 2)}$ · แพ้เฉลี่ย {n0(o.avg_loss, 2)}$ (ชนะหนึ่งไม้ = แพ้ {(o.avg_win / o.avg_loss).toFixed(1)} ไม้)
          {o.avg_risk_pct !== null && <> · เสี่ยงจริงเฉลี่ย {o.avg_risk_pct.toFixed(2)}% ต่อไม้</>}
        </div>
      )}
      <div className="jn-groups">
        {Object.entries(s.groups).map(([title, g]) => (
          <div key={title} className="jn-group">
            <h4>{title}</h4>
            {Object.entries(g).map(([k, v]) => (
              <div key={k} className={`jn-row ${v.thin ? "jn-thin" : ""}`} title={v.thin ? "ไม้น้อยเกิน ยังสรุปไม่ได้" : ""}>
                <span>{k}</span>
                <span>{v.wins}/{v.n} ({pct(v.win_rate)})</span>
                <span className={v.net >= 0 ? "jn-pos" : "jn-neg"}>{v.net >= 0 ? "+" : ""}{n0(v.net)}$</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="wv-muted">สีจาง = ไม้ในกลุ่มนั้นยังไม่ถึง 10 ไม้ อ่านเป็นสัญญาณ ยังไม่ใช่ข้อสรุป</div>
    </section>
  );
}

function TradeCard({ t, groups }: { t: Trade; groups: Group[] }) {
  const [tags, setTags] = useState<Record<string, string[]>>(t.tags || {});
  const [note, setNote] = useState(t.note ?? "");
  const [saved, setSaved] = useState<"idle" | "saving" | "ok" | "err">("idle");

  async function save(next: Record<string, string[]>, nextNote = note) {
    setTags(next);
    setSaved("saving");
    try {
      const res = await fetch(`${API_BASE}/api/journal/${t.id}/tags`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: next, note: nextNote }),
      });
      setSaved(res.ok ? "ok" : "err");
    } catch {
      setSaved("err");
    }
  }

  function toggle(g: Group, opt: string) {
    const cur = tags[g.key] ?? [];
    const on = cur.includes(opt);
    const vals = g.single ? (on ? [] : [opt]) : on ? cur.filter((x) => x !== opt) : [...cur, opt];
    const next = { ...tags, [g.key]: vals };
    if (!vals.length) delete next[g.key];
    save(next);
  }

  const c = t.context;
  const win = (t.pnl ?? 0) > 0;
  return (
    <article id={`t${t.id}`} className={`card jn-trade ${t.status === "open" ? "jn-open" : win ? "jn-win" : "jn-loss"}`}>
      <div className="jn-head">
        <b>{t.side === "long" ? "Long" : "Short"} {t.inst?.replace("-SWAP", "")}</b>
        <span className="wv-muted">
          {t.opened_at ? new Date(t.opened_at + "Z").toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" }) : "ไม่มีเวลาเข้า (นำเข้าจากชีต)"}
        </span>
        <span className="jn-pnl">
          {t.status === "open" ? "เปิดอยู่" : t.pnl !== null ? <span className={win ? "jn-pos" : "jn-neg"}>{win ? "+" : ""}{n0(t.pnl, 2)}$</span> : "—"}
          {t.liquidated && " · liquidate"}
        </span>
      </div>
      <div className="jn-facts">
        เข้า {n0(t.entry, 1)}{t.exit ? ` → ออก ${n0(t.exit, 1)}` : ""} · SL {n0(t.sl, 1)} · TP {n0(t.tp, 1)}
        {t.risk_usd !== undefined && <> · เสี่ยงจริง {n0(t.risk_usd, 2)}${t.risk_pct !== undefined && ` (${t.risk_pct.toFixed(2)}%)`}</>}
      </div>
      {c && (
        <div className="jn-ctx">
          {c.trend && <span>เทรนด์ {Object.entries(c.trend).map(([k, v]) => `${k}${TREND[v] ?? v}`).join(" ")}</span>}
          {c.against_trend && c.against_trend.length > 0 && <span className="jn-warn">สวน {c.against_trend.join(", ")}</span>}
          {c.stop_pct !== undefined && c.noise_pct_4h !== undefined && (
            <span className={c.stop_inside_noise ? "jn-warn" : ""}>
              stop {c.stop_pct.toFixed(2)}% vs แกว่ง 4H {c.noise_pct_4h.toFixed(2)}%
            </span>
          )}
          {c.rr !== undefined && <span className={c.rr > 5 ? "jn-warn" : ""}>R:R {c.rr.toFixed(1)}</span>}
          {c["4H"]?.rsi !== undefined && <span>RSI 4H {c["4H"].rsi.toFixed(0)}</span>}
          {c["4H"]?.macd_hist && <span>MACD 4H {c["4H"].macd_hist}</span>}
          {c.ema_4h && <span>EMA 4H ฝั่งเดียวกับไม้ {c.ema_4h.aligned}/{c.ema_4h.of}</span>}
        </div>
      )}
      <div className="jn-tags">
        {groups.map((g) => (
          <div key={g.key} className="jn-tag-group">
            <span className="jn-tag-label">{g.label}</span>
            {g.options.map((o) => (
              <button key={o} type="button" onClick={() => toggle(g, o)}
                      className={`jn-chip ${(tags[g.key] ?? []).includes(o) ? "on" : ""}`}>{o}</button>
            ))}
          </div>
        ))}
      </div>
      <textarea className="jn-note" placeholder="เหตุผลเพิ่มเติม (ไม่บังคับ)" value={note}
                onChange={(e) => setNote(e.target.value)} onBlur={() => note !== (t.note ?? "") && save(tags, note)} />
      <div className="wv-muted">
        {saved === "saving" ? "กำลังบันทึก…" : saved === "ok" ? "บันทึกแล้ว ✓" : saved === "err" ? "บันทึกไม่สำเร็จ — ลองอีกครั้ง" : ""}
      </div>
    </article>
  );
}

export default function JournalView({ data }: { data: JournalData }) {
  return (
    <>
      <Stats s={data.stats} />
      {data.trades.length === 0 && (
        <div className="card">
          ยังไม่มีไม้ — ใส่ OKX API key (Read only) ใน <code>.env</code> แล้วรัน <code>.\schedule-journal.ps1</code> ครั้งเดียว
        </div>
      )}
      {data.trades.map((t) => <TradeCard key={t.id} t={t} groups={data.tag_groups} />)}
    </>
  );
}
