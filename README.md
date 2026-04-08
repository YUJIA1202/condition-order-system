# 条件单自动交易系统 — 后端

基于国金证券 QMT 接口的条件单执行系统，已实盘运行。

## 技术栈

- Python / FastAPI
- WebSocket 实时推送（含心跳保活与断线重连）
- XtQuant（国金证券行情与交易接口）

## 主要功能

- 股指价格条件单：监控沪深大盘指数，触及阈值时自动对个股/ETF下单
- 量价均线条件单：价格触发后进行量能二次验证，过滤虚涨虚跌
- WebSocket 每秒广播实时行情，支持多客户端连接
- 量比阈值与均价线偏离阈值可自定义

## 本地运行

1. 安装依赖：`pip install -r requirements.txt`
2. 配置 `qmt_bridge.py` 中的账号与QMT路径
3. 确保国金证券QMT客户端已启动
4. 启动服务先进虚拟环境再：`uvicorn main:app --reload`

## 相关仓库

前端：[condition-order-frontend](https://github.com/YUJIA1202/condition-order-frontend)
