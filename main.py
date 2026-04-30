# main.py
import asyncio
import json
import os
import time as _time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from qmt_bridge import (
    get_all_indices, place_order, get_positions,
    search_stock, get_stock_tick, get_stock_ticks,
    get_kline, get_sectors, get_history_pnl,
)
from condition import ConditionManager
from volume_condition import VolumeConditionManager

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

condition_mgr        = ConditionManager(place_order)
volume_condition_mgr = VolumeConditionManager(place_order)

# ─── 缓存 ────────────────────────────────────────────────────────
_pos_cache   = {"data": []}
_pnl_cache   = {"data": [], "ts": 0}
_index_cache = {"data": [], "ts": 0}
_kline_cache = {}

# ─── 配置文件路径 ─────────────────────────────────────────────────
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "positions_config.json")


# ─── WebSocket 连接管理 ───────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] 连接数: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        print(f"[WS] 断开，连接数: {len(self.active)}")

    async def broadcast(self, data: dict):
        msg = json.dumps(data, ensure_ascii=False)
        for ws in self.active.copy():
            try:
                await ws.send_text(msg)
            except Exception:
                if ws in self.active:
                    self.active.remove(ws)

manager = ConnectionManager()


# ─── 增量下载历史数据 ─────────────────────────────────────────────
def _do_download():
    try:
        from xtquant import xtdata
        xtdata.enable_hello = False
        xtdata.connect("127.0.0.1", 58610)
        codes   = ["516670.SH","600089.SH","159606.SZ","000001.SH","000300.SH"]
        periods = ["1d","5m","15m","30m","60m"]
        for code in codes:
            for period in periods:
                print(f"[数据] 增量下载 {code} {period}...")
                xtdata.download_history_data(code, period=period, incrementally=True)
        print("[数据] 增量下载完成")
    except Exception as e:
        print(f"[数据] 下载失败: {e}")

async def auto_download_loop():
    await asyncio.to_thread(_do_download)
    while True:
        from datetime import datetime
        now      = datetime.now()
        next_run = now.replace(hour=8, minute=50, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run.replace(day=now.day+1)
        await asyncio.sleep((next_run-now).total_seconds())
        await asyncio.to_thread(_do_download)


# ─── 推送循环 ─────────────────────────────────────────────────────
async def market_push_loop():
    while True:
        if manager.active:
            indices          = get_all_indices()
            triggered_index  = condition_mgr.check(indices)
            active_codes     = volume_condition_mgr.get_active_codes()
            stock_ticks      = get_stock_ticks(active_codes) if active_codes else {}
            triggered_volume = volume_condition_mgr.check(stock_ticks)
            sectors          = get_sectors()
            await manager.broadcast({
                "type":             "market",
                "indices":          indices,
                "triggered":        triggered_index,
                "volume_triggered": triggered_volume,
                "stock_ticks":      stock_ticks,
                "sectors":          sectors,
            })
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup():
    asyncio.create_task(market_push_loop())
    asyncio.create_task(auto_download_loop())
    print(f"[启动] http://localhost:8000")
    print(f"[配置] positions_config.json: {_CONFIG_PATH}")
    print(f"[配置] 文件存在: {os.path.exists(_CONFIG_PATH)}")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ─── 持仓配置 ────────────────────────────────────────────────────
@app.get("/positions-config")
def api_positions_config():
    print(f"[config] path={_CONFIG_PATH}, exists={os.path.exists(_CONFIG_PATH)}")
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"[config] loaded keys: {list(data.keys())}")
            return data
    except Exception as e:
        print(f"[config] error: {e}")
        return {}


# ─── 持仓（实时，失败时兜底缓存）───────────────────────────────
@app.get("/positions")
def api_positions():
    result = get_positions()
    if result:
        _pos_cache["data"] = result
        return result
    return _pos_cache["data"]

@app.post("/order")
def api_order(body: dict):
    return place_order(body["code"], body["action"], body["qty"])


# ─── 股指条件单 ──────────────────────────────────────────────────
@app.get("/conditions")
def api_get_conditions():
    return condition_mgr.list()

@app.post("/conditions")
def api_add_condition(body: dict):
    return condition_mgr.add(body)

@app.delete("/conditions/{cid}")
def api_delete_condition(cid: str):
    return condition_mgr.remove(cid)


# ─── 量能条件单 ──────────────────────────────────────────────────
@app.get("/volume-conditions")
def api_get_volume_conditions():
    return volume_condition_mgr.list()

@app.post("/volume-conditions")
def api_add_volume_condition(body: dict):
    return volume_condition_mgr.add(body)

@app.delete("/volume-conditions/{cid}")
def api_delete_volume_condition(cid: str):
    return volume_condition_mgr.remove(cid)


# ─── 股票搜索 ────────────────────────────────────────────────────
@app.get("/search-stock")
def api_search_stock(q: str = ""):
    return search_stock(q)


# ─── 个股 Tick ───────────────────────────────────────────────────
@app.get("/stock-tick/{code}")
def api_stock_tick(code: str):
    return get_stock_tick(code)

@app.get("/stock-tick")
def api_stock_tick_query(code: str = ""):
    return get_stock_tick(code)


# ─── K线（5分钟缓存）────────────────────────────────────────────
@app.get("/kline/{code}")
def api_kline_path(code: str, period: str = "1d", count: int = 60):
    key = f"{code}-{period}-{count}"
    now = _time.time()
    if key in _kline_cache and now - _kline_cache[key]["ts"] < 300:
        return _kline_cache[key]["data"]
    result = get_kline(code, period, count)
    _kline_cache[key] = {"data": result, "ts": now}
    return result

@app.get("/kline")
def api_kline_query(code: str = "", period: str = "1d", count: int = 60):
    key = f"{code}-{period}-{count}"
    now = _time.time()
    if key in _kline_cache and now - _kline_cache[key]["ts"] < 300:
        return _kline_cache[key]["data"]
    result = get_kline(code, period, count)
    _kline_cache[key] = {"data": result, "ts": now}
    return result


# ─── 历史每日盈亏（5分钟缓存）───────────────────────────────────
@app.get("/history-pnl")
def api_history_pnl(days: int = 365):
    now = _time.time()
    if _pnl_cache["data"] and now - _pnl_cache["ts"] < 300:
        return _pnl_cache["data"]
    result = get_history_pnl(days)
    _pnl_cache["data"] = result
    _pnl_cache["ts"]   = now
    return result


# ─── 历史指数收盘价（5分钟缓存）─────────────────────────────────
@app.get("/history-index")
def api_history_index(days: int = 365):
    now = _time.time()
    if _index_cache["data"] and now - _index_cache["ts"] < 300:
        return _index_cache["data"]
    from datetime import datetime
    result_map = {}
    for code, key in [("000001.SH", "shanghai"), ("000300.SH", "hs300")]:
        bars = get_kline(code, "1d", days)
        for bar in bars:
            date = datetime.fromtimestamp(bar["t"]).strftime("%Y-%m-%d")
            if date not in result_map:
                result_map[date] = {"date": date}
            result_map[date][key] = bar["c"]
    result = sorted(result_map.values(), key=lambda x: x["date"])
    _index_cache["data"] = result
    _index_cache["ts"]   = now
    return result
