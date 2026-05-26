"""
每日抓取 10 ETF 估值水位 (PE百分位)
策略: 分时段慢取，每次间隔 60s 避免限流
数据源: tushare (龙头股PE百分位) + akshare (沪深300指数PE)
输出: etf_data.json

用法: python3 fetch_etf_data.py          # 全部ETF (约10分钟)
      python3 fetch_etf_data.py --one    # 只取一个 (用于cron分时)
"""
import json, time, sys
from datetime import date
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "etf_data.json"
TUSHARE_TOKEN = "157c83b19dafd70820d7e0d111690d51731bc11c739f4a9d89aed7a8"

# ETF → 龙头股 (用龙头股PE百分位近似行业指数PE百分位)
PROXY_MAP = {
    "513180": ("恒生科技", "HK", "002230.SZ", None),    # 科大讯飞(CN科技代理)
    "512010": ("医药",     "CN", "600276.SH", None),    # 恒瑞医药
    "512880": ("证券",     "CN", "600030.SH", None),    # 中信证券
    "159928": ("消费",     "CN", "600519.SH", None),    # 贵州茅台
    "516160": ("新能源",   "CN", "300750.SZ", None),    # 宁德时代
    "512480": ("半导体",   "CN", "688981.SH", None),    # 中芯国际
    "510300": ("沪深300",  "CN", "000300.SH", "ak"),    # 指数PE, 用akshare
    "QQQ":    ("纳指100",  "US", None, None),
    "XLV":    ("美股医药", "US", None, None),
    "XLK":    ("美股科技", "US", None, None),
}


def fetch_tushare_stock_pe_percentile(stock_code: str) -> dict | None:
    """通过龙头股 PE_TTM 历史计算百分位"""
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)

    df = pro.daily_basic(
        ts_code=stock_code,
        start_date='20200101',
        end_date=date.today().strftime('%Y%m%d'),
        fields='ts_code,trade_date,pe_ttm'
    )
    if df is None or df.empty:
        return None

    df = df.dropna(subset=['pe_ttm'])
    df = df[df['pe_ttm'] > 0].sort_values('trade_date')
    if df.empty:
        return None

    cur = float(df.iloc[-1]['pe_ttm'])
    vals = df['pe_ttm'].astype(float)
    rank = (vals <= cur).sum()
    pct = round((rank / len(vals)) * 100, 1)
    return {"pe": round(cur, 2), "percentile": pct, "n": len(vals)}


def fetch_akshare_index_pe(name: str) -> dict | None:
    """akshare 指数PE (沪深300等)"""
    import akshare as ak
    df = ak.stock_index_pe_lg(symbol=name)
    if df is None or df.empty:
        return None
    df = df.dropna(subset=['滚动市盈率'])
    df = df[df['滚动市盈率'] > 0]
    if df.empty:
        return None
    cur = float(df.iloc[-1]['滚动市盈率'])
    vals = df['滚动市盈率'].astype(float)
    rank = (vals <= cur).sum()
    pct = round((rank / len(vals)) * 100, 1)
    return {"pe": round(cur, 2), "percentile": pct, "n": len(vals)}


def save_one(code: str, name: str, region: str, pct: float, pe: float = None):
    today = date.today().isoformat()
    if OUTPUT_FILE.exists():
        hist = json.loads(OUTPUT_FILE.read_text())
    else:
        hist = {}

    if code not in hist:
        hist[code] = []
    hist[code] = [p for p in hist[code] if p.get("date") != today]
    hist[code].append({"date": today, "percentile": pct, "pe": pe})
    hist[code] = sorted(hist[code], key=lambda x: x["date"])[-90:]

    # 元数据
    meta = hist.get("_meta", {})
    meta[code] = {"name": name, "region": region}
    hist["_meta"] = meta

    OUTPUT_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2))
    print(f"  → saved: {code} {name} PE%={pct}%")


def fetch_one(code: str):
    """取单只 ETF 数据"""
    name, region, proxy, source = PROXY_MAP[code]
    print(f"[{code}] {name} ...", end=" ", flush=True)

    if source == "ak":
        r = fetch_akshare_index_pe("沪深300")
    elif proxy:
        r = fetch_tushare_stock_pe_percentile(proxy)
    else:
        r = None  # 美股/港股暂跳过, 需要 yfinance

    if r:
        save_one(code, name, region, r["percentile"], r.get("pe"))
    else:
        print("  skip (no data)")


def fetch_all():
    """串行慢取全部 ETF (约10分钟)"""
    codes = list(PROXY_MAP.keys())
    success = 0
    for i, code in enumerate(codes):
        fetch_one(code)
        if i < len(codes) - 1:
            time.sleep(60)  # tushare 免费版限流间隔
    print(f"\nDone. Updated {success} ETFs.")


if __name__ == "__main__":
    if "--one" in sys.argv:
        # 分时模式: 一次只取一个, 用于 cron 每10分钟触发
        # 从状态文件读取下一个待取 code
        state_file = OUTPUT_FILE.parent / ".fetch_state"
        codes = list(PROXY_MAP.keys())
        idx = 0
        if state_file.exists():
            idx = int(state_file.read_text().strip())
        if idx < len(codes):
            code = codes[idx]
            fetch_one(code)
            state_file.write_text(str(idx + 1))
            print(f"Progress: {idx+1}/{len(codes)}")
        else:
            state_file.write_text("0")
            print("All done, resetting.")
    else:
        print(f"=== ETF PE Fetch {date.today().isoformat()} ===\n")
        fetch_all()
