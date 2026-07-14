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

RETRYABLE_CODES = {500, 502, 503, 504}   # 429 ไม่อยู่ในนี้ — จัดการแยกด้วย fallback ไปโมเดลถัดไป


def generate_with_fallback(client, contents, config=None, max_attempts: int = 4, base_delay: float = 1.0):
    """ไล่ MODEL_CHAIN ทีละตัว: แต่ละตัว retry เฉพาะ error ชั่วคราว (5xx) ด้วย exponential backoff,
    เจอ 429 (โควตาเต็ม) -> ข้ามไปโมเดลถัดไปทันที (ไม่ retry ซ้ำโมเดลเดิม). ทุกโมเดลใน chain ล้ม/
    โควตาเต็มหมด -> โยน error ตัวสุดท้ายออกไป (ให้ caller ตัดสินใจเอง เช่น ข้าม ticker นี้ไป)."""
    last_error: Exception | None = None
    for model in MODEL_CHAIN:
        for attempt in range(1, max_attempts + 1):
            try:
                kwargs = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                return client.models.generate_content(**kwargs)
            except errors.APIError as e:
                last_error = e
                if e.code == 429:
                    print(f"[fallback] {model} โควตาเต็ม (429) -> ลองโมเดลถัดไป")
                    break   # ออกจาก retry loop ของโมเดลนี้ -> ไปโมเดลถัดไปใน MODEL_CHAIN
                if e.code not in RETRYABLE_CODES or attempt == max_attempts:
                    raise
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                print(f"[retry] {model} {e.code}, attempt {attempt}/{max_attempts}, waiting {delay:.1f}s")
                time.sleep(delay)
    raise last_error