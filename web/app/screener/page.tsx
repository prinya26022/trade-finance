import Link from "next/link";
import { getScreener, getHealthTrends } from "@/lib/api";
import type { ScreenerResponse, HealthTrends } from "@/lib/types";
import ScreenerView from "./screener-view";

export const dynamic = "force-dynamic";

export default async function ScreenerPage() {
  let data: ScreenerResponse | null = null;
  let healthTrends: HealthTrends = {};
  let error: string | null = null;
  try {
    // อ่าน cache เสมอตอนโหลดหน้า — ปุ่ม 'รีเฟรช' ค่อยสแกนใหม่ทั้งก้อน (ช้า)
    [data, healthTrends] = await Promise.all([getScreener(false), getHealthTrends()]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>Screener</h1>
        <p>
          หาหุ้นพื้นฐานแข็ง + ราคาถูก จาก list คัดมือ (large-cap สภาพคล่องสูง กระจายหลายเซกเตอร์ —
          ไม่ใช่ S&amp;P 500 เต็มรูปแบบ) ด้วยเอนจิ้นเดียวกับ health score (ไม่เรียก LLM เลย)
        </p>
      </header>

      {error || !data ? (
        <div className="error">
          Cannot reach the API ({error ?? "no data"}). Start it with{" "}
          <code>uvicorn src.api.main:app --port 8000</code>
        </div>
      ) : (
        <ScreenerView initial={data} healthTrends={healthTrends} />
      )}

      <p className="disclaimer">
        Educational research tool. Not investment advice — ตัวที่ข้อมูลไม่พอ/reverse-DCF คำนวณไม่ได้
        ถูกข้ามออกจาก list นี้ (ไม่ใช่ตัดสินว่า &quot;แย่&quot;).
      </p>
    </main>
  );
}
