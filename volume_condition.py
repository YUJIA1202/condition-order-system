# volume_condition.py
import uuid
import time
import json
import os
from datetime import datetime
from typing import Callable

VOLUME_CONDITION_FILE = "volume_conditions_data.json"


def _is_trading_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (925 <= t <= 1130) or (1300 <= t <= 1500)


class VolumeConditionManager:
    def __init__(self, place_order_fn: Callable):
        self.place_order = place_order_fn
        self.conditions: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(VOLUME_CONDITION_FILE):
            try:
                with open(VOLUME_CONDITION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.conditions = {item["id"]: item for item in data}
                print(f"[量能条件单] 已加载 {len(self.conditions)} 条")
            except Exception as e:
                print(f"[量能条件单] 加载失败: {e}")
                self.conditions = {}

    def _save(self):
        try:
            with open(VOLUME_CONDITION_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self.conditions.values()), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[量能条件单] 保存失败: {e}")

    def add(self, body: dict) -> dict:
        cid = str(uuid.uuid4())[:8]
        self.conditions[cid] = {
            "id":                  cid,
            "stock_code":          body["stock_code"],
            "stock_name":          body.get("stock_name", ""),
            "action":              body["action"],
            "trigger_price":       float(body["trigger_price"]),
            "op":                  body["op"],
            "qty":                 int(body["qty"]),
            "vol_ratio_threshold": float(body.get("vol_ratio_threshold", 1.5)),
            "vwap_dev_threshold":  float(body.get("vwap_dev_threshold", 1.5)),
            "status":              "active",
            "cancel_reason":       None,
            "trigger_time":        None,
            "order_result":        None,
            "created_at":          int(time.time()),
        }
        self._save()
        print(f"[量能条件单] 新增 {cid}: {body['stock_code']} {body['op']} {body['trigger_price']}")
        return self.conditions[cid]

    def remove(self, cid: str) -> dict:
        if cid in self.conditions:
            del self.conditions[cid]
            self._save()
            return {"success": True, "msg": f"已删除 {cid}"}
        return {"success": False, "msg": "条件单不存在"}

    def list(self) -> list:
        return list(self.conditions.values())

    def get_active_codes(self) -> list:
        return list({
            cond["stock_code"]
            for cond in self.conditions.values()
            if cond["status"] == "active"
        })

    def check(self, stock_ticks: dict) -> list:
        if not _is_trading_time():
            return []

        events = []

        for cid, cond in self.conditions.items():
            if cond["status"] != "active":
                continue

            tick = stock_ticks.get(cond["stock_code"])
            if tick is None:
                continue

            price = tick["price"]
            vwap = tick["vwap"]
            vol_ratio = tick["vol_ratio"]
            change = tick["change"]

            hit = False
            if cond["op"] == "lte" and price <= cond["trigger_price"]:
                hit = True
            elif cond["op"] == "gte" and price >= cond["trigger_price"]:
                hit = True
            if not hit:
                continue

            vol_thr = cond["vol_ratio_threshold"]
            vwap_thr = cond["vwap_dev_threshold"] / 100
            vwap_dev = (price - vwap) / vwap if vwap > 0 else 0

            is_rising = change >= 0
            is_heavy = vol_ratio >= vol_thr
            is_light = vol_ratio < vol_thr
            price_above_vwap = vwap_dev >= vwap_thr
            price_below_vwap = vwap_dev <= -vwap_thr

            cancel = False
            cancel_reason = ""

            if cond["action"] == "buy":
                if not is_rising:
                    if is_heavy and price_below_vwap:
                        cancel = True
                        cancel_reason = (
                            f"放量下跌（量比{vol_ratio}x≥{vol_thr}x）"
                            f"且跌破均价线{abs(vwap_dev)*100:.1f}%，取消买入"
                        )
                else:
                    if is_heavy and price_above_vwap:
                        cancel = True
                        cancel_reason = (
                            f"价格拉升但均价线未跟随（偏离{vwap_dev*100:.1f}%≥{cond['vwap_dev_threshold']}%）"
                            f"，量比{vol_ratio}x，取消买入"
                        )
            elif cond["action"] == "sell":
                if is_rising:
                    if is_heavy and price_above_vwap:
                        cancel = True
                        cancel_reason = (
                            f"放量上涨（量比{vol_ratio}x≥{vol_thr}x）"
                            f"且均价线同步走高，取消卖出"
                        )
                else:
                    if is_light:
                        cancel = True
                        cancel_reason = (
                            f"缩量下跌（量比{vol_ratio}x<{vol_thr}x）"
                            f"，判断为震荡，取消卖出"
                        )

            now = int(time.time())

            if cancel:
                self.conditions[cid]["status"] = "cancelled"
                self.conditions[cid]["cancel_reason"] = cancel_reason
                self.conditions[cid]["trigger_time"] = now
                self._save()
                print(f"[量能取消] {cid} | {cancel_reason}")
                events.append({
                    **cond,
                    "status": "cancelled",
                    "cancel_reason": cancel_reason,
                    "current_price": price,
                    "vwap": vwap,
                    "vol_ratio": vol_ratio,
                })
            else:
                result = self.place_order(cond["stock_code"], cond["action"], cond["qty"])
                self.conditions[cid]["status"] = "triggered"
                self.conditions[cid]["trigger_time"] = now
                self.conditions[cid]["order_result"] = result
                self._save()
                print(f"[量能触发] {cid} | {cond['action']} {cond['stock_code']} {cond['qty']}手 | 量比{vol_ratio} 偏离{vwap_dev*100:.1f}%")
                print(f"[量能下单结果] {cid} | success={result.get('success')} | order_id={result.get('order_id')} | msg={result.get('msg')}")
                events.append({
                    **cond,
                    "status": "triggered",
                    "current_price": price,
                    "vwap": vwap,
                    "vol_ratio": vol_ratio,
                    "order_result": result,
                })

        return events
