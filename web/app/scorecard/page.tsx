import Link from "next/link";
import { getScorecard } from "@/lib/api";
import type { Scorecard } from "@/lib/types";
import ScorecardView from "./scorecard-view";

export const dynamic = "force-dynamic";

export default async function ScorecardPage() {
  let data: Scorecard | null = null;
  let error: string | null = null;
  try {
    data = await getScorecard();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>สมุดพกของเอเจนต์</h1>
        <p>
          เกณฑ์เดียวกับที่ใช้จับข้ออ้างคนอื่น เอามาจับคะแนนของเราเอง ·
          คะแนนที่ขยับเพราะข้อมูลฝั่งเรา ไม่ใช่เพราะบริษัท คือคะแนนที่เชื่อไม่ได้
        </p>
      </header>

      {error || !data ? (
        <div className="error">
          Cannot reach the API ({error ?? "no data"}). Start it with{" "}
          <code>uvicorn src.api.main:app --port 8000</code>
        </div>
      ) : (
        <ScorecardView data={data} />
      )}

      <p className="disclaimer">
        Educational research tool. Not investment advice.
      </p>
    </main>
  );
}
