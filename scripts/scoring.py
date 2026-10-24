"""麦险分评分引擎

把麦当劳订单行为映射成一张信贷风格的评分卡。

设计原则（这决定了它像不像真的风控模型，而不是拍脑袋）：
1. 每个维度只用 MCP 真实返回的字段算，缺字段就走中性分，绝不编造。
2. 分箱而非连续映射 —— 真评分卡就是分箱的，边界写在 DIMENSIONS 里可审计。
3. 单调性有业务解释：不是「消费越多分越高」，集中度是 U 型，自律度是惩罚项。
4. 分数域 300-900，对齐 FICO / 芝麻分的直觉。
"""

from __future__ import annotations

import math
import re
from datetime import datetime

# ---------------------------------------------------------------- 权重表

WEIGHTS = {
    "stability": 0.20,     # 履约稳定性
    "budget": 0.20,        # 预算约束力
    "discipline": 0.25,    # 自律度
    "concentration": 0.15, # 集中度
    "asset": 0.20,         # 资产健康度
}

DIMENSION_META = {
    "stability": ("履约稳定性", "下单间隔是否规律，衡量行为可预测性"),
    "budget": ("预算约束力", "单笔金额是否稳定，衡量冲动消费倾向"),
    "discipline": ("自律度", "深夜订单与热量密度，衡量生活方式风险"),
    "concentration": ("集中度", "门店与品类分布，U 型：过度集中和过度分散都扣分"),
    "asset": ("资产健康度", "积分与券的沉睡率，衡量资产管理能力"),
}

RATING_BANDS = [
    (780, "AAA", "优质客户", "建议通过 · 可提额"),
    (720, "AA", "优质客户", "建议通过"),
    (660, "A", "正常客户", "建议通过"),
    (600, "BBB", "观察类", "建议通过 · 纳入关注"),
    (540, "BB", "观察类", "建议通过 · 限制额度"),
    (480, "B", "关注类", "人工复核"),
    (420, "CCC", "关注类", "人工复核 · 限制额度"),
    (0, "C", "高风险", "建议拒件"),
]


# ---------------------------------------------------------------- 工具函数

def _cv(values: list[float]) -> float | None:
    """变异系数 = 标准差 / 均值。样本 < 2 时无意义，返回 None。"""
    if len(values) < 2:
        return None
    mu = sum(values) / len(values)
    if mu <= 0:
        return None
    var = sum((v - mu) ** 2 for v in values) / len(values)
    return math.sqrt(var) / mu


def _hhi(counter: dict[str, int]) -> float:
    """赫芬达尔指数 = Σ(份额²)，0~1。1 表示全部集中在一处。"""
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return sum((c / total) ** 2 for c in counter.values())


def _bin_score(value: float | None, bins: list[tuple[float, int]], neutral: int) -> int:
    """分箱打分。bins 按阈值降序排列：[(阈值, 分数), ...]，value >= 阈值 取该分。"""
    if value is None:
        return neutral
    for threshold, score in bins:
        if value >= threshold:
            return score
    return bins[-1][1] if bins else neutral


def _parse_time(raw) -> datetime | None:
    """兼容时间戳（秒/毫秒）与常见时间字符串。"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:  # 毫秒
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- 特征层

CATEGORY_RULES = [
    ("汉堡", r"汉堡|巨无霸|麦香|双层|鸡腿堡|牛堡|麦辣|板烧|安格斯"),
    ("小食", r"薯条|鸡块|鸡翅|麦乐鸡|洋葱|薯格|玉米|派"),
    ("饮料", r"可乐|雪碧|美汁源|咖啡|拿铁|红茶|牛奶|豆浆|气泡|特饮"),
    ("甜品", r"冰淇淋|圣代|麦旋风|甜筒|华夫|蛋糕|布丁"),
    ("早餐", r"满分|粥|油条|饼|蛋|早餐"),
    ("沙拉", r"沙拉|蔬菜|轻食"),
]


def _categorize(name: str) -> str:
    for label, pattern in CATEGORY_RULES:
        if re.search(pattern, name):
            return label
    return "其他"


def extract_features(orders: list[dict], account: dict | None,
                     coupons: list[dict], nutrition: list[dict],
                     now: datetime | None = None) -> dict:
    """把原始 MCP 数据整理成特征。缺数据返回 None 而不是 0，交由分箱走中性分。"""
    now = now or datetime.now()

    times: list[datetime] = []
    amounts: list[float] = []
    hour_hist = [0] * 24          # 24 小时下单分布
    timeline: list[tuple] = []    # (归一化位置, 是否深夜) 供报告画时间轴
    store_counter: dict[str, int] = {}
    cat_counter: dict[str, int] = {}
    item_counter: dict[str, int] = {}
    late_count = 0
    kcal_total = 0.0
    kcal_matched = 0

    # 营养表：名称 → 每份能量(kcal)
    nutri = {}
    for row in nutrition or []:
        if not isinstance(row, dict):
            continue
        nm = str(row.get("name") or row.get("foodName") or row.get("productName") or "")
        kcal = row.get("energy") or row.get("kcal") or row.get("calorie")
        try:
            kcal = float(kcal)
        except (TypeError, ValueError):
            continue
        if nm:
            nutri[nm] = kcal

    for od in orders or []:
        if not isinstance(od, dict):
            continue
        t = _parse_time(
            od.get("createTime") or od.get("orderTime") or od.get("time")
            or od.get("createdAt") or od.get("create_time")
        )
        amt = od.get("realTotalAmount") or od.get("payAmount") or od.get("actualAmount") \
            or od.get("totalAmount") or od.get("amount") or od.get("pay_amount")
        try:
            amt = float(str(amt).replace("¥", "").replace(",", "").replace("元", ""))
        except (TypeError, ValueError):
            amt = None

        if t:
            times.append(t)
            is_late = t.hour >= 22 or t.hour < 5
            hour_hist[t.hour] += 1
            timeline.append((t, is_late))
            if is_late:
                late_count += 1
        if amt is not None:
            amounts.append(amt)

        store = od.get("storeName") or od.get("store") or od.get("restaurantName")
        if store:
            store_counter[str(store)] = store_counter.get(str(store), 0) + 1

        items = (od.get("orderProductList") or od.get("items")
                 or od.get("products") or od.get("orderItems")
                 or od.get("mealList") or od.get("details") or [])
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    nm = (it.get("productName") or it.get("name")
                          or it.get("mealName") or it.get("itemName")
                          or it.get("skuName"))
                    qty = it.get("quantity") or it.get("qty") or it.get("count") or 1
                    try:
                        qty = int(qty)
                    except (TypeError, ValueError):
                        qty = 1
                    sub = it.get("comboItemList")
                    names = [str(nm)] if nm else []
                    if isinstance(sub, list):
                        for s in sub:
                            if isinstance(s, dict):
                                n = s.get("name") or s.get("itemName")
                                if n:
                                    names.append(str(n))
                elif isinstance(it, str):
                    names, qty = [it], 1
                else:
                    continue
                for n in names:
                    cat_counter[_categorize(n)] = cat_counter.get(_categorize(n), 0) + 1
                    item_counter[n] = item_counter.get(n, 0) + max(qty, 1)
                    if n in nutri:
                        kcal_total += nutri[n] * max(qty, 1)
                        kcal_matched += 1

    times.sort()
    gaps: list[float] = []
    for a, b in zip(times, times[1:]):
        d = (b - a).total_seconds() / 86400.0
        if d > 0:
            gaps.append(d)

    # 最长连续下单天数
    streak, best_streak = 1, 0
    day_list = sorted({t.date() for t in times})
    for prev, cur in zip(day_list, day_list[1:]):
        if (cur - prev).days == 1:
            streak += 1
        else:
            streak = 1
        best_streak = max(best_streak, streak)
    if day_list:
        best_streak = max(best_streak, 1)

    # 券结构
    total_coupons = len(coupons or [])
    expiring_coupons = 0
    for c in coupons or []:
        if not isinstance(c, dict):
            continue
        exp = (c.get("expireTime") or c.get("endTime") or c.get("validEndTime")
               or c.get("expiryDate") or c.get("endDate"))
        et = _parse_time(exp)
        if et and 0 <= (et - now).days <= 7:
            expiring_coupons += 1

    # 积分结构
    avail = frozen = expiring_pts = None
    if isinstance(account, dict):
        def _num(*keys):
            for k in keys:
                v = account.get(k)
                if v not in (None, ""):
                    try:
                        return float(str(v).replace(",", ""))
                    except ValueError:
                        continue
            return None
        avail = _num("availablePoints", "available", "points", "usablePoints")
        frozen = _num("frozenPoints", "frozen")
        expiring_pts = _num("expiringPoints", "expirePoints", "willExpirePoints")

    return {
        "order_count": len(times),
        "times": times,
        "amounts": amounts,
        "gap_cv": _cv(gaps),
        "avg_gap": (sum(gaps) / len(gaps)) if gaps else None,
        "amount_cv": _cv(amounts),
        "avg_amount": (sum(amounts) / len(amounts)) if amounts else None,
        "total_amount": sum(amounts) if amounts else None,
        "max_amount": max(amounts) if amounts else None,
        "late_ratio": (late_count / len(times)) if times else None,
        "late_count": late_count,
        "store_hhi": _hhi(store_counter) if store_counter else None,
        "cat_hhi": _hhi(cat_counter) if cat_counter else None,
        "store_count": len(store_counter),
        "top_store": max(store_counter, key=store_counter.get) if store_counter else None,
        "top_item": max(item_counter, key=item_counter.get) if item_counter else None,
        "top_item_count": max(item_counter.values()) if item_counter else 0,
        "cat_counter": cat_counter,
        "avg_kcal": (kcal_total / len(times)) if (times and kcal_matched) else None,
        "kcal_matched": kcal_matched,
        "best_streak": best_streak if times else None,
        "tenure_days": ((times[-1] - times[0]).days + 1) if len(times) >= 2 else None,
        "total_coupons": total_coupons,
        "expiring_coupons": expiring_coupons,
        "avail_points": avail,
        "frozen_points": frozen,
        "expiring_points": expiring_pts,
        "first_order": times[0] if times else None,
        "last_order": times[-1] if times else None,
        "hour_hist": hour_hist,
        "timeline": _normalize_timeline(timeline),
        "peak_hour": max(range(24), key=lambda h: hour_hist[h]) if sum(hour_hist) else None,
    }


def _normalize_timeline(timeline: list[tuple]) -> list[tuple]:
    """把订单时间归一化到 0.0–1.0，供报告画时间轴。样本 <2 时无法归一化。"""
    if len(timeline) < 2:
        return []
    ts = [t for t, _ in timeline]
    lo, hi = min(ts), max(ts)
    span = (hi - lo).total_seconds()
    if span <= 0:
        return [(0.5, late) for _, late in timeline]
    return [(((t - lo).total_seconds() / span), late) for t, late in timeline]


# ---------------------------------------------------------------- 评分层

def _score_stability(f: dict) -> tuple[int, str]:
    """合规性 × 节奏健康度，各占一半。

    只看规律性会掉进一个坑：每天吃麦当劳的变异系数接近 0，会被判成"极稳定=优质"，
    但高频依赖在授信逻辑里是共债风险，不是稳定性。所以必须同时看平均间隔。
    """
    cv, gap = f["gap_cv"], f["avg_gap"]
    regular = _bin_score(cv, [(1.5, 25), (1.0, 45), (0.7, 65), (0.4, 80), (0.0, 95)], neutral=60)
    rhythm = _bin_score(gap, [(14, 70), (7, 95), (3, 80), (1.5, 45), (0.0, 25)], neutral=60)
    s = int(round(regular * 0.5 + rhythm * 0.5))

    if cv is None:
        r_note = "规律性样本不足，给中性分"
    elif cv < 0.4:
        r_note = f"间隔变异 {cv:.2f}，节律可预测"
    elif cv < 1.0:
        r_note = f"间隔变异 {cv:.2f}，偶有波动"
    else:
        r_note = f"间隔变异 {cv:.2f}，下单随机"
    if gap is None:
        g_note = "节奏样本不足"
    elif gap < 1.5:
        g_note = f"平均 {gap:.1f} 天一单，高频依赖，扣分项"
    elif gap < 3:
        g_note = f"平均 {gap:.1f} 天一单，频次偏高"
    elif gap < 7:
        g_note = f"平均 {gap:.1f} 天一单，节奏正常"
    elif gap < 14:
        g_note = f"平均 {gap:.1f} 天一单，节奏健康"
    else:
        g_note = f"平均 {gap:.1f} 天一单，频次稀疏"
    return s, f"{r_note}；{g_note}"


def _score_budget(f: dict) -> tuple[int, str]:
    cv = f["amount_cv"]
    s = _bin_score(cv, [(1.2, 30), (0.8, 45), (0.5, 62), (0.3, 78), (0.0, 90)], neutral=60)
    avg = f["avg_amount"]
    if cv is None:
        note = "金额样本不足，给中性分"
    elif cv < 0.3:
        note = f"单笔金额变异 {cv:.2f}，预算约束强，几乎不冲动加购"
    elif cv < 0.8:
        note = f"单笔金额变异 {cv:.2f}，偶有大额，尚在合理区间"
    else:
        note = f"单笔金额变异 {cv:.2f}，消费金额大幅跳动，冲动特征明显"
    # 金额稳定是预算意识强的信号，但绝对水平过高本身也是负担
    if avg is not None:
        if avg > 60:
            s -= 10
        elif avg > 45:
            s -= 5
        s = max(5, min(100, s))
        note += f"；单均 ¥{avg:.1f}"
    return s, note


def _score_discipline(f: dict) -> tuple[int, str]:
    late = f["late_ratio"] or 0.0
    kcal = f["avg_kcal"]
    s = 100.0 - 55.0 * late
    if kcal is not None:
        if kcal > 1200:
            s -= 25
        elif kcal > 800:
            s -= 15
        elif kcal > 500:
            s -= 8
    s = max(5, min(100, int(round(s))))
    parts = []
    if f["late_count"]:
        parts.append(f"深夜（22:00-05:00）下单 {f['late_count']} 笔，占比 {late:.0%}")
    else:
        parts.append("无深夜订单")
    if kcal is not None:
        parts.append(f"单均约 {kcal:.0f} kcal")
    else:
        parts.append("热量数据未匹配到营养表，该子项不计分")
    return s, "；".join(parts)


def _score_concentration(f: dict) -> tuple[int, str]:
    sh, ch = f["store_hhi"], f["cat_hhi"]
    if sh is None and ch is None:
        return 60, "门店与品类数据不足，给中性分"
    vals = [v for v in (sh, ch) if v is not None]
    hhi = sum(vals) / len(vals)
    # U 型：既不鼓励孤注一掷，也不鼓励毫无忠诚
    if 0.25 <= hhi <= 0.60:
        s = 90
        note = f"综合集中度 {hhi:.2f}，有固定偏好又保留弹性，最健康"
    elif 0.60 < hhi <= 0.80 or 0.15 <= hhi < 0.25:
        s = 70
        note = f"综合集中度 {hhi:.2f}，略偏一端"
    elif hhi > 0.80:
        s = 60
        note = f"综合集中度 {hhi:.2f}，过度集中于单一门店/品类，单点依赖风险"
    else:
        s = 50
        note = f"综合集中度 {hhi:.2f}，分布过于分散，缺乏稳定偏好"
    return s, note


def _score_asset(f: dict) -> tuple[int, str]:
    rates = []
    if f["avail_points"] and f["expiring_points"] is not None and f["avail_points"] > 0:
        rates.append(f["expiring_points"] / f["avail_points"])
    if f["total_coupons"]:
        rates.append(f["expiring_coupons"] / f["total_coupons"])
    if not rates:
        return 65, "未获取到积分或券数据，该维度给中性分"
    r = max(rates)
    s = _bin_score(r, [(0.7, 20), (0.5, 38), (0.3, 55), (0.1, 75), (0.0, 92)], neutral=65)
    detail = []
    if f["expiring_points"] is not None:
        detail.append(f"即将过期积分 {f['expiring_points']:.0f}")
    if f["total_coupons"]:
        detail.append(f"在手券 {f['total_coupons']} 张，其中 7 日内到期 {f['expiring_coupons']} 张")
    detail.append(f"综合沉睡率 {r:.0%}")
    return s, "；".join(detail)


SCORERS = {
    "stability": _score_stability,
    "budget": _score_budget,
    "discipline": _score_discipline,
    "concentration": _score_concentration,
    "asset": _score_asset,
}


def build_scorecard(f: dict) -> dict:
    dims = {}
    for key, fn in SCORERS.items():
        score, note = fn(f)
        title, desc = DIMENSION_META[key]
        dims[key] = {
            "key": key,
            "title": title,
            "desc": desc,
            "score": score,
            "weight": WEIGHTS[key],
            "note": note,
        }
    weighted = sum(d["score"] * d["weight"] for d in dims.values())
    final = int(round(300 + weighted / 100.0 * 600))
    final = max(300, min(900, final))
    rating, band_name, decision = "C", "高风险", "建议拒件"
    for threshold, r, bn, dec in RATING_BANDS:
        if final >= threshold:
            rating, band_name, decision = r, bn, dec
            break

    # 白户（Thin File）：样本太少时不做判人性结论，这是授信的基本纪律
    thin = f["order_count"] < 5 or (f["tenure_days"] or 0) < 14
    if thin:
        decision = "样本不足 · 暂不评级（白户）"

    return {
        "dimensions": dims,
        "weighted": round(weighted, 1),
        "score": final,
        "rating": rating,
        "band": band_name,
        "decision": decision,
        "thin_file": thin,
        "events": build_events(f),
    }


def build_events(f: dict) -> list[dict]:
    """风险事件流水。每条都有真实数据支撑，编不出来的不写。"""
    ev = []
    if f["late_count"]:
        ev.append({
            "level": "high" if (f["late_ratio"] or 0) >= 0.3 else "mid",
            "code": "LATE-NIGHT",
            "text": f"深夜时段下单 {f['late_count']} 笔，占比 {f['late_ratio']:.0%}",
            "action": "建议将 22:00 后的加餐纳入月度预算",
        })
    if f["best_streak"] and f["best_streak"] >= 3:
        ev.append({
            "level": "mid",
            "code": "STREAK",
            "text": f"最长连续 {f['best_streak']} 天下单",
            "action": "连续性偏高，注意是否形成依赖",
        })
    if f["expiring_points"]:
        ev.append({
            "level": "high",
            "code": "DORMANT-POINTS",
            "text": f"有 {f['expiring_points']:.0f} 积分即将过期",
            "action": "过期前兑换，属于典型的资产减值",
        })
    if f["expiring_coupons"]:
        ev.append({
            "level": "mid",
            "code": "COUPON-EXPIRY",
            "text": f"{f['expiring_coupons']} 张券将在 7 日内失效",
            "action": "优先核销临期券，避免时间价值归零",
        })
    avg, mx, cv = f["avg_amount"], f["max_amount"], f["amount_cv"]
    if avg and mx and mx > avg * 2.5:
        ev.append({
            "level": "mid",
            "code": "AMOUNT-SPIKE",
            "text": f"单笔最高 ¥{mx:.1f}，为单均 ¥{avg:.1f} 的 {mx / avg:.1f} 倍",
            "action": "大额异动，可能来自团餐或多人拼单",
        })
    if f["store_count"] and f["store_count"] >= 5:
        ev.append({
            "level": "low",
            "code": "STORE-DRIFT",
            "text": f"涉及 {f['store_count']} 家不同门店",
            "action": "门店漂移，忠诚度信号偏弱",
        })
    if f["cat_hhi"] and f["cat_hhi"] > 0.7:
        top = max(f["cat_counter"], key=f["cat_counter"].get) if f["cat_counter"] else "未知"
        ev.append({
            "level": "low",
            "code": "CATEGORY-LOCK",
            "text": f"品类高度集中于「{top}」",
            "action": "结构单一，可尝试扩展搭配",
        })
    if not ev:
        ev.append({
            "level": "low",
            "code": "CLEAN",
            "text": "未触发任何风险规则",
            "action": "保持当前消费节律",
        })
    return ev
