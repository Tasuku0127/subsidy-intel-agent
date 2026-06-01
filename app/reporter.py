"""
reporter.py: Markdown ダイジェストレポート生成
"""
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.diff import DiffChunk, format_diff_for_llm
from app.classifier import Classification

REPORTS_DIR = Path(__file__).parent.parent / "reports"


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    source_url: str
    changed: bool
    chunks: list[DiffChunk]
    classification: Optional[Classification]
    suggestions: str
    error: Optional[str] = None


def generate_report(results: list[SourceResult], run_date: Optional[str] = None) -> Path:
    """
    全ソースの結果をまとめた Markdown レポートを生成し、ファイルパスを返す。
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = run_date or datetime.now().strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"{today}_digest.md"

    changed = [r for r in results if r.changed and not r.error]
    errors = [r for r in results if r.error]
    no_change = [r for r in results if not r.changed and not r.error]

    lines: list[str] = [
        f"# 補助金・制度インテリジェンス レポート",
        f"**実行日時:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**監視ソース数:** {len(results)}件  ",
        f"**変更検知:** {len(changed)}件  |  **変更なし:** {len(no_change)}件  |  **エラー:** {len(errors)}件",
        "",
        "---",
        "",
    ]

    # --- 変更あり ---
    if changed:
        lines.append("## 変更が検知されたソース\n")
        for r in changed:
            cls = r.classification
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                cls.severity if cls else "low", "⚪"
            )
            lines += [
                f"### {severity_emoji} {r.source_name}",
                f"- **ID:** `{r.source_id}`",
                f"- **URL:** {r.source_url}",
                f"- **変更タイプ:** `{cls.change_type if cls else 'unknown'}`",
                f"- **Severity:** `{cls.severity if cls else 'unknown'}`",
                "",
                "#### 差分（抜粋）",
                "```diff",
                format_diff_for_llm(r.chunks, max_chars=1500),
                "```",
                "",
            ]
            if r.suggestions:
                lines += [
                    "#### AI 修正案",
                    r.suggestions,
                    "",
                ]
            lines += ["---", ""]
    else:
        lines += ["## 変更なし", "監視対象の全ソースで変更は検知されませんでした。", "", "---", ""]

    # --- エラー ---
    if errors:
        lines.append("## エラー\n")
        for r in errors:
            lines += [
                f"- **{r.source_name}** (`{r.source_id}`): {r.error}",
            ]
        lines += ["", "---", ""]

    # --- 変更なし一覧 ---
    if no_change:
        lines.append("## 変更なし（一覧）\n")
        for r in no_change:
            lines.append(f"- {r.source_name} (`{r.source_id}`)")
        lines.append("")

    lines += [
        "---",
        "",
        "> ⚠️ 本レポートは AI による自動生成です。数字・期限・対象条件は必ず公式ソースで最終確認してください。",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
