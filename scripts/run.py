"""麦险分主入口

用法：
    python run.py --mock              # 离线演示，无需 Token，全流程跑通
    python run.py --live              # 接真实 MCP（需 MCD_MCP_TOKEN）
    python run.py --live --out r.html # 指定报告落盘路径
    python run.py --mock --json       # 只输出结构化结果，不生成 HTML

铁律：本程序全程只读。不创建订单、不取消订单、不兑换商品、不抽奖、不领券。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import mcp_client, mock_data, report, scoring  # noqa: E402


def collect_live(client) -> dict:
    """按顺序拉只读数据。任一步失败不整体崩，缺什么后面走中性分。"""
    out = {"is_mock": False}
    tools = [
        ("orders", "order-list", {}),
        ("account", "query-my-account", {}),
        ("coupons", "query-my-coupons", {}),
        ("nutrition", "list-nutrition-foods", {}),
    ]
    for key, tool, args in tools:
        try:
            out[key] = client.call(tool, args)
            print(f"  [ok]   {tool}")
        except mcp_client.McpError as e:
            print(f"  [warn] {tool} 拉取失败：{e}", file=sys.stderr)
            out[key] = [] if key in ("orders", "coupons", "nutrition") else None
    # order-list 可能包在 {list: [...]} 里
    if isinstance(out.get("orders"), dict):
        for k in ("list", "orders", "items", "records", "data"):
            if isinstance(out["orders"].get(k), list):
                out["orders"] = out["orders"][k]
                break
    if isinstance(out.get("coupons"), dict):
        for k in ("list", "coupons", "items", "data"):
            if isinstance(out["coupons"].get(k), list):
                out["coupons"] = out["coupons"][k]
                break
    if isinstance(out.get("nutrition"), dict):
        for k in ("list", "foods", "items", "data"):
            if isinstance(out["nutrition"].get(k), list):
                out["nutrition"] = out["nutrition"][k]
                break
    out["now"] = datetime.now()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="麦险分 · 麦当劳个人餐饮信用评分")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true", help="接真实 MCP（需 MCD_MCP_TOKEN）")
    g.add_argument("--mock", action="store_true", help="离线演示数据，无需 Token")
    ap.add_argument("--token", help="显式传入 Token（不推荐，会进 shell history）")
    ap.add_argument("--out", help="报告 HTML 落盘路径，默认系统临时目录")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON，不生成 HTML")
    args = ap.parse_args()

    if args.mock:
        print("模式：离线演示（DEMO DATA，固定种子 1024，非真实账号数据）")
        data = mock_data.build_mock()
        now = datetime.now()
    else:
        print("模式：真实 MCP（只读）")
        try:
            client = mcp_client.McpClient(token=args.token)
        except mcp_client.McpError as e:
            print(f"启动失败：{e}", file=sys.stderr)
            return 2
        data = collect_live(client)
        now = data.pop("now", datetime.now())

    f = scoring.extract_features(
        data.get("orders") or [],
        data.get("account"),
        data.get("coupons") or [],
        data.get("nutrition") or [],
        now=now,
    )
    if f["order_count"] == 0:
        print("未取到任何订单，无法评分。请确认 Token 有效且账号有历史订单。", file=sys.stderr)
        return 3

    card = scoring.build_scorecard(f)

    if args.json:
        print(json.dumps({"features": {k: str(v) for k, v in f.items()},
                          "card": card}, ensure_ascii=False, indent=2))
        return 0

    path = report.write_report(f, card, bool(data.get("is_mock")), args.out)

    print()
    print("=" * 52)
    print(f"  麦险分   {card['score']}    评级 {card['rating']} · {card['band']}")
    print(f"  审批结论 {card['decision']}")
    print(f"  样本     {f['order_count']} 笔订单 / 观察窗 "
          f"{f['tenure_days'] if f['tenure_days'] else '不足'} 天")
    print("=" * 52)
    for d in card["dimensions"].values():
        print(f"  {d['title']:<8} {d['score']:>3}  ×{int(d['weight'] * 100)}%   {d['note']}")
    print("-" * 52)
    print(f"  报告已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
