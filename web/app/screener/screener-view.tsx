"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { ScreenerResponse, ScreenerResult, HealthTrends } from "@/lib/types";
import { getScreener, addToWatchlist } from "@/lib/api";
import { Tip } from "@/lib/glossary";
import { Sparkline, trendColor } from "@/lib/charts";

function pct(x: number | null | undefined) {
  return x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}
function num(x: number | null | undefined, digits = 1) {
  return x == null ? "—" : x.toFixed(digits);
}
const tierClass = (tier: string) => (tier === "strong" ? "ok" : tier === "weak" ? "bad" : "");

function ago(epochSeconds: number): string {
  const mins = Math.round((Date.now() / 1000 - epochSeconds) / 60);
  if (mins < 1) return "เมื่อสักครู่";
  if (mins < 60) return `${mins} นาทีที่แล้ว`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ชม.ที่แล้ว`;
  return `${Math.round(hours / 24)} วันที่แล้ว`;
}

export default function ScreenerView({ initial, healthTrends }: { initial: ScreenerResponse; healthTrends: HealthTrends }) {
  const router = useRouter();
  const [data, setData] = useState(initial);
  const [refreshing, setRefreshing] = useState(false);
  const [busyTicker, setBusyTicker] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    if (!confirm("สแกนใหม่ทั้ง list — ใช้เวลาสักครู่ (นาทีระดับ, ยิงข้อมูลจริงทีละตัว) ดำเนินการต่อ?")) return;
    setRefreshing(true);
    setMsg(null);
    try {
      const fresh = await getScreener(true);
      setData(fresh);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  async function add(ticker: string) {
    setBusyTicker(ticker);
    try {
      await addToWatchlist(ticker);
      setData({
        ...data,
        results: data.results.map((r) => (r.ticker === ticker ? { ...r, already_watching: true } : r)),
      });
      setMsg(`เพิ่ม ${ticker} เข้า watchlist แล้ว`);
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyTicker(null);
    }
  }

  return (
    <>
      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi-label">สแกนล่าสุด</span>
          <span className="kpi-val" style={{ fontSize: 16 }}>{ago(data.computed_at)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">ผ่านเกณฑ์ข้อมูลพอ</span>
          <span className="kpi-val">{data.results.length}</span>
        </div>
        <div className="kpi" style={{ display: "flex", alignItems: "center" }}>
          <button className="btn" disabled={refreshing} onClick={refresh}>
            {refreshing ? "กำลังสแกน…" : "รีเฟรชผลสแกน"}
          </button>
        </div>
      </div>
      {msg && <div className="notice">{msg}</div>}

      {data.results.length === 0 ? (
        <div className="empty">ยังไม่มีผลสแกน (cache ว่าง) — กด &quot;รีเฟรชผลสแกน&quot; เพื่อสแกนครั้งแรก</div>
      ) : (
        <div className="table-scroll">
          <table className="pf-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">
                  <Tip def="Piotroski /8 (พื้นฐาน) + reverse-DCF /3 (ราคาถูก/แพง) — เอนจิ้นเดียวกับ health score ในหน้ารวม/portfolio">
                    Health
                  </Tip>
                </th>
                <th className="num">P/E</th>
                <th className="num">ROIC</th>
                <th className="num">
                  <Tip def="ตลาดคาด FCF โตกี่%/ปี เทียบ realistic growth ที่บริษัททำได้จริง — ลบ = ตลาดคาดหวังน้อยกว่าที่ทำได้จริง (ถูก)">
                    Valuation gap
                  </Tip>
                </th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r: ScreenerResult) => (
                <tr key={r.ticker}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Link href={`/ticker/${r.ticker}`} className="ticker-link">{r.ticker}</Link>
                      {(healthTrends[r.ticker]?.length ?? 0) >= 2 && (
                        <Tip def="แนวโน้ม health score ช่วงหลังสุด (มีให้เฉพาะตัวที่อยู่ใน watchlist มาสักพักแล้ว) — เขียว=ดีขึ้น, แดง=แย่ลง">
                          <Sparkline points={healthTrends[r.ticker]} color={trendColor(healthTrends[r.ticker])} />
                        </Tip>
                      )}
                    </div>
                  </td>
                  <td className={`num ${tierClass(r.tier)}`}>
                    {num(r.score)}/{r.max}
                    <div className="muted-sm">{r.label} ({num(r.fundamental_score)}/8 + {num(r.valuation_score)}/3)</div>
                  </td>
                  <td className="num">{r.pe != null ? r.pe.toFixed(1) : "—"}</td>
                  <td className="num">{r.roic != null ? `${r.roic.toFixed(1)}%` : "—"}</td>
                  <td className={`num ${r.gap != null && r.gap < 0 ? "ok" : ""}`}>
                    {pct(r.gap)}
                    <div className="muted-sm">{r.lens} lens</div>
                  </td>
                  <td className="actions">
                    <button
                      className="btn-sm"
                      disabled={r.already_watching || busyTicker === r.ticker}
                      onClick={() => add(r.ticker)}
                    >
                      {r.already_watching ? "อยู่ใน watchlist แล้ว" : busyTicker === r.ticker ? "กำลังเพิ่ม…" : "+ เพิ่มเข้า watchlist"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
