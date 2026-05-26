"""
每日抓取 10 支 ETF 的 PE 估值水位 (百分位)
中国 ETF: akshare (东方财富)
美股 ETF: yfinance (Yahoo Finance)
输出: etf_data.json (供 signals-economy.html 读取)
"""
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "etf_data.json"

ETFS = [
    # [code, name, region, market_code]
    ("513180", "恒生科技", "CN", "1.513180"),
    ("512010", "医药", "CN", "1.512010"),
    ("512880", "证券", "CN", "1.512880"),
    ("159928", "消费", "CN", "0.159928"),
    ("516160", "新能源", "CN", "1.516160"),
    ("512480", "半导体", "CN", "1.512480"),
    ("510300", "沪深300", "CN", "1.510300"),
    ("QQQ", "纳指100", "US", "QQQ"),
    ("XLV", "美股医药", "US", "XLV"),
    ("XLK", "美股科技", "US", "XLK"),
]


def fetch_cn_etf_valuation(market_code: str) -> dict:
    """通过东方财富API获取A股ETF的PE百分位"""
    try:
        import requests
        # 东方财富基金详情API
        secid = market_code  # e.g. "1.513180"
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields=f57,f58,f170,f171"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json().get("data", {})

        pe = data.get("f170", None)   # PE (TTM)
        pb = data.get("f171", None)   # PB

        if pe and float(pe) > 0:
            pe = round(float(pe), 2)
            # 尝试获取PE百分位 (部分ETF有此数据)
            url2 = (
                f"https://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstmentData"
                f"?secid={secid}&pageIndex=1&pageSize=1"
            )
            try:
                resp2 = requests.get(url2, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://fund.eastmoney.com/"
                })
                d2 = resp2.json()
            except Exception:
                d2 = {}

            return {"pe": pe, "pb": float(pb) if pb else None, "raw": d2}
        return {}
    except Exception as e:
        print(f"  fetch_cn error: {e}")
        return {}


def fetch_cn_index_pe_percentile(index_code: str) -> float | None:
    """通过akshare获取指数PE历史并计算当前百分位"""
    try:
        import akshare as ak
        df = ak.index_value_hist_funddb(symbol=index_code, indicator="市盈率")
        if df is None or df.empty:
            return None
        current_pe = float(df.iloc[-1]["市盈率"])
        pe_values = df["市盈率"].dropna().astype(float)
        rank = (pe_values <= current_pe).sum()
        percentile = round((rank / len(pe_values)) * 100, 1)
        return percentile
    except Exception as e:
        print(f"  index_pe error for {index_code}: {e}")
        return None


# 指数映射: ETF代码 → 跟踪指数代码 (用于查询PE百分位)
INDEX_MAP = {
    "513180": "000896",  # 中证港股通科技
    "512010": "000991",  # 中证医药
    "512880": "399975",  # 中证全指证券
    "159928": "000932",  # 中证消费
    "516160": "399808",  # 中证新能源
    "512480": "990001",  # 中证全指半导体
    "510300": "000300",  # 沪深300
}


def fetch_us_etf_valuation(symbol: str) -> dict:
    """通过yfinance获取美股ETF估值数据"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")

        # 获取历史PE计算百分位
        hist = ticker.history(period="5y")
        if len(hist) > 100:
            # 用价格变动模拟估值变化 (简化)
            pass

        result = {}
        if pe and float(pe) > 0:
            result["pe"] = round(float(pe), 2)
        if pb and float(pb) > 0:
            result["pb"] = round(float(pb), 2)
        return result
    except Exception as e:
        print(f"  fetch_us error for {symbol}: {e}")
        return {}


def fetch_all():
    """抓取所有ETF数据"""
    results = {}
    today_str = date.today().isoformat()

    for code, name, region, mkt_code in ETFS:
        print(f"Fetching {code} ({name})...")

        if region == "CN" and code in INDEX_MAP:
            percentile = fetch_cn_index_pe_percentile(INDEX_MAP[code])
            if percentile is not None:
                results[code] = {
                    "name": name,
                    "percentile": percentile,
                    "date": today_str,
                    "region": region,
                }
                print(f"  PE%: {percentile}%")
                time.sleep(0.3)  # 避免请求过快
            else:
                print(f"  skipped (no data)")
        elif region == "US":
            print(f"  US ETF: manual PE calculation needed, skipping auto")
        else:
            print(f"  skipped")

    return results


def update_data_file(new_data: dict):
    """追加今日数据到JSON文件，保留30天历史"""
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r") as f:
            history = json.load(f)
    else:
        history = {}

    today_str = date.today().isoformat()

    for code, entry in new_data.items():
        if code not in history:
            history[code] = []

        # 去重：如果今天已有数据则更新
        updated = False
        for pt in history[code]:
            if pt.get("date") == today_str:
                pt["percentile"] = entry["percentile"]
                pt["pe"] = entry.get("pe")
                updated = True
                break

        if not updated:
            history[code].append({
                "date": today_str,
                "percentile": entry["percentile"],
                "pe": entry.get("pe"),
            })

        # 只保留最近60条
        history[code] = sorted(
            history[code],
            key=lambda x: x["date"]
        )[-60:]

    # 同时保存ETF元数据
    meta = {e[0]: {"name": e[1], "region": e[2]} for e in ETFS}
    history["_meta"] = meta

    with open(OUTPUT_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    print(f"=== ETF Valuation Fetch {date.today().isoformat()} ===\n")
    data = fetch_all()
    if data:
        update_data_file(data)
        print(f"\nDone. {len(data)} ETFs updated.")
    else:
        print("\nNo data fetched.")
