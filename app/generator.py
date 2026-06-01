"""
generator.py: Claude API を使った修正案生成
"""
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたはインハウスマーケ向けの制作・広告コピーの専門家です。
以下のルールを厳守してください。
- 事実は【差分抜粋】の範囲からのみ推論し、憶測で制度内容を創作しない
- 数字・期限・対象条件は、出典の抜粋を引用しながら提案する
- 日本語で、マーケ実務に使える短い文にする
- 免責・注意書きの提案を必ず含める（「最終確認は公式サイトへ」）
- 広告案は媒体規約に配慮し誇大表現を避ける（「最大○○円」「最高○○%」は差分に根拠がある場合のみ）
"""

USER_TEMPLATE = """\
以下は補助金/制度ページの差分です。差分に基づき、下記3点を作成してください。

## 監視ソース
- 名称: {source_name}
- URL: {source_url}

## 差分（抜粋）
```
{diff_excerpt}
```

## 自社の関連ページ（URLリスト）
{related_pages}

## 出力要件
1. **自社ページ修正文案**
   - 変更点の要約（3〜5行）
   - LP/記事に差し込める修正文（注意書き・免責・公式リンク含む）
2. **広告訴求更新案（RSA想定）**
   - 見出し案 3本（15文字以内）
   - 説明文案 2本（80文字以内）
3. **確認ポイント**
   - 人が公式サイトで必ず確認すべき点を箇条書き
"""


def generate_suggestions(
    source_name: str,
    source_url: str,
    diff_excerpt: str,
    related_pages: Optional[list[str]] = None,
    model: str = "claude-opus-4-6",
) -> str:
    """
    差分から修正案を生成して返す（Markdown 文字列）。
    失敗時は空文字列を返しログに記録。
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    pages_str = "\n".join(f"- {p}" for p in (related_pages or [])) or "（未設定）"
    user_msg = USER_TEMPLATE.format(
        source_name=source_name,
        source_url=source_url,
        diff_excerpt=diff_excerpt,
        related_pages=pages_str,
    )

    try:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return message.content[0].text
    except anthropic.APIError as exc:
        logger.error("Claude API error: %s", exc)
        return ""
