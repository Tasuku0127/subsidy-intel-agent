"""
test_quality_pipeline.py: API不要の完全パイプライン品質テスト

fetcher（ローカルfile://）→ extractor → store → diff → classify → report の
エンドツーエンドで出力品質を検証する。
Claude API は使わず、generator はモックする。
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path
import unittest.mock as mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fetcher import fetch
from app.extractor import extract
from app.store import init_db, save_snapshot, get_last_two_snapshots
from app.diff import compute_diff, format_diff_for_llm
from app.classifier import classify
from app.reporter import generate_report, SourceResult

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parent.parent


class TestFetcherLocalFiles:
    """fetcher のローカルファイル対応テスト（file:// スキーム）"""

    def test_fetch_local_before(self):
        """file:// スキームで before.html が読めること"""
        url = "file://tests/fixtures/before.html"
        html = fetch(url, user_agent="test", timeout=5)
        assert "補助金" in html, "ローカルHTMLが読み込めていない"

    def test_fetch_local_sii_battery(self):
        url = "file://tests/fixtures/sii_battery_before.html"
        html = fetch(url, user_agent="test", timeout=5)
        assert "蓄電" in html

    def test_fetch_nonexistent_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            fetch("file://tests/fixtures/nonexistent.html", user_agent="test", timeout=5)


class TestStorePipeline:
    """store を使ったスナップショット管理の品質テスト"""

    def setup_method(self):
        """テスト用に一時DBパスを使う"""
        self.tmpdir = tempfile.mkdtemp()
        # store モジュールの DB_PATH をモンキーパッチ
        import app.store as store_module
        self._orig_db_path = store_module.DB_PATH
        store_module.DB_PATH = Path(self.tmpdir) / "test_snapshots.db"
        store_module.init_db()

    def teardown_method(self):
        import app.store as store_module
        store_module.DB_PATH = self._orig_db_path
        shutil.rmtree(self.tmpdir)

    def test_first_save_returns_changed(self):
        import app.store as store_module
        _, is_changed = store_module.save_snapshot("test_src", "テキスト内容")
        assert is_changed is True, "初回保存は変更ありとして扱われるべき"

    def test_same_text_returns_not_changed(self):
        import app.store as store_module
        store_module.save_snapshot("test_src", "テキスト内容")
        _, is_changed = store_module.save_snapshot("test_src", "テキスト内容")
        assert is_changed is False, "同一テキストは変更なしとして扱われるべき"

    def test_different_text_returns_changed(self):
        import app.store as store_module
        store_module.save_snapshot("test_src", "旧テキスト")
        _, is_changed = store_module.save_snapshot("test_src", "新テキスト（変更あり）")
        assert is_changed is True, "異なるテキストは変更ありとして扱われるべき"

    def test_get_last_two_returns_correct_order(self):
        import app.store as store_module
        store_module.save_snapshot("test_src", "first")
        store_module.save_snapshot("test_src", "second")
        previous, current = store_module.get_last_two_snapshots("test_src")
        assert current == "second", "current が最新でない"
        assert previous == "first", "previous が前回でない"

    def test_compression_roundtrip(self):
        """gzip 圧縮・展開で文字化けしないか"""
        import app.store as store_module
        original = "補助金制度：1kWhあたり4万円（上限20万円）令和7年3月31日締切"
        store_module.save_snapshot("compress_test", original)
        _, current = store_module.get_last_two_snapshots("compress_test")
        assert current == original, "gzip 圧縮後に文字列が変化した"


class TestReporterOutput:
    """レポート生成の品質テスト（実際のMarkdownを検証）"""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # reporter の出力先を一時ディレクトリに向ける
        import app.reporter as reporter_module
        self._orig_reports_dir = reporter_module.REPORTS_DIR
        reporter_module.REPORTS_DIR = self.tmpdir

    def teardown_method(self):
        import app.reporter as reporter_module
        reporter_module.REPORTS_DIR = self._orig_reports_dir
        shutil.rmtree(self.tmpdir)

    def _make_result(self, changed: bool, suggestions="AI案テキスト", error=None):
        old = extract((FIXTURES / "sii_battery_before.html").read_text(encoding="utf-8"))
        new = extract((FIXTURES / "sii_battery_after.html").read_text(encoding="utf-8"))
        chunks = compute_diff(old, new) if changed else []
        cls = classify(chunks) if chunks else None
        return SourceResult(
            source_id="test_src",
            source_name="テスト：SII蓄電池",
            source_url="https://example.com/test",
            changed=changed,
            chunks=chunks,
            classification=cls,
            suggestions=suggestions,
            error=error,
        )

    def test_report_file_created(self):
        result = self._make_result(changed=False)
        report_path = generate_report([result], run_date="quality-test")
        assert report_path.exists(), "レポートファイルが生成されていない"

    def test_report_has_header(self):
        result = self._make_result(changed=False)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "# 補助金・制度インテリジェンス レポート" in content

    def test_report_shows_changed_source(self):
        result = self._make_result(changed=True)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "テスト：SII蓄電池" in content
        assert "変更が検知されたソース" in content

    def test_report_shows_no_change_section(self):
        result = self._make_result(changed=False)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "変更なし" in content

    def test_report_includes_diff(self):
        result = self._make_result(changed=True)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "```diff" in content, "diff ブロックがレポートにない"

    def test_report_includes_severity_emoji(self):
        result = self._make_result(changed=True)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "🔴" in content or "🟡" in content or "🟢" in content, \
            "severity 絵文字がレポートにない"

    def test_report_includes_ai_suggestion(self):
        result = self._make_result(changed=True, suggestions="## AI提案\nLP修正案：XXX")
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "LP修正案" in content, "AI修正案がレポートに反映されていない"

    def test_report_shows_error_section(self):
        result = self._make_result(changed=False, error="タイムアウト: 30秒経過")
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "エラー" in content
        assert "タイムアウト" in content

    def test_report_has_disclaimer(self):
        """免責表記が必ずレポートに含まれること"""
        result = self._make_result(changed=True)
        report_path = generate_report([result], run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        assert "公式ソース" in content or "公式" in content, \
            "公式確認を促す免責文がレポートにない"

    def test_report_count_summary_accurate(self):
        """変更/変更なし/エラーのカウントが正確か"""
        results = [
            self._make_result(changed=True),
            self._make_result(changed=False),
            self._make_result(changed=False, error="取得失敗"),
        ]
        report_path = generate_report(results, run_date="quality-test")
        content = report_path.read_text(encoding="utf-8")
        # "変更検知: 1件" などが含まれるか
        assert "1件" in content, "変更件数のカウントがレポートに含まれていない"


class TestEndToEndPipeline:
    """fetcher → extractor → diff → classify → report の完全パイプライン"""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        import app.store as store_module
        import app.reporter as reporter_module
        self._orig_db = store_module.DB_PATH
        self._orig_reports = reporter_module.REPORTS_DIR
        store_module.DB_PATH = self.tmpdir / "snapshots.db"
        reporter_module.REPORTS_DIR = self.tmpdir / "reports"
        store_module.init_db()

    def teardown_method(self):
        import app.store as store_module
        import app.reporter as reporter_module
        store_module.DB_PATH = self._orig_db
        reporter_module.REPORTS_DIR = self._orig_reports
        shutil.rmtree(self.tmpdir)

    def test_full_pipeline_before_to_after(self):
        """before → after のパイプラインで変更検知からレポートまで完走するか"""
        import app.store as store_module

        # Step1: before を first snapshot として保存
        html_before = (FIXTURES / "sii_battery_before.html").read_text(encoding="utf-8")
        text_before = extract(html_before)
        store_module.save_snapshot("pipeline_test", text_before)

        # Step2: after で変更検知
        html_after = (FIXTURES / "sii_battery_after.html").read_text(encoding="utf-8")
        text_after = extract(html_after)
        _, is_changed = store_module.save_snapshot("pipeline_test", text_after)
        assert is_changed, "after → 変更なしと判定された（パイプライン全体が機能していない）"

        # Step3: diff
        previous, current = store_module.get_last_two_snapshots("pipeline_test")
        chunks = compute_diff(previous, current)
        assert len(chunks) > 0

        # Step4: classify
        cls = classify(chunks)
        assert cls.severity == "high"

        # Step5: report（AI 部分はモック）
        result = SourceResult(
            source_id="pipeline_test",
            source_name="SII 蓄電池（パイプラインテスト）",
            source_url="https://example.com/",
            changed=True,
            chunks=chunks,
            classification=cls,
            suggestions="[テスト用モック提案]",
        )
        report_path = generate_report([result], run_date="pipeline-test")
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "SII 蓄電池" in content
        assert "high" in content

    def test_no_change_pipeline(self):
        """同一ページの2回取得 → 変更なしレポートが生成されること"""
        import app.store as store_module

        html = (FIXTURES / "nochange_1.html").read_text(encoding="utf-8")
        text = extract(html)
        store_module.save_snapshot("nochange_test", text)
        store_module.save_snapshot("nochange_test", text)

        previous, current = store_module.get_last_two_snapshots("nochange_test")
        chunks = compute_diff(previous, current)
        assert len(chunks) == 0

        result = SourceResult(
            source_id="nochange_test",
            source_name="変更なしテスト",
            source_url="https://example.com/nochange",
            changed=False,
            chunks=[],
            classification=None,
            suggestions="",
        )
        report_path = generate_report([result], run_date="nochange-test")
        content = report_path.read_text(encoding="utf-8")
        assert "変更なし" in content
