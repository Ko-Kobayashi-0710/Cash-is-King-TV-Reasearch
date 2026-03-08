# Cash is King TV リサーチエージェント

ポッドキャスト「Cash is King TV」の各回のリサーチを自動化するエージェント。
企業名とティッカーを与えると、EDINET・yfinance・IRページ・Webを自分で取りに行き、
定量・定性の両面から分析し、markdownレポートを生成する。

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# APIキーの設定
cp .env.example .env
# .envを編集してANTHROPIC_API_KEYを設定する
```

## 実行方法

```bash
# 基本実行
python research.py --company "企業名" --ticker "XXXX.T"

# EDINETコードを直接指定（検索省略でスピードアップ）
python research.py --company "杉孝ホールディングス" --ticker "XXXX.T" --edinet-code "EXXXXX"

# 競合他社を手動指定
python research.py --company "トヨタ自動車" --ticker "7203.T" --competitors "7267.T,7270.T"

# IRページURLを直接指定
python research.py --company "マネーフォワード" --ticker "3994.T" --ir-url "https://moneyforward.com/ir/"

# EDINETとIRページの取得をスキップ（高速モード）
python research.py --company "ソフトバンク" --ticker "9434.T" --skip-edinet --skip-ir
```

## ディレクトリ構成

```
cash-is-king-research/
├── CLAUDE.md              ← このファイル
├── .env                   ← APIキー（gitignore済み）
├── .env.example           ← APIキーのテンプレート
├── requirements.txt       ← Python依存パッケージ
├── research.py            ← エントリーポイント
├── agent/
│   ├── __init__.py
│   ├── fetcher.py         ← yfinance・IRページ・Web取得
│   ├── edinet.py          ← EDINET APIv2専用モジュール
│   ├── analyzer.py        ← 財務計算・指標抽出
│   └── reporter.py        ← LLM呼び出し・レポート生成
├── prompts/
│   └── system.md          ← Claude用システムプロンプト全文
└── output/
    └── [企業名]_cash_is_king.md
```

## アーキテクチャ

### データ取得の3層構造

**層1: yfinance（財務数値の骨格）**
- PL・BS・CFの直近5期分を無料・APIキー不要で取得
- `fetcher.py` の `fetch_yfinance_data()` が担当

**層2: EDINET APIv2（有価証券報告書の全文）**
- 企業のEDINETコードで検索し、直近の有価証券報告書をXBRL/PDFで取得
- セグメント別数値・前受金・役員報酬などを抽出
- `edinet.py` の `fetch_securities_report_text()` が担当

**層3: IRページ + Web（定性・最新情報）**
- 企業公式IRページから決算説明資料PDFを取得・テキスト抽出
- Web検索（DuckDuckGo）で直近1年のニュース・業界動向を収集
- `fetcher.py` の `fetch_ir_page_and_pdfs()` と `fetch_news_and_industry()` が担当

### LLM呼び出し
- モデル: `claude-opus-4-6`（Anthropic最上位モデル）
- Adaptive Thinkingを使用（深い分析のため）
- ストリーミング出力でレポートをリアルタイム表示
- `reporter.py` の `generate_report()` が担当

### Cash is King 3軸評価
1. **他人のカネで回す（タイミング）**: CCC・前受金・デポジット
2. **使ったカネが残存する（残存）**: FCF・減価償却・資産耐用年数
3. **投じるほど効率が上がる（複利）**: ROIC推移・規模の経済・ネットワーク効果

## 注意事項

- EDINETコードは https://disclosure.edinet-fsa.go.jp で企業名から検索可能
- 日本株ティッカーは証券コード＋`.T`（例: `7203.T`）
- PDFが取得できない場合はその旨を明記してWebから補完する
- 財務数値は必ず出典（何期の有報・決算資料か）を明記する
- 推測・仮説は「〜と考えられる」と明示し、ファクトと混在させない
