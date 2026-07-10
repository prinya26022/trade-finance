"use client";

import { Fragment, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Portfolio, Analysis, ChangeReport, WatchlistItem } from "@/lib/types";
import { resolveHealth } from "@/lib/health";
import { HealthMeter } from "../health-meter";
import { setHolding, addShares, sellHolding } from "@/lib/api";
import { Tip } from "@/lib/glossary";

function money(x: number | null | undefined) {
  if (x == null) return "—";
  const sign = x < 0 ? "-" : "";
  return `${sign}$${Math.abs(x).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function signedPct(x: number | null | undefined) {
  return x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(2)}%`;
}
const pnlClass = (x: number | null | undefined) => (x == null ? "" : x >= 0 ? "ok" : "bad");

export default function PortfolioView({
  portfolio,
  analyses,
  changes,
  watchlist,
}: {
  portfolio: Portfolio;
  analyses: Analysis[];
  changes: ChangeReport[];
  watchlist: WatchlistItem[];
}) {
  const router = useRouter();
  const analysisByTicker = new Map(analyses.map((a) => [a.ticker, a]));
  const changesByTicker = new Map(changes.map((c) => [c.ticker, c.changes]));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [addingFor, setAddingFor] = useState<string | null>(null); // ticker ที่กำลังเปิดฟอร์ม 'ซื้อเพิ่ม'

  // ticker ที่ยัง watch อยู่ (ยังไม่ถือ) -> เลือกมาตั้งเป็น holding ได้
  const holdingTickers = new Set(portfolio.positions.map((p) => p.ticker));
  const watchingOptions = watchlist.filter((w) => !holdingTickers.has(w.ticker));

  async function run(fn: () => Promise<void>, ok: string) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(ok);
      setAddingFor(null);
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* ---- summary ---- */}
      <div className="kpi-row">
        <div className="kpi">
          <span className="kpi-label">มูลค่าพอร์ต</span>
          <span className="kpi-val">{money(portfolio.total_value)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">กำไร/ขาดทุน (ยังไม่ realize)</span>
          <span className={`kpi-val ${pnlClass(portfolio.total_pnl)}`}>
            {money(portfolio.total_pnl)} <span className="kpi-sub">{signedPct(portfolio.total_return)}</span>
          </span>
        </div>
        <div className="kpi">
          <Tip def="กี่โพซิชันที่ผลตอบแทนตั้งแต่วันซื้อ 'ชนะ' การเอาเงินก้อนเดียวกันไปใส่ benchmark — วัด edge จริง ไม่ใช่แค่กำไร">
            <span className="kpi-label">ชนะ {portfolio.benchmark}</span>
          </Tip>
          <span className="kpi-val">
            {portfolio.beating_benchmark}/{portfolio.total_positions}
          </span>
        </div>
      </div>
      {msg && <div className="notice">{msg}</div>}

      {/* ---- add holding ---- */}
      {watchingOptions.length > 0 && (
        <AddHoldingForm
          options={watchingOptions}
          busy={busy}
          onSubmit={(t, price, date, shares) =>
            run(
              () => setHolding(t, { entry_price: price, entry_date: date || null, shares: shares ?? null }),
              `ตั้ง ${t} เป็น holding แล้ว`
            )
          }
        />
      )}

      {/* ---- holdings table ---- */}
      {portfolio.positions.length === 0 ? (
        <div className="empty">ยังไม่มีโพซิชันที่ถืออยู่ — ตั้ง holding จากด้านบน หรือเพิ่ม ticker ในหน้ารวมก่อน</div>
      ) : (
        <div className="table-scroll">
          <table className="pf-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">หุ้น @ ทุนเฉลี่ย</th>
                <th className="num">ราคาตอนนี้</th>
                <th className="num">มูลค่า</th>
                <th className="num">กำไร/ขาดทุน</th>
                <th className="num">edge vs {portfolio.benchmark}</th>
                <th>health</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map((p) => {
                const a = analysisByTicker.get(p.ticker);
                const chg = changesByTicker.get(p.ticker) ?? [];
                const breached = chg.some((c) => c.severity === "alert");
                const health = a ? resolveHealth(a, chg) : null;
                return (
                  <Fragment key={p.ticker}>
                    <tr className={breached ? "row-breach" : ""}>
                      <td>
                        <Link href={`/ticker/${p.ticker}`} className="ticker-link">{p.ticker}</Link>
                        {breached && <Tip def="เงื่อนไขออก (invalidation) โดนแตะ — ทบทวน thesis"><span className="breach-flag">⚠</span></Tip>}
                      </td>
                      <td className="num">
                        {p.shares ?? "—"} @ {p.entry_price.toFixed(2)}
                        {p.weight != null && <div className="muted-sm">{p.weight}% ของพอร์ต</div>}
                      </td>
                      <td className="num">{p.current_price.toFixed(2)}</td>
                      <td className="num">{money(p.market_value)}</td>
                      <td className={`num ${pnlClass(p.unrealized_pnl)}`}>
                        {money(p.unrealized_pnl)}
                        <div className="muted-sm">{signedPct(p.your_return)}</div>
                      </td>
                      <td className={`num ${pnlClass(p.edge)}`}>{signedPct(p.edge)}</td>
                      <td>{health && <HealthMeter health={health} size="sm" />}</td>
                      <td className="actions">
                        <button className="btn-sm" disabled={busy} onClick={() => setAddingFor(addingFor === p.ticker ? null : p.ticker)}>
                          ซื้อเพิ่ม
                        </button>
                        <button
                          className="btn-sm btn-danger"
                          disabled={busy}
                          onClick={() => {
                            if (confirm(`ขาย/เลิกถือ ${p.ticker}? (กลับเป็น watching, entry เดิมยังเก็บไว้)`))
                              run(() => sellHolding(p.ticker), `${p.ticker} กลับเป็น watching แล้ว`);
                          }}
                        >
                          ขาย
                        </button>
                      </td>
                    </tr>
                    {addingFor === p.ticker && (
                      <tr key={p.ticker + "-add"} className="add-row">
                        <td colSpan={8}>
                          <AddSharesForm
                            ticker={p.ticker}
                            busy={busy}
                            onSubmit={(price, shares) =>
                              run(() => addShares(p.ticker, { price, shares }), `ซื้อ ${p.ticker} เพิ่มแล้ว — เฉลี่ยราคาให้อัตโนมัติ`)
                            }
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function AddHoldingForm({
  options,
  busy,
  onSubmit,
}: {
  options: WatchlistItem[];
  busy: boolean;
  onSubmit: (ticker: string, price: number, date: string, shares?: number) => void;
}) {
  const [ticker, setTicker] = useState(options[0]?.ticker ?? "");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState("");
  const [shares, setShares] = useState("");
  return (
    <form
      className="hold-form"
      onSubmit={(e) => {
        e.preventDefault();
        const p = parseFloat(price);
        if (!ticker || !p) return;
        onSubmit(ticker, p, date, shares ? parseFloat(shares) : undefined);
      }}
    >
      <span className="form-title">＋ ตั้ง holding:</span>
      <select className="input" value={ticker} onChange={(e) => setTicker(e.target.value)}>
        {options.map((o) => (
          <option key={o.ticker} value={o.ticker}>{o.ticker}</option>
        ))}
      </select>
      <input className="input" placeholder="ราคาที่ซื้อ" value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
      <input className="input" placeholder="วันที่ (YYYY-MM-DD)" value={date} onChange={(e) => setDate(e.target.value)} />
      <input className="input" placeholder="จำนวนหุ้น" value={shares} onChange={(e) => setShares(e.target.value)} inputMode="decimal" />
      <button className="btn" disabled={busy} type="submit">ตั้ง</button>
    </form>
  );
}

function AddSharesForm({
  ticker,
  busy,
  onSubmit,
}: {
  ticker: string;
  busy: boolean;
  onSubmit: (price: number, shares: number) => void;
}) {
  const [price, setPrice] = useState("");
  const [shares, setShares] = useState("");
  return (
    <form
      className="hold-form"
      onSubmit={(e) => {
        e.preventDefault();
        const p = parseFloat(price);
        const s = parseFloat(shares);
        if (!p || !s) return;
        onSubmit(p, s);
      }}
    >
      <span className="form-title">ซื้อ {ticker} เพิ่ม:</span>
      <input className="input" placeholder="ราคาที่ซื้อเพิ่ม" value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
      <input className="input" placeholder="จำนวนหุ้น" value={shares} onChange={(e) => setShares(e.target.value)} inputMode="decimal" />
      <button className="btn" disabled={busy} type="submit">เฉลี่ยเข้า position</button>
      <span className="muted-sm">ระบบคำนวณราคาเฉลี่ยถ่วงน้ำหนักให้อัตโนมัติ</span>
    </form>
  );
}