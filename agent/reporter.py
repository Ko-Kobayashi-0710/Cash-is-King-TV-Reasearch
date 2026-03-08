"""
LLM呼び出し・レポート生成モジュール
Claude API（claude-opus-4-6）を使ってCash is King分析レポートを生成する
"""

import os
import json
import datetime
from pathlib import Path
from typing import Optional

import anthropic


SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.md"


def _load_system_prompt() -> str:
    """システムプロンプトをファイルから読み込む"""
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return "あなたはポッドキャスト「Cash is King TV」のリサーチャーです。"


def _build_analysis_prompt(
    company_name: str,
    ticker: str,
    financial_summary: str,
    edinet_text: Optional[str],
    ir_pdfs: list[dict],
    news_data: dict,
    competitor_comparison: str,
    competitors_raw: dict,
    sources: list[dict],
) -> str:
    """LLMへの分析依頼プロンプトを構築する"""

    sections = []
    sections.append(f"# 分析対象: {company_name}（ティッカー: {ticker}）")
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
    if edinet_text:
        sections.append("## 有価証券報告書（EDINET）からの抜粋")
        sections.append(edinet_text[:15000])  # 最大15,000字
        sections.append("")

    # IRページのPDF
    if ir_pdfs:
        sections.append("## IRページ・決算説明資料からの抜粋")
        for pdf_info in ir_pdfs[:2]:
            url = pdf_info.get("url", "")
            text = pdf_info.get("text", "")
            sections.append(f"### 出典: {url}")
            sections.append(text[:8000])  # 各PDF最大8,000字
            sections.append("")

    # ニュース・業界動向
    news_items = news_data.get("company_news", [])[:10]
    industry_items = news_data.get("industry_trends", [])[:5]

    if news_items:
        sections.append("## 直近のニュース・動向")
        for item in news_items:
            title = item.get("title", "")
            url = item.get("url", "")
            body = item.get("body", "")[:300]
            sections.append(f"- **{title}** ({url})\n  {body}")
        sections.append("")

    if industry_items:
        sections.append("## 業界動向")
        for item in industry_items:
            title = item.get("title", "")
            url = item.get("url", "")
            body = item.get("body", "")[:300]
            sections.append(f"- **{title}** ({url})\n  {body}")
        sections.append("")

    # 参照URL一覧（後で参照資料テーブルに使う）
    sections.append("## 収集済み参照資料")
    for s in sources:
        sections.append(f"- {s.get('name', '')}: {s.get('url', '')} ({s.get('date', '')})")
    sections.append("")

    # 分析依頼
    sections.append("---")
    sections.append("")
    sections.append("## 分析レポート生成依頼")
    sections.append("")
    sections.append(f"""
上記のデータをもとに、{company_name} の Cash is King 分析レポートを以下のフォーマットで生成してください。

**重要な指示:**
1. ファクトなき考察は書かない。必ず数字か一次情報に根拠を置く
2. 「儲かっている」で終わらない。なぜ儲かるのかの構造を言語化する
3. 驚きのある考察を必ず1つ入れる（「実は○○だった」という逆説的発見）
4. 比較なき分析は弱い。必ず競合・類似業態と比べて相対化する
5. 「Cash is Kingの秘訣」は必ず独自の命名をする（例：「撤去できない資産が生む二重ロック」）
6. データが取得できなかった項目は推測ではなく「データ未取得」と明記する
7. 推測・仮説は「〜と考えられる」と明示し、ファクトと混在させない

**出力フォーマット（必ずこの構造で）:**

```markdown
# {company_name} Cash is King分析

## 1. 外観
（この会社が何をしている会社か、3〜5行で）

## 2. 財務サマリー
（PL・BS・CFの主要指標。比較対象との横並び表）

## 3. Cash is King 3軸評価
| 軸 | 評価 | 根拠 |
|---|---|---|
| ① 他人のカネで回す | ◎/○/△/× | 具体的数値 |
| ② 使ったカネが残存する | ◎/○/△/× | 具体的数値 |
| ③ 投じるほど効率が上がる | ◎/○/△/× | 具体的数値 |

（各軸の詳細考察。各軸300〜500字）

## 4. 競合・類似ビジネスとの比較
（表形式＋考察500字以上）

## 5. Cash is Kingの秘訣
（必ず独自の命名をすること。例：「XXXが生むYYY効果」）
（ここが番組のメインコンテンツ。最も驚きのある考察を500〜800字で）

## 6. なぜ今注目されるのか
（M&A・IPO・業界変化・政策変更などのフック。200〜400字）

## 7. スタートアップへの示唆
（このビジネス構造から起業家・投資家が学べること。200〜400字）

## 参照資料
| 資料名 | URL | 取得日 |
|---|---|---|
（収集した全URLを記載）
```
""")

    return "\n".join(sections)


def generate_report(
    company_name: str,
    ticker: str,
    financial_summary: str,
    edinet_result: dict,
    ir_result: dict,
    news_data: dict,
    competitor_comparison: str,
    competitors_raw: dict,
    sources: list[dict],
) -> str:
    """
    Claude APIを呼び出してCash is King分析レポートを生成する。
    ストリーミングで出力し、完成したMarkdown文字列を返す。
    """
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "")
    )

    system_prompt = _load_system_prompt()

    edinet_text = edinet_result.get("text") if edinet_result else None
    ir_pdfs = ir_result.get("pdfs", []) if ir_result else []

    user_prompt = _build_analysis_prompt(
        company_name=company_name,
        ticker=ticker,
        financial_summary=financial_summary,
        edinet_text=edinet_text,
        ir_pdfs=ir_pdfs,
        news_data=news_data,
        competitor_comparison=competitor_comparison,
        competitors_raw=competitors_raw,
        sources=sources,
    )

    print(f"\n[Reporter] Claude API ({company_name}) にレポート生成を依頼中...")
    print("[Reporter] ストリーミング出力開始:\n")
    print("=" * 60)

    report_text = ""

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                report_text += text

        final_message = stream.get_final_message()
        usage = final_message.usage
        print(f"\n\n[Reporter] 完了 - 入力: {usage.input_tokens} tokens, 出力: {usage.output_tokens} tokens")

    except anthropic.APIError as e:
        error_msg = f"\n\n⚠️ Claude API エラー: {e}\n\nデータ収集は完了していますが、レポート生成に失敗しました。"
        print(error_msg)
        report_text = error_msg

    print("=" * 60)
    return report_text


def save_report(company_name: str, report_text: str, output_dir: Path) -> Path:
    """レポートをファイルに保存する"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # ファイル名に使えない文字を除去
    safe_name = "".join(c for c in company_name if c.isalnum() or c in "ー・_- ")
    safe_name = safe_name.strip()
    if not safe_name:
        safe_name = "report"

    filename = f"{safe_name}_cash_is_king.md"
    output_path = output_dir / filename

    output_path.write_text(report_text, encoding="utf-8")
    print(f"\n[Reporter] レポートを保存しました: {output_path}")
    return output_path


def build_sources_list(
    edinet_result: dict,
    ir_result: dict,
    news_data: dict,
    yf_ticker: str,
) -> list[dict]:
    """収集した全情報源のリストを構築する"""
    sources = []
    today = datetime.date.today().isoformat()

    # yfinance
    sources.append({
        "name": f"yfinance ({yf_ticker})",
        "url": f"https://finance.yahoo.com/quote/{yf_ticker}",
        "date": today,
    })

    # EDINET
    if edinet_result and edinet_result.get("source_url"):
        sources.append({
            "name": f"有価証券報告書（EDINET）{edinet_result.get('submit_date', '')}",
            "url": edinet_result["source_url"],
            "date": today,
        })

    # IRページ
    if ir_result and ir_result.get("ir_url"):
        sources.append({
            "name": "IRページ",
            "url": ir_result["ir_url"],
            "date": today,
        })

    # IRページのPDF
    for pdf_info in (ir_result or {}).get("pdfs", []):
        url = pdf_info.get("url", "")
        sources.append({
            "name": f"決算説明資料PDF",
            "url": url,
            "date": pdf_info.get("retrieved_date", today),
        })

    # ニュース
    for item in news_data.get("company_news", [])[:10]:
        url = item.get("url", "")
        if url:
            sources.append({
                "name": item.get("title", "ニュース記事")[:50],
                "url": url,
                "date": today,
            })

    return sources
