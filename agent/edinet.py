"""
EDINET APIv2 専用モジュール
有価証券報告書の取得・テキスト抽出を担当する
"""

import os
import io
import zipfile
import datetime
import requests
from typing import Optional


EDINET_API_BASE = "https://disclosure.edinet-fsa.go.jp/api/v2"


def _get_api_key() -> str:
    key = os.environ.get("EDINET_API_KEY", "")
    return key


def search_edinet_code(company_name: str) -> Optional[str]:
    """
    企業名からEDINETコードを検索する。
    EDINET全文書リストAPIを使って企業名に部分一致するコードを返す。
    見つからない場合はNoneを返す。
    """
    # 直近30日分のドキュメントリストを走査して企業名を探す
    api_key = _get_api_key()
    today = datetime.date.today()
    for days_back in range(0, 365, 30):
        target_date = today - datetime.timedelta(days=days_back)
        date_str = target_date.strftime("%Y-%m-%d")
        params = {"date": date_str, "type": 2}
        if api_key:
            params["Subscription-Key"] = api_key
        try:
            resp = requests.get(
                f"{EDINET_API_BASE}/documents.json",
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for doc in data.get("results", []):
                if company_name in (doc.get("filerName") or ""):
                    return doc.get("edinetCode")
        except Exception:
            continue
    return None


def get_latest_securities_report(edinet_code: str) -> Optional[dict]:
    """
    指定されたEDINETコードの直近の有価証券報告書メタデータを返す。
    docID・提出日・書類名などを含むdictを返す。見つからない場合はNone。
    """
    api_key = _get_api_key()
    today = datetime.date.today()
    # 過去2年分のドキュメントリストを走査
    for days_back in range(0, 730, 1):
        target_date = today - datetime.timedelta(days=days_back)
        date_str = target_date.strftime("%Y-%m-%d")
        params = {"date": date_str, "type": 2}
        if api_key:
            params["Subscription-Key"] = api_key
        try:
            resp = requests.get(
                f"{EDINET_API_BASE}/documents.json",
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for doc in data.get("results", []):
                if doc.get("edinetCode") == edinet_code and doc.get("docTypeCode") == "120":
                    return doc
        except Exception:
            continue
    return None


def download_document_pdf(doc_id: str) -> Optional[bytes]:
    """
    指定されたdocIDのPDF書類（type=2: PDF）をダウンロードしてbytesで返す。
    失敗した場合はNoneを返す。
    """
    api_key = _get_api_key()
    params = {"type": 2}
    if api_key:
        params["Subscription-Key"] = api_key
    try:
        resp = requests.get(
            f"{EDINET_API_BASE}/documents/{doc_id}",
            params=params,
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def download_document_xbrl(doc_id: str) -> Optional[str]:
    """
    指定されたdocIDのXBRL書類（type=1: ZIP）をダウンロードし、
    主要テキストを抽出して文字列で返す。失敗した場合はNoneを返す。
    """
    api_key = _get_api_key()
    params = {"type": 1}
    if api_key:
        params["Subscription-Key"] = api_key
    try:
        resp = requests.get(
            f"{EDINET_API_BASE}/documents/{doc_id}",
            params=params,
            timeout=120,
        )
        if resp.status_code != 200:
            return None
        # ZIPを展開してXBRLやtxtを抽出
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            texts = []
            for name in z.namelist():
                if name.endswith(".xbrl") or name.endswith(".txt") or name.endswith(".xml"):
                    try:
                        raw = z.read(name).decode("utf-8", errors="ignore")
                        # タグを除去して本文のみ抽出（簡易）
                        import re
                        clean = re.sub(r"<[^>]+>", " ", raw)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if len(clean) > 100:
                            texts.append(clean[:50000])  # 各ファイル最大50,000字
                    except Exception:
                        continue
            if texts:
                return "\n\n---\n\n".join(texts)[:200000]
    except Exception:
        pass
    return None


def fetch_securities_report_text(company_name: str, edinet_code: Optional[str] = None) -> dict:
    """
    企業名またはEDINETコードから有価証券報告書のテキストを取得する。
    返却値:
        {
            "edinet_code": str or None,
            "doc_id": str or None,
            "submit_date": str or None,
            "doc_description": str or None,
            "text": str or None,
            "source_url": str or None,
            "error": str or None,
        }
    """
    result = {
        "edinet_code": edinet_code,
        "doc_id": None,
        "submit_date": None,
        "doc_description": None,
        "text": None,
        "source_url": None,
        "error": None,
    }

    # EDINETコード未指定の場合は検索
    if not edinet_code:
        print(f"[EDINET] {company_name} のEDINETコードを検索中...")
        edinet_code = search_edinet_code(company_name)
        if not edinet_code:
            result["error"] = f"{company_name} のEDINETコードが見つかりませんでした"
            return result
        result["edinet_code"] = edinet_code
        print(f"[EDINET] EDINETコード: {edinet_code}")

    # 最新の有価証券報告書を取得
    print(f"[EDINET] 有価証券報告書を検索中 (EDINETコード: {edinet_code})...")
    doc_meta = get_latest_securities_report(edinet_code)
    if not doc_meta:
        result["error"] = f"有価証券報告書が見つかりませんでした (EDINETコード: {edinet_code})"
        return result

    doc_id = doc_meta.get("docID")
    result["doc_id"] = doc_id
    result["submit_date"] = doc_meta.get("submitDateTime", "")[:10]
    result["doc_description"] = doc_meta.get("docDescription", "有価証券報告書")
    result["source_url"] = f"https://disclosure.edinet-fsa.go.jp/E01EW/BLMainController.jsp?uji.verb=W1E62071CXP001Action&uji.bean=ee.bean.parent.EEParentBean&TID=W1E62071CXP001&PID=W1E62071CXP001&SESSIONKEY=&lgKbn=2&dflg=0&iflg=0&dispKbn=1&defKey={doc_id}"
    print(f"[EDINET] 書類ID: {doc_id}, 提出日: {result['submit_date']}")

    # XBRLでテキスト取得を試みる
    print("[EDINET] XBRLからテキスト抽出中...")
    text = download_document_xbrl(doc_id)
    if text:
        result["text"] = text
        return result

    # XBRLが失敗したらPDF取得（pdfplumberで後処理）
    print("[EDINET] XBRL失敗。PDFをダウンロード中...")
    pdf_bytes = download_document_pdf(doc_id)
    if pdf_bytes:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages[:100]:  # 最大100ページ
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                result["text"] = "\n\n".join(pages_text)[:200000]
            return result
        except Exception as e:
            result["error"] = f"PDF解析エラー: {e}"
            return result

    result["error"] = "XBRLもPDFも取得できませんでした"
    return result
