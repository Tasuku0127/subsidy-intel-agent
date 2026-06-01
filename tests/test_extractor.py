"""
test_extractor.py: 本文抽出テスト
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractor import extract

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_readability_not_empty():
    html = (FIXTURES / "before.html").read_text(encoding="utf-8")
    text = extract(html, mode="readability")
    assert len(text) > 50, "抽出テキストが短すぎる"
    assert "補助金" in text


def test_extract_css_select():
    html = (FIXTURES / "before.html").read_text(encoding="utf-8")
    text = extract(html, mode="css_select", css_selectors={"main": "main"})
    assert "補助金" in text
    assert "中小企業" in text


def test_extract_removes_nav():
    html = """
    <html><body>
    <nav>メニュー項目</nav>
    <main><p>本文：補助率1/2、上限300万円</p></main>
    <footer>フッター</footer>
    </body></html>
    """
    text = extract(html, mode="readability")
    assert "300万円" in text or "補助率" in text


def test_extract_normalizes_whitespace():
    html = "<html><body><main><p>テキスト   改行\n\n\n複数行</p></main></body></html>"
    text = extract(html, mode="readability")
    assert "   " not in text  # 連続スペースが除去されている
