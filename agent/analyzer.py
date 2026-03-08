"""
財務計算・指標抽出モジュール
取得したデータからCash is King分析に必要な財務指標を計算する
"""

from typing import Optional


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _safe_get(d: dict, *keys) -> Optional[float]:
    """ネストされたdictから安全に数値を取得する"""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        # キーの部分一致検索（yfinanceのインデックスは英語）
        found = None
        for k, v in current.items():
            if key.lower() in k.lower():
                found = v
                break
        if found is None:
            return None
        current = found
    if isinstance(current, (int, float)) and current == current:  # NaN check
        return float(current)
    return None


def _get_latest_value(data: dict, metric_key: str) -> Optional[float]:
    """
    yfinanceのDataFrame変換後dictから最新期の指標値を取得する。
    columnsは日付文字列（降順）、indexは指標名。
    """
    if not data or not isinstance(data, dict):
        return None
    # errorキーがあればスキップ
    if "error" in data:
        return None
    # 最初のcolumn（最新期）を取得
    try:
        first_col = next(iter(data))
        col_data = data[first_col]
        if not isinstance(col_data, dict):
            return None
        for k, v in col_data.items():
            if metric_key.lower() in k.lower():
                if isinstance(v, (int, float)) and v == v:
                    return float(v)
    except Exception:
        pass
    return None


def _get_series(data: dict, metric_key: str, periods: int = 5) -> dict:
    """
    yfinanceのDataFrame変換後dictから複数期の指標値を時系列で取得する。
    返却: {date_str: value}
    """
    result = {}
    if not data or not isinstance(data, dict) or "error" in data:
        return result
    try:
        for date_str, col_data in list(data.items())[:periods]:
            if not isinstance(col_data, dict):
                continue
            for k, v in col_data.items():
                if metric_key.lower() in k.lower():
                    if isinstance(v, (int, float)) and v == v:
                        result[date_str] = float(v)
                    break
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# 主要財務指標の計算
# ---------------------------------------------------------------------------

def calculate_pl_metrics(yf_data: dict) -> dict:
    """PLから主要指標を計算する"""
    fin = yf_data.get("financials", {})
    info = yf_data.get("info", {})

    metrics = {}

    # 売上収益（Revenue）
    revenue_series = _get_series(fin, "Total Revenue", 5)
    if not revenue_series:
        revenue_series = _get_series(fin, "Revenue", 5)
    metrics["revenue_series"] = revenue_series

    # 売上総利益（Gross Profit）
    gross_series = _get_series(fin, "Gross Profit", 5)
    metrics["gross_profit_series"] = gross_series

    # 営業利益（Operating Income）
    op_income_series = _get_series(fin, "Operating Income", 5)
    if not op_income_series:
        op_income_series = _get_series(fin, "EBIT", 5)
    metrics["operating_income_series"] = op_income_series

    # 純利益（Net Income）
    net_income_series = _get_series(fin, "Net Income", 5)
    metrics["net_income_series"] = net_income_series

    # 粗利率の時系列計算
    gross_margin_series = {}
    for date in revenue_series:
        rev = revenue_series.get(date)
        gp = gross_series.get(date)
        if rev and gp and rev != 0:
            gross_margin_series[date] = round(gp / rev * 100, 2)
    metrics["gross_margin_series"] = gross_margin_series

    # 営業利益率の時系列計算
    op_margin_series = {}
    for date in revenue_series:
        rev = revenue_series.get(date)
        op = op_income_series.get(date)
        if rev and op and rev != 0:
            op_margin_series[date] = round(op / rev * 100, 2)
    metrics["operating_margin_series"] = op_margin_series

    # yfinance infoから補完
    metrics["operating_margin_latest"] = info.get("operatingMargins")
    metrics["profit_margin_latest"] = info.get("profitMargins")
    metrics["revenue_growth"] = info.get("revenueGrowth")

    return metrics


def calculate_bs_metrics(yf_data: dict) -> dict:
    """BSから主要指標を計算する"""
    bs = yf_data.get("balance_sheet", {})
    info = yf_data.get("info", {})

    metrics = {}

    # 最新期BSから主要項目取得
    if bs and "error" not in bs:
        first_col = next(iter(bs), None)
        if first_col:
            col = bs[first_col]

            def find_val(keyword):
                for k, v in col.items():
                    if keyword.lower() in k.lower():
                        if isinstance(v, (int, float)) and v == v:
                            return float(v)
                return None

            total_assets = find_val("Total Assets")
            total_liabilities = find_val("Total Liabilities")
            stockholders_equity = find_val("Stockholders Equity") or find_val("Total Equity")
            total_debt = find_val("Total Debt") or find_val("Long Term Debt")
            current_assets = find_val("Current Assets")
            current_liabilities = find_val("Current Liabilities")
            cash = find_val("Cash") or find_val("Cash And Cash Equivalents")
            accounts_receivable = find_val("Accounts Receivable") or find_val("Net Receivables")
            inventory = find_val("Inventory")
            accounts_payable = find_val("Accounts Payable") or find_val("Payables")
            # 前受金・デポジット関連
            deferred_revenue = find_val("Deferred Revenue")
            other_current_liabilities = find_val("Other Current Liabilities")

            metrics["total_assets"] = total_assets
            metrics["total_liabilities"] = total_liabilities
            metrics["stockholders_equity"] = stockholders_equity
            metrics["total_debt"] = total_debt
            metrics["current_assets"] = current_assets
            metrics["current_liabilities"] = current_liabilities
            metrics["cash"] = cash
            metrics["accounts_receivable"] = accounts_receivable
            metrics["inventory"] = inventory
            metrics["accounts_payable"] = accounts_payable
            metrics["deferred_revenue"] = deferred_revenue

            # D/Eレシオ
            if total_debt and stockholders_equity and stockholders_equity != 0:
                metrics["de_ratio"] = round(total_debt / stockholders_equity, 2)

            # 流動比率
            if current_assets and current_liabilities and current_liabilities != 0:
                metrics["current_ratio"] = round(current_assets / current_liabilities, 2)

    # infoから補完
    metrics["de_ratio_info"] = info.get("debtToEquity")
    metrics["current_ratio_info"] = info.get("currentRatio")

    return metrics


def calculate_cf_metrics(yf_data: dict) -> dict:
    """CFから主要指標を計算する"""
    cf = yf_data.get("cashflow", {})
    fin = yf_data.get("financials", {})
    info = yf_data.get("info", {})

    metrics = {}

    # 営業CF時系列
    op_cf_series = _get_series(cf, "Operating Cash Flow", 5)
    if not op_cf_series:
        op_cf_series = _get_series(cf, "Cash Flow From Operations", 5)
    metrics["operating_cf_series"] = op_cf_series

    # 設備投資（CapEx）時系列
    capex_series = _get_series(cf, "Capital Expenditure", 5)
    if not capex_series:
        capex_series = _get_series(cf, "Capital Expenditures", 5)
    metrics["capex_series"] = capex_series

    # FCF = 営業CF - CapEx
    fcf_series = {}
    for date in op_cf_series:
        op_cf = op_cf_series.get(date)
        capex = capex_series.get(date, 0) or 0
        # CapExは通常マイナス表記
        if op_cf is not None:
            fcf_series[date] = op_cf + capex  # capexがマイナスなのでadd
    metrics["fcf_series"] = fcf_series

    # FCFマージン = FCF / 売上
    revenue_series = _get_series(fin, "Total Revenue", 5)
    fcf_margin_series = {}
    for date in fcf_series:
        fcf = fcf_series.get(date)
        rev = revenue_series.get(date)
        if fcf is not None and rev and rev != 0:
            fcf_margin_series[date] = round(fcf / rev * 100, 2)
    metrics["fcf_margin_series"] = fcf_margin_series

    # infoから補完
    metrics["free_cashflow_info"] = info.get("freeCashflow")
    metrics["operating_cashflow_info"] = info.get("operatingCashflow")

    return metrics


def calculate_ccc(bs_metrics: dict, pl_metrics: dict) -> dict:
    """
    CCC（キャッシュコンバージョンサイクル）を計算する
    CCC = 売上債権日数 + 棚卸資産日数 - 買入債務日数
    """
    ccc_data = {}

    # 最新期の売上を使用
    latest_revenue = None
    rev_series = pl_metrics.get("revenue_series", {})
    if rev_series:
        latest_revenue = next(iter(rev_series.values()), None)

    if not latest_revenue or latest_revenue == 0:
        ccc_data["error"] = "売上データが取得できませんでした"
        return ccc_data

    ar = bs_metrics.get("accounts_receivable")
    inventory = bs_metrics.get("inventory")
    ap = bs_metrics.get("accounts_payable")

    # COGS（売上原価）の近似値として売上の60%を仮定（正確な値がない場合）
    latest_gp = None
    gp_series = pl_metrics.get("gross_profit_series", {})
    if gp_series:
        latest_gp = next(iter(gp_series.values()), None)
    cogs = latest_revenue - (latest_gp or 0) if latest_gp else latest_revenue * 0.6

    # 売上債権日数（DSO）
    if ar:
        dso = round(ar / latest_revenue * 365, 1)
        ccc_data["dso_days"] = dso

    # 棚卸資産日数（DIO）
    if inventory and cogs and cogs != 0:
        dio = round(inventory / cogs * 365, 1)
        ccc_data["dio_days"] = dio

    # 買入債務日数（DPO）
    if ap and cogs and cogs != 0:
        dpo = round(ap / cogs * 365, 1)
        ccc_data["dpo_days"] = dpo

    # CCC
    dso = ccc_data.get("dso_days", 0) or 0
    dio = ccc_data.get("dio_days", 0) or 0
    dpo = ccc_data.get("dpo_days", 0) or 0
    if dso or dio or dpo:
        ccc_data["ccc_days"] = round(dso + dio - dpo, 1)

    return ccc_data


def calculate_roic(yf_data: dict) -> dict:
    """
    ROICを計算する
    ROIC = NOPAT / 投下資本
    NOPAT = 営業利益 × (1 - 実効税率)
    投下資本 = 有利子負債 + 株主資本
    """
    result = {}
    info = yf_data.get("info", {})

    # ROEとROAはinfoから取得
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    if roe is not None:
        result["roe"] = round(roe * 100, 2)
    if roa is not None:
        result["roa"] = round(roa * 100, 2)

    # 簡易ROIC計算
    fin = yf_data.get("financials", {})
    bs = yf_data.get("balance_sheet", {})

    op_income = _get_latest_value(fin, "Operating Income")
    if not op_income:
        op_income = _get_latest_value(fin, "EBIT")

    total_debt = None
    equity = None
    if bs and "error" not in bs:
        first_col = next(iter(bs), None)
        if first_col:
            col = bs[first_col]
            for k, v in col.items():
                if "total debt" in k.lower() or "long term debt" in k.lower():
                    if isinstance(v, (int, float)) and v == v:
                        total_debt = float(v)
                elif "stockholders equity" in k.lower() or "total equity" in k.lower():
                    if isinstance(v, (int, float)) and v == v:
                        equity = float(v)

    if op_income and (total_debt is not None or equity is not None):
        invested_capital = (total_debt or 0) + (equity or 0)
        if invested_capital != 0:
            # 仮定: 実効税率30%
            nopat = op_income * 0.7
            result["roic"] = round(nopat / invested_capital * 100, 2)
            result["invested_capital"] = invested_capital

    return result


def format_financial_summary(
    company_name: str,
    ticker: str,
    yf_data: dict,
    pl_metrics: dict,
    bs_metrics: dict,
    cf_metrics: dict,
    ccc_data: dict,
    roic_data: dict,
) -> str:
    """財務サマリーをMarkdown形式の文字列にフォーマットする"""

    def fmt_bn(val, unit="億円"):
        """数値を億円または百万ドル単位で表示する"""
        if val is None:
            return "N/A"
        # yfinanceは通常JPY or USDで返す（JPYは円単位）
        return f"{val/1e8:,.1f} {unit}"

    def fmt_pct(val):
        if val is None:
            return "N/A"
        return f"{val:.1f}%"

    def fmt_num(val):
        if val is None:
            return "N/A"
        return f"{val:,.1f}"

    lines = []
    lines.append(f"## 財務データ概要: {company_name} ({ticker})")
    lines.append("")

    # PLサマリー
    lines.append("### PL（損益計算書）")
    rev_series = pl_metrics.get("revenue_series", {})
    gm_series = pl_metrics.get("gross_margin_series", {})
    om_series = pl_metrics.get("operating_margin_series", {})

    if rev_series:
        lines.append("| 期 | 売上 | 粗利率 | 営業利益率 |")
        lines.append("|---|---|---|---|")
        for date in list(rev_series.keys())[:5]:
            rev = rev_series.get(date)
            gm = gm_series.get(date)
            om = om_series.get(date)
            lines.append(f"| {date} | {fmt_bn(rev)} | {fmt_pct(gm)} | {fmt_pct(om)} |")
    else:
        lines.append("（売上データを取得できませんでした）")
    lines.append("")

    # BSサマリー
    lines.append("### BS（貸借対照表）直近期末")
    lines.append(f"- 総資産: {fmt_bn(bs_metrics.get('total_assets'))}")
    lines.append(f"- 株主資本: {fmt_bn(bs_metrics.get('stockholders_equity'))}")
    lines.append(f"- 有利子負債: {fmt_bn(bs_metrics.get('total_debt'))}")
    lines.append(f"- D/Eレシオ: {fmt_num(bs_metrics.get('de_ratio') or bs_metrics.get('de_ratio_info'))}")
    lines.append(f"- 流動比率: {fmt_num(bs_metrics.get('current_ratio') or bs_metrics.get('current_ratio_info'))}")
    lines.append(f"- 前受金・繰延収益: {fmt_bn(bs_metrics.get('deferred_revenue'))}")
    lines.append("")

    # CFサマリー
    lines.append("### CF（キャッシュフロー）")
    fcf_series = cf_metrics.get("fcf_series", {})
    fcf_margin_series = cf_metrics.get("fcf_margin_series", {})
    op_cf_series = cf_metrics.get("operating_cf_series", {})

    if op_cf_series:
        lines.append("| 期 | 営業CF | FCF | FCFマージン |")
        lines.append("|---|---|---|---|")
        for date in list(op_cf_series.keys())[:5]:
            op_cf = op_cf_series.get(date)
            fcf = fcf_series.get(date)
            fcf_margin = fcf_margin_series.get(date)
            lines.append(f"| {date} | {fmt_bn(op_cf)} | {fmt_bn(fcf)} | {fmt_pct(fcf_margin)} |")
    else:
        lines.append("（CFデータを取得できませんでした）")
    lines.append("")

    # CCC
    lines.append("### CCC（キャッシュコンバージョンサイクル）")
    if ccc_data.get("ccc_days") is not None:
        lines.append(f"- 売上債権日数（DSO）: {ccc_data.get('dso_days', 'N/A')} 日")
        lines.append(f"- 棚卸資産日数（DIO）: {ccc_data.get('dio_days', 'N/A')} 日")
        lines.append(f"- 買入債務日数（DPO）: {ccc_data.get('dpo_days', 'N/A')} 日")
        lines.append(f"- **CCC合計: {ccc_data.get('ccc_days')} 日**（マイナスほど有利）")
    else:
        lines.append("（CCCの計算に必要なデータが不足しています）")
    lines.append("")

    # ROIC
    lines.append("### 資本効率")
    lines.append(f"- ROE: {fmt_pct(roic_data.get('roe'))}")
    lines.append(f"- ROA: {fmt_pct(roic_data.get('roa'))}")
    if roic_data.get("roic"):
        lines.append(f"- ROIC（簡易）: {fmt_pct(roic_data.get('roic'))}")
    lines.append("")

    return "\n".join(lines)


def build_competitor_comparison(
    target_name: str,
    target_data: dict,
    competitors: dict,
) -> str:
    """競合比較テーブルをMarkdown形式で生成する"""
    lines = []
    lines.append("### 競合比較テーブル")
    lines.append("")
    lines.append("| 指標 | " + target_name + " | " + " | ".join(competitors.keys()) + " |")
    lines.append("|---|" + "---|" * (1 + len(competitors)))

    def get_info_val(yf_d: dict, key: str) -> str:
        info = yf_d.get("info", {})
        val = info.get(key)
        if val is None:
            return "N/A"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)

    def get_margin(yf_d: dict, key: str) -> str:
        info = yf_d.get("info", {})
        val = info.get(key)
        if val is None:
            return "N/A"
        return f"{val*100:.1f}%"

    metrics_to_show = [
        ("営業利益率", "operatingMargins", get_margin),
        ("純利益率", "profitMargins", get_margin),
        ("ROE", "returnOnEquity", get_margin),
        ("ROA", "returnOnAssets", get_margin),
        ("D/Eレシオ", "debtToEquity", get_info_val),
        ("流動比率", "currentRatio", get_info_val),
    ]

    for metric_name, key, formatter in metrics_to_show:
        row = [metric_name, formatter(target_data, key)]
        for comp_data in competitors.values():
            row.append(formatter(comp_data, key))
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)
