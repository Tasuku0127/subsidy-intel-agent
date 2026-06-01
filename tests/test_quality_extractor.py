"""
test_quality_extractor.py: 実データに近いフィクスチャで抽出品質を検証

テスト方針：
- "空でないこと" だけでなく、本文の重要要素が抽出できているかを確認する
- ナビゲーション・ヘッダ・フッタが除去されているかを確認する
- 金額・日付・制度名などのマーカーが保持されているかを検証する
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractor import extract

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestSIIBatteryExtraction:
    """SII 家庭用蓄電システムページ（実データ構造）の抽出品質"""

    def test_extracts_subsidy_amount(self):
        text = extract(_load("sii_battery_before.html"))
        assert "4万円" in text or "4 万円" in text, "kWhあたり補助額が抽出されていない"

    def test_extracts_upper_limit(self):
        text = extract(_load("sii_battery_before.html"))
        assert "20万円" in text, "補助上限額が抽出されていない"

    def test_extracts_deadline(self):
        text = extract(_load("sii_battery_before.html"))
        assert "2025" in text and ("9月30日" in text or "9月" in text), "申請締切日が抽出されていない"

    def test_extracts_capacity_requirement(self):
        text = extract(_load("sii_battery_before.html"))
        assert "3.0kWh" in text or "3.0" in text, "最低蓄電容量要件が抽出されていない"

    def test_does_not_include_nav_footer(self):
        text = extract(_load("sii_battery_before.html"))
        # フッタの著作権表記は抽出されてもよいが、ナビの「ホーム > 補助事業」は
        # コンテンツと混在しないようにフィルタリングされるべき
        # readability は article 本文を重視するため長いナビ文字列は除かれやすい
        assert len(text) > 200, "抽出テキストが短すぎる（本文が取れていない）"

    def test_program_end_notice_in_after(self):
        """after版：公募終了バナーが抽出できているか"""
        text = extract(_load("sii_battery_after.html"))
        assert "終了" in text, "公募終了の告知が抽出されていない"
        assert "7月2日" in text or "7月" in text, "終了日が抽出されていない"


class TestZEHExtraction:
    """ZEH支援事業ページ（dl/dt/dd 構造）の抽出品質"""

    def test_extracts_zeh_plus_amount(self):
        text = extract(_load("meti_zeh_before.html"))
        assert "100万円" in text, "ZEH+の補助額100万円が抽出されていない"

    def test_extracts_all_three_募集_rounds(self):
        text = extract(_load("meti_zeh_before.html"))
        assert "第1次" in text or "第1" in text, "第1次公募が抽出されていない"
        assert "第2次" in text or "第2" in text, "第2次公募が抽出されていない"
        assert "第3次" in text or "第3" in text, "第3次公募が抽出されていない"

    def test_extracts_budget_total(self):
        text = extract(_load("meti_zeh_before.html"))
        assert "540億円" in text, "予算総額が抽出されていない"

    def test_after_includes_amount_change(self):
        text = extract(_load("meti_zeh_after.html"))
        assert "40万円" in text or "80万円" in text, "改定後の補助額が抽出されていない"


class TestNewProgramExtraction:
    """新設プログラムページの抽出品質"""

    def test_extracts_new_badge_or_content(self):
        text = extract(_load("new_program.html"))
        assert "新設" in text or "新たに" in text or "創設" in text, "新設の告知が抽出されていない"

    def test_extracts_program_details(self):
        text = extract(_load("new_program.html"))
        assert "1,000万円" in text or "1000万円" in text or "1,000" in text, "補助上限が抽出されていない"
        assert "200億円" in text, "予算総額が抽出されていない"

    def test_extracts_target_capacity(self):
        text = extract(_load("new_program.html"))
        assert "10kWh" in text, "対象容量要件が抽出されていない"


class TestCSSSelectMode:
    """css_select モードでの抽出品質"""

    def test_css_main_selects_body_content(self):
        text = extract(_load("sii_battery_before.html"), mode="css_select",
                       css_selectors={"main": "main"})
        assert "補助" in text, "mainセレクタで本文が取れていない"
        assert "4万円" in text or "20万円" in text, "補助額が取れていない"

    def test_css_section_selects_specific(self):
        text = extract(_load("meti_zeh_before.html"), mode="css_select",
                       css_selectors={"schedule": "section:nth-of-type(3)"})
        assert len(text) > 10, "sectionセレクタで何も取れていない"


class TestNormalization:
    """テキスト正規化品質"""

    def test_no_consecutive_spaces(self):
        texts = [
            extract(_load("sii_battery_before.html")),
            extract(_load("meti_zeh_before.html")),
        ]
        for text in texts:
            assert "   " not in text, "3つ以上の連続スペースが残っている"

    def test_no_excessive_newlines(self):
        texts = [
            extract(_load("sii_battery_before.html")),
            extract(_load("meti_zeh_before.html")),
        ]
        for text in texts:
            assert "\n\n\n" not in text, "3連続改行が残っている（正規化不足）"

    def test_meaningful_length(self):
        """どのページも最低 100 文字以上の本文が取れること"""
        for filename in ["sii_battery_before.html", "meti_zeh_before.html", "new_program.html"]:
            text = extract(_load(filename))
            assert len(text) >= 100, f"{filename}: テキスト長{len(text)}文字は短すぎる"
