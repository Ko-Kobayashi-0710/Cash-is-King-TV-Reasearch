"""
データ取得モジュール
yfinance・IRページ・Web検索・記事全文・YouTube字幕からデータを収集する
"""

import re
import io
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

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YT_TRANSCRIPT = True
except ImportError:
    HAS_YT_TRANSCRIPT = False


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
        col_key = str(col)[:10]
        result[col_key] = {}
        for idx in df.index:
            val = df.loc[idx, col]
            try:
                if hasattr(val, "item"):
                    val = val.item()
                if val is None or (isinstance(val, float) and (val != val)):
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

    if not ir_url:
        print(f"[IR] {company_name} のIRページを検索中...")
        ir_url = _search_ir_url(company_name)
        if not ir_url:
            result["error"] = f"{company_name} のIRページが見つかりませんでした"
            return result
        result["ir_url"] = ir_url
        print(f"[IR] IRページURL: {ir_url}")

    pdf_links = _find_pdf_links(ir_url)
    if not pdf_links:
        result["error"] = "PDFリンクが見つかりませんでした"
        return result

    print(f"[IR] PDFリンクを {len(pdf_links)} 件発見")

    priority_keywords = ["決算", "説明", "presentation", "earnings", "results", "investor"]
    selected_pdfs = _prioritize_pdfs(pdf_links, priority_keywords, max_count=3)

    for pdf_url in selected_pdfs:
        print(f"[IR] PDFを取得中: {pdf_url}")
        pdf_text = _download_and_extract_pdf(pdf_url)
        if pdf_text:
            result["pdfs"].append({
                "url": pdf_url,
                "text": pdf_text[:30000],
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
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CashIsKingResearch/1.0)"}
        resp = requests.get(pdf_url, headers=headers, timeout=60)
        if resp.status_code != 200:
            return None
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            pages_text = []
            for page in pdf.pages[:50]:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            return "\n\n".join(pages_text) if pages_text else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 記事全文スクレイピング
# ---------------------------------------------------------------------------

# ペイウォール・読み込み不要ドメインのブロックリスト
_BLOCKED_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "youtu.be",
    "nikkei.com",  # ペイウォール
}

def fetch_article_content(url: str, max_chars: int = 3000) -> Optional[str]:
    """
    URLのページ本文をスクレイピングして返す。
    ペイウォール・SNS・動画サイトはスキップ。
    """
    if not HAS_BS4:
        return None

    domain = urlparse(url).netloc.lower()
    if any(blocked in domain for blocked in _BLOCKED_DOMAINS):
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")

        # 不要タグを除去
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        # 本文候補タグを優先順位順に探す
        content = None
        for selector in ["article", "main", ".article-body", ".post-content",
                         ".entry-content", "#content", ".content"]:
            el = soup.select_one(selector)
            if el:
                content = el.get_text(separator="\n", strip=True)
                break

        if not content:
            content = soup.get_text(separator="\n", strip=True)

        # 連続する空行を整理
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        text = "\n".join(lines)

        return text[:max_chars] if text else None

    except Exception:
        return None


# ---------------------------------------------------------------------------
# 層3: Web検索 + 記事全文取得
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 10) -> list[dict]:
    """
    Web検索を実行して結果を返す。
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


def _enrich_with_full_text(results: list[dict], max_articles: int = 5) -> list[dict]:
    """
    検索結果リストに対して、上位N件の記事全文を取得して追記する。
    """
    enriched = 0
    for item in results:
        if enriched >= max_articles:
            break
        url = item.get("url", "")
        if not url:
            continue
        full_text = fetch_article_content(url, max_chars=3000)
        if full_text and len(full_text) > len(item.get("body", "")):
            item["full_text"] = full_text
            enriched += 1
    return results


def fetch_news_and_industry(company_name: str, ticker: str) -> dict:
    """
    企業・業界に関するニュース・インタビュー・ブログ・業界動向を網羅的に収集する。
    検索ヒットした記事の全文を取得する。
    """
    print(f"[Web] {company_name} の情報を網羅的に収集中...")
    result = {
        "company_news": [],
        "interviews": [],
        "industry_trends": [],
        "analyst_reports": [],
    }

    # --- 企業ニュース・決算 ---
    news_queries = [
        f"{company_name} 決算 業績 2024 2025",
        f"{company_name} M&A 事業戦略 提携",
        f"{ticker} earnings results 2024 2025",
        f"{company_name} 新サービス 新規事業",
    ]
    for query in news_queries:
        hits = web_search(query, max_results=5)
        result["company_news"].extend(hits)

    # --- CEO・経営陣インタビュー ---
    interview_queries = [
        f"{company_name} 社長 CEO インタビュー",
        f"{company_name} 代表取締役 対談 経営戦略",
        f"{company_name} founder interview note",
        f'"{company_name}" CEO interview 2024 2025',
    ]
    for query in interview_queries:
        hits = web_search(query, max_results=5)
        result["interviews"].extend(hits)

    # --- 業界・市場分析 ---
    industry_queries = [
        f"{company_name} 業界 市場規模 トレンド 2024 2025",
        f"{company_name} 競合比較 シェア",
        f"{company_name} ビジネスモデル 解説 分析",
        f"{company_name} site:note.com OR site:diamond.jp OR site:toyokeizai.net",
    ]
    for query in industry_queries:
        hits = web_search(query, max_results=5)
        result["industry_trends"].extend(hits)

    # --- アナリスト・投資家レポート ---
    analyst_queries = [
        f"{company_name} アナリスト レポート 投資判断",
        f"{company_name} 株主 投資家向け説明",
    ]
    for query in analyst_queries:
        hits = web_search(query, max_results=5)
        result["analyst_reports"].extend(hits)

    # 重複除去
    result["company_news"] = _dedupe_results(result["company_news"])
    result["interviews"] = _dedupe_results(result["interviews"])
    result["industry_trends"] = _dedupe_results(result["industry_trends"])
    result["analyst_reports"] = _dedupe_results(result["analyst_reports"])

    # 全文取得（各カテゴリ上位5件）
    print(f"[Web] 記事全文を取得中...")
    result["company_news"] = _enrich_with_full_text(result["company_news"], max_articles=5)
    result["interviews"] = _enrich_with_full_text(result["interviews"], max_articles=5)
    result["industry_trends"] = _enrich_with_full_text(result["industry_trends"], max_articles=3)
    result["analyst_reports"] = _enrich_with_full_text(result["analyst_reports"], max_articles=2)

    total = (len(result["company_news"]) + len(result["interviews"]) +
             len(result["industry_trends"]) + len(result["analyst_reports"]))
    print(f"[Web] 収集完了: ニュース{len(result['company_news'])}件 / "
          f"インタビュー{len(result['interviews'])}件 / "
          f"業界動向{len(result['industry_trends'])}件 / "
          f"アナリスト{len(result['analyst_reports'])}件")

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


# ---------------------------------------------------------------------------
# YouTube字幕取得
# ---------------------------------------------------------------------------

def fetch_youtube_transcripts(company_name: str, max_videos: int = 3) -> list[dict]:
    """
    企業関連のYouTube動画の字幕（文字起こし）を取得する。
    """
    if not HAS_YT_TRANSCRIPT:
        print("[YouTube] youtube-transcript-api が未インストールのためスキップ")
        return []

    print(f"[YouTube] {company_name} 関連動画の字幕を検索中...")

    # YouTube動画IDを検索で探す
    yt_queries = [
        f"{company_name} 決算説明 YouTube site:youtube.com",
        f"{company_name} 社長 インタビュー YouTube site:youtube.com",
        f"{company_name} IR説明会 site:youtube.com",
    ]

    video_ids = []
    yt_id_pattern = re.compile(
        r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
    )

    for query in yt_queries:
        hits = web_search(query, max_results=5)
        for hit in hits:
            url = hit.get("url", "")
            m = yt_id_pattern.search(url)
            if m:
                vid_id = m.group(1)
                if vid_id not in video_ids:
                    video_ids.append(vid_id)
        if len(video_ids) >= max_videos:
            break

    if not video_ids:
        print("[YouTube] 対象動画が見つかりませんでした")
        return []

    transcripts = []
    for vid_id in video_ids[:max_videos]:
        try:
            # 日本語優先、英語フォールバック
            transcript_list = YouTubeTranscriptApi.get_transcript(
                vid_id, languages=["ja", "en"]
            )
            text = " ".join(seg["text"] for seg in transcript_list)
            yt_url = f"https://www.youtube.com/watch?v={vid_id}"
            transcripts.append({
                "video_id": vid_id,
                "url": yt_url,
                "text": text[:5000],  # 最大5,000字
            })
            print(f"[YouTube] 字幕取得完了: {yt_url} ({len(text):,}字)")
        except Exception as e:
            print(f"[YouTube] 字幕取得失敗 ({vid_id}): {e}")

    return transcripts


# ---------------------------------------------------------------------------
# 競合ティッカー検索
# ---------------------------------------------------------------------------

def fetch_competitor_tickers(company_name: str) -> list[str]:
    """
    Web検索で競合他社のティッカーシンボルを探す（補助関数）
    """
    query = f"{company_name} 競合 同業他社 上場 ticker"
    results = web_search(query, max_results=10)
    tickers = []
    pattern = re.compile(r"\b(\d{4})\.T\b")
    for r in results:
        text = r.get("title", "") + " " + r.get("body", "")
        matches = pattern.findall(text)
        for m in matches:
            ticker_str = f"{m}.T"
            if ticker_str not in tickers:
                tickers.append(ticker_str)
    return tickers[:5]
