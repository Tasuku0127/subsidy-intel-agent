"""
classifier.py: 変更タイプの分類（ルールベース）
曖昧な場合のみ LLM 補助（オプション）。
"""
import re
from dataclasses import dataclass
from typing import Optional

from app.diff import DiffChunk

CHANGE_TYPES = (
    "deadline_change",
    "amount_change",
    "eligibility_change",
    "program_end",
    "new_program",
    "procedure_change",
    "other",
)

_RULES: list[tuple[str, re.Pattern]] = [
    # 終了・廃止は最優先（金額・期間を含むことが多いため先に判定）
    ("program_end",        re.compile(r"終了しました|終了となりました|廃止されました|受付を終了|公募は終了")),
    # 新設（既存ページへの追加告知）
    ("new_program",        re.compile(r"新設|新たに創設|募集開始|公募開始|新たな補助")),
    # 期限変更（受付期間・締切を含む広範なパターン）
    ("deadline_change",    re.compile(r"締切|期限|受付終了|申請期間|受付期間|締め切り|公募期間|繰り上げ|繰り上がり")),
    # 対象・要件変更（金額系キーワードと被らないよう、対象外・対象者など限定的に）
    ("eligibility_change", re.compile(r"対象外|対象者|対象要件|資格要件|適用除外|対象となりません")),
    # 金額変更
    ("amount_change",      re.compile(r"[\d,]+\s*(?:万円|億円|円)|補助率|上限額|補助額|交付額")),
    # 手続き変更
    ("procedure_change",   re.compile(r"手続き|書類|申請方法|申込|提出|様式")),
    # 対象・要件変更（広範パターン。より具体的なものが先にマッチしなかった場合のフォールバック）
    ("eligibility_change", re.compile(r"対象|要件|条件|資格|適用")),
]


@dataclass
class Classification:
    change_type: str
    severity: str
    reason: str


def classify(chunks: list[DiffChunk], severity_rules: Optional[list[dict]] = None) -> Classification:
    """
    差分チャンクを分析し、変更タイプと severity を返す。
    severity_rules: sources.yml の severity_rules（ソース独自ルール）
    """
    all_text = _chunks_to_text(chunks)

    # --- ルールベース分類 ---
    matched_type = "other"
    for ctype, pattern in _RULES:
        if pattern.search(all_text):
            matched_type = ctype
            break

    # --- severity 判定 ---
    severity = _determine_severity(all_text, chunks, severity_rules)

    reason = f"ルールベース分類: '{matched_type}' にマッチ"
    return Classification(change_type=matched_type, severity=severity, reason=reason)


def _determine_severity(text: str, chunks: list[DiffChunk], custom_rules: Optional[list[dict]]) -> str:
    # カスタムルール（sources.yml）を優先チェック
    if custom_rules:
        for rule in custom_rules:
            if re.search(rule["match"], text):
                return rule.get("severity", "medium")

    # 組み込みルール
    HIGH_RE = re.compile(r"締切|期限|受付終了|申請期間|上限額|対象条件|補助率")
    MED_RE = re.compile(r"手続き|書類|申請方法|様式|注意")

    if HIGH_RE.search(text):
        return "high"
    if any(c.has_amount or c.has_date for c in chunks):
        return "high"
    if MED_RE.search(text):
        return "medium"
    return "low"


def _chunks_to_text(chunks: list[DiffChunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        parts.extend(c.lines_old)
        parts.extend(c.lines_new)
    return "\n".join(parts)
