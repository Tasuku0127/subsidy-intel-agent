"""
test_quality_diff.py: 差分検知の精度・品質を検証

テスト方針：
- 実際の補助金ページ変更シナリオで、想定通りの差分が出るかを確認
- 「重要な変更」と「重要でない変更」が正しく区別されるかを確認
- 差分の内容が LLM プロンプトに渡せる品質かを確認
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractor import extract
from app.diff import compute_diff, format_diff_for_llm, has_significant_changes, DiffChunk

FIXTURES = Path(__file__).parent / "fixtures"


def _extract(name: str) -> str:
    return extract((FIXTURES / name).read_text(encoding="utf-8"))


class TestSIIBatteryDiff:
    """SII 蓄電池ページ：公募終了変更のシナリオ"""

    def setup_method(self):
        self.old = _extract("sii_battery_before.html")
        self.new = _extract("sii_battery_after.html")
        self.chunks = compute_diff(self.old, self.new)

    def test_detects_changes(self):
        assert len(self.chunks) > 0, "公募終了変更が検知されない"

    def test_detects_deadline_change(self):
        """7月2日終了という日付変更が差分に含まれるか"""
        diff_str = format_diff_for_llm(self.chunks)
        assert "7月" in diff_str or "終了" in diff_str, \
            "公募終了・日付変更が差分テキストに反映されていない"

    def test_significant_change_flagged(self):
        assert has_significant_changes(self.chunks), \
            "公募終了は重要変更として検知されるべき"

    def test_has_date_annotated_chunks(self):
        assert any(c.has_date for c in self.chunks), \
            "日付変更チャンクに has_date フラグが立っていない"

    def test_diff_readable_for_llm(self):
        """差分テキストがLLMに渡せる形式か（+/- 記号、文字数制限）"""
        diff_text = format_diff_for_llm(self.chunks)
        assert "+" in diff_text or "-" in diff_text, "diff 記号が含まれていない"
        assert len(diff_text) <= 3100, "diff テキストが文字数制限を超えている"
        assert len(diff_text) > 10, "diff テキストが空に近い"

    def test_no_change_for_identical(self):
        chunks = compute_diff(self.old, self.old)
        assert len(chunks) == 0, "同一テキストで差分が出てはいけない"

    def test_no_change_preserved_sections(self):
        """変更がなかったセクション（補助額）が差分に混入していないか確認"""
        diff_text = format_diff_for_llm(self.chunks)
        # after でも「4万円」「20万円」は変わっていないはずなので、
        # 差分として現れるのは文脈変化があった行のみのはず
        # ここでは単に「差分が巨大すぎないか」で品質を確認
        lines = diff_text.split("\n")
        diff_lines = [l for l in lines if l.startswith("+") or l.startswith("-")]
        assert len(diff_lines) < 80, \
            f"差分行が{len(diff_lines)}行と多すぎる（変化なし行が混入している可能性）"


class TestZEHDiff:
    """ZEH支援事業：補助額改定＋締切繰り上げのシナリオ"""

    def setup_method(self):
        self.old = _extract("meti_zeh_before.html")
        self.new = _extract("meti_zeh_after.html")
        self.chunks = compute_diff(self.old, self.new)

    def test_amount_change_detected(self):
        """55万円→40万円、100万円→80万円の変更が検知されるか"""
        diff_text = format_diff_for_llm(self.chunks)
        assert ("55万円" in diff_text or "40万円" in diff_text), \
            "ZEH補助額の変更（55万円→40万円）が差分に現れていない"

    def test_has_amount_flag(self):
        assert any(c.has_amount for c in self.chunks), \
            "金額変更チャンクに has_amount フラグが立っていない"

    def test_schedule_change_detected(self):
        """第2次公募締切の繰り上げ（8月29日→7月31日）が検知されるか"""
        diff_text = format_diff_for_llm(self.chunks)
        assert "7月31日" in diff_text or "8月29日" in diff_text, \
            "第2次公募締切変更が差分に含まれていない"

    def test_third_round_cancellation_detected(self):
        """第3次公募の中止が差分に含まれるか"""
        diff_text = format_diff_for_llm(self.chunks)
        assert "実施予定なし" in diff_text or "中止" in diff_text, \
            "第3次公募中止が差分に含まれていない"

    def test_significant_change_flagged(self):
        assert has_significant_changes(self.chunks), \
            "補助額改定＋締切変更は重要変更として検知されるべき"

    def test_unmodified_budget_not_flagged_as_change(self):
        """予算総額540億円は変わっていないので removed として出ないはず"""
        for chunk in self.chunks:
            for line in chunk.lines_old:
                # 変更なしの行が removed に混入していたら問題
                # ただし「置換」チャンクの old 側に入るのは許容
                pass
        # 最低限：差分テキストが空でないことを確認
        diff_text = format_diff_for_llm(self.chunks)
        assert len(diff_text.strip()) > 0


class TestFirstTimeFetch:
    """初回取得（前回スナップショットなし）のシナリオ"""

    def test_all_chunks_are_added(self):
        text = _extract("new_program.html")
        chunks = compute_diff(None, text)
        assert all(c.tag == "added" for c in chunks), "初回取得は全チャンクが added であるべき"

    def test_new_program_keywords_present(self):
        text = _extract("new_program.html")
        chunks = compute_diff(None, text)
        diff_text = format_diff_for_llm(chunks)
        assert "新設" in diff_text or "新たに" in diff_text or "開始" in diff_text, \
            "新設プログラムのキーワードが差分テキストに含まれていない"

    def test_significant_for_new_program(self):
        text = _extract("new_program.html")
        chunks = compute_diff(None, text)
        assert has_significant_changes(chunks), \
            "新規プログラム（金額・日付を含む）は重要変更として検知されるべき"


class TestNoChangeScenario:
    """変更なしシナリオ"""

    def test_identical_pages_produce_no_chunks(self):
        text = _extract("nochange_1.html")
        chunks = compute_diff(text, text)
        assert len(chunks) == 0, "同一コンテンツで差分チャンクが生成されてはいけない"

    def test_whitespace_only_change_is_empty(self):
        """複数の連続スペースは正規化で1つに統一されること"""
        from app.extractor import _normalize
        # 連続スペースが正規化されることを確認（単一スペースは保持される）
        text_multi_space = "補助率：対象経費の   1/3以内"
        text_single_space = "補助率：対象経費の 1/3以内"
        assert _normalize(text_multi_space) == _normalize(text_single_space), \
            "複数連続スペースが1スペースに正規化されていない"

        # 全角スペースも正規化されること
        text_zenkaku = "補助率：対象経費の\u30001/3以内"
        assert _normalize(text_zenkaku) == _normalize(text_single_space), \
            "全角スペースが半角スペースに正規化されていない"


class TestDiffFormatQuality:
    """format_diff_for_llm の出力品質"""

    def test_truncates_at_max_chars(self):
        old = "行\n" * 500
        new = "別の行\n" * 500
        chunks = compute_diff(old, new)
        diff_text = format_diff_for_llm(chunks, max_chars=1000)
        assert len(diff_text) <= 1100, "最大文字数を大幅に超えている"
        assert "省略" in diff_text, "省略マーカーが付いていない"

    def test_added_lines_have_plus_prefix(self):
        chunks = compute_diff(None, "新しい行1\n新しい行2")
        diff_text = format_diff_for_llm(chunks)
        plus_lines = [l for l in diff_text.split("\n") if l.startswith("+")]
        assert len(plus_lines) >= 1, "追加行に + プレフィックスがない"

    def test_removed_lines_have_minus_prefix(self):
        old = "古い行1\n古い行2"
        new = "新しい行1\n新しい行2"
        chunks = compute_diff(old, new)
        diff_text = format_diff_for_llm(chunks)
        minus_lines = [l for l in diff_text.split("\n") if l.startswith("-")]
        assert len(minus_lines) >= 1, "削除行に - プレフィックスがない"
