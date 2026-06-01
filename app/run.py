"""
run.py: エントリーポイント
Usage:
  python -m app.run --mode once
  python -m app.run --mode once --source meti_solarpower
  python -m app.run --mode demo
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fetcher import fetch
from app.extractor import extract
from app.store import init_db, save_snapshot, get_last_two_snapshots, log_run
from app.diff import compute_diff, format_diff_for_llm, has_significant_changes
from app.classifier import classify
from app.generator import generate_suggestions
from app.reporter import generate_report, SourceResult

console = Console()


def setup_logging():
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "app.log", encoding="utf-8"),
        ],
    )


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def process_source(source: dict, defaults: dict) -> SourceResult:
    """1ソースを処理して SourceResult を返す"""
    source_id = source["id"]
    source_name = source["name"]
    source_url = source["url"]
    mode = source.get("extract_mode", defaults.get("extract_mode", "readability"))
    css_selectors = source.get("css_selectors")
    user_agent = source.get("user_agent", defaults.get("user_agent", "SubsidyWatcher/0.1"))
    timeout = source.get("timeout_seconds", defaults.get("timeout_seconds", 25))
    severity_rules = source.get("severity_rules", [])

    # --- fetch ---
    try:
        html = fetch(source_url, user_agent=user_agent, timeout=timeout)
    except Exception as exc:
        log_run(source_id, "fetch_error", str(exc))
        return SourceResult(
            source_id=source_id, source_name=source_name, source_url=source_url,
            changed=False, chunks=[], classification=None, suggestions="",
            error=f"fetch失敗: {exc}"
        )

    # --- extract ---
    try:
        text = extract(html, mode=mode, css_selectors=css_selectors)
    except Exception as exc:
        log_run(source_id, "extract_error", str(exc))
        return SourceResult(
            source_id=source_id, source_name=source_name, source_url=source_url,
            changed=False, chunks=[], classification=None, suggestions="",
            error=f"抽出失敗: {exc}"
        )

    # --- store & diff ---
    _hash, is_changed = save_snapshot(source_id, text)
    previous, current = get_last_two_snapshots(source_id)
    chunks = compute_diff(previous, current)

    if not is_changed:
        log_run(source_id, "no_change")
        return SourceResult(
            source_id=source_id, source_name=source_name, source_url=source_url,
            changed=False, chunks=[], classification=None, suggestions=""
        )

    # --- classify ---
    classification = classify(chunks, severity_rules)

    # --- generate suggestions ---
    diff_text = format_diff_for_llm(chunks)
    suggestions = ""
    if diff_text.strip() and os.environ.get("ANTHROPIC_API_KEY"):
        suggestions = generate_suggestions(
            source_name=source_name,
            source_url=source_url,
            diff_excerpt=diff_text,
        )
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        suggestions = "（ANTHROPIC_API_KEY 未設定のため AI 案は省略）"

    log_run(source_id, "changed", f"type={classification.change_type} sev={classification.severity}")
    return SourceResult(
        source_id=source_id, source_name=source_name, source_url=source_url,
        changed=True, chunks=chunks, classification=classification, suggestions=suggestions
    )


def run_once(target_source_id: str | None = None):
    config = load_config()
    defaults = config.get("defaults", {})
    sources = config.get("sources", [])

    if target_source_id:
        sources = [s for s in sources if s["id"] == target_source_id]
        if not sources:
            console.print(f"[red]source_id '{target_source_id}' が見つかりません[/red]")
            return

    init_db()
    results: list[SourceResult] = []

    console.print(Panel(f"[bold cyan]補助金インテリジェンス Agent[/bold cyan]\n監視ソース: {len(sources)}件"))

    for source in track(sources, description="処理中..."):
        result = process_source(source, defaults)
        results.append(result)
        status = "🔴 変更あり" if result.changed else ("⚠️ エラー" if result.error else "✅ 変更なし")
        console.print(f"  {status}: {result.source_name}")

    # --- レポート生成 ---
    report_path = generate_report(results)
    console.print(f"\n[green]レポート生成完了:[/green] {report_path}")

    # --- 最終出力: レポートの内容サマリーをターミナルに表示 ---
    changed_count = sum(1 for r in results if r.changed)
    if changed_count:
        console.print(f"\n[bold red]⚠️  {changed_count}件の変更を検知しました。レポートを確認してください。[/bold red]")
    else:
        console.print("\n[green]✅ 変更なし。全ソースが前回と同一でした。[/green]")


def run_demo():
    """テストデータを使ったデモ実行"""
    console.print(Panel("[bold magenta]デモモード[/bold magenta]\nテストフィクスチャを使って差分検知を実行します"))

    # テスト用フィクスチャを使って config の test_local_before ソースを処理
    config = load_config()
    defaults = config.get("defaults", {})
    test_sources = [s for s in config.get("sources", []) if "test" in s.get("tags", [])]

    if not test_sources:
        console.print("[yellow]テストソースが sources.yml にありません[/yellow]")
        return

    init_db()
    results = []
    for source in test_sources:
        # before / after 両方を順に処理してデモ差分を生成
        result = process_source(source, defaults)
        results.append(result)

    report_path = generate_report(results)
    console.print(f"\n[green]デモレポート:[/green] {report_path}")


def main():
    setup_logging()
    load_dotenv()

    parser = argparse.ArgumentParser(description="補助金インテリジェンス Agent")
    parser.add_argument("--mode", choices=["once", "demo"], default="once")
    parser.add_argument("--source", help="特定のソースIDのみ処理")
    args = parser.parse_args()

    if args.mode == "demo":
        run_demo()
    else:
        run_once(target_source_id=args.source)


if __name__ == "__main__":
    main()
