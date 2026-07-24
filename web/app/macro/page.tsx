import Link from "next/link";
import MacroView from "./macro-view";

export const dynamic = "force-dynamic";

export default function MacroPage() {
  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>เรดาร์มหภาค</h1>
        <p>
          ตัวเลขเศรษฐกิจล่าสุด (CPI / PPI / ว่างงาน / NFP) + <b>สถิติย้อนหลัง</b>ว่าครั้งก่อนๆ
          ที่ตัวเลขออกแบบนี้ ตลาดขยับยังไง — พร้อม<b>ช่วงเหวี่ยง</b>ให้เห็นว่ามั่วแค่ไหน.
          จงใจ<b>ไม่ฟันธงทิศทาง</b> (สงคราม/เงินเฟ้อ ≠ ทองขึ้น/คริปโตลงเสมอ). สำหรับดูภาพเทรดสั้น —
          แยกขาดจากพอร์ตลงทุนระยะยาว.
        </p>
      </header>

      <MacroView />

      <p className="disclaimer">
        ข้อมูลย้อนหลังเพื่อประกอบการมองภาพ ไม่ใช่คำแนะนำซื้อ/ขาย. ผลในอดีตไม่รับประกันอนาคต —
        ตัวเลข n น้อยหรือช่วงเหวี่ยงกว้าง = ความสัมพันธ์อ่อน เชื่อไม่ได้.
      </p>
    </main>
  );
}
