import Link from "next/link";
import { API_BASE } from "@/lib/api";
import JournalView, { type JournalData } from "./journal-view";

export const dynamic = "force-dynamic";

// Phase 55 — สมุดเทรด. ตัวเลขทุกตัวมาจาก OKX เอง หน้านี้มีไว้ "แตะเหตุผล" กับดูสถิติเท่านั้น
// ไม่มีช่องให้กรอกราคา/ผลเอง — ชีตเดิมของผู้ใช้หยุดไปเพราะต้องกรอกเองทุกไม้
export default async function JournalPage() {
  let data: JournalData | null = null;
  let error: string | null = null;
  try {
    const res = await fetch(`${API_BASE}/api/journal`, { cache: "no-store" });
    if (!res.ok) throw new Error(`API ${res.status}`);
    data = await res.json();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>สมุดเทรด</h1>
        <p>
          ไม้จาก OKX ถูกดึงมาเอง พร้อมกราฟ ณ ตอนที่กดเข้า — ที่เหลือคือ<b>แตะเหตุผล 2–3 ปุ่ม</b>.
          ไม่แตะก็ไม่เป็นไร ไม้ยังถูกบันทึกครบ. สถิติด้านบนบอกว่าไม้แบบไหนของคุณชนะ ด้วยตัวเลขจริง ไม่ใช่ความจำ.
        </p>
      </header>
      {error ? (
        <div className="error">Cannot reach the API ({error}). Start it with <code>uvicorn src.api.main:app --port 8000</code></div>
      ) : data && <JournalView data={data} />}
      <p className="disclaimer">
        บันทึกและสถิติของคุณเอง — ไม่ใช่คำแนะนำซื้อ/ขาย. ระบบอ่านจาก OKX อย่างเดียว ไม่ส่งคำสั่งเทรด.
      </p>
    </main>
  );
}
