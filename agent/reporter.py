"""
データダンプ・ファイル出力モジュール
収集した財務データ・ニュースをClaude.aiに貼り付け用のmarkdownファイルとして出力する
"""

import datetime
from pathlib import Path
from typing import Optional


SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.md"


def _load_system_prompt() -> str:
    """システムプロンプトをファイルから読み込む"""
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return "あなたはポッドキャスト「Cash is King TV」のリサーチャーです。"


def build_data_dump(
    company_name: str,
    ticker: str,
    financial_summary: str,
    edinet_result: dict,
    ir_result: dict,
    news_data: dict,
    competitor_comparison: str,
    competitors_raw: dict,
    sources: list[dict],
    youtube_transcripts: Optional[list[dict]] = None,
) -> str:
    """
    収集したデータをClaude.aiに貼り付け用のmarkdown形式でまとめる。
    ファイル末尾にシステムプロンプト＋分析依頼プロンプトを付与する。
    """
    sections = []

    # ヘッダー
    today = datetime.date.today().isoformat()
    sections.append(f"# {company_name} リサーチデータ（{today}）")
    sections.append("")
    sections.append("> このファイルをClaude.aiに貼り付けて分析レポートを生成してください。")
    sections.append("")
    sections.append("---")
    sections.append("")

    # 財務サマリー
    sections.append("## 取得した財務データ")
    sections.append(financial_summary)
    sections.append("")

    # 競合比較
    if competitor_comparison:
        sections.append("## 競合比較データ")
        sections.append(competitor_comparison)
        sections.append("")

    # EDINET有価証券報告書
    edinet_text = edinet_result.get("text") if edinet_result else None
    if edinet_text:
        sections.append("## 有価証券報告書（EDINET）からの抜粋")
        sections.append(edinet_text[:15000])
        sections.append("")
    elif edinet_result and edinet_result.get("error"):
        sections.append("## 有価証券報告書（EDINET）")
        sections.append(f"⚠️ 未取得: {edinet_result['error']}")
        sections.append("")

    # IRページのPDF
    ir_pdfs = ir_result.get("pdfs", []) if ir_result else []
    if ir_pdfs:
        sections.append("## IRページ・決算説明資料からの抜粋")
        for pdf_info in ir_pdfs[:2]:
            url = pdf_info.get("url", "")
            text = pdf_info.get("text", "")
            sections.append(f"### 出典: {url}")
            sections.append(text[:8000])
            sections.append("")

    # ニュース・動向
    news_items = news_data.get("company_news", [])[:10]
    if news_items:
        sections.append("## 直近のニュース・動向")
        for item in news_items:
            title = item.get("title", "")
            url = item.get("url", "")
            full_text = item.get("full_text", "")
            snippet = item.get("body", "")[:300]
            content = full_text[:1500] if full_text else snippet
            sections.append(f"### {title}\n出典: {url}\n\n{content}")
            sections.append("")
        sections.append("")

    # インタビュー記事
    interview_items = news_data.get("interviews", [])[:5]
    if interview_items:
        sections.append("## 経営陣インタビュー・発言")
        for item in interview_items:
            title = item.get("title", "")
            url = item.get("url", "")
            full_text = item.get("full_text", "")
            snippet = item.get("body", "")[:300]
            content = full_text[:2000] if full_text else snippet
            sections.append(f"### {title}\n出典: {url}\n\n{content}")
            sections.append("")
        sections.append("")

    # 業界動向
    industry_items = news_data.get("industry_trends", [])[:5]
    if industry_items:
        sections.append("## 業界動向・市場分析")
        for item in industry_items:
            title = item.get("title", "")
            url = item.get("url", "")
            full_text = item.get("full_text", "")
            snippet = item.get("body", "")[:300]
            content = full_text[:1500] if full_text else snippet
            sections.append(f"### {title}\n出典: {url}\n\n{content}")
            sections.append("")
        sections.append("")

    # アナリスト・投資家レポート
    analyst_items = news_data.get("analyst_reports", [])[:3]
    if analyst_items:
        sections.append("## アナリスト・投資家向けレポート")
        for item in analyst_items:
            title = item.get("title", "")
            url = item.get("url", "")
            full_text = item.get("full_text", "")
            snippet = item.get("body", "")[:300]
            content = full_text[:1500] if full_text else snippet
            sections.append(f"### {title}\n出典: {url}\n\n{content}")
            sections.append("")
        sections.append("")

    # YouTube字幕
    if youtube_transcripts:
        sections.append("## YouTube動画（字幕・文字起こし）")
        for yt in youtube_transcripts:
            url = yt.get("url", "")
            text = yt.get("text", "")
            sections.append(f"### 動画: {url}\n\n{text}")
            sections.append("")
        sections.append("")

    # 参照URL一覧
    sections.append("## 収集済み参照資料")
    for s in sources:
        sections.append(f"- {s.get('name', '')}: {s.get('url', '')} ({s.get('date', '')})")
    sections.append("")

    # ===================================================================
    # Claude.aiへの依頼プロンプト
    # ===================================================================
    sections.append("---")
    sections.append("")
    sections.append("## ▼ ここから下をClaude.aiへのプロンプトとして使用してください")
    sections.append("")
    sections.append("```")
    sections.append(_load_system_prompt())
    sections.append("```")
    sections.append("")
    sections.append(f"""
上記のデータをもとに、{company_name} の Cash is King 分析を **2つ** 生成してください。

分析は必ず以下の**7定石の順序**で進めること。各定石の結果が次の定石の入力になる連鎖構造なので、順序を変えてはならない。

---

### 【出力1】リサーチレポート（markdown形式）

**分析ルール:**
1. ファクトなき考察は書かない。必ず数字か一次情報に根拠を置く
2. 「儲かっている」で終わらない。なぜ儲かるのかの構造を言語化する
3. 驚きのある考察を必ず1つ入れる（「実は○○だった」という逆説的発見）
4. 比較なき分析は弱い。必ず競合・類似業態と比べて相対化する
5. 「Cash is Kingの秘訣」は必ず独自の命名をする（例：「撤去できない資産が生む二重ロック」）
6. データが取得できなかった項目は「データ未取得」と明記する
7. 推測・仮説は「〜と考えられる」と明示し、ファクトと混在させない
8. 定石3のKPI特定を省略しない（業種固有KPIを飛ばすと定石7の考察が表面的になる）
9. 定石6の会計・ファイナンス乖離は必ず数値（EBITDAマージン - 営業利益率の差）で示す
10. 軸②の残存資産は、BSに載らない人材・関係性・認証・データも評価対象に含める
11. 軸③の効率は、ROIC（BS的複利）と販管費レバレッジ（PL的複利）の両方を評価する

**レポートの構造:**

# {company_name} Cash is King分析

## 0. サマリー（収録用・60秒で読める）
- この会社が何をしている会社か（1行）
- Cash is Kingの秘訣（命名して1行で）
- 最も驚くべき定量事実（1つだけ）

## 1. 外観
（この会社が何をしている会社か、3〜5行で）

## 2. ステークホルダー構造（定石2）
（経営陣・金融機関・大株主・顧客のそれぞれの意図を読み解く。注目すべき数値と意図を表形式で）

## 3. 業種固有KPI（定石3）
（この業種で「本当に重要な数字」は何か。KPI分類を特定し、直近3期分の数値を時系列で提示）

## 4. 財務構造サマリー（定石4）
（PL・BS・CF・ROIC・CapEx vs D&Aの5期推移。PLとCFの乖離チェック結果を明示）

## 5. 時系列・競合比較（定石5）
（利益率・CF・借入の急変点とイベントの照合。競合との差異が最も大きい指標を特定）
| 指標 | {company_name} | 競合A | 競合B |
|---|---|---|---|
（売上高営業利益率・EBITDAマージン・CCC・ROIC・1人あたり売上を横並びで比較）

## 6. 会計 vs ファイナンス乖離分析（定石6）
| 論点 | 会計視点 | ファイナンス視点 |
|---|---|---|
（EBITDAマージン - 営業利益率の乖離幅を数値で明示。乖離の意味を解釈する）

## 7. Cash is King 3軸評価（定石7）
| 軸 | 評価 | 根拠となる定量数値 |
|---|---|---|
| ① 他人のカネで回す | ◎/○/△/× | CCCの日数・前受金額・DPO vs DSO差 |
| ② 使ったカネが残存する | ◎/○/△/× | EBITDAマージン乖離幅・残存資産の種類と規模 |
| ③ 投じるほど効率が上がる | ◎/○/△/× | ROICの推移・売上成長率 vs 販管費増加率の乖離 |

### 軸①の詳細考察（300〜500字）
（CCCと前受金構造で判定。「誰のカネで事業が動いているか」を問う）

### 軸②の詳細考察（300〜500字）
（BS資産だけでなく、人材・データ・関係性・認証など非BSの残存資産も評価する）

### 軸③の詳細考察（300〜500字）
（ROIC推移＝BS的複利。売上成長率 vs 販管費増加率の乖離＝PL的複利。両方で判定する）

## 8. ビジネスモデルの逆算（秘訣の命名）
（必ず独自の命名をすること。500〜800字。「なぜこの会社は儲かり続けるのか」の構造的な理由を発見する）

## 9. なぜ今注目されるのか
（200〜400字）

## 10. スタートアップへの示唆
（200〜400字。驚きのある示唆を優先する。自明な結論は価値がない）

## データソース一覧
| 資料名 | URL | 取得日 |
|---|---|---|

---

### 【出力2】Podcast収録用原稿（即興用メモ形式）

# {company_name} Podcast原稿

> 収録目安: 20〜30分

## 【オープニング】掴み（2〜3分）
- （番組の始まり方・今日のテーマ）
- （この会社を選んだ理由・今注目すべき理由）
- （リスナーへの問いかけ例）

## 【パート1】この会社、何をしている会社？（3〜4分）
- （ビジネスを一言で説明するフレーズ）
- （売上・規模感の数字）
- （直感的に「へぇ」となる事実）

## 【パート2】財務を解剖する（5〜7分）
- （PL・CF・BSで最も重要な数字とその意味）
- （競合との比較で浮かび上がること）
- （「普通の会社と何が違うか」を表す指標）
- （EBITDAマージン vs 営業利益率の乖離が何を示すか）
- （CapEx vs D&A比率から見える投資・回収フェーズ）

## 【パート3】Cash is King 3軸評価（7〜10分）
### ① 他人のカネで回す
- （CCC・前受金・タイミングの話と数値）
### ② 使ったカネが残存する
- （物理資産だけでなく人材・データ・関係性など非BS残存資産の話）
- （EBITDAマージン乖離幅とその意味）
### ③ 投じるほど効率が上がる
- （ROIC推移＝資本の複利の話）
- （売上成長率 vs 販管費増加率の乖離＝損益の複利の話）

## 【パート4】Cash is Kingの秘訣（5〜7分）
- （秘訣の命名を紹介）
- （逆説的な発見・驚きポイント）
- （なぜこの構造が強固なのか）

## 【パート5】なぜ今注目か・スタートアップへの示唆（3〜4分）
- （今のタイミングで取り上げる理由）
- （起業家・投資家が学べること）

## 【クロージング】まとめ（1〜2分）
- （今日のキーメッセージ1行）
- （次回への橋渡し）

**原稿の注意事項:**
- 箇条書きは体言止め・キーワード中心で。完全な文章にしない
- 数字は具体的に（「大きい」ではなく「売上1,000億円規模」）
- 「Cash is Kingの秘訣」の命名はレポートと同じものを使う
- 「0. サマリー」は収録直前に読む想定で、60秒以内に口頭で話せる分量に収める
""")

    return "\n".join(sections)


def save_report(
    company_name: str,
    data_dump: str,
    output_dir: Path,
    podcast_script: Optional[str] = None,  # 後方互換のため残す（未使用）
) -> Path:
    """データダンプをファイルに保存する"""
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c for c in company_name if c.isalnum() or c in "ー・_- ")
    safe_name = safe_name.strip()
    if not safe_name:
        safe_name = "report"

    filename = f"{safe_name}_cash_is_king.md"
    output_path = output_dir / filename

    output_path.write_text(data_dump, encoding="utf-8")
    print(f"\n[Reporter] ファイルを保存しました: {output_path}")
    return output_path


def build_sources_list(
    edinet_result: dict,
    ir_result: dict,
    news_data: dict,
    yf_ticker: str,
    youtube_transcripts: Optional[list[dict]] = None,
) -> list[dict]:
    """収集した全情報源のリストを構築する"""
    sources = []
    today = datetime.date.today().isoformat()

    sources.append({
        "name": f"yfinance ({yf_ticker})",
        "url": f"https://finance.yahoo.com/quote/{yf_ticker}",
        "date": today,
    })

    if edinet_result and edinet_result.get("source_url"):
        sources.append({
            "name": f"有価証券報告書（EDINET）{edinet_result.get('submit_date', '')}",
            "url": edinet_result["source_url"],
            "date": today,
        })

    if ir_result and ir_result.get("ir_url"):
        sources.append({
            "name": "IRページ",
            "url": ir_result["ir_url"],
            "date": today,
        })

    for pdf_info in (ir_result or {}).get("pdfs", []):
        url = pdf_info.get("url", "")
        sources.append({
            "name": "決算説明資料PDF",
            "url": url,
            "date": pdf_info.get("retrieved_date", today),
        })

    for category, label in [
        ("company_news", "ニュース"),
        ("interviews", "インタビュー"),
        ("industry_trends", "業界動向"),
        ("analyst_reports", "アナリストレポート"),
    ]:
        for item in news_data.get(category, [])[:10]:
            url = item.get("url", "")
            if url:
                sources.append({
                    "name": f"[{label}] {item.get('title', '')[:50]}",
                    "url": url,
                    "date": today,
                })

    for yt in (youtube_transcripts or []):
        url = yt.get("url", "")
        if url:
            sources.append({
                "name": f"[YouTube] {url}",
                "url": url,
                "date": today,
            })

    return sources
