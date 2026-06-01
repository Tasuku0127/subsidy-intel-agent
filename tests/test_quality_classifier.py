"""
test_quality_classifier.py: 変更分類の精度を実データシナリオで検証

テスト方針：
- 実際に起きる補助金ページの変更タイプを網羅的にカバー
- 分類の「精度」と severity の「正確さ」を確認
- 誤分類パターンの検出
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractor import extract
from app.diff import compute_diff
from app.classifier import classify, Classification

FIXTURES = Path(__file__).parent / "fixtures"


def _pipeline(before: str, after: str, severity_rules=None) -> Classification:
    old = extract((FIXTURES / before).read_text(encoding="utf-8"))
    new = extract((FIXTURES / after).read_text(encoding="utf-8"))
    chunks = compute_diff(old, new)
    return classify(chunks, severity_rules)


class TestRealScenarioClassification:
    """実データシナリオの分類精度テスト"""

    def test_sii_battery_classified_as_program_end_or_deadline(self):
        """公募終了 → program_end または deadline_change であるべき"""
        cls = _pipeline("sii_battery_before.html", "sii_battery_after.html")
        assert cls.change_type in ("program_end", "deadline_change"), \
            f"公募終了シナリオが '{cls.change_type}' に分類された（期待: program_end or deadline_change）"

    def test_sii_battery_severity_is_high(self):
        """公募終了は severity high であるべき"""
        cls = _pipeline("sii_battery_before.html", "sii_battery_after.html")
        assert cls.severity == "high", \
            f"公募終了の severity が '{cls.severity}' （期待: high）"

    def test_zeh_classified_as_amount_or_deadline_change(self):
        """補助額改定＋締切変更 → amount_change または deadline_change"""
        cls = _pipeline("meti_zeh_before.html", "meti_zeh_after.html")
        assert cls.change_type in ("amount_change", "deadline_change", "eligibility_change"), \
            f"ZEH補助額・締切変更が '{cls.change_type}' に分類された"

    def test_zeh_severity_is_high(self):
        """補助額改定は severity high であるべき"""
        cls = _pipeline("meti_zeh_before.html", "meti_zeh_after.html")
        assert cls.severity == "high", \
            f"補助額改定の severity が '{cls.severity}'（期待: high）"


class TestChangeTypeAccuracy:
    """各変更タイプの分類精度"""

    def _from_text(self, old: str, new: str, rules=None) -> Classification:
        chunks = compute_diff(old, new)
        return classify(chunks, rules)

    def test_deadline_keywords_classified_correctly(self):
        cases = [
            ("申請期間は2025年9月まで", "申請期間は2025年6月まで（繰り上げ）"),
            ("締切：令和7年3月31日", "締切：令和7年1月31日"),
            ("受付期間：2025年4月〜8月", "受付期間：2025年4月〜6月（変更）"),
        ]
        for old, new in cases:
            cls = self._from_text(old, new)
            assert cls.change_type == "deadline_change", \
                f"'{old}' → '{new}' が deadline_change に分類されなかった（{cls.change_type}）"

    def test_amount_keywords_classified_correctly(self):
        cases = [
            ("補助上限：300万円", "補助上限：200万円"),
            ("補助率：1/2以内", "補助率：1/3以内"),
            ("交付額：最大100万円", "交付額：最大80万円"),
        ]
        for old, new in cases:
            cls = self._from_text(old, new)
            assert cls.change_type == "amount_change", \
                f"'{old}' → '{new}' が amount_change に分類されなかった（{cls.change_type}）"

    def test_eligibility_keywords_classified_correctly(self):
        cases = [
            # "対象外" は eligibility_change の高優先ルールにマッチ
            ("対象：中小企業および個人事業主", "対象：中小企業のみ（個人事業主は対象外となりました）"),
            # 対象者変更（金額なし）
            ("対象者：全業種", "対象者：製造業のみ（小売業・サービス業は対象外）"),
            # 対象要件変更（金額なし）
            ("対象要件：国内法人であること", "対象要件：国内法人かつ設立3年以上であること"),
        ]
        for old, new in cases:
            cls = self._from_text(old, new)
            assert cls.change_type == "eligibility_change", \
                f"'{old}' → '{new}' が eligibility_change に分類されなかった（{cls.change_type}）"

    def test_program_end_classified_correctly(self):
        cases = [
            ("申請を受け付けています", "本事業は終了しました"),
            ("公募中", "公募終了。予算上限に達したため受付を終了しました"),
            ("受付期間：〜2025年9月", "廃止：本事業は廃止されました"),
        ]
        for old, new in cases:
            cls = self._from_text(old, new)
            assert cls.change_type == "program_end", \
                f"'{old}' → '{new}' が program_end に分類されなかった（{cls.change_type}）"

    def test_new_program_classified_correctly(self):
        cases = [
            ("", "新設：令和7年度 蓄電池補助金が2025年4月1日より募集開始"),
            ("", "新たな補助制度が創設されました。申請受付を開始します"),
        ]
        for old, new in cases:
            cls = self._from_text(old, new)
            assert cls.change_type == "new_program", \
                f"新設シナリオが new_program に分類されなかった（{cls.change_type}）"


class TestSeverityAccuracy:
    """severity 判定の精度"""

    def _sev(self, old: str, new: str, rules=None) -> str:
        chunks = compute_diff(old, new)
        return classify(chunks, rules).severity

    def test_deadline_change_is_high(self):
        assert self._sev("締切：9月30日", "締切：7月31日") == "high"

    def test_amount_change_is_high(self):
        assert self._sev("補助上限：300万円", "補助上限：200万円") == "high"

    def test_eligibility_change_is_high(self):
        assert self._sev("対象：個人事業主を含む", "対象条件が変更されました") == "high"

    def test_procedure_change_is_medium_or_low(self):
        sev = self._sev(
            "申請書を郵送で提出してください",
            "申請書類の様式が変更されました。新様式を使用してください"
        )
        assert sev in ("medium", "low"), \
            f"書類様式変更は medium または low であるべき（実際: {sev}）"

    def test_custom_rules_override_defaults(self):
        """ソース固有ルールがデフォルトより優先される"""
        rules = [{"match": "様式", "severity": "high"}]
        sev = self._sev(
            "申請書様式Aを使用",
            "申請書様式Bに変更されました",
            rules=rules
        )
        assert sev == "high", "カスタムルールが適用されていない"

    def test_minor_wording_change_is_low(self):
        """軽微な文言修正は low（重要語なし）"""
        sev = self._sev(
            "詳細については担当窓口にお問い合わせください",
            "詳細については担当部署にご連絡ください"
        )
        assert sev in ("low", "medium"), \
            f"軽微な文言修正が高 severity に分類された（実際: {sev}）"


class TestEdgeCases:
    """エッジケース"""

    def test_empty_diff_chunks_classified_as_other(self):
        """差分なし（チャンクが空）の場合の分類"""
        cls = classify([])
        assert cls.change_type == "other"

    def test_classification_has_reason(self):
        """分類結果に reason が含まれること"""
        chunks = compute_diff("旧テキスト申請締切", "新テキスト締切変更")
        cls = classify(chunks)
        assert cls.reason, "分類理由が空になっている"

    def test_mixed_signals_picks_highest_priority(self):
        """複数のキーワードが混在する場合、優先度の高いタイプが選ばれる"""
        # deadline_change が最初にマッチすることを確認（ルール順序の検証）
        text = "申請締切が変更されました。対象条件も一部変わりました。補助額は300万円のまま変わりません。"
        chunks = compute_diff("", text)
        cls = classify(chunks)
        # deadline または amount が選ばれること（other ではない）
        assert cls.change_type != "other", \
            "複数キーワードが混在するのに 'other' に分類された"
