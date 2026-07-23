import Link from "next/link";
import ChatView from "./chat-view";

export const dynamic = "force-dynamic";

export default function ChatPage() {
  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>ถามพอร์ต</h1>
        <p>
          ถามอะไรก็ได้เกี่ยวกับ watchlist/portfolio ของคุณ — agent จะไปดึงข้อมูลจริง (health,
          reverse-DCF, เปลี่ยนแปลงล่าสุด, ผลตอบแทน) มาตอบพร้อมอ้างอิง ไม่เดาเอง
        </p>
      </header>

      <ChatView />

      <p className="disclaimer">
        Educational research tool. Not investment advice — คำตอบมาจากข้อมูลที่ระบบมีอยู่ ณ ตอนนี้
        (ไม่ได้ดึงราคา/งบใหม่สด) และเป็นคำแนะนำเพื่อช่วยคิด ไม่ใช่คำสั่งซื้อ/ขาย.
      </p>
    </main>
  );
}