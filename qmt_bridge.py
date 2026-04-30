# qmt_bridge.py
import time
from datetime import datetime

USE_MOCK = False
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

def _get_xtdata():
    from xtquant import xtdata
    try:
        xtdata.enable_hello = False
        xtdata.connect(QMT_HOST, QMT_PORT)
    except Exception as e:
        print(f"[QMT] connection failed: {e}")
    return xtdata

def _parse_time(t_str) -> int:
    s = str(t_str).strip()
    try:
        if len(s) == 8:
            return int(datetime.strptime(s, "%Y%m%d").timestamp())
        elif len(s) >= 14:
            return int(datetime.strptime(s[:14], "%Y%m%d%H%M%S").timestamp())
        else:
            return int(s[:10])
    except Exception:
        return 0

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
        print(f"[QMT] get_tick {code} failed: {e}")
        return None

def get_all_indices() -> list:
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick(INDEX_CODES)
        result = []
        for code in INDEX_CODES:
            tick = data.get(code, {})
            if not tick:
                continue
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
        print(f"[QMT] get_all_indices failed: {e}")
        return []

def search_stock(keyword: str) -> list:
    if not keyword or len(keyword.strip()) < 1:
        return []
    keyword_raw = keyword.strip()
    keyword_up  = keyword_raw.upper()
    try:
        xtdata = _get_xtdata()
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
                print(f"[QMT] search_instruments failed: {e}")

        all_codes = []
        for sector in ["沪深A股", "上交所ETF", "深交所ETF", "沪深ETF"]:
            try:
                codes = xtdata.get_stock_list_in_sector(sector)
                if codes:
                    all_codes.extend(codes)
            except Exception:
                pass

        all_codes = list(dict.fromkeys(all_codes))
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

        return results
    except Exception as e:
        print(f"[QMT] search_stock failed: {e}")
        return []

def get_stock_tick(code: str) -> dict | None:
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick([code])
        tick = data.get(code, {})
        if not tick:
            return None
        price      = tick.get("lastPrice", 0)
        last_close = tick.get("lastClose", 0) or 1
        amount     = tick.get("amount", 0)
        volume     = tick.get("volume", 0)
        vol_ratio  = tick.get("volRatio", 1.0)
        change = round((price - last_close) / last_close * 100, 3) if last_close else 0
        vwap = round(amount / (volume * 100), 3) if (volume > 0 and amount > 0) else round(last_close, 3)
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
        print(f"[QMT] get_stock_tick {code} failed: {e}")
        return None

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
                continue
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
        print(f"[QMT] get_stock_ticks failed: {e}")
        return {}

def place_order(code: str, action: str, qty: int) -> dict:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        from xtquant import xtconstant
        trader = XtQuantTrader(
            r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini",
            9999
        )
        trader.start()
        trader.connect()
        time.sleep(2)  # 等待连接建立
        acc       = _XTTYPE_.StockAccount(ACCOUNT_ID)
        direction = xtconstant.STOCK_BUY if action == "buy" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE
        tick = get_stock_tick(code)
        if not tick:
            return {"success": False, "order_id": "", "msg": f"failed to get price for {code}"}
        price    = tick["price"]
        order_id = trader.order_stock(
            acc, code, direction, qty * 100, price_type, price,
            "ETF-DESK", "auto order"
        )
        trader.stop()
        print(f"[QMT] place_order {action} {code} {qty}手 @ {price} -> order_id={order_id}")
        return {
            "success":  order_id > 0,
            "order_id": str(order_id),
            "msg":      f"{action} {code} {qty} @ {price}",
        }
    except Exception as e:
        print(f"[QMT] place_order failed: {e}")
        return {"success": False, "order_id": "", "msg": str(e)}

def get_positions() -> list:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        trader = XtQuantTrader(
            r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini",
            9999
        )
        trader.start()
        trader.connect()
        time.sleep(2)  # 等待连接建立
        acc = _XTTYPE_.StockAccount(ACCOUNT_ID)
        positions = trader.query_stock_positions(acc)
        result = []
        for p in positions:
            price = p.last_price if p.last_price and p.last_price > 0 else p.avg_price
            result.append({
                "code":  p.stock_code.split(".")[0],
                "name":  p.instrument_name,
                "qty":   p.volume,
                "cost":  round(p.avg_price, 3),
                "price": round(price, 3),
            })
        trader.stop()
        return result
    except Exception as e:
        print(f"[QMT] get_positions failed: {e}")
        return []

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
        )
        if raw is None or "close" not in raw or code not in raw["close"].index:
            return []
        closes = raw["close"].loc[code].tolist()
        opens  = raw["open"].loc[code].tolist()
        highs  = raw["high"].loc[code].tolist()
        lows   = raw["low"].loc[code].tolist()
        vols   = raw["volume"].loc[code].tolist()
        times  = raw["close"].columns.tolist()
        bars = []
        for i in range(len(closes)):
            bars.append({
                "t": _parse_time(times[i]),
                "o": round(float(opens[i]),  3),
                "h": round(float(highs[i]),  3),
                "l": round(float(lows[i]),   3),
                "c": round(float(closes[i]), 3),
                "v": int(vols[i]),
            })
        return bars
    except Exception as e:
        print(f"[QMT] get_kline {code} failed: {e}")
        return []

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
        print(f"[QMT] get_sectors failed: {e}")
        return []

def get_history_pnl(days: int = 365) -> list:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        trader = XtQuantTrader(
            r"C:\Users\86182\Desktop\etf-desk\国金证券QMT交易端\userdata_mini",
            9999
        )
        trader.start()
        trader.connect()
        time.sleep(2)  # 等待连接建立
        acc = _XTTYPE_.StockAccount(ACCOUNT_ID)
        raw_positions = trader.query_stock_positions(acc)
        positions = []
        for p in raw_positions:
            if p.volume <= 0:
                continue
            positions.append({
                "code": p.stock_code,
                "qty":  p.volume,
                "cost": round(p.avg_price, 3),
            })
        trader.stop()
        print(f"[DEBUG history-pnl] positions: {positions}")
        if not positions:
            return []

        result_map = {}
        for pos in positions:
            bars = get_kline(pos["code"], "1d", days)
            print(f"[DEBUG history-pnl] {pos['code']} bars: {len(bars)}")
            for i, bar in enumerate(bars):
                date = datetime.fromtimestamp(bar["t"]).strftime("%Y-%m-%d")
                prev_close = bars[i-1]["c"] if i > 0 else bar["o"]
                daily_pnl  = round((bar["c"] - prev_close) * pos["qty"], 2)
                if date not in result_map:
                    result_map[date] = {"date": date, "dailyPnl": 0.0}
                result_map[date]["dailyPnl"] += daily_pnl

        total_cost = sum(p["qty"] * p["cost"] for p in positions)
        final = []
        for d in sorted(result_map.values(), key=lambda x: x["date"]):
            d["dailyPct"] = round(d["dailyPnl"] / total_cost * 100, 3) if total_cost else 0
            d["month"]    = d["date"][:7]
            final.append(d)
        return final

    except Exception as e:
        print(f"[QMT] get_history_pnl failed: {e}")
        return []