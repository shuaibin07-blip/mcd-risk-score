# MCP 集成说明

> 参赛作品，非麦当劳官方产品。

## 接入的 MCP Server

| 项 | 值 |
|---|---|
| 名称 | `mcd-mcp`（麦当劳中国 MCP Server） |
| 地址 | `https://mcp.mcd.cn` |
| 协议 | Streamable HTTP（JSON-RPC 2.0） |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}` |
| 限流 | 600 次 / 分钟（超限返回 429） |

配置文件见 [`mcp-config.example.json`](mcp-config.example.json)，**仅含环境变量占位符，不含真实 Token**。

## 实际使用的 Tool

本项目**只使用只读工具**。下表 4 个是数据输入源：

| Tool | 用途 | 用于哪些维度 |
|---|---|---|
| `order-list` | 历史到店/外送订单 | 履约稳定性、预算约束力、自律度、集中度 |
| `query-my-account` | 积分（可用 / 累计 / 冻结 / **即将过期**） | 资产健康度 |
| `query-my-coupons` | 在手优惠券及有效期 | 资产健康度 |
| `list-nutrition-foods` | 餐品营养成分（能量等） | 自律度（热量子项） |

### 被显式拒绝的写实工具

以下 7 个工具会真实产生后果，**在 `scripts/mcp_client.py` 的 `WRITE_TOOLS` 黑名单中，
协议层直接抛 `WRITE_BLOCKED` 拒绝，没有环境变量开关、没有绕过路径**：

```
create-order            创建点餐订单
cancel-order            取消订单
mall-create-order       积分兑换下单
party-order-create      主题活动下单
draw-lottery            积分抽奖
auto-bind-coupons       一键领券
delivery-create-address 新增配送地址
```

防的不是恶意，是误触发。Agent 自动下单一次就是真钱出去，责任说不清。

## 调用流程

```
run.py
  └─ McpClient.call(tool, args)
       ├─ 白名单校验（不在 READ_ONLY_TOOLS 直接拒）
       ├─ POST https://mcp.mcd.cn
       │    headers: Authorization / Content-Type / Accept: application/json, text/event-stream
       │    body:    {"jsonrpc":"2.0","id":n,"method":"tools/call",
       │              "params":{"name":"order-list","arguments":{}}}
       ├─ 响应解析：SSE 与裸 JSON 双兼容，复用 Mcp-Session-Id
       ├─ 优先读 result.structuredContent，退回从 content[].text 抠 JSON
       └─ unwrap: {success, code, message, data} → data
  └─ scoring.extract_features(orders, account, coupons, nutrition)
       └─ scoring.build_scorecard(features)  → 五维分 + 评级 + 风险事件
  └─ report.write_report(...)  → 单文件 HTML
```

## 字段容错

官方未公开 JSON Schema，同一业务含义在不同响应里字段名不一致。
`mcp_client.FIELD_ALIASES` 按「任一命中即可」做映射，取不到返回 `None` 走中性分，**绝不猜字段含义**：

| 业务含义 | 实际见过的字段名 |
|---|---|
| 订单 ID | `orderId` / `orderNo` / `id` |
| 下单时间 | `createTime` / `orderTime` / `time` / `createdAt` |
| 实付金额 | `realTotalAmount` / `payAmount` / `actualAmount` / `totalAmount` / `amount` |
| 商品列表 | `orderProductList` / `items` / `products` / `orderItems` / `mealList` / `details` |
| 商品名 | `productName` / `name` / `mealName` / `itemName` / `skuName` |
| 数量 | `quantity` / `itemQuantity` / `qty` / `num` / `count` |
| 门店名 | `storeName` / `store` / `restaurantName` |
| 渠道 | `takeWay` / `orderType` / `deliveryType` |

## 业务价值

1. **对用户**：把零散的消费记录变成一份可理解的自我观察报告——深夜加餐频率、
   沉睡的积分和临期券、消费集中度，这些平时没人会自己算。
2. **对 MCP 生态**：示范了一条「只读数据 + 专业方法论」的 Skill 路径。
   不需要下单能力也能做出有深度的作品，且用户零顾虑。
3. **对风控场景**：证明评分卡方法论可以迁移到消费行为分析，
   特征工程、分箱、权重、U 型曲线这些授信模型的构件在这里同样成立。

## 隐私

- Token 只从环境变量 `MCD_MCP_TOKEN` 读取，不写入任何文件，报错信息不回显。
- 报告含个人消费数据，默认落盘到系统临时目录，不进仓库（`.gitignore` 已排除）。
- 全程只读：不创建/取消订单，不消耗积分，不领取优惠券，不抽奖。
