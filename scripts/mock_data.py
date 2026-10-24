"""离线演示数据（固定种子，任何环境跑出来都一样）

为什么必须有这个：评审和路人没有 MCP Token，跑不起来就不会给 Star。
所以本项目在没有 Token 时也能完整跑通全流程，并在报告上明确标注「演示数据」。

数据画像刻意做成一个真实的成都打工人：工作日午餐为主、偶尔深夜加餐、
攒了一堆券没用、有积分快过期。这样演示出来的报告才有说服力。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

SEED = 1024

PRODUCTS = [
    ("巨无霸", 25.0), ("麦香鸡", 15.0), ("麦香鱼", 16.0), ("双层吉士汉堡", 18.0),
    ("板烧鸡腿堡", 22.0), ("麦辣鸡腿堡", 21.0), ("安格斯厚牛堡", 34.0),
    ("大薯条", 12.0), ("中薯条", 10.0), ("麦乐鸡（10块）", 22.0), ("麦辣鸡翅", 13.0),
    ("中可乐", 8.0), ("大雪碧", 10.0), ("美汁源果粒橙", 9.0), ("鲜煮咖啡", 12.0),
    ("麦旋风", 9.0), ("甜筒", 6.0), ("香芋派", 7.0), ("菠萝派", 7.0),
    ("猪柳蛋麦满分", 14.0), ("热豆浆", 7.0), ("玉米杯", 8.0),
]

STORES = [
    "麦当劳(成都天府三街店)", "麦当劳(成都银泰中心in99店)", "麦当劳(成都软件园店)",
    "麦当劳(成都世纪城店)", "麦当劳(成都天府广场店)",
]

NUTRITION = [
    {"name": "巨无霸", "energy": 550}, {"name": "麦香鸡", "energy": 370},
    {"name": "麦香鱼", "energy": 340}, {"name": "双层吉士汉堡", "energy": 440},
    {"name": "板烧鸡腿堡", "energy": 480}, {"name": "麦辣鸡腿堡", "energy": 570},
    {"name": "安格斯厚牛堡", "energy": 720}, {"name": "大薯条", "energy": 490},
    {"name": "中薯条", "energy": 340}, {"name": "麦乐鸡（10块）", "energy": 470},
    {"name": "麦辣鸡翅", "energy": 390}, {"name": "中可乐", "energy": 150},
    {"name": "大雪碧", "energy": 210}, {"name": "美汁源果粒橙", "energy": 160},
    {"name": "鲜煮咖啡", "energy": 15}, {"name": "麦旋风", "energy": 280},
    {"name": "甜筒", "energy": 180}, {"name": "香芋派", "energy": 250},
    {"name": "菠萝派", "energy": 240}, {"name": "猪柳蛋麦满分", "energy": 390},
    {"name": "热豆浆", "energy": 120}, {"name": "玉米杯", "energy": 90},
]


def build_mock(now: datetime | None = None, n: int = 68) -> dict:
    """返回与真实 MCP 结构一致的字典，供 scoring 直接消费。"""
    rng = random.Random(SEED)
    now = now or datetime.now()
    start = now - timedelta(days=400)

    orders = []
    # 画像：工作日午餐为主的加班族，深夜加餐偏多，节奏不规则（故意不做成完美数据）
    day = start
    while len(orders) < n and day <= now:
        day += timedelta(days=1)
        if day.weekday() >= 5 and rng.random() < 0.85:
            continue          # 周末多数不下单
        if rng.random() < 0.42:
            continue          # 工作日也有跳过
        if rng.random() < 0.26:
            hour, minute = rng.randint(22, 23), rng.randint(0, 59)   # 深夜加餐
        elif rng.random() < 0.13:
            hour, minute = rng.randint(7, 9), rng.randint(0, 59)     # 早餐
        else:
            hour, minute = rng.randint(11, 13), rng.randint(0, 59)   # 午餐

        picks = rng.sample(PRODUCTS, rng.randint(1, 2))
        items, total = [], 0.0
        for name, price in picks:
            qty = 1 if rng.random() < 0.85 else 2
            items.append({"productName": name, "quantity": qty})
            total += price * qty
        if rng.random() < 0.06:          # 偶发团餐大额
            total += rng.uniform(40, 90)
        total = round(max(12.0, total - (rng.uniform(0, 8) if rng.random() < 0.45 else 0)), 1)

        orders.append({
            "orderId": f"MOCK{len(orders):04d}",
            "createTime": day.replace(hour=hour, minute=minute).strftime("%Y-%m-%d %H:%M:%S"),
            "realTotalAmount": total,
            "storeName": rng.choices(STORES, weights=[42, 24, 16, 12, 6])[0],
            "takeWay": "外送" if rng.random() < 0.4 else "堂食",
            "orderProductList": items,
        })

    account = {
        "availablePoints": 2380,
        "totalPoints": 5120,
        "frozenPoints": 60,
        "expiringPoints": 640,
    }

    coupons = [
        {"name": "麦辣鸡腿堡立减5元", "expireTime": (now + timedelta(days=3)).strftime("%Y-%m-%d")},
        {"name": "大薯条免费券", "expireTime": (now + timedelta(days=5)).strftime("%Y-%m-%d")},
        {"name": "麦旋风第二份半价", "expireTime": (now + timedelta(days=41)).strftime("%Y-%m-%d")},
        {"name": "早餐套餐7折", "expireTime": (now + timedelta(days=62)).strftime("%Y-%m-%d")},
        {"name": "满30减6", "expireTime": (now + timedelta(days=18)).strftime("%Y-%m-%d")},
        {"name": "中可乐兑换券", "expireTime": (now + timedelta(days=2)).strftime("%Y-%m-%d")},
    ]

    return {
        "orders": orders,
        "account": account,
        "coupons": coupons,
        "nutrition": NUTRITION,
        "is_mock": True,
    }
