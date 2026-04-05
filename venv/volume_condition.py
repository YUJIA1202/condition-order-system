# volume_condition.py
import uuid
import time
from typing import Callable

class VolumeConditionManager:
    def __init__(self, place_order_fn: Callable):
        self.place_order = place_order_fn
        self.conditions: dict = {}

    def add(self, body: dict) -> dict:
        cid = str(uuid.uuid4())[:8]
        self.conditions[cid] = {
            "id":            cid,
            "stock_code":    body["stock_code"],    # 触发标的，同时也是下单标的
            "stock_name":    body.get("stock_name", ""),
            "action":        body["action"],         # "buy" | "sell"
            "trigger_price": float(body["trigger_price"]),
            "op":            body["op"],             # "lte"(≤) | "gte"(≥)
            "qty":           int(body["qty"]),
            # 量能参数
            "vol_ratio_threshold": float(body.get("vol_ratio_threshold", 1.5)),
            "vwap_dev_threshold":  float(body.get("vwap_dev_threshold", 1.5)),  # 百分比，如1.5代表1.5%
            # 状态
            "status":        "active",   # "active" | "triggered" | "cancelled"
            "cancel_reason": None,
            "trigger_time":  None,
            "order_result":  None,
            "created_at":    int(time.time()),
        }
        print(f"[量能条件单] 新增 {cid}: {body['stock_code']} {body['op']} {body['trigger_price']}")
        return self.conditions[cid]

    def remove(self, cid: str) -> dict:
        if cid in self.conditions:
            del self.conditions[cid]
            return {"success": True, "msg": f"已删除 {cid}"}
        return {"success": False, "msg": "条件单不存在"}

    def list(self) -> list:
        return list(self.conditions.values())

    def check(self, stock_ticks: dict) -> list:
        """
        stock_ticks: {code: {price, change, vwap, vol_ratio, ...}}
        由 main.py 的推送循环传入，每秒调用一次
        返回本次新触发（含取消）的条件单列表，用于前端日志展示
        """
        events = []

        for cid, cond in self.conditions.items():
            if cond["status"] != "active":
                continue

            tick = stock_ticks.get(cond["stock_code"])
            if tick is None:
                continue

            price     = tick["price"]
            vwap      = tick["vwap"]
            vol_ratio = tick["vol_ratio"]
            change    = tick["change"]   # 今日涨跌幅，正=上涨，负=下跌

            # ── 第一步：价格是否到达触发位 ──────────────────────────
            hit = False
            if cond["op"] == "lte" and price <= cond["trigger_price"]:
                hit = True
            elif cond["op"] == "gte" and price >= cond["trigger_price"]:
                hit = True

            if not hit:
                continue

            # ── 第二步：量能过滤 ─────────────────────────────────────
            vol_thr  = cond["vol_ratio_threshold"]
            vwap_thr = cond["vwap_dev_threshold"] / 100  # 转成小数

            # 均价线偏离度（正=价格在均价线上方，负=下方）
            vwap_dev = (price - vwap) / vwap if vwap > 0 else 0

            is_rising  = change >= 0   # 今日涨
            is_falling = change < 0    # 今日跌
            is_heavy   = vol_ratio >= vol_thr      # 放量
            is_light   = vol_ratio < vol_thr       # 缩量
            price_above_vwap = vwap_dev >= vwap_thr    # 价格大幅高于均价线
            price_below_vwap = vwap_dev <= -vwap_thr   # 价格大幅低于均价线

            cancel = False
            cancel_reason = ""

            if cond["action"] == "buy":
                if is_falling:
                    # 下跌买入：放量且大幅跌破均价线 → 真实抛压，不买
                    if is_heavy and price_below_vwap:
                        cancel = True
                        cancel_reason = (
                            f"放量下跌（量比{vol_ratio}x≥{vol_thr}x）"
                            f"且跌破均价线{abs(vwap_dev)*100:.1f}%，取消买入"
                        )
                else:
                    # 上涨买入（追涨/突破）：放量但均价线没跟上 → 虚涨，不买
                    if is_heavy and price_above_vwap:
                        cancel = True
                        cancel_reason = (
                            f"价格拉升但均价线未跟随（偏离{vwap_dev*100:.1f}%≥{cond['vwap_dev_threshold']}%）"
                            f"，量比{vol_ratio}x，取消买入"
                        )

            elif cond["action"] == "sell":
                if is_rising:
                    # 上涨卖出（止盈）：放量且均价线同步上行 → 还在强势，不卖
                    if is_heavy and price_above_vwap:
                        cancel = True
                        cancel_reason = (
                            f"放量上涨（量比{vol_ratio}x≥{vol_thr}x）"
                            f"且均价线同步走高，取消卖出"
                        )
                else:
                    # 下跌卖出（止损）：缩量下跌 → 只是震荡，不卖
                    if is_light:
                        cancel = True
                        cancel_reason = (
                            f"缩量下跌（量比{vol_ratio}x<{vol_thr}x）"
                            f"，判断为震荡，取消卖出"
                        )

            # ── 第三步：执行结果 ─────────────────────────────────────
            now = int(time.time())

            if cancel:
                self.conditions[cid]["status"]        = "cancelled"
                self.conditions[cid]["cancel_reason"] = cancel_reason
                self.conditions[cid]["trigger_time"]  = now
                print(f"[量能取消] {cid} | {cancel_reason}")
                events.append({
                    **cond,
                    "status":        "cancelled",
                    "cancel_reason": cancel_reason,
                    "current_price": price,
                    "vwap":          vwap,
                    "vol_ratio":     vol_ratio,
                })
            else:
                # 量能验证通过，正常下单
                result = self.place_order(cond["stock_code"], cond["action"], cond["qty"])
                self.conditions[cid]["status"]       = "triggered"
                self.conditions[cid]["trigger_time"] = now
                self.conditions[cid]["order_result"] = result
                print(f"[量能触发] {cid} | {cond['action']} {cond['stock_code']} {cond['qty']}手 | 量比{vol_ratio} 偏离{vwap_dev*100:.1f}%")
                events.append({
                    **cond,
                    "status":        "triggered",
                    "current_price": price,
                    "vwap":          vwap,
                    "vol_ratio":     vol_ratio,
                    "order_result":  result,
                })

        return events

    def get_active_codes(self) -> list:
        """返回所有活跃条件单的股票代码，供推送循环订阅行情用"""
        return list({
            cond["stock_code"]
            for cond in self.conditions.values()
            if cond["status"] == "active"
        })