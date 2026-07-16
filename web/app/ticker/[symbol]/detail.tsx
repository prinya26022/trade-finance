"use client";

import type { Analysis, Change, WatchlistItem, EdgePosition, Investigation, Timeline } from "@/lib/types";
import { GlossaryText, Tip, BADGES } from "@/lib/glossary";
import { resolveHealth } from "@/lib/health";
import { fySeries, latestValue, fmt } from "@/lib/facts";
import { LineChart, BarChart, type Series } from "@/lib/charts";
import { HealthMeter } from "../../health-meter";
import { HealthBreakdown } from "../../health-breakdown";

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
  investigation,
  timeline,
}: {
  ticker: string;
  history: Analysis[];
  changes: Change[];
  watchItem?: WatchlistItem;
  edge?: EdgePosition;
  investigation?: Investigation | null;
  timeline?: Timeline | null;
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
  // period เป็น 'MM-DD' (ไม่มีปี) -> ถ้า analyze() รันมากกว่า 1 ครั้ง/วัน (cron + รันมือ) จะชน
  // label กัน ทั้งทำให้ React key ซ้ำและแกน x งงว่าจุดไหนคือจุดไหน -> เก็บแค่ค่า 'ล่าสุดของวันนั้น'
  const healthByDay = new Map<string, number>();
  for (const h of [...history].filter((h) => h.health_score != null).reverse()) {
    healthByDay.set(h.run_at.slice(5, 10), h.health_score as number);
  }
  const healthTrend = [...healthByDay].map(([period, value]) => ({ period, value }));

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

      {/* ---- Phase 20.2: แตกคะแนนสุขภาพให้อ่านออก (พื้นฐาน X/8 + ราคา Y/3) ---- */}
      {a.health && <HealthBreakdown health={a.health} sentiment={s.sentiment} />}

      {s.thesis_assessment ? (
        <div className="thesis-box">
          <div className="section-title" style={{ margin: "0 0 4px" }}>Thesis check</div>
          <GlossaryText text={s.thesis_assessment} />
        </div>
      ) : null}

      {/* ---- Reverse-DCF (Phase 15) ---- */}
      {a.valuation && (
        <div className="valuation-box">
          <div className="section-title" style={{ margin: "0 0 4px" }}>
            <Tip def="แก้สมการ DCF ย้อนกลับ: เอาราคาตลาดตอนนี้ตั้งเป็นโจทย์ แล้วหาว่าตลาดกำลัง 'price' การเติบโตของกระแสเงินสดอิสระ (FCF) ไว้ที่กี่ % ต่อปีถึงจะได้ราคานี้พอดี แล้วเทียบกับที่บริษัทเคยโตจริงในอดีต">
              Reverse-DCF: ตลาดคาดหวังการเติบโตแค่ไหน
            </Tip>
          </div>
          {a.valuation.implied_growth != null ? (
            <>
              <p className="valuation-line">
                ตลาด price การเติบโตของ FCF ไว้ที่ <strong>{a.valuation.implied_growth.toFixed(1)}%/ปี</strong>
                {a.valuation.realistic_growth != null && (
                  <> เทียบ realistic growth <strong>{a.valuation.realistic_growth.toFixed(1)}%/ปี</strong></>
                )}
                {a.valuation.score != null && <> — คะแนนราคา <strong>{a.valuation.score}/3</strong></>}
                {" "}
                <span className={`lens-tag lens-${a.valuation.lens}`}>
                  {a.valuation.lens === "growth" ? "growth lens" : "standard lens"}
                </span>
              </p>
              {a.valuation.gap != null && (
                <p className={`valuation-gap ${a.valuation.gap >= 10 ? "gap-hot" : a.valuation.gap < 0 ? "gap-cold" : ""}`}>
                  {a.valuation.gap >= 0 ? "▲" : "▼"} gap {a.valuation.gap >= 0 ? "+" : ""}
                  {a.valuation.gap.toFixed(1)} pp
                  {a.valuation.historical_cagr != null && (
                    <span className="muted"> (historical CAGR อ้างอิง {a.valuation.historical_cagr.toFixed(1)}%/ปี)</span>
                  )}
                </p>
              )}
              {a.valuation.flags.length > 0 && (
                <p className="valuation-flag">
                  ⚠ ใช้ growth lens แทน sustainable growth เพราะ: {a.valuation.flags.join(", ")}
                </p>
              )}
              {a.valuation.lens === "growth" && a.valuation.rule_of_40 != null && (
                <p className="muted valuation-assump">
                  Rule of 40: {a.valuation.rule_of_40.toFixed(1)} (growth% + FCF margin%)
                  {a.valuation.rule_of_40 < 20 && " — ต่ำกว่า 20 ระวัง 'โตไม่จริง'"}
                </p>
              )}
              <p className="muted valuation-assump">
                สมมติฐาน: WACC (CAPM) {a.valuation.wacc}% (β={a.valuation.beta_used}) · terminal growth{" "}
                {a.valuation.terminal_growth}% · {a.valuation.years} ปี
              </p>
            </>
          ) : (
            <p className="muted">{a.valuation.note}</p>
          )}
        </div>
      )}

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

      {/* ---- Agentic investigation transcript (Phase 13) ---- */}
      {investigation && (
        <div className="investigation">
          <div className="section-title" style={{ margin: "0 0 6px" }}>
            🔬 การสืบของ agent
            <span className="inv-meta">
              {investigation.steps.length} สเต็ป · {investigation.run_at.slice(0, 10)}
              {investigation.stopped === "max_steps" && " · ชนเพดาน"}
            </span>
          </div>
          <ol className="inv-steps">
            {investigation.steps.map((st, i) => (
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
          <div className="inv-conclusion">
            <span className="inv-brain">🧠 สรุป</span>
            <GlossaryText text={investigation.conclusion} />
          </div>
        </div>
      )}

      {/* ---- Company biography timeline (Phase 14) ---- */}
      {timeline && timeline.events.length > 0 && (
        <div className="biography">
          <div className="section-title" style={{ margin: "0 0 6px" }}>
            📖 ชีวประวัติบริษัท
            <span className="inv-meta">{timeline.events.length} เหตุการณ์หลายปี</span>
          </div>
          {timeline.narrative && (
            <p className="verdict" style={{ borderLeftColor: "var(--amber)", background: "rgba(210,153,34,.08)", borderColor: "rgba(210,153,34,.25)" }}>
              {timeline.narrative}
            </p>
          )}
          <ol className="bio-events">
            {timeline.events.map((e, i) => (
              <li key={i} className={`bio-${e.kind === "8-K" ? "event" : "fund"}`}>
                <span className="bio-date">{e.date}</span>
                <span className={`bio-tag bio-tag-${e.kind === "8-K" ? "event" : "fund"}`}>
                  {e.kind === "8-K" ? "เหตุการณ์" : "พื้นฐาน"}
                </span>
                {e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer" className="bio-detail">
                    <GlossaryText text={e.detail} />
                  </a>
                ) : (
                  <span className="bio-detail"><GlossaryText text={e.detail} /></span>
                )}
              </li>
            ))}
          </ol>
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
                  <Tip def={h.health?.reasons.join("\n") ?? ""}>
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
