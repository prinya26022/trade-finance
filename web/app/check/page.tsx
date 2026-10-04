import Link from "next/link";
import CheckView from "./check-view";

export const dynamic = "force-dynamic";

// Phase 55.2 — เช็กลิสต์ก่อนกดเข้า. ไม่มีเกณฑ์ตายตัว: ทุกข้อบอกว่า "ไม้หน้าตาแบบนี้ ในอดีตของคุณเอง
// ได้ผลยังไง" จากสมุดที่อัปเดตทุกชั่วโมง พร้อมจำนวนไม้. ไม่บอกว่าควรเข้าไหม — บันทึกไว้เทียบกับผลจริง
export default function CheckPage() {
  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>เช็กก่อนกดเข้า</h1>
        <p>
          ใส่ stop / TP แล้วดูว่าไม้นี้หน้าตาเหมือนไม้แบบไหนในอดีตของคุณ — และไม้แบบนั้นได้ผลยังไง.
          ระบบ<b>ไม่ห้ามและไม่แนะนำ</b>ให้เข้า แค่บันทึกไว้ แล้วจับคู่กับไม้จริงบน OKX เพื่อวัดว่า
          ไม้ที่เช็กก่อนเข้ากับไม้ที่กดเข้าเลย ต่างกันจริงไหม.
        </p>
      </header>
      <CheckView />
      <p className="disclaimer">
        สถิติจากไม้ของคุณเอง ไม่ใช่คำแนะนำซื้อ/ขาย. กลุ่มที่มีไม้ไม่ถึง 10 ไม้อ่านเป็นสัญญาณ ยังไม่ใช่ข้อสรุป.
      </p>
    </main>
  );
}
