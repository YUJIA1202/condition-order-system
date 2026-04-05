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

# ─── Mock数据 ─────────────────────────────────────────────────────
MOCK_BASE = {
    "000001.SH": 3948.55,
    "399001.SZ": 11823.45,
    "399006.SZ": 2187.32,
    "688000.SH": 986.54,
    "899050.BJ": 1243.88,
}
MOCK_PRICES = {k: v for k, v in MOCK_BASE.items()}

# Mock个股价格池，搜索时随机生成并缓存
_MOCK_STOCK_PRICES = {}

def _mock_tick(code):
    MOCK_PRICES[code] = MOCK_PRICES[code] * (1 + (random.random()-0.5)*0.0006)
    price = MOCK_PRICES[code]
    base  = MOCK_BASE[code]
    return {
        "code":   code,
        "price":  round(price, 2),
        "change": round((price-base)/base*100, 3),
        "volume": random.randint(100000, 999999),
        "time":   int(time.time()*1000),
    }

def _mock_stock_tick(code, name=""):
    """
    模拟个股Tick，含均价线（vwap）和量比（vol_ratio）
    """
    if code not in _MOCK_STOCK_PRICES:
        # 根据代码段猜价格范围，让mock数据看起来合理
        if code.startswith(("51", "15", "58", "56")):
            base = round(random.uniform(0.5, 5.0), 3)   # ETF价格区间
        else:
            base = round(random.uniform(5.0, 50.0), 3)  # 个股价格区间
        _MOCK_STOCK_PRICES[code] = {"base": base, "price": base}

    entry = _MOCK_STOCK_PRICES[code]
    entry["price"] = entry["price"] * (1 + (random.random()-0.5)*0.0008)
    price = round(entry["price"], 3)
    base  = entry["base"]
    change = round((price - base) / base * 100, 3)

    # 模拟均价线：在当前价附近随机偏移，偏移控制在±1%以内
    vwap = round(price * (1 + (random.random()-0.5)*0.01), 3)

    # 模拟量比：大多数时候在0.5~2.0之间，偶尔放量
    vol_ratio = round(random.uniform(0.5, 2.0), 2)

    return {
        "code":      code,
        "name":      name,
        "price":     price,
        "change":    change,
        "vwap":      vwap,          # 均价线（当日成交额/成交量）
        "vol_ratio": vol_ratio,     # 量比（来自xtdata full_tick的volRatio字段）
        "volume":    random.randint(10000, 9999999),
        "time":      int(time.time()*1000),
    }

# ─── 获取单个指数Tick（原有）────────────────────────────────────────
def get_tick(code: str) -> dict:
    if USE_MOCK:
        return _mock_tick(code)
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick([code])
        tick = data.get(code, {})
        if not tick:
            return _mock_tick(code)
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
        return _mock_tick(code)

# ─── 获取所有指数（原有）─────────────────────────────────────────────
def get_all_indices() -> list:
    if USE_MOCK:
        return [_mock_tick(code) for code in MOCK_BASE.keys()]
    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick(INDEX_CODES)
        result = []
        for code in INDEX_CODES:
            tick = data.get(code, {})
            if not tick:
                result.append(_mock_tick(code))
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
        print(f"[QMT] get_all_indices 失败: {e}")
        return [_mock_tick(code) for code in MOCK_BASE.keys()]

# ─── 【新增】搜索股票/ETF ──────────────────────────────────────────
def search_stock(keyword: str) -> list:
    """
    根据关键词搜索股票或ETF（代码或名称）
    返回最多15条结果，格式：[{code, name, market}, ...]

    xtdata.get_stock_list_in_sector() 可获取板块内所有股票
    xtdata.search_instruments() 可按关键词搜索（新版xtquant支持）
    """
    if not keyword or len(keyword.strip()) < 1:
        return []

    keyword = keyword.strip().upper()

    if USE_MOCK:
        return _mock_search(keyword)

    try:
        xtdata = _get_xtdata()

        # 方法一：优先用 search_instruments（新版xtquant）
        # 返回格式：[{stock_code, instrument_name, ...}, ...]
        if hasattr(xtdata, "search_instruments"):
            raw = xtdata.search_instruments(keyword)
            results = []
            for item in raw[:15]:
                code = item.get("stock_code", "")
                name = item.get("instrument_name", "")
                if code:
                    results.append({
                        "code": code,
                        "name": name,
                        "display": f"{code.split('.')[0]}  {name}",
                    })
            if results:
                return results

        # 方法二：fallback —— 从全市场列表里手动匹配
        # 获取沪深全部股票代码列表
        all_codes = []
        for sector in ["沪深A股", "上交所ETF", "深交所ETF"]:
            try:
                codes = xtdata.get_stock_list_in_sector(sector)
                all_codes.extend(codes)
            except Exception:
                pass

        if not all_codes:
            return _mock_search(keyword)

        # 批量拉取名称（get_instrument_detail 返回每只股票的详情）
        results = []
        for code in all_codes:
            short_code = code.split(".")[0]
            # 先按代码匹配（快速）
            if keyword in short_code or keyword in code:
                detail = xtdata.get_instrument_detail(code) or {}
                name = detail.get("InstrumentName", "")
                results.append({
                    "code": code,
                    "name": name,
                    "display": f"{short_code}  {name}",
                })
                if len(results) >= 15:
                    break

        # 如果代码没搜到，再按名称搜（慢，但兜底）
        if not results:
            for code in all_codes[:5000]:  # 限制范围防止太慢
                detail = xtdata.get_instrument_detail(code) or {}
                name = detail.get("InstrumentName", "")
                if keyword in name:
                    short_code = code.split(".")[0]
                    results.append({
                        "code": code,
                        "name": name,
                        "display": f"{short_code}  {name}",
                    })
                    if len(results) >= 15:
                        break

        return results if results else _mock_search(keyword)

    except Exception as e:
        print(f"[QMT] search_stock '{keyword}' 失败: {e}")
        return _mock_search(keyword)


def _mock_search(keyword: str) -> list:
    """Mock搜索结果，用于开发调试"""
    MOCK_STOCKS = [
        {"code": "510300.SH", "name": "沪深300ETF"},
        {"code": "510500.SH", "name": "中证500ETF"},
        {"code": "510050.SH", "name": "上证50ETF"},
        {"code": "159915.SZ", "name": "创业板ETF"},
        {"code": "159919.SZ", "name": "沪深300ETF(深)"},
        {"code": "512000.SH", "name": "券商ETF"},
        {"code": "512880.SH", "name": "证券ETF"},
        {"code": "515000.SH", "name": "地产ETF"},
        {"code": "603083.SH", "name": "剑桥科技"},
        {"code": "000001.SZ", "name": "平安银行"},
        {"code": "000858.SZ", "name": "五 粮 液"},
        {"code": "600519.SH", "name": "贵州茅台"},
        {"code": "300750.SZ", "name": "宁德时代"},
        {"code": "002594.SZ", "name": "比亚迪"},
        {"code": "601318.SH", "name": "中国平安"},
    ]
    keyword_lower = keyword.lower()
    results = []
    for s in MOCK_STOCKS:
        short = s["code"].split(".")[0]
        if keyword_lower in short.lower() or keyword_lower in s["name"].lower():
            results.append({
                "code":    s["code"],
                "name":    s["name"],
                "display": f"{short}  {s['name']}",
            })
    # 没匹配到就返回前5条兜底
    return results[:15] if results else [
        {
            "code": s["code"],
            "name": s["name"],
            "display": f"{s['code'].split('.')[0]}  {s['name']}",
        }
        for s in MOCK_STOCKS[:5]
    ]


# ─── 【新增】获取个股实时Tick（含均价线和量比）──────────────────────
def get_stock_tick(code: str) -> dict:
    """
    获取个股/ETF的实时Tick数据，比 get_tick 多返回：
      - vwap:      当日均价线（成交额/成交量）
      - vol_ratio: 量比（xtdata full_tick 的 volRatio 字段）
      - change:    今日涨跌幅%

    vwap 计算：tick['amount'] / tick['volume']
    vol_ratio 直接读：tick['volRatio']
    """
    # 从 code 里提取名称（如果有带名称的场合）
    if USE_MOCK:
        return _mock_stock_tick(code)

    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick([code])
        tick = data.get(code, {})
        if not tick:
            print(f"[QMT] get_stock_tick {code} 返回空，使用Mock")
            return _mock_stock_tick(code)

        price      = tick.get("lastPrice", 0)
        last_close = tick.get("lastClose", 0) or 1
        amount     = tick.get("amount", 0)    # 当日累计成交额（元）
        volume     = tick.get("volume", 0)    # 当日累计成交量（股）
        vol_ratio  = tick.get("volRatio", 1.0) # 量比，xtdata直接提供

        change = round((price - last_close) / last_close * 100, 3) if last_close else 0

        # 均价线：累计成交额 / 累计成交量
        # amount 单位是元，volume 单位是股，直接除即可
        if volume > 0 and amount > 0:
            vwap = round(amount / volume, 3)
        else:
            # 开盘前或数据异常时用昨收代替
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
        return _mock_stock_tick(code)


# ─── 【新增】批量获取多只股票Tick（用于条件单引擎轮询）──────────────
def get_stock_ticks(codes: list) -> dict:
    """
    批量获取多只股票的Tick，返回 {code: tick_dict}
    比循环调用 get_stock_tick 更高效（一次请求）
    """
    if not codes:
        return {}

    if USE_MOCK:
        return {code: _mock_stock_tick(code) for code in codes}

    try:
        xtdata = _get_xtdata()
        data = xtdata.get_full_tick(codes)
        result = {}
        for code in codes:
            tick = data.get(code, {})
            if not tick:
                result[code] = _mock_stock_tick(code)
                continue

            price      = tick.get("lastPrice", 0)
            last_close = tick.get("lastClose", 0) or 1
            amount     = tick.get("amount", 0)
            volume     = tick.get("volume", 0)
            vol_ratio  = tick.get("volRatio", 1.0)

            change = round((price - last_close) / last_close * 100, 3) if last_close else 0
            vwap = round(amount / volume, 3) if (volume > 0 and amount > 0) else round(last_close, 3)

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
        return {code: _mock_stock_tick(code) for code in codes}


# ─── 下单（原有）─────────────────────────────────────────────────
def place_order(code: str, action: str, qty: int) -> dict:
    if USE_MOCK:
        print(f"[模拟下单] {action.upper()} {code} {qty}手")
        return {
            "success":  True,
            "order_id": f"MOCK_{int(time.time())}",
            "msg":      f"模拟{action} {code} {qty}手 成功",
        }
    try:
        from xtquant.xttrader import XtQuantTrader
        from xtquant import xtconstant

        trader = XtQuantTrader(
            "C:\\Users\\86182\\Desktop\\etf-desk\\国金证券QMT交易端\\userdata_mini",
            int(time.time())
        )
        trader.start()
        account = trader.get_account(ACCOUNT_ID)

        direction = xtconstant.STOCK_BUY if action == "buy" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE

        tick = get_stock_tick(code)
        price = tick["price"]

        order_id = trader.order_stock(
            account, code, direction, qty, price_type, price,
            "ETF-DESK", "量能条件单自动下单"
        )
        return {
            "success":  order_id > 0,
            "order_id": str(order_id),
            "msg":      f"{action} {code} {qty}手 @ {price}",
        }
    except Exception as e:
        print(f"[QMT] place_order 失败: {e}")
        return {"success": False, "order_id": "", "msg": str(e)}


# ─── 查持仓（原有）───────────────────────────────────────────────
def get_positions() -> list:
    try:
        from xtquant.xttrader import XtQuantTrader, _XTTYPE_
        trader = XtQuantTrader(
            "C:\\Users\\86182\\Desktop\\etf-desk\\国金证券QMT交易端\\userdata_mini",
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
        return result if result else _mock_positions()
    except Exception as e:
        print(f"[QMT] get_positions 失败: {e}")
        return _mock_positions()


def _mock_positions():
    return [
        {"code":"510300","name":"沪深300ETF","qty":5000,"cost":3.921,"price":4.012},
        {"code":"159915","name":"创业板ETF",  "qty":3000,"cost":1.842,"price":1.798},
        {"code":"512000","name":"券商ETF",    "qty":2000,"cost":1.205,"price":1.231},
    ]