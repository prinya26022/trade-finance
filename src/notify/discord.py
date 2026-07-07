"""ส่งข้อความเข้า Discord ผ่าน Incoming Webhook (ไม่ต้องทำบอท/OAuth).

ตั้งค่า: สร้าง Webhook ใน Discord (Channel Settings > Integrations > Webhooks)
แล้วใส่ URL ใน .env เป็น DISCORD_WEBHOOK_URL=... (ถ้าไม่ตั้ง จะข้ามเงียบๆ ไม่พัง).
ใช้ urllib (stdlib) — ไม่เพิ่ม dependency.
"""
import json
import os
import urllib.error
import urllib.request

DISCORD_CONTENT_LIMIT = 2000   # เพดานข้อความ Discord ต่อ message


def post(content: str, webhook_url: str | None = None) -> bool:
    """ส่งข้อความ (markdown) เข้า Discord; คืน True ถ้าสำเร็จ.
    ถ้าไม่มี webhook URL -> ข้ามเงียบๆ (ให้ flow อื่นทำงานต่อได้)."""
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("[discord] ไม่มี DISCORD_WEBHOOK_URL — ข้ามการส่ง")
        return False

    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[: DISCORD_CONTENT_LIMIT - 40] + "\n… (ตัดทอน — ดูเต็มบนเว็บ)"

    data = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            # Discord/Cloudflare คืน 403 ถ้า User-Agent เป็นค่า default ของ urllib -> ต้องตั้งเอง
            "User-Agent": "trade-finance-agent/1.0 (+local research tool)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"[discord] ส่งไม่สำเร็จ: HTTP {e.code} — {body}")
        return False
    except Exception as e:
        print(f"[discord] ส่งไม่สำเร็จ: {e}")
        return False


def _chunk_lines(content: str, limit: int = DISCORD_CONTENT_LIMIT) -> list[str]:
    """แบ่ง content เป็นหลายก้อน แต่ละก้อน <= limit ตัวอักษร ตัดที่ขอบบรรทัด (ไม่ตัดกลางคำ/กลางประโยค)."""
    chunks, cur = [], ""
    for line in content.split("\n"):
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) > limit:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def post_chunks(content: str, webhook_url: str | None = None) -> bool:
    """เหมือน post() แต่แบ่งข้อความยาวเป็นหลาย message แทนตัดทอน — ใช้กับ report ที่อาจยาว
    (เช่น monthly ทบทวน thesis ทุกตัว) กัน 'เสียข้อมูลเงียบๆ' ที่ post() เดี่ยวๆ จะตัดทิ้ง."""
    ok = True
    for chunk in _chunk_lines(content):
        ok = post(chunk, webhook_url) and ok
    return ok
