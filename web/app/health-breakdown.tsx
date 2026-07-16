// Phase 20.2: "ทำไมได้คะแนนนี้" — แตกคะแนนสุขภาพ (เลขเดียว) ให้เห็นว่าประกอบจาก 2 ขา
//   สุขภาพ = พื้นฐาน X/8 (คุณภาพธุรกิจ) + ราคา Y/3 (ถูก/แพง)
// เป้าหมายเชิงสอน: ให้คนที่เดิมดูแค่เลขรวม เข้าใจว่า health 8 ที่มาจาก 'พื้นฐานแกร่ง+แพง'
// ต่างจาก health 8 ที่มาจาก 'พื้นฐานกลางๆ+ถูกมาก' คนละเรื่องกัน — และเห็นว่าเกณฑ์ไหนผ่าน/ตก
// ข้อมูลทั้งหมด (components/criteria) มาจาก health JSON ที่ backend เก็บอยู่แล้ว ไม่ต้องคำนวณสด
import { Tip } from "@/lib/glossary";
import type { Fact, PersistedHealth } from "@/lib/types";
import { fySeries, latestValue } from "@/lib/facts";

const FUND_MAX = 8;
const VAL_MAX = 3;

// คำอธิบายไทยรายเกณฑ์ (key = label จาก PIOTROSKI_CRITERIA ใน health.py — ต้องตรงเป๊ะ)
const CRITERION_HELP: Record<string, string> = {
  "ROIC>WACC":
    "ผลตอบแทนต่อเงินลงทุน (ROIC) สูงกว่าต้นทุนเงินทุน (WACC) = ยิ่งลงทุนยิ่งสร้างมูลค่า ไม่ใช่เผาเงิน",
  "Net Margin สูง(>=10%)":
    "กำไรสุทธิเกิน 10% ของยอดขาย = มีอำนาจตั้งราคา + คุมต้นทุนได้ดี",
  "FCF+คุณภาพกำไร":
    "มีเงินสดอิสระ (FCF) เป็นบวก และกำไรทางบัญชีแปลงเป็นเงินสดจริง (ไม่ใช่กำไรบนกระดาษ)",
  "รายได้เติบโตจริง(>3%)":
    "ยอดขายโตเกินเงินเฟ้อ (>3%/ปี) = โตจริง ไม่ใช่แค่ตามเงินเฟ้อ",
  "หนี้ไม่บานปลาย":
    "หนี้เทียบกำไร (Net Debt/EBITDA) ไม่สูงเกินไป หรือมีเงินสดสุทธิ (net-cash)",
  "จ่ายดอกเบี้ยไหว/net-cash":
    "กำไรจากการดำเนินงานพอจ่ายดอกเบี้ยสบายๆ (Interest Coverage) หรือไม่มีหนี้เลย",
  "Margin ขยาย":
    "กำไรจากการดำเนินงาน (Operating Margin) กว้างขึ้นเทียบปีก่อน = ประสิทธิภาพดีขึ้น",
  "ไม่เจือจางหุ้น":
    "จำนวนหุ้นไม่เพิ่ม (ไม่ออกหุ้นใหม่มาเจือจางผู้ถือเดิม) — ยิ่งลด (ซื้อหุ้นคืน) ยิ่งดี",
};

// ตัวเลขจริงเบื้องหลังแต่ละเกณฑ์ — ดึงจาก facts (ที่มีอยู่แล้ว, ไม่คำนวณสด) มาโชว์ข้างชื่อเกณฑ์
// เพื่อให้เห็นว่า '✓ ผ่าน' ไม่ใช่แค่ label ลอยๆ แต่มาจากตัวเลขงบจริงเท่าไหร่ (จุดสอนหลักของ 20.2)
// mapping ต้องตรงกับ input ของแต่ละ criterion ใน health.py::PIOTROSKI_CRITERIA เป๊ะ
function criterionValue(label: string, facts: Fact[]): string | null {
  switch (label) {
    case "ROIC>WACC": {
      const roic = latestValue(facts, "ROIC");
      return roic ? `ROIC ${roic.value.toFixed(1)}%` : null;
    }
    case "Net Margin สูง(>=10%)": {
      const s = fySeries(facts, "Net Margin");
      return s.length ? `Net Margin ${s[s.length - 1].value.toFixed(1)}%` : null;
    }
    case "FCF+คุณภาพกำไร": {
      const fcf = latestValue(facts, "FCF Margin");
      return fcf ? `FCF Margin ${fcf.value.toFixed(1)}%` : null;
    }
    case "รายได้เติบโตจริง(>3%)": {
      const cagr = latestValue(facts, "Revenue CAGR");
      return cagr ? `Revenue CAGR ${cagr.value.toFixed(1)}%` : null;
    }
    case "หนี้ไม่บานปลาย": {
      const netDebt = latestValue(facts, "Net Debt");
      if (netDebt && netDebt.value <= 0) return "Net Cash (ไม่มีหนี้สุทธิ)";
      const nde = latestValue(facts, "Net Debt / EBITDA");
      return nde ? `Net Debt/EBITDA ${nde.value.toFixed(1)}x` : null;
    }
    case "จ่ายดอกเบี้ยไหว/net-cash": {
      const cov = latestValue(facts, "Interest Coverage");
      if (cov) return `Interest Coverage ${cov.value.toFixed(1)}x`;
      const netDebt = latestValue(facts, "Net Debt");
      return netDebt && netDebt.value <= 0 ? "Net Cash (ไม่มีดอกเบี้ยต้องจ่าย)" : null;
    }
    case "Margin ขยาย": {
      const s = fySeries(facts, "Operating Margin");
      if (s.length < 2) return null;
      const [prev, last] = s.slice(-2);
      return `Operating Margin ${prev.value.toFixed(1)}% → ${last.value.toFixed(1)}%`;
    }
    case "ไม่เจือจางหุ้น": {
      const s = fySeries(facts, "Diluted Shares");
      if (s.length < 2) return null;
      const [prev, last] = s.slice(-2);
      if (!prev.value) return null;
      const pct = ((last.value - prev.value) / prev.value) * 100;
      return `จำนวนหุ้น ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
    }
    default:
      return null;
  }
}

// degree 0-1 -> สัญลักษณ์/สี/คำ (ไล่ระดับตั้งแต่ 19.3 จึงมี 'ก้ำกึ่ง' ไม่ใช่แค่ผ่าน/ตก)
function mark(d: number | null): { sym: string; cls: string; word: string } {
  if (d == null) return { sym: "–", cls: "na", word: "ข้อมูลไม่พอ" };
  if (d >= 0.75) return { sym: "✓", cls: "pass", word: "ผ่าน" };
  if (d >= 0.25) return { sym: "◐", cls: "partial", word: "ก้ำกึ่ง" };
  return { sym: "✗", cls: "fail", word: "ไม่ผ่าน" };
}

// score/3 ของราคา -> ความหมายสั้นๆ (รายละเอียดเต็มอยู่ในกล่อง Reverse-DCF ด้านล่าง)
function valMeaning(score: number | null): string {
  if (score == null) return "ประเมินราคาไม่ได้ (ข้อมูลไม่พอ/ยังขาดทุน)";
  if (score >= 2.5) return "ราคาน่าสนใจ — ตลาดคาดการเติบโตต่ำกว่าที่บริษัททำได้จริง";
  if (score >= 1.5) return "ราคาพอสมเหตุผล — ตลาดคาดใกล้เคียงกับที่ทำได้จริง";
  if (score >= 0.5) return "เริ่มแพง — ตลาดคาดสูงกว่าที่ทำได้จริงพอควร";
  return "แพง — ราคาสะท้อนการเติบโตที่สูงกว่าที่บริษัทเคยทำได้จริงมาก";
}

function Bar({ value, max, tier }: { value: number; max: number; tier: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span className="bd-bar">
      <span className={`bd-bar-fill bd-bar-${tier}`} style={{ width: `${pct}%` }} />
    </span>
  );
}

export function HealthBreakdown({
  health,
  sentiment,
  facts,
}: {
  health: PersistedHealth;
  sentiment: string;
  facts: Fact[];
}) {
  const c = health.components;
  const f = health.fundamental;
  // render เฉพาะแถวที่มีข้อมูลแตกได้จริง (Phase 18+, ไม่ excluded) — แถวเก่า/excluded ข้ามไป
  if (!c || !f || c.strength == null || c.valuation == null) return null;

  const max = health.max ?? 11;
  const hasBreach = c.breach_penalty != null && c.breach_penalty < 0;

  return (
    <div className="breakdown">
      <div className="section-title" style={{ margin: "0 0 8px" }}>
        <Tip def="คะแนนสุขภาพธุรกิจไม่ใช่เลขลอยๆ — มันคือผลบวกของ 2 ขา: คุณภาพธุรกิจ (จากงบจริง 8 ข้อ) กับ ราคาถูก/แพง (จาก reverse-DCF). เลขรวมเท่ากันแต่ที่มาต่างกันได้มาก">
          ทำไมได้คะแนนนี้
        </Tip>
      </div>

      <div className="bd-formula">
        สุขภาพ <strong>{health.score?.toFixed(1)}</strong>/{max} ={" "}
        <span className="bd-formula-part">พื้นฐาน {c.strength.toFixed(1)}/{FUND_MAX}</span>
        {" + "}
        <span className="bd-formula-part">ราคา {c.valuation.toFixed(1)}/{VAL_MAX}</span>
        {hasBreach && <span className="bd-formula-pen"> − เงื่อนไขออกโดนแตะ {c.breach_penalty}</span>}
      </div>

      {/* ---- ขาที่ 1: พื้นฐาน (คุณภาพธุรกิจ) ---- */}
      <div className="bd-leg">
        <div className="bd-leg-head">
          <Tip def="Piotroski-style checklist: เช็คคุณภาพธุรกิจจากงบการเงินจริง 8 ข้อ (กำไร/หนี้/กระแสเงินสด/การเติบโต) แต่ละข้อไล่ระดับ 0-1 ไม่ใช่แค่ผ่าน/ตก — ยิ่งเข้าใกล้ 8 ยิ่งเป็นธุรกิจคุณภาพสูง">
            <span className="bd-leg-name">พื้นฐาน — คุณภาพธุรกิจ</span>
          </Tip>
          <span className="bd-leg-score">{c.strength.toFixed(1)}<span className="bd-leg-max">/{FUND_MAX}</span></span>
        </div>
        <Bar value={c.strength} max={FUND_MAX} tier={health.tier} />
        <div className="bd-crits">
          {f.criteria.map(([label, deg]) => {
            const m = mark(deg);
            const help = CRITERION_HELP[label] ?? "";
            const val = criterionValue(label, facts);
            return (
              <Tip key={label} def={`${m.word}${help ? " — " + help : ""}`}>
                <span className={`bd-crit bd-crit-${m.cls}`}>
                  <span className="bd-crit-sym">{m.sym}</span> {label}
                  {val && <span className="bd-crit-val"> · {val}</span>}
                </span>
              </Tip>
            );
          })}
        </div>
      </div>

      {/* ---- ขาที่ 2: ราคา (ถูก/แพง) ---- */}
      <div className="bd-leg">
        <div className="bd-leg-head">
          <Tip def="reverse-DCF: เอาราคาตลาดตอนนี้ตั้งเป็นโจทย์ แล้วหาว่าตลาดคาดการเติบโตของกระแสเงินสด (FCF) ไว้กี่ %/ปี เทียบกับที่บริษัทเคยทำได้จริง — ตลาดคาดต่ำกว่าจริง = ถูก (คะแนนสูง)">
            <span className="bd-leg-name">ราคา — ถูกหรือแพง</span>
          </Tip>
          <span className="bd-leg-score">{c.valuation.toFixed(1)}<span className="bd-leg-max">/{VAL_MAX}</span></span>
        </div>
        <Bar value={c.valuation} max={VAL_MAX} tier={health.tier} />
        <div className="bd-note">{valMeaning(c.valuation)} <span className="muted">(รายละเอียดในกล่อง Reverse-DCF ด้านล่าง)</span></div>
      </div>

      {/* ---- ข่าว: บริบท ไม่นับคะแนน ---- */}
      <div className="bd-sentiment">
        📰 มุมมองข่าว <strong>{sentiment}</strong> — ไม่นับรวมในคะแนน (เป็นบริบทอ้างอิงเท่านั้น
        ตั้งแต่ตัดข่าวรายวันออกจากคะแนน เพราะมันคือ noise ไม่ใช่คุณภาพธุรกิจ)
      </div>
    </div>
  );
}