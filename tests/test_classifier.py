"""
test_classifier.py: 変更分類テスト
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.diff import DiffChunk
from app.classifier import classify


def _chunk(text: str) -> DiffChunk:
    c = DiffChunk(tag="changed", lines_old=[], lines_new=text.splitlines())
    from app.diff import _annotate
    _annotate(c)
    return c


def test_classify_deadline_change():
    chunks = [_chunk("申請締切が2025年9月30日から2025年7月31日に変更されました")]
    cls = classify(chunks)
    assert cls.change_type == "deadline_change"
    assert cls.severity == "high"


def test_classify_amount_change():
    chunks = [_chunk("補助上限額が300万円から200万円に引き下げられました")]
    cls = classify(chunks)
    assert cls.change_type == "amount_change"
    assert cls.severity == "high"


def test_classify_program_end():
    chunks = [_chunk("本補助金プログラムは2025年3月31日をもって終了しました")]
    cls = classify(chunks)
    assert cls.change_type == "program_end"


def test_classify_new_program():
    chunks = [_chunk("新たな補助金制度が2025年4月1日より募集開始されます")]
    cls = classify(chunks)
    assert cls.change_type == "new_program"


def test_custom_severity_rules():
    chunks = [_chunk("申請書類の様式が変更されました")]
    custom_rules = [{"match": "申請", "severity": "high"}]
    cls = classify(chunks, severity_rules=custom_rules)
    assert cls.severity == "high"
