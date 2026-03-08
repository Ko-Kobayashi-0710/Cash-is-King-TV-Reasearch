#!/usr/bin/env python3
"""
Cash is King TV リサーチエージェント
エントリーポイント

使い方:
    python research.py --company "杉孝ホールディングス" --ticker "XXXX.T"
    python research.py --company "トヨタ自動車" --ticker "7203.T"
    python research.py --company "マネーフォワード" --ticker "3994.T" --edinet-code "E34947"
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# プロジェクトルートをPATHに追加
sys.path.insert(0, str(Path(__file__).parent))

from agent.fetcher import (
    fetch_yfinance_data,
    fetch_multiple_tickers,
    fetch_ir_page_and_pdfs,
    fetch_news_and_industry,
    fetch_competitor_tickers,
)
from agent.edinet import fetch_securities_report_text
from agent.analyzer import (
    calculate_pl_metrics,
    calculate_bs_metrics,
    calculate_cf_metrics,
    calculate_ccc,
    calculate_roic,
    format_financial_summary,
    build_competitor_comparison,
)
from agent.reporter import (
    generate_report,
    save_report,
    build_sources_list,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cash is King TV リサーチエージェント",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python research.py --company "杉孝ホールディングス" --ticker "XXXX.T"
  python research.py --company "トヨタ自動車" --ticker "7203.T"
  python research.py --company "マネーフォワード" --ticker "3994.T" --edinet-code "E34947"
  python research.py --company "コインチェック" --ticker "1491.T" --competitors "7177.T,8473.T"
  python research.py --company "Tesla" --ticker "TSLA" --ir-url "https://ir.tesla.com"
        """,
    )
    parser.add_argument(
        "--company", "-c",
        required=True,
        help="企業名（例: 杉孝ホールディングス）",
    )
    parser.add_argument(
        "--ticker", "-t",
        required=True,
        help="ティッカーシンボル（例: 7203.T）",
    )
    parser.add_argument(
        "--edinet-code",
        default=None,
        help="EDINETコード（省略時は企業名で自動検索）",
    )
    parser.add_argument(
        "--ir-url",
        default=None,
        help="IRページURL（省略時は自動検索）",
    )
    parser.add_argument(
        "--competitors",
        default=None,
        help="競合他社ティッカー（カンマ区切り、例: 7270.T,7267.T）",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="レポート出力ディレクトリ（デフォルト: output）",
    )
    parser.add_argument(
        "--skip-edinet",
        action="store_true",
        help="EDINET取得をスキップする",
    )
    parser.add_argument(
        "--skip-ir",
        action="store_true",
        help="IRページ取得をスキップする",
    )
    return parser.parse_args()


def check_api_keys():
    """必要なAPIキーの確認"""
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"⚠️  以下のAPIキーが設定されていません: {', '.join(missing)}")
        print("   .env ファイルに設定してください。")
        if "ANTHROPIC_API_KEY" in missing:
            sys.exit(1)


def main():
    args = parse_args()
    check_api_keys()

    company_name = args.company
    ticker = args.ticker
    output_dir = Path(args.output_dir)

    print(f"\n{'='*60}")
    print(f"Cash is King TV リサーチエージェント")
    print(f"企業: {company_name} ({ticker})")
    print(f"{'='*60}\n")

    # -------------------------------------------------------------------
    # STEP 1: データ収集
    # -------------------------------------------------------------------
    print("【STEP 1】データ収集開始\n")

    # 1-1. yfinanceでターゲット企業データ取得
    print("--- 1-1. yfinance: ターゲット企業 ---")
    yf_data = fetch_yfinance_data(ticker)

    # 1-2. 競合企業のyfinanceデータ取得
    print("\n--- 1-2. yfinance: 競合企業 ---")
    competitor_tickers = []
    if args.competitors:
        competitor_tickers = [t.strip() for t in args.competitors.split(",") if t.strip()]
    else:
        # Web検索で競合ティッカーを探す
        print(f"[競合検索] {company_name} の競合企業を検索中...")
        found = fetch_competitor_tickers(company_name)
        if found:
            # ターゲット自身を除外
            competitor_tickers = [t for t in found if t != ticker][:3]
            print(f"[競合検索] 発見: {competitor_tickers}")
        else:
            # デフォルト比較対象: マネーフォワード、トヨタ
            print("[競合検索] 見つからなかったためデフォルト比較対象を使用")
            competitor_tickers = ["3994.T", "7203.T"]

    competitors_raw = {}
    if competitor_tickers:
        competitors_raw = fetch_multiple_tickers(competitor_tickers)

    # 1-3. EDINETで有価証券報告書を取得
    edinet_result = {}
    if not args.skip_edinet:
        print("\n--- 1-3. EDINET: 有価証券報告書 ---")
        edinet_result = fetch_securities_report_text(
            company_name=company_name,
            edinet_code=args.edinet_code,
        )
        if edinet_result.get("error"):
            print(f"[EDINET] ⚠️  {edinet_result['error']}")
        else:
            text_len = len(edinet_result.get("text") or "")
            print(f"[EDINET] テキスト抽出完了: {text_len:,} 文字")
    else:
        print("\n--- 1-3. EDINET: スキップ ---")

    # 1-4. IRページから決算説明資料PDFを取得
    ir_result = {}
    if not args.skip_ir:
        print("\n--- 1-4. IRページ: 決算説明資料PDF ---")
        ir_result = fetch_ir_page_and_pdfs(
            company_name=company_name,
            ir_url=args.ir_url,
        )
        if ir_result.get("error"):
            print(f"[IR] ⚠️  {ir_result['error']}")
        else:
            pdf_count = len(ir_result.get("pdfs", []))
            print(f"[IR] PDF取得完了: {pdf_count} 件")
    else:
        print("\n--- 1-4. IRページ: スキップ ---")

    # 1-5. Web検索でニュース・業界動向を収集
    print("\n--- 1-5. Web検索: ニュース・業界動向 ---")
    news_data = fetch_news_and_industry(company_name, ticker)
    print(f"[Web] ニュース: {len(news_data.get('company_news', []))} 件, 業界動向: {len(news_data.get('industry_trends', []))} 件")

    # -------------------------------------------------------------------
    # STEP 2: 財務構造の解剖
    # -------------------------------------------------------------------
    print("\n【STEP 2】財務指標計算\n")

    pl_metrics = calculate_pl_metrics(yf_data)
    bs_metrics = calculate_bs_metrics(yf_data)
    cf_metrics = calculate_cf_metrics(yf_data)
    ccc_data = calculate_ccc(bs_metrics, pl_metrics)
    roic_data = calculate_roic(yf_data)

    # 財務サマリー文字列生成
    financial_summary = format_financial_summary(
        company_name=company_name,
        ticker=ticker,
        yf_data=yf_data,
        pl_metrics=pl_metrics,
        bs_metrics=bs_metrics,
        cf_metrics=cf_metrics,
        ccc_data=ccc_data,
        roic_data=roic_data,
    )

    # 競合比較テーブル生成
    competitor_comparison = ""
    if competitors_raw:
        # 競合社名をティッカーから取得
        comp_names = {}
        for comp_ticker, comp_data in competitors_raw.items():
            info = comp_data.get("info", {})
            name = info.get("longName") or info.get("shortName") or comp_ticker
            comp_names[name] = comp_data
        competitor_comparison = build_competitor_comparison(
            target_name=company_name,
            target_data=yf_data,
            competitors=comp_names,
        )

    # -------------------------------------------------------------------
    # STEP 3-5: 参照資料リスト構築 → LLMでレポート生成
    # -------------------------------------------------------------------
    print("\n【STEP 3-5】Cash is King分析レポート生成\n")

    sources = build_sources_list(
        edinet_result=edinet_result,
        ir_result=ir_result,
        news_data=news_data,
        yf_ticker=ticker,
    )

    report_text = generate_report(
        company_name=company_name,
        ticker=ticker,
        financial_summary=financial_summary,
        edinet_result=edinet_result,
        ir_result=ir_result,
        news_data=news_data,
        competitor_comparison=competitor_comparison,
        competitors_raw=competitors_raw,
        sources=sources,
    )

    # -------------------------------------------------------------------
    # レポート保存
    # -------------------------------------------------------------------
    output_path = save_report(company_name, report_text, output_dir)
    print(f"\n{'='*60}")
    print(f"✅ 分析完了!")
    print(f"   レポート: {output_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
