"""ธงข่าวภูมิรัฐศาสตร์ — 'จับตาเฉยๆ' (passive watch).

ดึงพาดหัวข่าวสงคราม/ความขัดแย้ง/มาตรการคว่ำบาตร จาก Google News RSS (ฟรี ไม่ต้องมีคีย์,
ใช้ urllib + xml.etree จาก stdlib). คืนแค่ 'มีเหตุการณ์อะไรอยู่ในข่าว' เป็น warn —
**ไม่ฟันธงทิศทางตลาด** (สงครามไม่ได้แปลว่าทองขึ้น/คริปโตลงเสมอ — folk-rule ที่พังบ่อย).

ล้มเหลว/เน็ตล่ม -> [] เพื่อไม่ให้ radar พังทั้งอัน.
"""
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

_UA = {"User-Agent": "trade-finance-agent/1.0 (+local research tool)"}
_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# คำค้นภูมิรัฐศาสตร์ที่กระทบตลาดระยะสั้นบ่อย (war-risk / commodity / risk-off triggers)
_KEYWORDS = (
    '"military strike" OR airstrike OR missile OR invasion OR '
    '"armed conflict" OR sanctions OR ceasefire OR "oil supply" OR "nuclear"'
)


@dataclass(frozen=True)
class GeoNewsItem:
    title: str
    source: str
    published: str      # ISO ถ้า parse ได้ ไม่งั้นคง string เดิม
    url: str

    def as_dict(self) -> dict:
        return {"title": self.title, "source": self.source,
                "published": self.published, "url": self.url}


def _parse_pubdate(s: str) -> str:
    """RFC-822 ('Wed, 22 Jul 2026 10:00:00 GMT') -> ISO; parse ไม่ได้ก็คืนของเดิม."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except (ValueError, TypeError):
            continue
    return s or ""


def _split_source(title: str) -> tuple[str, str]:
    """Google News ใส่ท้ายเป็น 'Headline - Source' -> แยกออก (ไม่มี ' - ' ก็คงเดิม)."""
    if " - " in title:
        head, _, src = title.rpartition(" - ")
        return head.strip(), src.strip()
    return title.strip(), ""


def fetch_geopolitical(max_items: int = 8, within_days: int = 3) -> list[GeoNewsItem]:
    """พาดหัวข่าวภูมิรัฐศาสตร์ล่าสุด (ใหม่สุดก่อน). ล้มเหลว -> []."""
    query = f"({_KEYWORDS}) when:{within_days}d"
    url = _RSS.format(q=urllib.parse.quote(query))
    try:
        req = urllib.request.Request(url, headers=_UA)
        raw = urllib.request.urlopen(req, timeout=20).read()
        root = ET.fromstring(raw)
    except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError):
        return []

    out: list[GeoNewsItem] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        if not raw_title:
            continue
        title, src = _split_source(raw_title)
        key = "".join(ch for ch in title.lower() if ch.isalnum())[:50]
        if key in seen:
            continue
        seen.add(key)
        out.append(GeoNewsItem(
            title=title,
            source=src or (item.findtext("source") or "").strip(),
            published=_parse_pubdate(item.findtext("pubDate") or ""),
            url=(item.findtext("link") or "").strip(),
        ))
        if len(out) >= max_items:
            break
    return out


def format_warn(items: list[GeoNewsItem]) -> str:
    """สรุปเป็นบล็อก warn สำหรับ Discord/UI — จับตาเฉยๆ ไม่ฟันธงทิศ."""
    if not items:
        return ""
    lines = ["⚠️ **จับตา: ข่าวภูมิรัฐศาสตร์** _(เฝ้าดูความเสี่ยง — ไม่ใช่สัญญาณซื้อขาย)_"]
    for it in items:
        src = f" — {it.source}" if it.source else ""
        lines.append(f"• {it.title}{src}")
    return "\n".join(lines)


if __name__ == "__main__":  # เดโม (แตะเน็ต): python -m src.macro.geonews
    print(format_warn(fetch_geopolitical()))
