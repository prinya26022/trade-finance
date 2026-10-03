import type React from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export const dynamic = "force-dynamic";

// Phase 54.2 — สามมุมมองของคลื่นชุดเดียวกัน วางคู่กัน: count ที่ผู้ใช้มาร์ก / เครื่องนับเอง /
// มุมมองของ Claude. ทั้งสามอ่านจากรายงานรอบเดียวกัน (snapshot) — หน้านี้ไม่ดึงราคาเอง
//
// สิ่งที่หน้านี้ต้องไม่ทำ: บอกว่าฝั่งไหน "ถูก". ประโยชน์ของการวางเทียบคือเห็นทางที่ตาตัวเองข้ามไป
// ไม่ใช่ได้คำตอบเดียว — จึงไม่มีการรวมคะแนน ไม่มีเปอร์เซ็นต์ และทุกฝั่งต้องบอกราคาที่ทำให้ตัวเองผิด

type Pivot = { label: string; ts: string; price: number; kind: string };
type Guide = { text: string; ok: boolean; value: string };
type Auto = {
  pattern: string; pivots: Pivot[]; complete: boolean; guides: Guide[]; state: string;
  kill_level: number | null; kill_text: string; matches_user: boolean; hits: number; unchecked: number;
};
type Scenario = {
  key: string; title: string; meaning: string; alive: boolean; kill_level: number | null;
  kill_text: string; confirm_text: string; targets: [string, number][]; bias: string;
};
type Check = { text: string; up: boolean | null };
type Trend = { tf: string; state: string; checks: Check[]; lines: Record<string, number> };
type Report = {
  name: string; symbol: string; pivots: Pivot[]; last: { ts: string; close: number }; state: string;
  scenarios: Scenario[]; evidence: { text: string; leans: string }[]; trend: Trend[]; valid: boolean;
  auto: Auto[]; parent: { auto: Auto[] } | null; parent_note: string;
};
type Claude = { asof: string | null; price: string | null; by: string; text: string; age_hours: number | null } | null;
type Snapshot = {
  available: boolean; reason?: string; how?: string; age_hours?: number | null; stale?: boolean;
  stem?: string; generated_at?: string; report?: Report; claude?: Claude;
};

const fmt = (x: number | null | undefined) =>
  typeof x === "number" ? x.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—";
const STATE: Record<string, string> = { up: "🟢 ขาขึ้น", down: "🔴 ขาลง", mixed: "🟡 ปนกัน", unknown: "⚪ วัดไม่ได้" };
const PATTERN: Record<string, string> = { impulse: "impulse 5 คลื่น", zigzag: "zigzag ABC", flat: "flat ABC" };
const STALE_CLAUDE_HOURS = 24;

// markdown แค่ที่คำตอบจากแชทใช้จริง (ตัวหนา / ลิสต์ / ตัวเอียงทั้งบรรทัด) — ไม่ลง library ทั้งตัว
// และไม่ใช้ dangerouslySetInnerHTML เพราะข้อความนี้มาจากการแปะของคน
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : part,
  );
}

function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let items: string[] = [];
  const flush = () => {
    if (items.length) blocks.push(<ul key={blocks.length}>{items.map((x, i) => <li key={i}>{inline(x)}</li>)}</ul>);
    items = [];
  };
  for (const line of text.split("\n")) {
    const t = line.trim();
    if (t.startsWith("- ")) { items.push(t.slice(2)); continue; }
    flush();
    if (!t) continue;
    const italic = t.startsWith("_") && t.endsWith("_");
    blocks.push(<p key={blocks.length} className={italic ? "wv-muted" : ""}>{inline(italic ? t.slice(1, -1) : t)}</p>);
  }
  flush();
  return <>{blocks}</>;
}

async function load(path: string) {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

function AutoList({ title, counts }: { title: string; counts: Auto[] }) {
  if (!counts?.length) return null;
  const mine = counts.findIndex((c) => c.matches_user);
  return (
    <div className="wv-auto">
      <h4>
        {title} · {mine >= 0 ? <>count ของคุณอยู่อันดับ <b>{mine + 1}</b></> : "ไม่มีแบบไหนตรงกับของคุณ"}
      </h4>
      <ol>
        {counts.map((c, i) => (
          <li key={i} className={c.matches_user ? "wv-mine" : ""}>
            <div className="wv-auto-head">
              {c.matches_user && "⭐ "}<b>{PATTERN[c.pattern] ?? c.pattern}</b> — {c.state} ·{" "}
              ตำรา {c.hits}/{c.guides.length}{c.unchecked ? ` (+${c.unchecked} ยังตรวจไม่ได้)` : ""}
            </div>
            <div className="wv-pts">{c.pivots.map((p) => `${p.label}=${fmt(p.price)}`).join("  ")}</div>
            {c.kill_level !== null && <div className="wv-kill">ผิดเมื่อ{c.kill_text} {fmt(c.kill_level)}</div>}
            <div className="wv-guides">
              {c.guides.map((g, k) => (
                <span key={k} className={g.ok ? "wv-ok" : "wv-no"}>{g.ok ? "✓" : "✗"} {g.text} ({g.value})</span>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default async function WavePage({ searchParams }: { searchParams: Promise<{ s?: string }> }) {
  const { s } = await searchParams;
  let stems: string[] = [];
  let snap: Snapshot | null = null;
  let error: string | null = null;
  try {
    stems = (await load("/api/waves")).stems;
    const stem = s && stems.includes(s) ? s : stems[0];
    if (stem) snap = await load(`/api/wave/${stem}`);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }
  const r = snap?.report;
  const claude = snap?.claude ?? null;
  const claudeOld = claude?.age_hours != null && claude.age_hours > STALE_CLAUDE_HOURS;

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>คลื่น — สามมุมมอง</h1>
        <p>
          count ที่คุณมาร์ก · ทุก count ที่เครื่องหาเจอและผ่านกฎเหล็ก · มุมมองของ Claude — จากรายงานรอบเดียวกัน.
          จงใจ<b>ไม่ตัดสินว่าฝั่งไหนถูก</b>: ประโยชน์คือเห็นทางที่ตาตัวเองข้ามไป และทุกฝั่งต้องบอกราคาที่ทำให้ตัวเองผิด.
          ส่วนเทรดสั้น แยกขาดจากพอร์ตลงทุนระยะยาว.
        </p>
        {stems.length > 1 && (
          <div className="nav-links">
            {stems.map((x) => <Link key={x} href={`/wave?s=${x}`} className="nav-link">{x}</Link>)}
          </div>
        )}
      </header>

      {error && (
        <div className="error">
          Cannot reach the API ({error}). Start it with <code>uvicorn src.api.main:app --port 8000</code>
        </div>
      )}
      {!error && (!snap || !snap.available || !r) && (
        <div className="card">
          ยังไม่มีรายงานคลื่น — รัน <code>python -m src.wave data/waves/btc.json --snapshot</code>
        </div>
      )}

      {r && snap && (
        <>
          <div className={`wv-age ${snap.stale ? "wv-stale" : ""}`}>
            {r.symbol} {fmt(r.last.close)} · รายงานเมื่อ {snap.age_hours ?? "?"} ชม.ก่อน
            {snap.stale && " — เก่าแล้ว (เกิน 12 ชม. = แท่ง 4H ผ่านไป 3 แท่ง) รันใหม่ก่อนใช้"}
          </div>

          <div className="wv-trend">
            {r.trend.map((t) => (
              <span key={t.tf} className={`wv-tf wv-${t.state}`} title={t.checks.map((c) => c.text).join(" · ")}>
                {t.tf} {STATE[t.state]}
              </span>
            ))}
          </div>

          <div className="wv-cols">
            <section className="card wv-col">
              <h3>1 · count ที่คุณมาร์ก</h3>
              <div className="wv-pts">{r.pivots.map((p) => `${p.label}=${fmt(p.price)}`).join("  ")}</div>
              <p className="wv-state">กฎเหล็ก {r.valid ? "ผ่านครบ ✅" : "ผิด ❌"} · {r.state}</p>
              {r.scenarios.map((sc) => (
                <div key={sc.key} className="wv-sc">
                  <b>ฉาก {sc.key} — {sc.title}</b> {sc.alive ? "🟢" : "⚫"}
                  <div className="wv-kill">ผิดเมื่อ {sc.kill_text}</div>
                  {sc.confirm_text && <div className="wv-muted">ชัดขึ้นเมื่อ {sc.confirm_text}</div>}
                  <div className="wv-muted">🎯 {sc.targets.map(([t, x]) => `${t} ${fmt(x)}`).join(" · ")}</div>
                </div>
              ))}
              {r.parent_note && <p className="wv-muted">ภาพใหญ่: {r.parent_note}</p>}
              <details>
                <summary>หลักฐานตามตำรา ({r.evidence.length})</summary>
                <ul className="wv-ev">
                  {r.evidence.map((e, i) => (
                    <li key={i}>{e.text} {e.leans !== "-" && <b>→ {e.leans}</b>}</li>
                  ))}
                </ul>
              </details>
            </section>

            <section className="card wv-col">
              <h3>2 · เครื่องนับเอง</h3>
              <p className="wv-muted">
                ไล่ทุกลำดับจุดกลับตัว คัดที่ผิดกฎเหล็กทิ้ง เรียงตามจำนวนข้อที่เข้าตำรา (ไม่ใช่โอกาส)
              </p>
              <AutoList title="ระดับย่อย 4H" counts={r.auto} />
              {r.parent && <AutoList title="ระดับใหญ่ Day" counts={r.parent.auto} />}
            </section>

            <section className="card wv-col">
              <h3>3 · มุมมองของ Claude</h3>
              {claude ? (
                <>
                  <div className={`wv-muted ${claudeOld ? "wv-stale" : ""}`}>
                    {claude.by} · เขียนตอนราคา {claude.price} · {claude.age_hours ?? "?"} ชม.ก่อน
                    {claudeOld && " — ราคาขยับไปแล้ว อ่านเป็นบริบท"}
                  </div>
                  <div className="wv-claude"><Markdown text={claude.text} /></div>
                </>
              ) : (
                <p className="wv-muted">
                  ยังไม่มี — รัน <code>python -m src.wave pack data/waves/{snap.stem}.json</code> แล้วแปะไฟล์ในแชท
                  Claude, เอาคำตอบกลับด้วย <code>python -m src.wave claude data/waves/{snap.stem}.json reply.md</code>
                </p>
              )}
            </section>
          </div>

          <div className="wv-imgs">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${API_BASE}/api/wave/${snap.stem}/image/wave?t=${snap.generated_at}`} alt="count ที่มาร์ก" />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${API_BASE}/api/wave/${snap.stem}/image/auto?t=${snap.generated_at}`} alt="เครื่องนับเอง" />
          </div>
        </>
      )}

      <p className="disclaimer">
        ตรวจ count และไล่ทุกทางที่ราคายังไม่ฆ่า — ไม่ใช่สัญญาณซื้อ/ขาย และไม่มีฝั่งไหนรู้อนาคต.
        ราคาจาก yfinance (BTC-USD) อาจต่างจาก exchange บน TradingView หลักสิบดอลลาร์.
      </p>
    </main>
  );
}
