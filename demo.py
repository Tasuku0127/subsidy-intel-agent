"""
demo.py: 面接デモ用スクリプト
before.html → after.html の差分を投入し、
変更検知 → 分類 → Claude 修正案生成 → digest.md 出力 の一連のフローを実演する。

Usage:
  python demo.py
"""
import sys
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from app.extractor import extract
from app.diff import compute_diff, format_diff_for_llm
from app.classifier import classify
from app.generator import generate_suggestions
from app.reporter import generate_report, SourceResult
from app.store import init_db, save_snapshot, get_last_two_snapshots
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console(width=100)
FIXTURES = Path(__file__).parent / "tests" / "fixtures"

SOURCE_META = {
    "id": "demo_subsidy",
    "name": "再エネ補助金ページ（デモ）",
    "url": "https://example.energy-supply.jp/subsidy/",
    "severity_rules": [
        {"match": "(申請|締切|期限|金額|補助率|対象)", "severity": "high"}
    ],
}


def main():
    console.print(Panel(
        "[bold cyan]補助金インテリジェンス Agent — デモ実行[/bold cyan]\n"
        "before.html → after.html の変更を検知し、AI修正案を Markdown レポートに出力します",
        expand=False
    ))

    init_db()

    # ─── Step 1: before.html をスナップショットとして登録 ───────────────
    console.rule("[bold white][1/5] before.html をスナップショットとして登録[/bold white]")
    before_html = (FIXTURES / "before.html").read_text(encoding="utf-8")
    before_text = extract(before_html)
    save_snapshot(SOURCE_META["id"], before_text)
    console.print("[green]✓ スナップショット保存完了（SQLite + gzip 圧縮）[/green]")

    # ─── Step 2: after.html を取得 → 差分検知 ───────────────────────────
    console.rule("[bold white][2/5] after.html を取得（変更あり）→ 差分検知[/bold white]")
    after_html = (FIXTURES / "after.html").read_text(encoding="utf-8")
    after_text = extract(after_html)
    _hash, is_changed = save_snapshot(SOURCE_META["id"], after_text)

    if not is_changed:
        console.print("[yellow]差分なし（前回と同一）[/yellow]")
        return

    previous, current = get_last_two_snapshots(SOURCE_META["id"])
    chunks = compute_diff(previous, current)
    diff_text = format_diff_for_llm(chunks)

    console.print(f"[green]✓ 差分検知: {len(chunks)} チャンク[/green]")
    console.print()
    console.print(Syntax(diff_text[:900], "diff", theme="monokai", line_numbers=False))

    # ─── Step 3: 変更タイプ分類 ──────────────────────────────────────────
    console.rule("[bold white][3/5] 変更タイプ分類（ルールベース）[/bold white]")
    cls = classify(chunks, SOURCE_META["severity_rules"])

    sev_color = {"high": "red", "medium": "yellow", "low": "green"}.get(cls.severity, "white")
    sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(cls.severity, "⚪")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", width=20)
    table.add_column()
    table.add_row("変更タイプ",   f"[bold]{cls.change_type}[/bold]")
    table.add_row("Severity",     f"[bold {sev_color}]{sev_emoji} {cls.severity.upper()}[/bold {sev_color}]")
    table.add_row("判定根拠",     cls.reason)
    console.print(table)

    # ─── Step 4: Claude API で修正案生成 ─────────────────────────────────
    console.rule("[bold white][4/5] Claude API で修正案生成[/bold white]")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        console.print("[dim]Claude API にリクエスト中...[/dim]")
        suggestions = generate_suggestions(
            source_name=SOURCE_META["name"],
            source_url=SOURCE_META["url"],
            diff_excerpt=diff_text,
        )
        console.print(suggestions)
    else:
        suggestions = "（ANTHROPIC_API_KEY 未設定のため省略）"
        console.print(f"[yellow]{suggestions}[/yellow]")

    # ─── Step 5: Markdown レポート出力 ───────────────────────────────────
    console.rule("[bold white][5/5] Markdown レポート生成 → reports/ に出力[/bold white]")
    result = SourceResult(
        source_id=SOURCE_META["id"],
        source_name=SOURCE_META["name"],
        source_url=SOURCE_META["url"],
        changed=True,
        chunks=chunks,
        classification=cls,
        suggestions=suggestions,
    )
    report_path = generate_report([result], run_date="demo")
    console.print(f"[green]✓ レポート出力完了[/green]")
    console.print(f"   📄 [bold]{report_path}[/bold]")

    # レポートの先頭部分をプレビュー表示
    console.print()
    preview = report_path.read_text(encoding="utf-8")[:600]
    console.print(Panel(
        Syntax(preview + "\n...(続く)", "markdown", theme="github-dark"),
        title="[bold]レポートプレビュー[/bold]",
        border_style="green",
        expand=False
    ))

    # ─── 完了サマリー ────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold green]✅  デモ完了！[/bold green]\n\n"
        f"[white]出力レポート:[/white] [bold cyan]{report_path.name}[/bold cyan]\n\n"
        "[dim]このツールが実現すること：[/dim]\n"
        "  🛡  [bold]更新漏れをゼロに[/bold] — 定期クロールで変更を自動検知\n"
        "  ⚡  [bold]制作工数を削る[/bold] — Claude が修正案・広告案を即時生成\n"
        "  📈  [bold]広告訴求の鮮度を上げる[/bold] — 鮮度向上でCVR・CPAを改善",
        title="Summary",
        border_style="cyan",
        expand=False
    ))

    # レポートを自動で開く（macOS）
    try:
        subprocess.run(["open", str(report_path)], check=True, capture_output=True)
        console.print(f"[dim]（レポートをエディタで開きました）[/dim]")
    except Exception:
        console.print(f"[dim]open コマンドで手動確認: open {report_path}[/dim]")


if __name__ == "__main__":
    main()
