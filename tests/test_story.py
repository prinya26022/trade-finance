"""เรื่องอนาคต 3 ข้อต่อ ticker (Phase 56)."""
import pytest

from src.thesis.story import all_stories, get_story, set_story


def test_set_get_and_overwrite(tmp_db):
    set_story("duol", "AI ทำให้บทเรียนดีขึ้น", "ผู้ใช้จ่ายเงินโต", "margin ถูกกด", author="claude-draft")
    s = get_story("DUOL")
    assert s["author"] == "claude-draft" and s["future"] == "AI ทำให้บทเรียนดีขึ้น"
    set_story("DUOL", "เขียนเอง", "ตัวเลข", "ผิดเมื่อ")       # ผู้ใช้แก้ = แทนร่างทั้งชุด
    assert get_story("DUOL")["author"] == "user" and [x["ticker"] for x in all_stories()] == ["DUOL"]


def test_story_must_answer_all_three(tmp_db):
    with pytest.raises(ValueError):
        set_story("DUOL", "เรื่องเล่าอย่างเดียว", "", "  ")
    assert get_story("DUOL") is None


def test_author_is_checked(tmp_db):
    with pytest.raises(ValueError):
        set_story("DUOL", "a", "b", "c", author="gemini")
