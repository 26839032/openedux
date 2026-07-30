"""
重建 etf_data.json — 统一用价格百分位，重算近90天
数据源: tushare fund_daily (CN) + akshare stock_us_daily (US)
"""
import json, time
from datetime import date, timedelta
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "etf_data.json"
TUSHARE_TOKEN = "157c83b19dafd70820d7e0d111690d51731bc11c739f4a9d89aed7a8"
LOOKBACK_DAYS = 90

ALL_ETFS = [
    ("513180", "恒生科技", "CN"),
    ("512010", "医药", "CN"),
    ("512880", "证券", "CN"),
    ("159928", "消费", "CN"),
    ("516160", "新能源", "CN"),
    ("512480", "半导体", "CN"),
    ("510300", "沪深300", "CN"),
    ("518880", "黄金", "CN"),
    ("512800", "银行", "CN"),
    ("159892", "恒生生物", "CN"),
    ("QQQ", "纳指100", "US"),
    ("XLV", "美股医药", "US"),
    ("XLK", "美股科技", "US"),
]


def fetch_cn_prices(code: str) -> list[tuple[str, float]]:
    """获取 CN ETF 全部历史价格，返回 [(date, close), ...]"""
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)

    for mkt in ['.SH', '.SZ']:
        try:
            df = pro.fund_daily(
                ts_code=code + mkt,
                start_date='20240101',
                end_date=date.today().strftime('%Y%m%d'),
                fields='ts_code,trade_date,close'
            )
            if df is not None and not df.empty:
                df = df.sort_values('trade_date')
                return [(r['trade_date'], float(r['close'])) for _, r in df.iterrows()]
        except Exception:
            continue
    return []


def fetch_us_prices(code: str) -> list[tuple[str, float]]:
    """获取 US ETF 全部历史价格，返回 [(date, close), ...]"""
    import akshare as ak
    try:
        df = ak.stock_us_daily(symbol=code, adjust='')
        if df is None or df.empty:
            return []
        df = df[df['date'] >= '20240101']
        return [(str(r['date'])[:10], float(r['close'])) for _, r in df.iterrows()]
    except Exception as e:
        print(f"  akshare error: {e}")
        return []


def compute_percentiles(prices: list[tuple[str, float]], lookback: int) -> list[dict]:
    """
    对每个交易日计算价格百分位（基于从2024-01-01到该日的全部历史）
    只保留最近 lookback 天
    """
    if len(prices) < 20:
        return []

    all_closes = [p[1] for p in prices]
    results = []

    for i, (dt, close) in enumerate(prices):
        # 百分位 = 当前价格在历史中的排名 / 历史总数
        history = all_closes[:i + 1]
        rank = sum(1 for v in history if v <= close)
        pct = round((rank / len(history)) * 100, 1)
        results.append({
            "date": dt,
            "percentile": pct,
            "price": round(close, 3),
        })

    # 只保留最近 lookback 天
    return results[-lookback:]


def main():
    print(f"=== 重建 ETF 数据 · {date.today().isoformat()} ===\n")

    result = {"_meta": {}}
    success = 0

    for code, name, region in ALL_ETFS:
        print(f"[{code}] {name} ...", end=" ", flush=True)

        if region == "US":
            prices = fetch_us_prices(code)
        else:
            prices = fetch_cn_prices(code)
            time.sleep(0.5)  # tushare 限流

        if not prices:
            print(f"❌ 无数据")
            continue

        records = compute_percentiles(prices, LOOKBACK_DAYS)
        if not records:
            print(f"❌ 数据不足")
            continue

        result[code] = records
        result["_meta"][code] = {"name": name, "region": region}
        latest = records[-1]
        print(f"✅ {len(records)}天  {records[0]['date']}→{latest['date']}  {latest['percentile']}%")
        success += 1

    # 写入
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n完成: {success}/{len(ALL_ETFS)} ETFs · 各 {LOOKBACK_DAYS} 天 · 统一价格百分位")


if __name__ == "__main__":
    main()
