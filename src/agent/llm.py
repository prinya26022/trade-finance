"""ตัวช่วยเรียก Gemini แบบมี fallback chain ข้ามโมเดล — โควตา free tier เป็นรายวันแยกต่อโมเดล
(20 requests/วัน/โมเดล, ยืนยันแล้วทั้ง gemini-2.5-flash และ gemini-3.5-flash) ดังนั้นเจอ 429
(โควตาเต็ม) แล้ว retry โมเดลเดิมไม่มีประโยชน์ — retryDelay สั้นๆ ที่ Google แนะนำ (หลักสิบวินาที)
ไม่ได้สะท้อนเวลารีเซ็ตโควตารายวันจริง (เที่ยงคืน Pacific) — จึงสลับไปโมเดลถัดไปใน MODEL_CHAIN
ทันทีแทน ให้ pipeline ทำงานต่อได้แม้โมเดลนึงโควตาเต็ม ไม่ใช่ล้มทั้งรอบ.

สำคัญ: การสลับโมเดลไม่กระทบความแม่นของ health score เลย เพราะตั้งแต่ Phase 17/18 คะแนนคำนวณ
จากตัวเลขจริงล้วน (Piotroski + reverse-DCF, deterministic, ไม่เรียก LLM) — โมเดลไหนตอบก็ได้
คะแนนเดียวกันเป๊ะสำหรับข้อมูลชุดเดียวกัน สิ่งที่ต่างกันมีแค่ 'เนื้อหาข้อความ' (beginner_summary,
sentiment ฯลฯ) ซึ่งตั้งแต่ Phase 19.3.1 ไม่กระทบคะแนนเลย (sentiment ถูกตัดออกจากผลรวม —
เหลือเป็น metadata แสดงผลเท่านั้น).
"""
import random
import time

from google.genai import errors

# เรียงจากใหม่/แรงสุดก่อน — แต่ละตัวเป็นคนละ quota pool กัน
MODEL_CHAIN = ["gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash"]

# ---- quota lane สำหรับงานที่ "ผู้ใช้กดเอง" (Phase 28) ----
# โควตา free tier แยกรายวันต่อโมเดล ดังนั้น 'ถังโควตา' คือทรัพยากรที่ต้องจัดสรร ไม่ใช่แค่ลำดับ
# ความแรง. งานสองประเภทนี้ไม่ควรแย่งถังเดียวกัน:
#   - งานที่ต้องรันทุกวันให้ได้ (analyze รายวัน 8 ticker = 8 call) -> เริ่มหัว chain
#   - งานที่กดเล่นได้ไม่จำกัด (ปุ่มสืบ = ได้ถึง 7 call/ครั้ง, chat) -> ข้ามหัว chain ไปเริ่มตัวถัดไป
# ผลคือกดสืบตอนบ่ายจนโควตาหมด ก็ยังไม่กระทบรอบวิเคราะห์พรุ่งนี้ (คนละถัง) และถ้าจำเป็นจริงๆ ค่อย
# ไต่มาแตะโมเดลของงานรายวันเป็นตัวสุดท้าย — ไม่ใช่ตัวแรก (เจอจริง 2026-07-29: ทดสอบปุ่มไม่กี่รอบ
# gemini-3.5-flash ก็ขึ้น 429 ทั้งที่เป็นโมเดลหลักของ pipeline รายวัน)
#
# เป็น 'หมุน' (rotate) ไม่ใช่ 'กลับด้าน' (reverse) โดยตั้งใจ: ลองทั้งสองแบบกับการสืบจริงแล้ว —
# gemini-2.5-flash (ตัวท้ายสุด) เดินครบ 6 สเต็ปไปกับ get_metric_trend อย่างเดียว ไม่แตะข่าว/SEC/
# reverse-DCF เลย ส่วน gemini-3-flash-preview ไล่ timeline -> reverse-DCF -> ข่าว แล้วเอะใจเองว่า
# net margin สูงผิดปกติน่าจะมาจากรายการภาษี. คุณภาพการ 'วางแผนว่าจะดูอะไรต่อ' คือหัวใจของ agentic
# loop จึงเอาตัวที่ดีที่สุดที่ไม่ใช่โมเดลของงานรายวันขึ้นหัวเลน
INTERACTIVE_CHAIN = MODEL_CHAIN[1:] + MODEL_CHAIN[:1]

RETRYABLE_CODES = {500, 502, 503, 504}   # 429 ไม่อยู่ในนี้ — จัดการแยกด้วย fallback ไปโมเดลถัดไป


def _log(msg: str) -> None:
    """print ที่ไม่มีวันล้มงานเพราะ console encode ไม่ได้ (เจอจริง Phase 28: uvicorn บน PowerShell
    ใช้ cp1252 -> ข้อความ log ภาษาไทยโยน UnicodeEncodeError ขึ้นไปกลางลูป fallback ทำให้การสืบ
    ตายด้วยเหตุผลที่ไม่เกี่ยวกับ Gemini เลย). log เป็นผลข้างเคียง ห้ามเป็นเหตุให้งานหลักพัง."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "backslashreplace").decode())


def generate_with_fallback(client, contents, config=None, max_attempts: int = 4,
                           base_delay: float = 1.0, models: list[str] | None = None):
    """ไล่ MODEL_CHAIN ทีละตัว: แต่ละตัว retry เฉพาะ error ชั่วคราว (5xx) ด้วย exponential backoff,
    เจอ 429 (โควตาเต็ม) -> ข้ามไปโมเดลถัดไปทันที (ไม่ retry ซ้ำโมเดลเดิม). ทุกโมเดลใน chain ล้ม/
    โควตาเต็มหมด -> โยน error ตัวสุดท้ายออกไป (ให้ caller ตัดสินใจเอง เช่น ข้าม ticker นี้ไป).

    bug fix (Phase 28, เจอจริงตอน verify ปุ่มสั่งสืบ): เดิม 5xx ที่ retry จนครบ max_attempts แล้ว
    ยังไม่หาย จะ `raise` ทิ้งทั้ง chain — ทั้งที่เหลืออีก 2 โมเดลที่ยังใช้ได้ เจอจริงเมื่อ
    gemini-3.5-flash ตอบ 503 'high demand' ต่อเนื่อง ขณะที่ gemini-3-flash-preview/2.5-flash
    ปกติดี = ล้มทั้งรอบวิเคราะห์ฟรีๆ. ตอนนี้ 5xx ที่ retry ไม่ขึ้น = ปฏิบัติเหมือน 429 (ไปโมเดล
    ถัดไป) และจะ raise ก็ต่อเมื่อหมด chain จริงๆ.

    models: override chain (ค่าปริยาย = MODEL_CHAIN) — GeminiPolicy ใช้เพื่อเรียงโมเดลที่อยากลองก่อน.
    """
    chain = models or MODEL_CHAIN
    last_error: Exception | None = None
    for model in chain:
        for attempt in range(1, max_attempts + 1):
            try:
                kwargs = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                return client.models.generate_content(**kwargs)
            except errors.APIError as e:
                last_error = e
                if e.code == 429:
                    _log(f"[fallback] {model} โควตาเต็ม (429) -> ลองโมเดลถัดไป")
                    break   # ออกจาก retry loop ของโมเดลนี้ -> ไปโมเดลถัดไปใน chain
                if e.code not in RETRYABLE_CODES:
                    raise   # error ถาวร (เช่น 400 prompt ผิดรูป) — เปลี่ยนโมเดลก็ไม่ช่วย
                if attempt == max_attempts:
                    _log(f"[fallback] {model} {e.code} ไม่หายหลัง {max_attempts} ครั้ง -> ลองโมเดลถัดไป")
                    break
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                _log(f"[retry] {model} {e.code}, attempt {attempt}/{max_attempts}, waiting {delay:.1f}s")
                time.sleep(delay)
    raise last_error