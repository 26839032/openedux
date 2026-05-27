"""
每日抓取 ETF 价格百分位 (统一标尺)
数据源: tushare fund_daily (CN) + us_daily (US)
输出: etf_data.json
"""
import json, time, sys
from datetime import date
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "etf_data.json"
TUSHARE_TOKEN = "157c83b19dafd70820d7e0d111690d51731bc11c739f4a9d89aed7a8"

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


def fetch_price_percentile(code: str, region: str) -> dict | None:
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)

    if region == "US":
        df = pro.us_daily(ts_code=code, start_date='20240101',
            end_date=date.today().strftime('%Y%m%d'),
            fields='ts_code,trade_date,close')
    else:
        # CN ETF: try .SH first, then .SZ
        for mkt in ['.SH', '.SZ']:
            try:
                df = pro.fund_daily(ts_code=code + mkt, start_date='20240101',
                    end_date=date.today().strftime('%Y%m%d'),
                    fields='ts_code,trade_date,close')
                if df is not None and not df.empty:
                    break
            except:
                continue

    if df is None or df.empty:
        return None

    df = df.sort_values('trade_date')
    prices = df['close'].astype(float)
    cur = float(prices.iloc[-1])
    vals = prices.values

    rank = (vals <= cur).sum()
    pct = round((rank / len(vals)) * 100, 1)

    return {
        "percentile": pct,
        "price": round(cur, 3),
        "data_points": len(vals),
    }


def save(code: str, name: str, region: str, entry: dict):
    today = date.today().isoformat()
    if OUTPUT_FILE.exists():
        hist = json.loads(OUTPUT_FILE.read_text())
    else:
        hist = {}

    if code not in hist:
        hist[code] = []
    hist[code] = [p for p in hist[code] if p.get("date") != today]
    hist[code].append({
        "date": today,
        "percentile": entry["percentile"],
        "price": entry.get("price"),
    })
    hist[code] = sorted(hist[code], key=lambda x: x["date"])[-90:]

    meta = hist.get("_meta", {})
    meta[code] = {"name": name, "region": region}
    hist["_meta"] = meta

    OUTPUT_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    print(f"=== ETF Price Percentile {date.today().isoformat()} ===\n")
    success = 0
    for code, name, region in ALL_ETFS:
        print(f"[{code}] {name} ...", end=" ", flush=True)
        time.sleep(0.6)
        r = fetch_price_percentile(code, region)
        if r:
            save(code, name, region, r)
            print(f"{r['percentile']}%  (¥{r['price']})")
            success += 1
        else:
            print("no data")
    print(f"\nDone. {success}/{len(ALL_ETFS)} ETFs updated.")
