"""
データ取得モジュール
yfinance・IRページ・Web検索からデータを収集する
"""

import re
import datetime
import requests
from typing import Optional
from urllib.parse import urljoin, urlparse

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from duckduckgo_search import DDGS
    HAS_DDG = True
except ImportError:
    HAS_DDG = False


# ---------------------------------------------------------------------------
# 層1: yfinance
# ---------------------------------------------------------------------------

def fetch_yfinance_data(ticker: str) -> dict:
    """
    yfinanceで企業の財務データを取得する。
    返却値は各データフレームをdict形式に変換したもの。
    """
    if not HAS_YFINANCE:
        return {"error": "yfinance がインストールされていません"}

    print(f"[yfinance] {ticker} のデータを取得中...")
    result = {"ticker": ticker, "error": None}

    try:
        t = yf.Ticker(ticker)

        # 企業基本情報
        try:
            info = t.info or {}
            result["info"] = {
                "longName": info.get("longName", ""),
                "longBusinessSummary": info.get("longBusinessSummary", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "country": info.get("country", ""),
                "website": info.get("website", ""),
                "fullTimeEmployees": info.get("fullTimeEmployees"),
                "marketCap": info.get("marketCap"),
                "enterpriseValue": info.get("enterpriseValue"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "priceToBook": info.get("priceToBook"),
                "dividendYield": info.get("dividendYield"),
                "returnOnEquity": info.get("returnOnEquity"),
                "returnOnAssets": info.get("returnOnAssets"),
                "operatingMargins": info.get("operatingMargins"),
                "profitMargins": info.get("profitMargins"),
                "revenueGrowth": info.get("revenueGrowth"),
                "currentRatio": info.get("currentRatio"),
                "debtToEquity": info.get("debtToEquity"),
                "freeCashflow": info.get("freeCashflow"),
                "operatingCashflow": info.get("operatingCashflow"),
            }
        except Exception as e:
            result["info"] = {"error": str(e)}

        # PL（年次）
        try:
            fin = t.financials
            if fin is not None and not fin.empty:
                result["financials"] = _df_to_dict(fin)
        except Exception as e:
            result["financials"] = {"error": str(e)}

        # PL（四半期）
        try:
            qfin = t.quarterly_financials
            if qfin is not None and not qfin.empty:
                result["quarterly_financials"] = _df_to_dict(qfin)
        except Exception as e:
            result["quarterly_financials"] = {"error": str(e)}

        # BS
        try:
            bs = t.balance_sheet
            if bs is not None and not bs.empty:
                result["balance_sheet"] = _df_to_dict(bs)
        except Exception as e:
            result["balance_sheet"] = {"error": str(e)}

        # CF
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                result["cashflow"] = _df_to_dict(cf)
        except Exception as e:
            result["cashflow"] = {"error": str(e)}

        print(f"[yfinance] {ticker} のデータ取得完了")

    except Exception as e:
        result["error"] = str(e)

    return result


def _df_to_dict(df) -> dict:
    """pandas DataFrameをJSONシリアライズ可能なdictに変換する"""
    result = {}
    for col in df.columns:
        col_key = str(col)[:10]  # 日付を文字列に
        result[col_key] = {}
        for idx in df.index:
            val = df.loc[idx, col]
            try:
                if hasattr(val, "item"):
                    val = val.item()
                if val is None or (isinstance(val, float) and (val != val)):  # NaN check
                    val = None
                result[col_key][str(idx)] = val
            except Exception:
                result[col_key][str(idx)] = None
    return result


def fetch_multiple_tickers(tickers: list[str]) -> dict:
    """複数のティッカーのyfinanceデータを取得する（競合比較用）"""
    results = {}
    for ticker in tickers:
        results[ticker] = fetch_yfinance_data(ticker)
    return results


# ---------------------------------------------------------------------------
# 層3: IRページ スクレイピング
# ---------------------------------------------------------------------------

def fetch_ir_page_and_pdfs(company_name: str, ir_url: Optional[str] = None) -> dict:
    """
    企業のIRページから決算説明資料PDFを取得してテキスト抽出する。
    ir_urlが指定されていない場合はWeb検索でIRページを探す。
    """
    result = {
        "ir_url": ir_url,
        "pdfs": [],
        "error": None,
    }

    if not HAS_BS4:
        result["error"] = "BeautifulSoup4 がインストールされていません"
        return result

    # IRページURLを検索で特定
    if not ir_url:
        print(f"[IR] {company_name} のIRページを検索中...")
        ir_url = _search_ir_url(company_name)
        if not ir_url:
            result["error"] = f"{company_name} のIRページが見つかりませんでした"
            return result
        result["ir_url"] = ir_url
        print(f"[IR] IRページURL: {ir_url}")

    # IRページをスクレイピングしてPDFリンクを探す
    pdf_links = _find_pdf_links(ir_url)
    if not pdf_links:
        result["error"] = "PDFリンクが見つかりませんでした"
        return result

    print(f"[IR] PDFリンクを {len(pdf_links)} 件発見")

    # 決算関連PDFを優先して最大3件取得
    priority_keywords = ["決算", "説明", "presentation", "earnings", "results", "investor"]
    selected_pdfs = _prioritize_pdfs(pdf_links, priority_keywords, max_count=3)

    for pdf_url in selected_pdfs:
        print(f"[IR] PDFを取得中: {pdf_url}")
        pdf_text = _download_and_extract_pdf(pdf_url)
        if pdf_text:
            result["pdfs"].append({
                "url": pdf_url,
                "text": pdf_text[:30000],  # 最大30,000字
                "retrieved_date": datetime.date.today().isoformat(),
            })

    return result


def _search_ir_url(company_name: str) -> Optional[str]:
    """Web検索で企業のIRページURLを探す"""
    queries = [
        f"{company_name} IR investor relations site:jp",
        f"{company_name} 投資家情報 決算",
    ]
    for query in queries:
        results = web_search(query, max_results=5)
        for r in results:
            url = r.get("url", "")
            snippet = r.get("body", "").lower()
            title = r.get("title", "").lower()
            if any(kw in url.lower() or kw in title or kw in snippet
                   for kw in ["ir.", "/ir/", "investor", "投資家", "株主"]):
                return url
    return None


def _find_pdf_links(page_url: str) -> list[str]:
    """指定URLのページからPDFリンクを抽出する"""
    if not HAS_BS4:
        return []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CashIsKingResearch/1.0)"}
        resp = requests.get(page_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.content, "html.parser")
        pdf_links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.lower().endswith(".pdf"):
                full_url = urljoin(page_url, href)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
        return pdf_links
    except Exception:
        return []


def _prioritize_pdfs(pdf_links: list[str], keywords: list[str], max_count: int) -> list[str]:
    """キーワードに基づいてPDFを優先順位付けする"""
    scored = []
    for url in pdf_links:
        url_lower = url.lower()
        score = sum(1 for kw in keywords if kw.lower() in url_lower)
        scored.append((score, url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in scored[:max_count]]


def _download_and_extract_pdf(pdf_url: str) -> Optional[str]:
    """PDFをダウンロードしてテキスト抽出する"""
    if not HAS_PDFPLUMBER:
        return None
    try:
        import io
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CashIsKingResearch/1.0)"}
        resp = requests.get(pdf_url, headers=headers, timeout=60)
        if resp.status_code != 200:
            return None
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            pages_text = []
            for page in pdf.pages[:50]:  # 最大50ページ
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            return "\n\n".join(pages_text) if pages_text else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 層3: Web検索
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 10) -> list[dict]:
    """
    Web検索を実行して結果を返す。
    duckduckgo-searchが利用可能な場合はそれを使い、
    なければrequests+スクレイピングでフォールバック。
    """
    results = []

    if HAS_DDG:
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "body": r.get("body", ""),
                    })
            return results
        except Exception:
            pass

    # フォールバック: DuckDuckGo HTML検索
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CashIsKingResearch/1.0)"}
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200 and HAS_BS4:
            soup = BeautifulSoup(resp.content, "html.parser")
            for result_div in soup.find_all("div", class_="result")[:max_results]:
                title_tag = result_div.find("a", class_="result__a")
                snippet_tag = result_div.find("a", class_="result__snippet")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "url": title_tag.get("href", ""),
                        "body": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    })
    except Exception:
        pass

    return results


def fetch_news_and_industry(company_name: str, ticker: str) -> dict:
    """
    企業・業界に関する直近1年のニュースと業界動向を収集する
    """
    print(f"[Web] {company_name} のニュース・業界動向を検索中...")
    result = {
        "company_news": [],
        "industry_trends": [],
        "competitor_info": [],
    }

    # 企業ニュース
    queries_news = [
        f"{company_name} 決算 2024 2025",
        f"{company_name} M&A 事業戦略",
        f"{ticker} earnings results",
    ]
    for query in queries_news[:2]:
        news = web_search(query, max_results=5)
        result["company_news"].extend(news)

    # 業界動向
    queries_industry = [
        f"{company_name} 業界 市場規模 トレンド 2024 2025",
    ]
    for query in queries_industry:
        trends = web_search(query, max_results=5)
        result["industry_trends"].extend(trends)

    # 重複除去
    result["company_news"] = _dedupe_results(result["company_news"])
    result["industry_trends"] = _dedupe_results(result["industry_trends"])

    return result


def _dedupe_results(results: list[dict]) -> list[dict]:
    """URL重複を除去する"""
    seen = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
    return unique


def fetch_competitor_tickers(company_name: str) -> list[str]:
    """
    Web検索で競合他社のティッカーシンボルを探す（補助関数）
    """
    query = f"{company_name} 競合 同業他社 上場 ticker"
    results = web_search(query, max_results=10)
    tickers = []
    # 日本株ティッカーパターン（4桁数字.T）を抽出
    pattern = re.compile(r"\b(\d{4})\.T\b")
    for r in results:
        text = r.get("title", "") + " " + r.get("body", "")
        matches = pattern.findall(text)
        for m in matches:
            ticker_str = f"{m}.T"
            if ticker_str not in tickers:
                tickers.append(ticker_str)
    return tickers[:5]  # 最大5社
