# main.py
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from qmt_bridge import (
    get_all_indices, place_order, get_positions,
    search_stock, get_stock_tick, get_stock_ticks,
    get_kline,
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
                self.active.remove(ws)

manager = ConnectionManager()


# ─── 推送循环 ─────────────────────────────────────────────────────
async def market_push_loop():
    while True:
        if manager.active:
            # 1. 五大指数（股指条件单用）
            indices = get_all_indices()
            triggered_index = condition_mgr.check(indices)

            # 2. 量能条件单涉及的个股/ETF
            active_codes = volume_condition_mgr.get_active_codes()
            stock_ticks  = get_stock_ticks(active_codes) if active_codes else {}
            triggered_volume = volume_condition_mgr.check(stock_ticks)

            await manager.broadcast({
                "type":             "market",
                "indices":          indices,
                "triggered":        triggered_index,          # 股指条件单触发
                "volume_triggered": triggered_volume,         # 量能条件单触发/取消
                "stock_ticks":      stock_ticks,              # 个股实时行情（前端展示用）
            })

        await asyncio.sleep(1)


@app.on_event("startup")
async def startup():
    asyncio.create_task(market_push_loop())
    print("[启动] http://localhost:8000")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ─── 持仓 & 下单（原有）──────────────────────────────────────────
@app.get("/positions")
def api_positions():
    return get_positions()

@app.post("/order")
def api_order(body: dict):
    return place_order(body["code"], body["action"], body["qty"])


# ─── 股指条件单（原有，路径不变）────────────────────────────────────
@app.get("/conditions")
def api_get_conditions():
    return condition_mgr.list()

@app.post("/conditions")
def api_add_condition(body: dict):
    return condition_mgr.add(body)

@app.delete("/conditions/{cid}")
def api_delete_condition(cid: str):
    return condition_mgr.remove(cid)


# ─── 量能条件单（新增）───────────────────────────────────────────
@app.get("/volume-conditions")
def api_get_volume_conditions():
    return volume_condition_mgr.list()

@app.post("/volume-conditions")
def api_add_volume_condition(body: dict):
    return volume_condition_mgr.add(body)

@app.delete("/volume-conditions/{cid}")
def api_delete_volume_condition(cid: str):
    return volume_condition_mgr.remove(cid)


# ─── 股票搜索（新增）────────────────────────────────────────────
@app.get("/search-stock")
def api_search_stock(q: str = ""):
    return search_stock(q)


# ─── 获取单只股票实时Tick（新增，前端预览用）────────────────────────
@app.get("/stock-tick/{code}")
def api_stock_tick(code: str):
    # code 从路径传入时可能带点，如 510300.SH，FastAPI 默认截断
    # 所以前端请求时用 query param 更安全，这里两种都支持
    return get_stock_tick(code)

@app.get("/stock-tick")
def api_stock_tick_query(code: str = ""):
    return get_stock_tick(code)
# ─── import 行里加上 get_kline ────────────────────────────────────
# from qmt_bridge import (
#     ..., get_kline,   # ← 加这个
# )

@app.get("/kline")
def api_kline(code: str = "", period: str = "1d", count: int = 60):
    return get_kline(code, period, count)