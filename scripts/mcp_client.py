"""麦当劳 MCP 客户端（仅标准库）

设计约束：
1. 只读。本模块只暴露 READ_ONLY_TOOLS 白名单里的工具，任何写实工具
   （create-order / cancel-order / mall-create-order / party-order-create /
   draw-lottery / auto-bind-coupons / delivery-create-address）在协议层就被拒绝。
2. Token 不落盘。只从环境变量 MCD_MCP_TOKEN 或显式 --token 注入，
   错误信息中绝不回显 token。
3. 响应双兼容：官方 Server 可能返回普通 JSON，也可能返回 SSE 流，两种都要能解析。
4. 优先读 structuredContent，退回从 content[].text 里抠 JSON。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

MCP_URL = "https://mcp.mcd.cn"

# 写实工具黑名单：调用即拒绝，不给任何绕过路径
WRITE_TOOLS = {
    "create-order",
    "cancel-order",
    "mall-create-order",
    "party-order-create",
    "draw-lottery",
    "auto-bind-coupons",
    "delivery-create-address",
}

# 本 Skill 实际用到的只读工具
READ_ONLY_TOOLS = {
    "order-list",
    "query-my-account",
    "query-my-coupons",
    "query-my-prizes",
    "mall-order-list",
    "list-nutrition-foods",
    "campaign-calendar",
    "available-coupons",
    "now-time-info",
}


class McpError(Exception):
    """带分类的错误，message 中绝不出现 token。"""

    def __init__(self, kind: str, message: str):
        super().__init__(f"[{kind}] {message}")
        self.kind = kind


class McpClient:
    def __init__(self, token: str | None = None, timeout: int = 15):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "").strip()
        if not self.token:
            raise McpError(
                "TOKEN_MISSING",
                "未拿到 MCP Token。请设置环境变量 MCD_MCP_TOKEN，或改用 --mock 跑离线演示。"
                "申请入口：https://open.mcd.cn/mcp",
            )
        self.timeout = timeout
        self.session_id: str | None = None
        self._req_id = 0

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            MCP_URL, data=body, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # 会话 ID 需要复用，否则部分工具会拒答
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise McpError("TOKEN_INVALID", f"HTTP {e.code}：Token 无效或已过期")
            if e.code == 429:
                raise McpError("RATE_LIMIT", "HTTP 429：超过 600 次/分钟，请放慢调用")
            raise McpError("HTTP", f"HTTP {e.code}")
        except urllib.error.URLError as e:
            raise McpError("NETWORK", f"网络不可达：{e.reason}")
        except TimeoutError:
            raise McpError("TIMEOUT", f"请求超时（{self.timeout}s）")
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> dict:
        """SSE 与裸 JSON 双兼容。"""
        # SSE：取最后一个 data: 行
        if "event:" in raw or raw.lstrip().startswith("data:"):
            datas = [
                ln[5:].strip()
                for ln in raw.splitlines()
                if ln.strip().startswith("data:")
            ]
            if not datas:
                raise McpError("BAD_RESPONSE", "SSE 响应中没有 data 段")
            raw = datas[-1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise McpError("BAD_RESPONSE", "响应不是合法 JSON")

    def call(self, tool: str, arguments: dict | None = None, retries: int = 1) -> dict:
        if tool in WRITE_TOOLS:
            raise McpError("WRITE_BLOCKED", f"{tool} 是写实工具，本 Skill 只读，拒绝调用")
        if tool not in READ_ONLY_TOOLS:
            raise McpError("TOOL_DENIED", f"{tool} 不在只读白名单内")
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments or {}},
        }
        for attempt in range(retries + 1):
            resp = self._post(payload)
            if "error" in resp:
                err = resp["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                raise McpError("TOOL_ERROR", f"{tool}：{msg}")
            result = resp.get("result", resp)
            if result.get("isError"):
                raise McpError("TOOL_ERROR", f"{tool} 返回 isError")
            data = result.get("structuredContent")
            if data is None:
                data = _json_from_text(result.get("content"))
            if data is None:
                raise McpError("NO_DATA", f"{tool} 未返回 structuredContent，且无法从文本解析")
            return unwrap(data)
        raise McpError("RETRY_EXHAUSTED", f"{tool} 重试后仍失败")


def _json_from_text(content) -> dict | None:
    """从 content[].text 里抠出 JSON（官方会在文本里夹 Markdown + JSON）。"""
    if not isinstance(content, list):
        return None
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        # 先试整段
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 再试最大的一个 {...} 块
        for m in re.finditer(r"\{[\s\S]*\}", text):
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None


def unwrap(data):
    """官方统一包成 {success, code, message, data}，这里剥到 data。"""
    if isinstance(data, dict) and "success" in data and "data" in data:
        if not data.get("success"):
            raise McpError("BIZ_FAIL", f"{data.get('code')} {data.get('message')}".strip())
        return data.get("data")
    return data


# ---------- 字段容错映射 ----------
# 官方未公开 JSON Schema，同样的业务含义在不同工具里字段名不一致。
# 这里按「任一命中即可」做映射，宁可慢，不可猜。

FIELD_ALIASES = {
    "order_id": ("orderId", "orderNo", "id", "order_id"),
    "create_time": ("createTime", "orderTime", "time", "createdAt", "create_time"),
    "pay_amount": (
        "realTotalAmount",
        "payAmount",
        "actualAmount",
        "totalAmount",
        "amount",
        "pay_amount",
    ),
    "products": (
        "orderProductList",
        "items",
        "products",
        "orderItems",
        "mealList",
        "details",
    ),
    "product_name": ("productName", "name", "mealName", "itemName", "skuName"),
    "quantity": ("quantity", "itemQuantity", "qty", "num", "count"),
    "store_name": ("storeName", "store", "restaurantName", "store_name"),
    "channel": ("takeWay", "orderType", "channel", "deliveryType"),
}


def pick(obj: dict, key: str, default=None):
    """按别名表从对象里取字段，取不到返回 default（绝不猜）。"""
    if not isinstance(obj, dict):
        return default
    for alias in FIELD_ALIASES.get(key, (key,)):
        if alias in obj and obj[alias] not in (None, ""):
            return obj[alias]
    return default


def to_float(v, default=0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("¥", "").replace(",", "").replace("元", "")
    try:
        return float(s)
    except ValueError:
        return default
