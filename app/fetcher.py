"""
fetcher.py: HTML取得（requests + リトライ）
ローカルファイル URL (file://) にも対応（テスト用）
"""
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def fetch(url: str, *, user_agent: str, timeout: int, max_retries: int = 2) -> str:
    """
    HTML文字列を返す。失敗時は例外を送出。
    file:// スキームはローカルファイルを読む（テスト用）。
    """
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return _fetch_local(parsed)

    headers = {**DEFAULT_HEADERS, "User-Agent": user_agent}
    last_exc: Exception = RuntimeError("unreachable")

    for attempt in range(1, max_retries + 2):  # 1 + retry
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt <= max_retries:
                wait = 2 ** attempt
                logger.warning("fetch attempt %d failed for %s: %s — retrying in %ds", attempt, url, exc, wait)
                time.sleep(wait)
            else:
                logger.error("fetch failed after %d attempts for %s: %s", attempt, url, exc)

    raise last_exc


def _fetch_local(parsed) -> str:
    """file:// URL をローカルパスとして読む（テスト用）"""
    # file://tests/fixtures/before.html → プロジェクトルート基準
    rel_path = parsed.netloc + parsed.path  # tests/fixtures/before.html
    base = Path(__file__).parent.parent
    full_path = base / rel_path
    if not full_path.exists():
        raise FileNotFoundError(f"Local file not found: {full_path}")
    return full_path.read_text(encoding="utf-8")
