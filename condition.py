# condition.py
import uuid
import time
from typing import Callable

class ConditionManager:
    def __init__(self, place_order_fn: Callable):
        self.place_order = place_order_fn
        self.conditions: dict = {}

    def add(self, body: dict) -> dict:
        cid = str(uuid.uuid4())[:8]
        self.conditions[cid] = {
            "id":           cid,
            "index_code":   body["index_code"],
            "op":           body["op"],
            "price":        float(body["price"]),
            "action":       body["action"],
            "etf_code":     body["etf_code"],
            "qty":          int(body["qty"]),
            "active":       True,
            "triggered":    False,
            "trigger_time": None,
            "created_at":   int(time.time()),
        }
        print(f"[条件单] 新增 {cid}: {body['index_code']} {body['op']} {body['price']}")
        return self.conditions[cid]

    def remove(self, cid: str) -> dict:
        if cid in self.conditions:
            del self.conditions[cid]
            return {"success": True, "msg": f"已删除 {cid}"}
        return {"success": False, "msg": "条件单不存在"}

    def list(self) -> list:
        return list(self.conditions.values())

    def check(self, indices: list) -> list:
        price_map = {item["code"]: item["price"] for item in indices}
        newly_triggered = []

        for cid, cond in self.conditions.items():
            if not cond["active"] or cond["triggered"]:
                continue

            current_price = price_map.get(cond["index_code"])
            if current_price is None:
                continue

            hit = False
            if cond["op"] == "lte" and current_price <= cond["price"]:
                hit = True
            elif cond["op"] == "gte" and current_price >= cond["price"]:
                hit = True

            if hit:
                print(f"[触发] {cid} | {cond['index_code']} {cond['op']} {cond['price']} | 当前 {current_price} | {cond['action']} {cond['etf_code']} {cond['qty']}手")
                result = self.place_order(cond["etf_code"], cond["action"], cond["qty"])
                self.conditions[cid]["triggered"]    = True
                self.conditions[cid]["trigger_time"] = int(time.time())
                self.conditions[cid]["order_result"] = result
                newly_triggered.append({**cond, "current_price": current_price, "order_result": result})

        return newly_triggered