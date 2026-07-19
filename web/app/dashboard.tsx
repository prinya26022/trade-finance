"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type {
  Analysis,
  WatchlistItem,
  Change,
  ChangeReport,
  Portfolio,
  EdgePosition,
  HealthTrendPoint,
} from "@/lib/types";
import { addToWatchlist, removeFromWatchlist, freezeTicker, unfreezeTicker } from "@/lib/api";
import { GlossaryText, Tip, BADGES } from "@/lib/glossary";
import { resolveHealth } from "@/lib/health";
import { Sparkline, trendColor } from "@/lib/charts";
import { HealthMeter } from "./health-meter";

function pct(x: number | null | undefined) {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

function signed(x: number) {
  return `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}

// สรุป portfolio ด้านบนสุด — ตอบ 'ตอนนี้ถืออะไร ชนะ index หรือแค่โชค' (checklist ด่าน 182)
function PortfolioHeader({ portfolio }: { portfolio: Portfolio }) {
  if (portfolio.total_positions === 0) return null; // ไม่มี holding -> ไม่ต้องโชว์อะไร
  const { positions, benchmark, beating_benchmark, total_positions } = portfolio;
  const allEdge = positions.reduce((sum, p) => sum + p.edge, 0);
  return (
    <div className="portfolio">
      <div className="portfolio-head">
        <span className="section-title" style={{ margin: 0 }}>
          Portfolio · ถืออยู่ {total_positions} ตัว
        </span>
        <Tip def={`กี่ตัวที่ผลตอบแทนตั้งแต่วันซื้อ ชนะการเอาเงินก้อนเดียวกันไปใส่ ${benchmark}`}>
          <span className={beating_benchmark >= total_positions - beating_benchmark ? "ok" : "bad"}>
            ชนะ {benchmark} {beating_benchmark}/{total_positions}
          </span>
        </Tip>
      </div>
      <div className="portfolio-rows">
        {positions.map((p) => (
          <div key={p.ticker} className="pf-row">
            <span className="pf-ticker">{p.ticker}</span>
            <span className={p.your_return >= 0 ? "ok" : "bad"}>you {signed(p.your_return)}</span>
            <span className="muted">
              {p.benchmark} {signed(p.benchmark_return)}
            </span>
            <Tip def="ผลตอบแทนของคุณ ลบด้วยผลตอบแทน benchmark — บวก = มี edge จริง, ลบ = แพ้ index">
              <span className={`edge ${p.edge >= 0 ? "edge-win" : "edge-lose"}`}>
                edge {signed(p.edge)}
              </span>
            </Tip>
            <span className="muted pf-days">{p.holding_days}d</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalysisCard({
  a,
  changes,
  watchItem,
  edge,
  healthTrend,
  onRemove,
  onFreeze,
  onUnfreeze,
}: {
  a: Analysis;
  changes: Change[];
  watchItem?: WatchlistItem;
  edge?: EdgePosition;
  healthTrend: HealthTrendPoint[];
  onRemove: (ticker: string) => void;
  onFreeze: (ticker: string) => void;
  onUnfreeze: (ticker: string) => void;
}) {
  const s = a.summary;
  const isHolding = watchItem?.status === "holding";
  const isFrozen = watchItem?.status === "frozen";
  const health = resolveHealth(a, changes);
  const topSeverity = changes.some((c) => c.severity === "alert")
    ? "alert"
    : changes.some((c) => c.severity === "warn")
    ? "warn"
    : changes.length
    ? "info"
    : null;
  return (
    <div className={`card${isHolding ? " card-holding" : ""}`}>
      <div className="card-head">
        {topSeverity && <span className={`dot dot-${topSeverity}`} title="มีการเปลี่ยนแปลง" />}
        <Link href={`/ticker/${a.ticker}`} className="ticker ticker-link">
          {a.ticker}
        </Link>
        {isHolding ? (
          <Tip def="ถืออยู่จริง — invalidation/thesis-stop มีน้ำหนักเต็ม (ต่างจากแค่จับตา)">
            <span className="hold-tag">📌 HOLD</span>
          </Tip>
        ) : isFrozen ? (
          <Tip def="แช่แข็ง — ขายหมดแล้วแต่อยากดูว่าฟื้นไหม วิเคราะห์แค่รอบเดือนแทนรายวัน (ประหยัดโควตา Gemini)">
            <span className="frozen-tag">🧊 frozen</span>
          </Tip>
        ) : (
          <span className="watch-tag">👀 watch</span>
        )}
        <span className="price">${a.price?.toFixed(2)}</span>
        {!isHolding && (
          <span className="card-actions">
            <button
              className="chip-x card-freeze"
              title={
                isFrozen
                  ? `เลิกแช่แข็ง ${a.ticker} (กลับไปวิเคราะห์รายวัน)`
                  : `แช่แข็ง ${a.ticker} (วิเคราะห์รอบเดือนแทนรายวัน ประหยัดโควตา)`
              }
              onClick={() => (isFrozen ? onUnfreeze(a.ticker) : onFreeze(a.ticker))}
            >
              {isFrozen ? "▶" : "🧊"}
            </button>
            <button
              className="chip-x card-remove"
              title={`เอา ${a.ticker} ออกจาก watchlist (ประหยัดโควตา Gemini รายวัน)`}
              onClick={() => {
                if (confirm(`เอา ${a.ticker} ออกจาก watchlist? จะไม่ถูกวิเคราะห์อีกในรอบถัดไป`)) {
                  onRemove(a.ticker);
                }
              }}
            >
              ×
            </button>
          </span>
        )}
      </div>

      <div className="card-health">
        <HealthMeter health={health} size="sm" />
        {healthTrend.length >= 2 && (
          <Tip def="แนวโน้ม health score ช่วงหลังสุด — เขียว=ดีขึ้น, แดง=แย่ลง, เทา=แกว่งเล็กน้อย">
            <Sparkline points={healthTrend} color={trendColor(healthTrend)} />
          </Tip>
        )}
        <Link href={`/ticker/${a.ticker}`} className="deep-link">
          เจาะลึก →
        </Link>
      </div>

      {/* แถบ holding: ต้นทุน + edge vs benchmark (เฉพาะตัวที่ถืออยู่) */}
      {isHolding && watchItem?.entry_price != null && (
        <div className="hold-line">
          <span className="muted">
            เข้า ${watchItem.entry_price}
            {watchItem.entry_date ? ` · ${watchItem.entry_date}` : ""}
          </span>
          {edge && (
            <>
              <span className={edge.your_return >= 0 ? "ok" : "bad"}>you {signed(edge.your_return)}</span>
              <span className={`edge ${edge.edge >= 0 ? "edge-win" : "edge-lose"}`}>
                edge {signed(edge.edge)}
              </span>
            </>
          )}
        </div>
      )}

      {changes.length > 0 && (
        <div className="changes">
          <div className="section-title" style={{ margin: "0 0 6px" }}>
            เปลี่ยนตั้งแต่ครั้งก่อน
          </div>
          <ul className="list">
            {changes.map((c, i) => (
              <li key={i} className={`change change-${c.severity}`}>
                <GlossaryText text={c.detail} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="badges">
        <Tip def={BADGES[s.fundamental_strength]}>
          <span className={`badge b-${s.fundamental_strength}`}>{s.fundamental_strength}</span>
        </Tip>
        <Tip def={BADGES[s.valuation_view]}>
          <span className={`badge b-${s.valuation_view}`}>{s.valuation_view}</span>
        </Tip>
        <Tip def={BADGES[s.sentiment]}>
          <span className={`badge b-${s.sentiment}`}>{s.sentiment}</span>
        </Tip>
      </div>

      {s.beginner_summary && <p className="beginner">{s.beginner_summary}</p>}

      {s.strength_reasons.length > 0 && (
        <>
          <div className="section-title">Strengths</div>
          <ul className="list good">
            {s.strength_reasons.map((r, i) => (
              <li key={i}>
                <GlossaryText text={r} />
              </li>
            ))}
          </ul>
        </>
      )}

      {s.weak_points.length > 0 && (
        <>
          <div className="section-title">Weak points</div>
          <ul className="list weak">
            {s.weak_points.map((w, i) => (
              <li key={i}>
                <span className="area">{w.area}:</span> <GlossaryText text={w.detail} />
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="section-title">Thesis-relevant news</div>
      <ul className="list news">
        {s.thesis_relevant_news.length > 0 ? (
          s.thesis_relevant_news.map((n, i) => <li key={i}>{n}</li>)
        ) : (
          <li className="noise">All recent news is noise (no thesis impact)</li>
        )}
      </ul>

      <div className="meta">
        <Tip def="ความมั่นใจของ AI ต่อผลนี้ (0–1) ตามความครบของข้อมูล">
          <span>conf {a.confidence}</span>
        </Tip>
        <Tip def="ราคาที่ AI รายงาน ตรงกับราคาจริงไหม (กัน AI มั่วราคา)">
          <span className={a.price_ok ? "ok" : "bad"}>price {a.price_ok ? "✓" : "✗"}</span>
        </Tip>
        <Tip def="ข่าวที่ AI อ้าง เป็นข่าวจริงกี่ % (กัน AI แต่งข่าว)">
          <span>news {pct(a.news_grounded_ratio)}</span>
        </Tip>
        <Tip def="ตัวเลขงบที่ AI อ้าง ตรงกับงบจริงกี่ % — ยิ่งสูงยิ่งเชื่อได้ ต่ำ = ระวัง">
          <span>facts {pct(a.facts_grounded_ratio)}</span>
        </Tip>
        {a.extraction_accuracy != null && (
          <Tip
            def={
              "ความแม่นของ 'การคำนวณของเราเอง' (ROE/margin ฯลฯ) เทียบกับตัวเลขที่ yfinance " +
              "คำนวณเองอิสระ — ไม่ใช่ AI, จับบั๊กในโค้ดคำนวณ (ไม่ใช่ AI มั่ว)"
            }
          >
            <span className={a.extraction_accuracy >= 0.8 ? "ok" : "bad"}>
              extract {pct(a.extraction_accuracy)}
            </span>
          </Tip>
        )}
        {a.xbrl_accuracy != null && (
          <Tip
            def={
              "ความแม่นเทียบกับตัวเลขจาก SEC XBRL (10-K ที่บริษัทยื่นเองตามกฎหมาย) — ground truth " +
              "ที่อิสระจาก yfinance 100% (ต่างจาก extract ข้างซ้ายที่เทียบ yfinance กับ yfinance เอง)"
            }
          >
            <span className={a.xbrl_accuracy >= 0.8 ? "ok" : "bad"}>
              xbrl {pct(a.xbrl_accuracy)}
            </span>
          </Tip>
        )}
        <span style={{ marginLeft: "auto" }}>{a.run_at.replace("T", " ")}</span>
      </div>
    </div>
  );
}

export default function Dashboard({
  analyses,
  watchlist,
  changes,
  portfolio,
  healthTrends,
}: {
  analyses: Analysis[];
  watchlist: WatchlistItem[];
  changes: ChangeReport[];
  portfolio: Portfolio;
  healthTrends: Record<string, HealthTrendPoint[]>;
}) {
  const router = useRouter();
  const changesByTicker = new Map(changes.map((c) => [c.ticker, c.changes]));
  const watchByTicker = new Map(watchlist.map((w) => [w.ticker, w]));
  const edgeByTicker = new Map(portfolio.positions.map((p) => [p.ticker, p]));
  const [filter, setFilter] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // กรองฝั่ง client (ฟรี ไม่ยิง API) ตาม ticker
  const q = filter.trim().toUpperCase();
  const filtered = useMemo(
    () => (q ? analyses.filter((a) => a.ticker.includes(q)) : analyses),
    [analyses, q]
  );

  // Triage: แยก 'ต้องดูก่อน' (มี change ระดับ alert/warn เช่น breach/margin หาย) ออกจาก 'เงียบดี'.
  // holding ที่มี breach จะเด้งขึ้นบนสุดเองเพราะ breach คือ severity alert.
  const needsAttention = filtered.filter((a) => {
    const cs = changesByTicker.get(a.ticker) ?? [];
    return cs.some((c) => c.severity === "alert" || c.severity === "warn");
  });
  const attentionSet = new Set(needsAttention.map((a) => a.ticker));
  const quiet = filtered.filter((a) => !attentionSet.has(a.ticker));

  // ticker ที่อยู่ใน watchlist แต่ยังไม่เคยวิเคราะห์ -> โชว์เป็น "pending"
  const analyzed = new Set(analyses.map((a) => a.ticker));
  const pending = watchlist.filter((w) => !analyzed.has(w.ticker));

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    setBusy(true);
    setMsg(null);
    try {
      await addToWatchlist(t);
      setNewTicker("");
      setMsg(`Added ${t} — will be analyzed on the next agent run`);
      router.refresh(); // re-fetch server data (จะเห็น t โผล่ใน pending)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(ticker: string) {
    try {
      await removeFromWatchlist(ticker);
      router.refresh();
    } catch {
      /* เงียบไว้ — refresh จะสะท้อนสถานะจริง */
    }
  }

  async function handleFreeze(ticker: string) {
    try {
      await freezeTicker(ticker);
      router.refresh();
    } catch {
      /* เงียบไว้ — refresh จะสะท้อนสถานะจริง */
    }
  }

  async function handleUnfreeze(ticker: string) {
    try {
      await unfreezeTicker(ticker);
      router.refresh();
    } catch {
      /* เงียบไว้ — refresh จะสะท้อนสถานะจริง */
    }
  }

  function renderCard(a: Analysis) {
    return (
      <AnalysisCard
        key={a.id}
        a={a}
        changes={changesByTicker.get(a.ticker) ?? []}
        watchItem={watchByTicker.get(a.ticker)}
        edge={edgeByTicker.get(a.ticker)}
        healthTrend={healthTrends[a.ticker] ?? []}
        onRemove={handleRemove}
        onFreeze={handleFreeze}
        onUnfreeze={handleUnfreeze}
      />
    );
  }

  return (
    <>
      <PortfolioHeader portfolio={portfolio} />

      <div className="toolbar">
        <input
          className="input"
          placeholder="Filter tickers…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <form className="add-form" onSubmit={handleAdd}>
          <input
            className="input"
            placeholder="Add ticker (e.g. NVDA)"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
          />
          <button className="btn" disabled={busy} type="submit">
            {busy ? "Adding…" : "Add"}
          </button>
        </form>
      </div>
      {msg && <div className="notice">{msg}</div>}

      {pending.length > 0 && (
        <div className="pending">
          <span className="section-title" style={{ margin: 0 }}>In watchlist, not analyzed yet:</span>
          {pending.map((w) => (
            <span key={w.ticker} className="chip">
              {w.ticker}
              <button className="chip-x" onClick={() => handleRemove(w.ticker)} title="remove">
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="error">No tickers match “{filter}”.</div>
      ) : (
        <>
          <div className="triage-head triage-alert">
            ⚠️ ต้องดูก่อน · {needsAttention.length}
          </div>
          {needsAttention.length === 0 ? (
            <p className="triage-empty">ไม่มีอะไรต้องรีบดู — ทุกตัวเงียบดี ✓</p>
          ) : (
            <div className="grid">{needsAttention.map(renderCard)}</div>
          )}

          {quiet.length > 0 && (
            <>
              <div className="triage-head triage-quiet">✓ เงียบดี · {quiet.length}</div>
              <div className="grid">{quiet.map(renderCard)}</div>
            </>
          )}
        </>
      )}
    </>
  );
}
