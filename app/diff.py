"""
diff.py: テキスト差分の抽出と重要行のハイライト
段落単位で比較し、金額・日付・重要語を含む行を重み付け。
"""
import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

# 重要語パターン
_AMOUNT_RE = re.compile(r"[\d,]+\s*(?:万円|億円|円|%|％)")
_DATE_RE = re.compile(
    r"(?:令和|平成)?\s*\d+\s*年\s*\d+\s*月(?:\s*\d+\s*日)?|"
    r"\d{4}[/\-年]\d{1,2}[/\-月]\d{0,2}"
)
_KEYWORD_RE = re.compile(r"(?:申請|受付|締切|期限|募集|公募|対象|要件|条件|終了|開始|上限|下限|補助率)")


@dataclass
class DiffChunk:
    tag: str           # "added" | "removed" | "changed"
    lines_old: list[str] = field(default_factory=list)
    lines_new: list[str] = field(default_factory=list)
    has_amount: bool = False
    has_date: bool = False
    has_keyword: bool = False

    @property
    def importance(self) -> str:
        if self.has_amount or self.has_date or self.has_keyword:
            return "high"
        return "low"


def compute_diff(old_text: Optional[str], new_text: str) -> list[DiffChunk]:
    """
    old_text と new_text の差分を DiffChunk リストで返す。
    old_text が None の場合は「初回取得」として全行を added 扱い。
    """
    if old_text is None:
        lines = new_text.splitlines()
        chunk = DiffChunk(tag="added", lines_new=lines)
        _annotate(chunk)
        return [chunk] if lines else []

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    chunks: list[DiffChunk] = []

    for opcode, i1, i2, j1, j2 in sm.get_opcodes():
        if opcode == "equal":
            continue
        if opcode == "insert":
            c = DiffChunk(tag="added", lines_new=new_lines[j1:j2])
        elif opcode == "delete":
            c = DiffChunk(tag="removed", lines_old=old_lines[i1:i2])
        else:  # replace
            c = DiffChunk(tag="changed", lines_old=old_lines[i1:i2], lines_new=new_lines[j1:j2])
        _annotate(c)
        chunks.append(c)

    return chunks


def _annotate(chunk: DiffChunk) -> None:
    all_lines = chunk.lines_old + chunk.lines_new
    combined = "\n".join(all_lines)
    chunk.has_amount = bool(_AMOUNT_RE.search(combined))
    chunk.has_date = bool(_DATE_RE.search(combined))
    chunk.has_keyword = bool(_KEYWORD_RE.search(combined))


def format_diff_for_llm(chunks: list[DiffChunk], max_chars: int = 3000) -> str:
    """LLM に渡す差分テキストを生成（文字数制限付き）"""
    lines: list[str] = []
    for c in chunks:
        if c.tag == "added":
            for ln in c.lines_new:
                lines.append(f"+ {ln}")
        elif c.tag == "removed":
            for ln in c.lines_old:
                lines.append(f"- {ln}")
        else:
            for ln in c.lines_old:
                lines.append(f"- {ln}")
            for ln in c.lines_new:
                lines.append(f"+ {ln}")
        lines.append("")  # 空行で区切り

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n...(省略)"
    return result


def has_significant_changes(chunks: list[DiffChunk]) -> bool:
    return any(c.importance == "high" for c in chunks)
