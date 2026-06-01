"""
extractor.py: HTML → 本文テキスト抽出
readability-lxml を使ったモード（デフォルト）と CSS セレクタ指定モードをサポート。
"""
import re
import logging
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract(html: str, *, mode: str = "readability", css_selectors: Optional[dict] = None) -> str:
    """
    HTML から本文テキストを抽出して返す。
    mode: "readability" | "css_select"
    """
    if mode == "css_select" and css_selectors:
        return _extract_css(html, css_selectors)
    return _extract_readability(html)


def _extract_readability(html: str) -> str:
    try:
        from readability import Document
        doc = Document(html)
        content_html = doc.summary(html_partial=True)
        soup = BeautifulSoup(content_html, "lxml")
        text = soup.get_text(separator="\n")
    except Exception as exc:
        logger.warning("readability failed, falling back to bs4: %s", exc)
        soup = BeautifulSoup(html, "lxml")
        # ナビ・ヘッダ・フッタを除去
        for tag in soup.select("nav, header, footer, script, style, noscript"):
            tag.decompose()
        text = soup.get_text(separator="\n")

    return _normalize(text)


def _extract_css(html: str, selectors: dict) -> str:
    soup = BeautifulSoup(html, "lxml")
    parts: list[str] = []
    for _key, sel in selectors.items():
        found = soup.select(sel)
        for el in found:
            parts.append(el.get_text(separator="\n"))
    return _normalize("\n".join(parts))


def _normalize(text: str) -> str:
    # 連続空白・連続改行を整理
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
