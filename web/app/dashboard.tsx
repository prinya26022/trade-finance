"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Analysis, WatchlistItem } from "@/lib/types";
import { addToWatchlist, removeFromWatchlist } from "@/lib/api";
import { GlossaryText, Tip, BADGES } from "@/lib/glossary";

function pct(x: number | null | undefined) {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

function AnalysisCard({ a }: { a: Analysis }) {
  const s = a.summary;
  return (
    <div className="card">
      <div className="card-head">
        <span className="ticker">{a.ticker}</span>
        <span className="price">${a.price?.toFixed(2)}</span>
      </div>

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
        <span style={{ marginLeft: "auto" }}>{a.run_at.replace("T", " ")}</span>
      </div>
    </div>
  );
}

export default function Dashboard({
  analyses,
  watchlist,
}: {
  analyses: Analysis[];
  watchlist: WatchlistItem[];
}) {
  const router = useRouter();
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

  return (
    <>
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
        <div className="grid">
          {filtered.map((a) => (
            <AnalysisCard key={a.id} a={a} />
          ))}
        </div>
      )}
    </>
  );
}
