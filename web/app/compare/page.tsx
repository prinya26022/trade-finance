import Link from "next/link";
import { getClaudePeriods, getCompare } from "@/lib/api";
import type { CompareResult } from "@/lib/types";
import CompareView from "./compare-view";

export const dynamic = "force-dynamic";

// งานนี้ทำ "นานๆ ครั้ง" ไม่ใช่รายวัน — หน้าเว็บจึงต้องเปิดมาที่ **งวดล่าสุดที่มีข้อมูลจริง**
// ไม่ใช่เดือนปัจจุบัน. ถ้า default เป็นเดือนนี้ หน้าจะว่างเปล่าเกือบทั้งเดือนทั้งที่ข้อมูลมีอยู่
// แล้วดูเหมือนพัง ทั้งที่เป็นจังหวะการใช้งานปกติ
export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string }>;
}) {
  const { period: wanted } = await searchParams;

  let periods: string[] = [];
  let data: CompareResult | null = null;
  let error: string | null = null;
  try {
    periods = await getClaudePeriods();
    const period = wanted && periods.includes(wanted) ? wanted : periods[0];
    if (period) data = await getCompare(period);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>เทียบสองสำนัก</h1>
        <p>
          บทวิเคราะห์รายวันจาก API เทียบกับบทวิเคราะห์ที่แปะให้โมเดลอื่นอ่านในแชท ·
          คำสั่งและกรอบวิเคราะห์ชุดเดียวกัน ต่างกันที่ว่าใครตอบ
        </p>
      </header>

      {error ? (
        <div className="error">
          Cannot reach the API ({error}). Start it with{" "}
          <code>uvicorn src.api.main:app --port 8000</code>
        </div>
      ) : (
        <CompareView data={data} periods={periods} />
      )}

      <p className="disclaimer">
        Educational research tool. Not investment advice.
      </p>
    </main>
  );
}
