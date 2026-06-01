# 補助金・制度インテリジェンス Agent

> エナジーサプライ株式会社 インハウスマーケ向け PoC
> 作成者：扶（転職活動ポートフォリオ）

補助金・制度ページの変更を自動検知し、マーケ施策（LP / SEO / 広告）の修正案を **差分付き** で提案する内部向け AI ツール。

---

## 解決する課題

| 課題 | 本ツールのアプローチ |
|------|-------------------|
| 補助金ページの更新漏れ | 定期クロール＋差分検知で自動検出 |
| 更新検知の遅延（広告費ムダ） | Severity high → Slack 即時通知 |
| 修正作業の属人化 | Claude が自社ページ修正案・広告訴求案を自動生成 |

---

## アーキテクチャ

```
sources.yml
   │
   ▼
[fetcher]  → HTML 取得（requests, リトライ対応）
   │
   ▼
[extractor] → 本文抽出（readability-lxml / CSS セレクタ）
   │
   ▼
[store]    → スナップショット保存（SQLite + gzip）
   │
   ▼
[diff]     → 段落単位差分（金額・日付・重要語に重み付け）
   │
   ├─▶ [classifier] → 変更タイプ分類 (deadline_change / amount_change / ...)
   │
   └─▶ [generator]  → Claude API で修正案生成（LP文案 + 広告案 + 確認ポイント）
          │
          ▼
      [reporter]  → reports/YYYY-MM-DD_digest.md
          │
          ▼
      [notifier]  → Slack Webhook（high → 即時 / digest → 日次）
```

---

## セットアップ

```bash
# 1. 依存インストール
pip install -e ".[dev]"

# 2. 環境変数設定
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定
# （Slack 通知を使う場合は SLACK_WEBHOOK_URL も設定）

# 3. 監視対象の設定
vi config/sources.yml
```

---

## 使い方

### 通常実行（全ソース）
```bash
python -m app.run --mode once
```

### 特定ソースのみ
```bash
python -m app.run --mode once --source meti_solarpower
```

### デモ実行（面接用）
```bash
python demo.py
```
テストフィクスチャ（before.html → after.html）を使い、変更検知〜修正案生成〜レポート生成の一連フローをデモします。

### テスト実行
```bash
pytest tests/ -v
# カバレッジ付き
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## 設定：`config/sources.yml`

```yaml
version: 1
defaults:
  fetch_interval_hours: 24
  timeout_seconds: 25
  user_agent: "EnergySupplySubsidyWatcher/0.1"
  extract_mode: "readability"

sources:
  - id: "my_subsidy_page"
    name: "自社：補助金ページ"
    url: "https://example.com/subsidy/"
    owner_team: "marketing"
    tags: ["owned", "subsidy"]
    severity_rules:
      - match: "(申請|受付|締切|期限|募集)"
        severity: "high"
      - match: "(万円|補助率|上限)"
        severity: "high"
```

---

## 出力レポート例（`reports/YYYY-MM-DD_digest.md`）

```markdown
# 補助金・制度インテリジェンス レポート
実行日時: 2025-04-01 09:00
監視ソース数: 3件 | 変更検知: 1件 | 変更なし: 2件 | エラー: 0件

## 変更が検知されたソース

### 🔴 再エネ補助金ページ（デモ）
- 変更タイプ: `deadline_change`
- Severity: `high`

#### 差分（抜粋）
- 申請受付期間：...〜2025年9月30日
+ 申請受付期間：...〜2025年7月31日（締切繰り上げ）

#### AI 修正案
**自社ページ修正文案**
...（Claude が生成）...

**広告訴求更新案（RSA）**
...
```

---

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API キー |
| `SLACK_WEBHOOK_URL` | オプション | Slack Incoming Webhook URL |

---

## ディレクトリ構造

```
subsidy-intel-agent/
├── app/
│   ├── run.py         # エントリーポイント
│   ├── fetcher.py     # HTML取得
│   ├── extractor.py   # 本文抽出
│   ├── diff.py        # 差分検知
│   ├── classifier.py  # 変更分類
│   ├── generator.py   # AI修正案生成（Claude）
│   ├── reporter.py    # Markdownレポート生成
│   ├── notifier.py    # Slack通知
│   └── store.py       # SQLiteスナップショット管理
├── config/
│   └── sources.yml    # 監視対象定義
├── tests/
│   ├── fixtures/      # テスト用HTML（before/after）
│   ├── test_diff.py
│   ├── test_extractor.py
│   └── test_classifier.py
├── reports/           # 生成レポート（.gitignore）
├── data/              # SQLite DB（.gitignore）
├── logs/              # ログ（.gitignore）
├── demo.py            # 面接デモ用スクリプト
├── .env.example
├── pyproject.toml
└── README.md
```

---

## デモシナリオ（面接で見せる用）

1. `sources.yml` の説明（監視対象の定義方法）
2. `python demo.py` を実行
3. ターミナルで差分検知 → Severity 判定 → Claude 修正案 を見せる
4. 生成された `reports/demo_digest.md` を開いて説明
5. 1分でまとめ：
   - 更新漏れゼロ（自動検知）
   - 制作工数削減（修正案自動生成）
   - 広告訴求の鮮度向上（即時 Slack 通知）

---

## セキュリティ・コンプラ

- 保存するのは「公開ページの本文テキスト」と「AI生成の提案文」のみ
- 個人情報は一切扱わない
- 公式・公的ソース中心。クロール間隔を守り負荷をかけない
- AI 生成物は必ず人が承認してから本番反映

---

## 拡張案（MVP 後）

- RAG 化：自社サイトの関連ページを自動検索して提案に反映
- Notion/Jira 連携：修正タスクを自動起票
- GitHub Actions でのスケジュール実行（cron）
- 競合監視（小規模）
