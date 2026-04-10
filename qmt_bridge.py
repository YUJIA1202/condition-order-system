# qmt_bridge.py
import time
import random

USE_MOCK = False  # 已接入真实QMT

QMT_HOST = "127.0.0.1"
QMT_PORT = 58610
ACCOUNT_ID = "8889091202"

INDEX_CODES = [
    "000001.SH",
    "399001.SZ",
    "399006.SZ",
    "688000.SH",
    "899050.BJ",
]

# ─── 初始化连接 ───────────────────────────────────────────────────
def _get_xtdata():
    from xtquant import xtdata
    try:
        xtdata.enable_hello = False
        xtdata.connect(QMT_HOST, QMT_PORT)
    except Exception as e:
        print(f"[QMT] 连接失败: {e}")
    return xtdata

# ─── 获取单个指数Tick ─────────────────────────────────────────────
def get_tick(code: str) -> dict | None:
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick([code])
        tick = data.get(code, {})
        if not tick:
            return None
        last_close = tick.get("lastClose", 0) or 1
        price = tick.get("lastPrice", 0)
        change = round((price - last_close) / last_close * 100, 3) if last_close else 0
        return {
            "code":   code,
            "price":  round(price, 3),
            "change": change,
            "volume": tick.get("volume", 0),
            "time":   tick.get("time", int(time.time()*1000)),
        }
    except Exception as e:
        print(f"[QMT] get_tick {code} 失败: {e}")
        return None

# ─── 获取所有指数 ─────────────────────────────────────────────────
def get_all_indices() -> list:
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick(INDEX_CODES)
        result = []
        for code in INDEX_CODES:
            tick = data.get(code, {})
            if not tick:
                continue  # 非交易时段跳过，不用Mock
            last_close = tick.get("lastClose", 0) or 1
            price = tick.get("lastPrice", 0)
            change = round((price - last_close) / last_close * 100, 3) if last_close else 0
            result.append({
                "code":   code,
                "price":  round(price, 3),
                "change": change,
                "volume": tick.get("volume", 0),
                "time":   tick.get("time", int(time.time()*1000)),
            })
        return result
    except Exception as e:
        print(f"[QMT] get_all_indices 失败: {e}")
        return []

# ─── 搜索股票/ETF ─────────────────────────────────────────────────
def search_stock(keyword: str) -> list:
    if not keyword or len(keyword.strip()) < 1:
        return []

    keyword_raw = keyword.strip()
    keyword_up  = keyword_raw.upper()

    try:
        xtdata = _get_xtdata()

        # 方法一：search_instruments
        if hasattr(xtdata, "search_instruments"):
            try:
                raw = xtdata.search_instruments(keyword_raw)
                if not raw:
                    raw = xtdata.search_instruments(keyword_up)
                results = []
                for item in (raw or [])[:15]:
                    code = item.get("stock_code", "")
                    name = item.get("instrument_name", "")
                    if code:
                        results.append({
                            "code":    code,
                            "name":    name,
                            "display": f"{code.split('.')[0]}  {name}",
                        })
                if results:
                    return results
            except Exception as e:
                print(f"[QMT] search_instruments 失败: {e}")

        # 方法二：从全市场列表匹配
        all_codes = []
        for sector in ["沪深A股", "上交所ETF", "深交所ETF", "沪深ETF"]:
            try:
                codes = xtdata.get_stock_list_in_sector(sector)
                if codes:
                    all_codes.extend(codes)
            except Exception:
                pass

        all_codes = list(dict.fromkeys(all_codes))
        print(f"[DEBUG] 全市场代码数: {len(all_codes)}, 搜索: {keyword_raw}")

        if not all_codes:
            return []

        results = []
        for code in all_codes:
            short_code = code.split(".")[0]
            if keyword_up in short_code or keyword_up in code.upper():
                detail = xtdata.get_instrument_detail(code) or {}
                name   = detail.get("InstrumentName", "")
                results.append({
                    "code":    code,
                    "name":    name,
                    "display": f"{short_code}  {name}",
                })
                if len(results) >= 15:
                    break

        if len(results) < 15:
            for code in all_codes[:8000]:
                short_code = code.split(".")[0]
                detail = xtdata.get_instrument_detail(code) or {}
                name   = detail.get("InstrumentName", "")
                if keyword_raw in name and not any(r["code"] == code for r in results):
                    results.append({
                        "code":    code,
                        "name":    name,
                        "display": f"{short_code}  {name}",
                    })
                    if len(results) >= 15:
                        break

        print(f"[DEBUG] 搜索 '{keyword_raw}' 结果数: {len(results)}")
        return results

    except Exception as e:
        print(f"[QMT] search_stock '{keyword_raw}' 失败: {e}")
        return []

# ─── 获取个股实时Tick ─────────────────────────────────────────────
def get_stock_tick(code: str) -> dict | None:
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick([code])
        tick = data.get(code, {})

        print(f"[DEBUG tick] {code}")
        print(f"  lastPrice = {tick.get('lastPrice')}")
        print(f"  lastClose = {tick.get('lastClose')}")
        print(f"  amount    = {tick.get('amount')}")
        print(f"  volume    = {tick.get('volume')}")
        print(f"  volRatio  = {tick.get('volRatio')}")
        print(f"  all keys  = {list(tick.keys()) if tick else 'empty'}")

        if not tick:
            print(f"[QMT] get_stock_tick {code} 返回空（非交易时段）")
            return None

        price      = tick.get("lastPrice", 0)
        last_close = tick.get("lastClose", 0) or 1
        amount     = tick.get("amount", 0)
        volume     = tick.get("volume", 0)
        vol_ratio  = tick.get("volRatio", 1.0)

        change = round((price - last_close) / last_close * 100, 3) if last_close else 0

        if volume > 0 and amount > 0:
            vwap = round(amount / (volume * 100), 3)
        else:
            vwap = round(last_close, 3)

        return {
            "code":      code,
            "price":     round(price, 3),
            "change":    change,
            "vwap":      vwap,
            "vol_ratio": round(vol_ratio, 2),
            "volume":    volume,
            "amount":    amount,
            "time":      tick.get("time", int(time.time()*1000)),
        }

    except Exception as e:
        print(f"[QMT] get_stock_tick {code} 失败: {e}")
        return None

# ─── 批量获取多只股票Tick ─────────────────────────────────────────
def get_stock_ticks(codes: list) -> dict:
    if not codes:
        return {}
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick(codes)
        result = {}
        for code in codes:
            tick = data.get(code, {})
            if not tick:
                continue  # 非交易时段跳过，不用Mock
            price      = tick.get("lastPrice", 0)
            last_close = tick.get("lastClose", 0) or 1
            amount     = tick.get("amount", 0)
            volume     = tick.get("volume", 0)
            vol_ratio  = tick.get("volRatio", 1.0)
            change = round((price - last_close) / last_close * 100, 3) if last_close else 0
            vwap = round(amount / (volume * 100), 3) if (volume > 0 and amount > 0) else round(last_close, 3)
            result[code] = {
                "code":      code,
                "price":     round(price, 3),
                "change":    change,
                "vwap":      vwap,
                "vol_ratio": round(vol_ratio, 2),
                "volume":    volume,
                "amount":    amount,
                "time":      tick.get("time", int(time.time()*1000)),
            }
        return result
    except Exception as e:
        print(f"[QMT] get_stock_ticks 失败: {e}")
        return {}

# ─── 下单 ─────────────────────────────────────────────────────────
def place_order(code: str, action: str, qty: int) -> dict:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        from xtquant import xtconstant

        trader = XtQuantTrader(
            r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini",
            int(time.time())
        )
        trader.start()
        trader.connect()

        acc        = _XTTYPE_.StockAccount(ACCOUNT_ID)
        direction  = xtconstant.STOCK_BUY if action == "buy" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE

        tick = get_stock_tick(code)
        if not tick:
            return {"success": False, "order_id": "", "msg": f"获取 {code} 价格失败，取消下单"}
        price = tick["price"]

        order_id = trader.order_stock(
            acc, code, direction, qty * 100, price_type, price,
            "ETF-DESK", "条件单自动下单"
        )
        trader.stop()
        return {
            "success":  order_id > 0,
            "order_id": str(order_id),
            "msg":      f"{action} {code} {qty}手 @ {price}",
        }
    except Exception as e:
        print(f"[QMT] place_order 失败: {e}")
        return {"success": False, "order_id": "", "msg": str(e)}

# ─── 查持仓 ───────────────────────────────────────────────────────
def get_positions() -> list:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        trader = XtQuantTrader(
            r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini",
            int(time.time())
        )
        trader.start()
        trader.connect()
        acc = _XTTYPE_.StockAccount(ACCOUNT_ID)
        positions = trader.query_stock_positions(acc)
        result = []
        for p in positions:
            result.append({
                "code":  p.stock_code.split(".")[0],
                "name":  p.instrument_name,
                "qty":   p.volume,
                "cost":  round(p.avg_price, 3),
                "price": round(p.last_price, 3),
            })
        trader.stop()
        return result
    except Exception as e:
        print(f"[QMT] get_positions 失败: {e}")
        return []

# ─── K线数据 ──────────────────────────────────────────────────────
def get_kline(code: str, period: str = "1d", count: int = 60) -> list:
    if not code:
        return []
    try:
        xtdata = _get_xtdata()
        period_map = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","60m":"60m","1d":"1d"}
        xt_period  = period_map.get(period, "1d")
        raw = xtdata.get_market_data(
            field_list=["open","high","low","close","volume"],
            stock_list=[code],
            period=xt_period,
            count=count,
            dividend_type="none",
        )
        if not raw or code not in raw.get("close", {}):
            return []
        closes = list(raw["close"][code].values())
        opens  = list(raw["open"][code].values())
        highs  = list(raw["high"][code].values())
        lows   = list(raw["low"][code].values())
        vols   = list(raw["volume"][code].values())
        times  = list(raw["close"][code].keys())
        bars = []
        for i in range(len(closes)):
            bars.append({
                "t": int(str(times[i])[:10]) if times[i] else 0,
                "o": round(opens[i],  3),
                "h": round(highs[i],  3),
                "l": round(lows[i],   3),
                "c": round(closes[i], 3),
                "v": int(vols[i]),
            })
        return bars
    except Exception as e:
        print(f"[QMT] get_kline {code} 失败: {e}")
        return []

# ─── 板块ETF数据 ──────────────────────────────────────────────────
SECTOR_ETFS = [
    {"code": "512000.SH", "name": "券商"},
    {"code": "512800.SH", "name": "银行"},
    {"code": "512480.SH", "name": "半导体"},
    {"code": "512010.SH", "name": "医药"},
    {"code": "512660.SH", "name": "军工"},
    {"code": "516160.SH", "name": "新能源"},
    {"code": "512690.SH", "name": "白酒"},
    {"code": "159928.SZ", "name": "消费"},
    {"code": "512400.SH", "name": "有色"},
    {"code": "515220.SH", "name": "煤炭"},
    {"code": "516210.SH", "name": "钢铁"},
    {"code": "512200.SH", "name": "地产"},
]

def get_sectors() -> list:
    try:
        xtdata = _get_xtdata()
        codes  = [s["code"] for s in SECTOR_ETFS]
        data   = xtdata.get_full_tick(codes)
        result = []
        for s in SECTOR_ETFS:
            tick = data.get(s["code"], {})
            if not tick:
                result.append({"code": s["code"], "name": s["name"], "change": 0.0, "price": 0.0})
                continue
            price      = tick.get("lastPrice", 0)
            last_close = tick.get("lastClose", 0) or 1
            change     = round((price - last_close) / last_close * 100, 2)
            result.append({
                "code":   s["code"],
                "name":   s["name"],
                "change": change,
                "price":  round(price, 3),
            })
        return result
    except Exception as e:
        print(f"[QMT] get_sectors 失败: {e}")
        return []