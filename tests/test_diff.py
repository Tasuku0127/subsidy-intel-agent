"""
test_diff.py: 差分検知テスト
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractor import extract
from app.diff import compute_diff, has_significant_changes, format_diff_for_llm

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return extract(html, mode="readability")


def test_no_change_returns_no_chunks():
    text = _load("before.html")
    chunks = compute_diff(text, text)
    assert len(chunks) == 0, "同一テキストで差分が出てはいけない"


def test_change_detected():
    old = _load("before.html")
    new = _load("after.html")
    chunks = compute_diff(old, new)
    assert len(chunks) > 0, "変更があるのに差分が検知されなかった"


def test_significant_change_detected():
    """金額・日付・重要語の変更を significant として検知する"""
    old = _load("before.html")
    new = _load("after.html")
    chunks = compute_diff(old, new)
    assert has_significant_changes(chunks), "金額/日付/重要語の変更が high として検知されるべき"


def test_first_time_fetch_all_added():
    """前回スナップショットなし → 全行 added"""
    text = _load("before.html")
    chunks = compute_diff(None, text)
    assert len(chunks) > 0
    assert all(c.tag == "added" for c in chunks)


def test_format_diff_for_llm():
    old = _load("before.html")
    new = _load("after.html")
    chunks = compute_diff(old, new)
    diff_text = format_diff_for_llm(chunks)
    assert "+" in diff_text or "-" in diff_text
    assert len(diff_text) <= 3100  # max_chars + 省略テキスト


def test_amount_change_annotated():
    """金額変更が has_amount フラグとしてマークされる"""
    old = "補助上限額：300万円"
    new = "補助上限額：200万円"
    chunks = compute_diff(old, new)
    assert any(c.has_amount for c in chunks)


def test_date_change_annotated():
    """日付変更が has_date フラグとしてマークされる"""
    old = "申請期限：2025年9月30日"
    new = "申請期限：2025年7月31日"
    chunks = compute_diff(old, new)
    assert any(c.has_date for c in chunks)
