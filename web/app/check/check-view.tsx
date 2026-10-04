"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";

type Hist = { group: string; bucket: string; n: number; wins?: number; win_rate?: number | null; net?: number; thin?: boolean };
type Wave = { key: string; title: string; with_trade: boolean; kill: number | null; kill_text: string;
              stop_vs_kill?: string; stop_beyond_kill?: boolean };
type Sizing = { risk_pct: number; coins: number; contracts: number; notional: number; margin?: number };
type Result = {
  id: number; asof: string; side: string; entry: number; sl: number | null; tp: number | null;
  risk_usd?: number; risk_pct?: number; equity?: number | null; sizing?: Sizing[];
  context: {
    trend?: Record<string, string>; with_trend?: string[]; against_trend?: string[];
    stop_pct?: number; noise_pct_4h?: number; stop_inside_noise?: boolean; stop_wrong_side?: boolean; rr?: number;
    ema_4h?: { aligned: number; of: number };
    "4H"?: { rsi?: number; macd_hist?: string }; "1H"?: { rsi?: number; macd_hist?: string };
  };
  history: Hist[]; wave: Wave[]; wave_asof?: string | null;
};

const TREND: Record<string, string> = { up: "🟢 ขึ้น", down: "🔴 ลง", mixed: "🟡 ปนกัน", unknown: "⚪ ?" };
const n0 = (x: number | null | undefined, d = 0) =>
  typeof x === "number" ? x.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }) : "—";
const num = (s: string) => (s.trim() === "" ? null : Number(s.replace(/,/g, "")));

export default function CheckView() {
  const [side, setSide] = useState<"long" | "short">("long");
  const [entry, setEntry] = useState("");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [margin, setMargin] = useState("");
  const [lever, setLever] = useState("");
  const [hasTime, setHasTime] = useState<boolean | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`${API_BASE}/api/check`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ side, entry: num(entry), sl: num(sl), tp: num(tp), margin: num(margin),
                               lever: num(lever), has_time: hasTime }),
      });
      if (!r.ok) throw new Error((await r.json()).detail ?? `API ${r.status}`);
      setRes(await r.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const c = res?.context;
  return (
    <>
      <section className="card ck-form">
        <div className="ck-row">
          {(["long", "short"] as const).map((s) => (
            <button key={s} type="button" className={`jn-chip ${side === s ? "on" : ""}`} onClick={() => setSide(s)}>
              {s === "long" ? "Long" : "Short"}
            </button>
          ))}
        </div>
        <div className="ck-grid">
          <label>ราคาเข้า<input inputMode="decimal" placeholder="ว่าง = ราคาตอนนี้" value={entry} onChange={(e) => setEntry(e.target.value)} /></label>
          <label>Stop loss<input inputMode="decimal" value={sl} onChange={(e) => setSl(e.target.value)} /></label>
          <label>TP<input inputMode="decimal" value={tp} onChange={(e) => setTp(e.target.value)} /></label>
          <label>มาร์จิน ($)<input inputMode="decimal" placeholder="ไม่บังคับ" value={margin} onChange={(e) => setMargin(e.target.value)} /></label>
          <label>Leverage<input inputMode="decimal" placeholder="ไม่บังคับ" value={lever} onChange={(e) => setLever(e.target.value)} /></label>
        </div>
        <div className="ck-row">
          <span className="jn-tag-label">มีเวลาดูไม้นี้ไหม</span>
          {[true, false].map((v) => (
            <button key={String(v)} type="button" className={`jn-chip ${hasTime === v ? "on" : ""}`}
                    onClick={() => setHasTime(hasTime === v ? null : v)}>{v ? "มีเวลาดู" : "ไม่มีเวลาดู"}</button>
          ))}
        </div>
        <button type="button" className="ck-go" onClick={run} disabled={busy || !sl}>
          {busy ? "กำลังเช็ก…" : "เช็ก"}
        </button>
        {!sl && <div className="wv-muted">ใส่ stop loss ก่อน — ทุกข้อในเช็กลิสต์วัดจากมัน</div>}
        {err && <div className="error">{err}</div>}
      </section>

      {res && c && (
        <>
          <section className="card">
            <h3 className="ck-h">ไม้นี้</h3>
            <div className="jn-facts">
              {res.side === "long" ? "Long" : "Short"} {n0(res.entry, 1)} · SL {n0(res.sl, 1)} · TP {n0(res.tp, 1)}
            </div>
            <ul className="ck-list">
              {c.stop_wrong_side && <li className="jn-neg">stop อยู่ผิดฝั่งของราคาเข้า</li>}
              {c.stop_pct !== undefined && (
                <li>stop ห่าง <b>{c.stop_pct.toFixed(2)}%</b> · แท่ง 4H แกว่งปกติ {n0(c.noise_pct_4h, 2)}%
                  {c.stop_inside_noise ? " → stop อยู่ในระยะที่ราคาแกว่งเป็นปกติ" : " → stop อยู่นอกระยะแกว่งปกติ"}</li>
              )}
              {c.rr !== undefined && <li>R:R ที่วาง <b>{c.rr.toFixed(1)}</b></li>}
              {res.risk_usd !== undefined && (
                <li>ถ้าโดน stop เสีย <b>{n0(res.risk_usd, 2)}$</b>{res.risk_pct !== undefined && <> = {res.risk_pct.toFixed(2)}% ของพอร์ต</>}</li>
              )}
              {c.trend && (
                <li>เทรนด์ตอนนี้: {Object.entries(c.trend).map(([k, v]) => `${k} ${TREND[v] ?? v}`).join(" · ")}
                  {c.against_trend && c.against_trend.length > 0 && <span className="jn-warn"> · ไม้นี้สวน {c.against_trend.join(", ")}</span>}</li>
              )}
              {c["4H"]?.rsi !== undefined && (
                <li>RSI 4H {c["4H"].rsi.toFixed(0)}{c["1H"]?.rsi !== undefined && ` · 1H ${c["1H"].rsi.toFixed(0)}`}
                  {c["4H"]?.macd_hist && ` · MACD 4H ${c["4H"].macd_hist}`}</li>
              )}
              {c.ema_4h && <li>EMA 4H ที่อยู่ฝั่งเดียวกับไม้นี้ {c.ema_4h.aligned}/{c.ema_4h.of} เส้น</li>}
            </ul>
          </section>

          <section className="card">
            <h3 className="ck-h">ไม้หน้าตาแบบนี้ ในอดีตของคุณ</h3>
            {res.history.length === 0 && <div className="wv-muted">ยังไม่มีข้อมูลพอจะเทียบ</div>}
            {res.history.map((h) => (
              <div key={h.group} className={`jn-row ${h.n < 10 ? "jn-thin" : ""}`}>
                <span>{h.group}: <b>{h.bucket}</b></span>
                <span>{h.n ? `${h.wins}/${h.n} ชนะ (${Math.round((h.win_rate ?? 0) * 100)}%)` : "ยังไม่มีไม้แบบนี้"}</span>
                <span className={(h.net ?? 0) >= 0 ? "jn-pos" : "jn-neg"}>{h.n ? `${(h.net ?? 0) >= 0 ? "+" : ""}${n0(h.net)}$` : ""}</span>
              </div>
            ))}
            <div className="wv-muted">สีจาง = ไม่ถึง 10 ไม้ · ตัวเลขเปลี่ยนตามสมุดที่อัปเดตทุกชั่วโมง</div>
          </section>

          {res.wave.length > 0 && (
            <section className="card">
              <h3 className="ck-h">เทียบกับฉากคลื่น</h3>
              {res.wave_asof && (() => {
                const h = (Date.now() - new Date(res.wave_asof + "Z").getTime()) / 3600000;
                return <div className={h > 12 ? "jn-warn" : "wv-muted"}>
                  จากรายงานคลื่นเมื่อ {h < 1 ? "ไม่ถึงชั่วโมง" : `${Math.round(h)} ชม.`}ก่อน
                  {h > 12 && " — เก่าแล้ว ราคาอาจผ่านเส้นไปแล้ว รัน python -m src.wave data/waves/btc.json --snapshot ใหม่"}
                </div>;
              })()}
              <ul className="ck-list">
                {res.wave.map((w) => (
                  <li key={w.key}>
                    ฉาก {w.key} — {w.title} {w.with_trade ? "· ไปทางเดียวกับไม้นี้" : "· สวนกับไม้นี้"}
                    <div className="wv-muted">ผิดเมื่อ {w.kill_text}</div>
                    {w.stop_vs_kill && <div className={w.stop_beyond_kill ? "" : "jn-warn"}>{w.stop_vs_kill}</div>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {res.sizing && (
            <section className="card">
              <h3 className="ck-h">ขนาดไม้ ถ้าจะให้เสี่ยงเท่านี้ของพอร์ต ({n0(res.equity, 0)}$)</h3>
              {res.sizing.map((s) => (
                <div key={s.risk_pct} className="jn-row">
                  <span>เสี่ยง {s.risk_pct}%</span>
                  <span>{s.contracts} สัญญา ({n0(s.coins, 4)} BTC) · มูลค่า {n0(s.notional)}$</span>
                  <span>{s.margin !== undefined ? `มาร์จิน ${n0(s.margin)}$` : ""}</span>
                </div>
              ))}
            </section>
          )}
          <div className="wv-muted">บันทึกเช็กนี้แล้ว (#{res.id}) — ถ้ากดเข้าบน OKX ภายใน 3 ชม. ระบบจะผูกกับไม้นั้นเอง</div>
        </>
      )}
    </>
  );
}
