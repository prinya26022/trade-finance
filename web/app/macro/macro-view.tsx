"use client";

import { useEffect, useState } from "react";
import { getMacro } from "../../lib/api";
import type { MacroResponse, MacroRelease, MacroReaction, AltSeason } from "../../lib/types";

const DIR: Record<string, { icon: string; cls: string }> = {
  up: { icon: "▲", cls: "macro-up" },
  down: { icon: "▼", cls: "macro-down" },
  flat: { icon: "▬", cls: "macro-flat" },
};

// แถบช่วงเหวี่ยง min..max พร้อมจุด mean — ให้ 'เห็น' ว่ากระจายกว้างแค่ไหนด้วยตา
function RangeBar({ r }: { r: MacroReaction }) {
  // สเกลตามค่าสุดโต่งของแถวนี้ (สมมาตรรอบ 0) เพื่ออ่านทิศ +/- ได้
  const bound = Math.max(Math.abs(r.min_pct), Math.abs(r.max_pct), 0.1);
  const pct = (v: number) => ((v + bound) / (2 * bound)) * 100;
  return (
    <div className="macro-rangebar" title={`ต่ำสุด ${r.min_pct}% … สูงสุด ${r.max_pct}%`}>
      <div className="macro-zero" />
      <div
        className="macro-range"
        style={{ left: `${pct(r.min_pct)}%`, width: `${pct(r.max_pct) - pct(r.min_pct)}%` }}
      />
      <div
        className={`macro-mean ${r.mean_pct >= 0 ? "pos" : "neg"}`}
        style={{ left: `${pct(r.mean_pct)}%` }}
      />
    </div>
  );
}

function ReleaseCard({ rel }: { rel: MacroRelease }) {
  const d = DIR[rel.direction] ?? DIR.flat;
  return (
    <section className="macro-card">
      <div className="macro-head">
        <h2>{rel.label}</h2>
        <span className="macro-ref">อ้างอิง {rel.ref_date.slice(0, 7)}</span>
      </div>
      <div className={`macro-signal ${d.cls}`}>
        <span className="macro-icon">{d.icon}</span>
        <span className="macro-desc">{rel.desc}</span>
        <span className="macro-nums">
          {fmt(rel.prev_signal)} → <b>{fmt(rel.signal)}</b> {rel.unit}
        </span>
      </div>

      {rel.reactions.length > 0 ? (
        <>
          <p className="macro-caption">
            ครั้งก่อนๆ ที่สัญญาณแบบนี้ สินทรัพย์ขยับใน {rel.reactions[0].horizon_days} วันถัดมา
            <span className="macro-note"> — ย้อนหลัง ไม่ใช่การทำนาย</span>
          </p>
          <table className="macro-table">
            <thead>
              <tr>
                <th>สินทรัพย์</th>
                <th>เฉลี่ย</th>
                <th className="macro-bar-col">ช่วงเหวี่ยง (min · ● เฉลี่ย · max)</th>
                <th>ขึ้น</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {rel.reactions.map((r) => (
                <tr key={r.asset}>
                  <td>{r.asset}</td>
                  <td className={r.mean_pct >= 0 ? "pos" : "neg"}>{fmtPct(r.mean_pct)}</td>
                  <td className="macro-bar-col">
                    <RangeBar r={r} />
                    <span className="macro-rangetext">
                      {fmtPct(r.min_pct)} … {fmtPct(r.max_pct)}
                    </span>
                  </td>
                  <td>{Math.round(r.share_up * 100)}%</td>
                  <td className="macro-n">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rel.approx && (
            <p className="macro-approx">
              * วันประกาศเป็น<b>ค่าประมาณ</b> (เดือนอ้างอิง + lag). ใส่ FRED_API_KEY ฟรีใน .env
              เพื่ออัปเกรดเป็นวันประกาศจริง
            </p>
          )}
        </>
      ) : (
        <p className="macro-caption">ตัวเลขทรงตัว — ไม่มีทิศให้เทียบสถิติ</p>
      )}
    </section>
  );
}

function AltSeasonCard({ a }: { a: AltSeason }) {
  return (
    <section className={`macro-card macro-alt macro-alt-${a.state}`}>
      <div className="macro-head">
        <h2>Alt vs BTC</h2>
        <span className="macro-ref">ETH/BTC ratio</span>
      </div>
      <div className="macro-alt-label">{a.label}</div>
      <div className="macro-alt-stats">
        <span>
          ETH 30 วัน <b className={a.eth_30d >= 0 ? "pos" : "neg"}>{fmtPct(a.eth_30d)}</b>
        </span>
        <span>
          BTC 30 วัน <b className={a.btc_30d >= 0 ? "pos" : "neg"}>{fmtPct(a.btc_30d)}</b>
        </span>
        <span>
          ratio 90 วัน <b className={a.change_90d >= 0 ? "pos" : "neg"}>{fmtPct(a.change_90d)}</b>
        </span>
      </div>
      <p className="macro-note">
        บอกว่าตอนนี้ ETH แรงกว่า/อ่อนกว่า BTC — ไม่ได้ทำนายว่า &quot;alt season&quot; กำลังมา
        (30 วันกับ 90 วันอาจสวนทางกันได้)
      </p>
    </section>
  );
}

export default function MacroView() {
  const [data, setData] = useState<MacroResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getMacro().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <p className="macro-loading">ดึงข้อมูลไม่สำเร็จ: {err}</p>;
  if (!data)
    return (
      <p className="macro-loading">
        กำลังดึงข้อมูลสด (FRED + ราคาย้อนหลัง + ข่าว) — ใช้เวลาสักครู่…
      </p>
    );

  return (
    <div className="macro-wrap">
      {data.altseason && <AltSeasonCard a={data.altseason} />}

      {data.releases.map((rel) => (
        <ReleaseCard key={rel.key} rel={rel} />
      ))}

      <section className="macro-geo">
        <h2>⚠️ จับตา: ข่าวภูมิรัฐศาสตร์</h2>
        <p className="macro-note">เฝ้าดูความเสี่ยงเฉยๆ — ไม่ใช่สัญญาณซื้อขาย</p>
        {data.geopolitical.length === 0 ? (
          <p className="macro-caption">ไม่มีพาดหัวเด่นในช่วงนี้</p>
        ) : (
          <ul className="macro-geolist">
            {data.geopolitical.map((n, i) => (
              <li key={i}>
                <a href={n.url} target="_blank" rel="noreferrer">
                  {n.title}
                </a>
                {n.source && <span className="macro-src"> — {n.source}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}
