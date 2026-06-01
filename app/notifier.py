"""
notifier.py: Slack Incoming Webhook 通知
high → 即時通知、medium/low → daily digest でまとめ通知
"""
import logging
import os
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def notify_slack(
    webhook_url: str,
    source_name: str,
    source_url: str,
    severity: str,
    change_type: str,
    summary: str,
    report_path: Optional[Path] = None,
) -> bool:
    """
    Slack に通知する。成功 True / 失敗 False。
    """
    severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
    severity_label = {"high": "緊急", "medium": "要確認", "low": "参考"}.get(severity, "不明")

    text = (
        f"{severity_emoji} *[補助金情報 {severity_label}]* `{change_type}`\n"
        f"*ソース:* {source_name}\n"
        f"*URL:* {source_url}\n"
        f"*概要:* {summary[:300]}"
    )
    if report_path:
        text += f"\n📄 レポート: `{report_path.name}`"

    payload = {"text": text}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack notification sent for %s", source_name)
        return True
    except requests.RequestException as exc:
        logger.error("Slack notification failed: %s", exc)
        return False


def notify_digest(webhook_url: str, report_path: Path, changed_count: int) -> bool:
    """日次ダイジェスト通知"""
    text = (
        f"📋 *補助金インテリジェンス 日次レポート*\n"
        f"変更検知: {changed_count}件\n"
        f"レポート: `{report_path.name}`"
    )
    payload = {"text": text}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Slack digest notification failed: %s", exc)
        return False
