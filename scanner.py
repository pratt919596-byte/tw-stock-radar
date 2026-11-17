from datetime import datetime, timedelta, timezone
import time
import pandas as pd
import requests
import yfinance as yf


def get_all_tw_stocks():
    """取得台股上市 (.TW) 與上櫃 (.TWO) 所有普通股代號"""
    stocks = {}
    # 上市股票
    try:
        res_twse = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=15,
        ).json()
        for item in res_twse:
            code = str(item.get("Code", "")).strip()
            name = str(item.get("Name", "")).strip()
            if len(code) == 4 and code.isdigit() and not code.startswith("00"):
                stocks[f"{code}.TW"] = (name, "上市")
    except Exception as e:
        print(f"上市清單讀取異常: {e}")

    # 上櫃股票
    try:
        res_tpex = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=15,
        ).json()
        for item in res_tpex:
            code = str(item.get("SecuritiesCompanyCode", "")).strip()
            name = str(item.get("CompanyName", "")).strip()
            if len(code) == 4 and code.isdigit() and not code.startswith("00"):
                stocks[f"{code}.TWO"] = (name, "上櫃")
    except Exception as e:
        print(f"上櫃清單讀取異常: {e}")

    return stocks


def check_strategy(df):
    """檢查單一股票是否符合三大起漲突破條件"""
    if len(df) < 35:
        return None

    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()

    # 1. 20日均線與布林通道 (20, 2)
    ma20 = close.rolling(window=20).mean()
    std20 = close.rolling(window=20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    bb_width = (bb_upper - bb_lower) / ma20

    # 2. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_hist = dif - dea

    c_today, c_yest = float(close.iloc[-1]), float(close.iloc[-2])
    ma20_today, ma20_yest = float(ma20.iloc[-1]), float(ma20.iloc[-2])
    bb_today, bb_yest = float(bb_width.iloc[-1]), float(bb_width.iloc[-2])
    hist_today, hist_yest = float(macd_hist.iloc[-1]), float(macd_hist.iloc[-2])
    vol_today = float(volume.iloc[-1])
    vol_ma5 = float(volume.rolling(window=5).mean().iloc[-1])

    # 核心三大條件 + 成交量 > 500 張濾網
    cond1_macd = (hist_yest < 0) and (hist_today > 0)
    cond2_bb = bb_today > bb_yest
    cond3_ma20 = (c_today > ma20_today) and (ma20_today > ma20_yest)
    cond_vol = vol_today > 500_000

    if cond1_macd and cond2_bb and cond3_ma20 and cond_vol:
        pct_change = ((c_today - c_yest) / c_yest) * 100
        vol_ratio = round(vol_today / vol_ma5, 2) if vol_ma5 > 0 else 0
        return {
            "close": round(c_today, 2),
            "pct": round(pct_change, 2),
            "ma20": round(ma20_today, 2),
            "lots": int(vol_today // 1000),
            "vol_ratio": vol_ratio,
            "above_zero": float(dif.iloc[-1]) > 0,
        }
    return None


def generate_html(results, total_scanned, update_time):
    """將篩選結果輸出成手機/電腦皆適用的 HTML 儀表板"""
    if results:
        rows = []
        for r in results:
            pct_color = (
                "#d93025"
                if r["pct"] > 0
                else ("#188038" if r["pct"] < 0 else "#555")
            )
            pct_sign = "+" if r["pct"] > 0 else ""
            dif_badge = (
                '<span class="badge strong">零軸上 (強)</span>'
                if r["above_zero"]
                else '<span class="badge weak">零軸下</span>'
            )
            vol_highlight = (
                ' style="color:#d93025;font-weight:bold;"'
                if r["vol_ratio"] >= 1.5
                else ""
            )
            yahoo_url = f"https://tw.stock.yahoo.com/quote/{r['code']}"

            rows.append(f"""
            <tr>
                <td><a href="{yahoo_url}" target="_blank" class="stock-link">{r['code']} {r['name']}</a><span class="mkt">{r['market']}</span></td>
                <td><strong>{r['close']}</strong></td>
                <td style="color:{pct_color};font-weight:bold;">{pct_sign}{r['pct']}%</td>
                <td>{r['ma20']}</td>
                <td>{r['lots']:,}</td>
                <td{vol_highlight}>{r['vol_ratio']}x</td>
                <td>{dif_badge}</td>
            </tr>""")
        table_body = "\n".join(rows)
    else:
        table_body = '<tr><td colspan="7" style="text-align:center;padding:30px;color:#666;">今日無同時符合三大突破條件的標的（或今日為休市日）</td></tr>'

    html_template = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>台股波段起漲突破雷達</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft JhengHei", sans-serif; background: #f4f6f9; color: #222; margin: 0; padding: 16px; }
        .container { max-width: 960px; margin: 0 auto; }
        .header { background: #1a237e; color: #fff; padding: 20px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .header h1 { margin: 0 0 8px 0; font-size: 22px; }
        .header p { margin: 0; font-size: 13px; opacity: 0.85; }
        .stats { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
        .stat-card { background: #fff; padding: 14px 18px; border-radius: 10px; flex: 1; min-width: 140px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
        .stat-card .label { font-size: 12px; color: #666; }
        .stat-card .val { font-size: 20px; font-weight: bold; color: #1a237e; margin-top: 4px; }
        .search-box { width: 100%; box-sizing: border-box; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 12px; font-size: 15px; }
        .table-wrap { background: #fff; border-radius: 12px; overflow-x: auto; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
        table { width: 100%; border-collapse: collapse; font-size: 14px; white-space: nowrap; }
        th { background: #f8f9fa; color: #444; font-weight: 600; text-align: left; padding: 12px 14px; border-bottom: 2px solid #eee; }
        td { padding: 12px 14px; border-bottom: 1px solid #f0f0f0; }
        tr:hover { background: #f9fbff; }
        .stock-link { color: #1565c0; text-decoration: none; font-weight: 600; }
        .stock-link:hover { text-decoration: underline; }
        .mkt { font-size: 11px; color: #888; margin-left: 4px; }
        .badge { padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .badge.strong { background: #ffebee; color: #c62828; }
        .badge.weak { background: #eceff1; color: #546e7a; }
        .footer { text-align: center; font-size: 12px; color: #888; margin-top: 20px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📈 台股波段起漲突破雷達</h1>
        <p>條件：MACD柱狀體由負翻正 ＋ 布林通道開口放大 ＋ 站上向上20日線（成交量 &gt; 500張）</p>
    </div>
    <div class="stats">
        <div class="stat-card"><div class="label">最後更新時間 (台灣時間)</div><div class="val" style="font-size:16px;">__UPDATE_TIME__</div></div>
        <div class="stat-card"><div class="label">符合條件檔數</div><div class="val">__MATCH_COUNT__ 檔</div></div>
        <div class="stat-card"><div class="label">全市場掃描總數</div><div class="val">__TOTAL_SCANNED__ 檔</div></div>
    </div>
    <input type="text" id="filterInput" class="search-box" onkeyup="filterTable()" placeholder="🔍 輸入代號、股名或「零軸上」快速篩選...">
    <div class="table-wrap">
        <table id="stockTable">
            <thead>
                <tr>
                    <th>代號 / 名稱 (點擊看線圖)</th>
                    <th>收盤價</th>
                    <th>漲跌幅</th>
                    <th>20日線</th>
                    <th>成交張數</th>
                    <th>量比 (vs5日)</th>
                    <th>MACD位置</th>
                </tr>
            </thead>
            <tbody>
                __TABLE_ROWS__
            </tbody>
        </table>
    </div>
    <div class="footer">依「量比 (vs 5日均量)」由大到小排序 ｜ 僅供技術分析參考，投資請嚴守停損紀律</div>
</div>
<script>
function filterTable() {
    const filter = document.getElementById("filterInput").value.toUpperCase();
    const rows = document.getElementById("stockTable").getElementsByTagName("tr");
    for (let i = 1; i < rows.length; i++) {
        const text = rows[i].textContent || rows[i].innerText;
        rows[i].style.display = text.toUpperCase().indexOf(filter) > -1 ? "" : "none";
    }
}
</script>
</body>
</html>"""

    final_html = (
        html_template.replace("__UPDATE_TIME__", update_time)
        .replace("__MATCH_COUNT__", str(len(results)))
        .replace("__TOTAL_SCANNED__", str(total_scanned))
        .replace("__TABLE_ROWS__", table_body)
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)


def main():
    stock_dict = get_all_tw_stocks()
    tickers = list(stock_dict.keys())
    print(f"開始掃描 {len(tickers)} 檔上市櫃普通股...")

    results = []
    batch_size = 120

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        try:
            data = yf.download(
                batch,
                period="3mo",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
            )
            for ticker in batch:
                try:
                    df = (
                        data[ticker].dropna()
                        if isinstance(data.columns, pd.MultiIndex)
                        else data.dropna()
                    )
                    hit = check_strategy(df)
                    if hit:
                        name, market = stock_dict[ticker]
                        hit["code"] = ticker.split(".")[0]
                        hit["name"] = name
                        hit["market"] = market
                        results.append(hit)
                except Exception:
                    continue
        except Exception as e:
            print(f"批次下載異常: {e}")
        time.sleep(1)

    # 依照量比由大到小排序
    results.sort(key=lambda x: x["vol_ratio"], reverse=True)

    tw_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M")
    generate_html(results, len(tickers), now_str)
    print(f"完成！共篩選出 {len(results)} 檔標的，已更新 index.html")

if __name__ == "__main__":
          main()
