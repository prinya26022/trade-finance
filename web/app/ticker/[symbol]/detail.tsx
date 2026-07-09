"use client";

import type { Analysis, Change, WatchlistItem, EdgePosition } from "@/lib/types";
import { GlossaryText, Tip, BADGES } from "@/lib/glossary";
import { resolveHealth } from "@/lib/health";
import { fySeries, latestValue, fmt } from "@/lib/facts";
import { LineChart, BarChart, type Series } from "@/lib/charts";
import { HealthMeter } from "../../health-meter";

const C = { blue: "#58a6ff", green: "#3fb950", amber: "#d29922", red: "#f85149" };

function signed(x: number) {
  return `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}

function ChartCard({
  title,
  hint,
  legend,
  children,
}: {
  title: string;
  hint?: string;
  legend?: { name: string; color: string }[];
  children: React.ReactNode;
}) {
  return (
    <div className="chart-card">
      <div className="chart-title">
        {hint ? <Tip def={hint}>{title}</Tip> : title}
      </div>
      {legend && (
        <div className="legend">
          {legend.map((l) => (
            <span key={l.name} className="legend-item">
              <span className="legend-dot" style={{ background: l.color }} />
              {l.name}
            </span>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}

export default function TickerDetail({
  ticker,
  history,
  changes,
  watchItem,
  edge,
}: {
  ticker: string;
  history: Analysis[];
  changes: Change[];
  watchItem?: WatchlistItem;
  edge?: EdgePosition;
}) {
  const a = history[0]; // ล่าสุด
  const s = a.summary;
  const health = resolveHealth(a, changes);
  const isHolding = watchItem?.status === "holding";
  const facts = a.facts ?? [];

  // series สำหรับกราฟ
  const gross = fySeries(facts, "Gross Margin");
  const op = fySeries(facts, "Operating Margin");
  const net = fySeries(facts, "Net Margin");
  const marginSeries: Series[] = [
    { name: "Gross", color: C.blue, points: gross },
    { name: "Operating", color: C.green, points: op },
    { name: "Net", color: C.amber, points: net },
  ].filter((x) => x.points.length >= 2);

  const fcf = fySeries(facts, "Free Cash Flow");
  const shares = fySeries(facts, "Diluted Shares");
  const dso = fySeries(facts, "DSO");

  // health score ต่อรอบวิเคราะห์ (Phase 10) — เก็บทุกแถวตั้งแต่ analyze() คำนวณแล้ว
  // (แถวเก่าก่อนหน้านั้น health_score เป็น null -> กรองออก ไม่ลากเส้นมั่ว)
  const healthTrend = [...history]
    .filter((h) => h.health_score != null)
    .reverse()   // history() คืนใหม่->เก่า, กราฟต้องเก่า->ใหม่
    .map((h) => ({ period: h.run_at.slice(5, 10), value: h.health_score as number }));

  const pctY = (v: number) => `${v.toFixed(0)}%`;

  return (
    <>
      {/* ---- Hero ---- */}
      <div className="detail-hero">
        <div className="hero-row">
          <h1 className="hero-ticker">{ticker}</h1>
          {isHolding ? <span className="hold-tag">📌 HOLD</span> : <span className="watch-tag">👀 watch</span>}
          <span className="hero-price">${a.price?.toFixed(2)}</span>
          <HealthMeter health={health} />
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
          {isHolding && watchItem?.entry_price != null && (
            <span className="hero-entry">
              เข้า ${watchItem.entry_price}
              {watchItem.entry_date ? ` · ${watchItem.entry_date}` : ""}
              {edge && (
                <>
                  {" · "}
                  <span className={edge.your_return >= 0 ? "ok" : "bad"}>you {signed(edge.your_return)}</span>
                  {" · "}
                  <span className={`edge ${edge.edge >= 0 ? "edge-win" : "edge-lose"}`}>edge {signed(edge.edge)}</span>
                </>
              )}
            </span>
          )}
        </div>
      </div>

      {/* ---- Friendly verdict ---- */}
      {s.beginner_summary && <p className="verdict">{s.beginner_summary}</p>}
      {s.thesis_assessment ? (
        <div className="thesis-box">
          <div className="section-title" style={{ margin: "0 0 4px" }}>Thesis check</div>
          <GlossaryText text={s.thesis_assessment} />
        </div>
      ) : null}

      {/* ---- Breaches / changes ---- */}
      {changes.length > 0 && (
        <div className="changes detail-changes">
          <div className="section-title" style={{ margin: "0 0 6px" }}>เปลี่ยน/เงื่อนไขที่โดนแตะ</div>
          <ul className="list">
            {changes.map((c, i) => (
              <li key={i} className={`change change-${c.severity}`}>
                <GlossaryText text={c.detail} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ---- Health trend (Phase 10) ---- */}
      {healthTrend.length >= 2 && (
        <>
          <div className="section-title">คะแนนสุขภาพย้อนหลัง</div>
          <div className="charts-grid" style={{ marginBottom: 18 }}>
            <ChartCard
              title="Health Score"
              hint="คะแนนที่คำนวณและบันทึกไว้ทุกครั้งที่วิเคราะห์ — ถ้าเด้งขึ้น/ลงผิดปกติวันไหน hover จุดนั้นดูเหตุผล หรือเทียบกับ badge/conf ของรอบนั้นได้"
            >
              <LineChart series={[{ name: "Health", color: C.blue, points: healthTrend }]} fmtY={(v) => v.toFixed(0)} />
            </ChartCard>
          </div>
        </>
      )}

      {/* ---- Charts ---- */}
      <div className="section-title">แนวโน้มหลายปี (จากงบจริง)</div>
      <div className="charts-grid">
        {marginSeries.length > 0 && (
          <ChartCard
            title="Margins"
            hint="กำไรขั้นต้น/ดำเนินงาน/สุทธิ เป็น % ของยอดขาย — เส้นชันขึ้น = ความสามารถทำกำไรดีขึ้น"
            legend={marginSeries.map((m) => ({ name: m.name, color: m.color }))}
          >
            <LineChart series={marginSeries} fmtY={pctY} />
          </ChartCard>
        )}
        {fcf.length >= 2 && (
          <ChartCard title="Free Cash Flow" hint="เงินสดจริงที่เหลือหลังลงทุน — โกหกยากสุด ดูว่าโตหรือหด">
            <BarChart points={fcf} color={C.green} fmtY={(v) => fmt(v, "USD")} />
          </ChartCard>
        )}
        {shares.length >= 2 && (
          <ChartCard
            title="Diluted Shares"
            hint="จำนวนหุ้น — ลดลง = ซื้อหุ้นคืน (ดีต่อผู้ถือ), เพิ่มขึ้น = เจือจาง (ระวัง)"
          >
            <LineChart series={[{ name: "Shares", color: C.blue, points: shares }]} fmtY={(v) => fmt(v, "num")} />
          </ChartCard>
        )}
        {dso.length >= 2 && (
          <ChartCard title="DSO (วันเก็บหนี้)" hint="ยิ่งพุ่งขึ้น = เก็บเงินช้าลง อาจดันยอดขายด้วยเครดิตหลวม (red flag)">
            <LineChart series={[{ name: "DSO", color: C.amber, points: dso }]} fmtY={(v) => v.toFixed(0)} />
          </ChartCard>
        )}
      </div>

      {/* ---- Strengths / weaknesses ---- */}
      <div className="two-col">
        <div>
          <div className="section-title">Strengths</div>
          <ul className="list good">
            {s.strength_reasons.map((r, i) => (
              <li key={i}><GlossaryText text={r} /></li>
            ))}
          </ul>
        </div>
        <div>
          <div className="section-title">Weak points</div>
          <ul className="list weak">
            {s.weak_points.map((w, i) => (
              <li key={i}><span className="area">{w.area}:</span> <GlossaryText text={w.detail} /></li>
            ))}
          </ul>
        </div>
      </div>

      {/* ---- News + what to watch ---- */}
      <div className="section-title">Thesis-relevant news</div>
      <ul className="list news">
        {s.thesis_relevant_news.length > 0 ? (
          s.thesis_relevant_news.map((n, i) => <li key={i}>{n}</li>)
        ) : (
          <li className="noise">All recent news is noise (no thesis impact)</li>
        )}
      </ul>
      {s.what_to_watch.length > 0 && (
        <>
          <div className="section-title">What to watch</div>
          <ul className="list">
            {s.what_to_watch.map((w, i) => (
              <li key={i}><GlossaryText text={w} /></li>
            ))}
          </ul>
        </>
      )}

      {/* ---- History timeline ---- */}
      {history.length > 1 && (
        <>
          <div className="section-title">ประวัติการวิเคราะห์</div>
          <div className="timeline">
            {history.map((h) => (
              <div key={h.id} className="tl-row">
                <span className="tl-date">{h.run_at.replace("T", " ")}</span>
                <span className="tl-price">${h.price?.toFixed(2)}</span>
                <span className={`badge b-${h.sentiment}`}>{h.sentiment}</span>
                <span className="muted">conf {h.confidence}</span>
                {h.health_score != null && (
                  <Tip def={h.health?.reasons.join(" · ") ?? ""}>
                    <span className="muted">health {h.health_score.toFixed(1)}</span>
                  </Tip>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
