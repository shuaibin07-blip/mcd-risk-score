"""麦险分报告卡生成器（单文件 HTML，无外部依赖）

黑金信贷终端风：深色底 + 麦当劳金 accent + 金属降级评级色（金→银→铜→铁锈）。
字体全部走系统栈，断网也不会塌。
"""

from __future__ import annotations

import html
import os
import tempfile
from datetime import datetime

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0B0E14;color:#E6EDF3;padding:28px 16px;
 font-family:ui-monospace,"Cascadia Code","SF Mono",Menlo,Consolas,
 "PingFang SC","Microsoft YaHei",monospace;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto}

.hd{display:flex;justify-content:space-between;align-items:flex-end;
 border-bottom:1px solid #232B3A;padding-bottom:14px;margin-bottom:22px;
 flex-wrap:wrap;gap:10px;position:relative}
.hd:after{content:"";position:absolute;left:0;bottom:-1px;width:96px;height:2px;background:#FFC72C}
.hd h1{font-size:19px;font-weight:600;letter-spacing:.06em}
.hd .sub{font-size:12px;color:#7D8899;margin-top:4px}
.meta{font-size:11px;color:#7D8899;text-align:right;line-height:1.8}
.badge{display:inline-block;padding:2px 8px;border:1px solid #30363D;border-radius:3px;
 font-size:10px;letter-spacing:.1em;color:#7D8899}
.badge.live{border-color:#FFC72C;color:#FFC72C}
.badge.demo{border-color:#8B949E;color:#8B949E}

.hero{display:flex;gap:34px;align-items:center;background:#131822;
 border:1px solid #232B3A;border-radius:10px;padding:26px 28px;flex-wrap:wrap}
.scoreWrap{position:relative;padding-right:96px}
.scoreNum{font-size:96px;font-weight:700;line-height:.92;letter-spacing:-.03em}
.scoreLbl{font-size:11px;color:#7D8899;letter-spacing:.24em;margin-top:8px}
.stamp{position:absolute;top:-4px;right:0;border:2px solid currentColor;
 border-radius:8px;padding:6px 11px;transform:rotate(-7deg);text-align:center;opacity:.95}
.stamp .r{font-size:22px;font-weight:700;letter-spacing:.04em}
.stamp .b{font-size:10px;letter-spacing:.1em;opacity:.85;margin-top:1px;white-space:nowrap}
.heroR{flex:1;min-width:250px}
.dec{font-size:18px;font-weight:600;margin-bottom:5px}
.decSub{font-size:12px;color:#7D8899;margin-bottom:16px}
.bar{height:8px;background:#1C2331;border-radius:4px;position:relative}
.bar .fill{height:100%;border-radius:4px}
.bar .mk{position:absolute;top:-5px;width:2px;height:18px;background:#E6EDF3;border-radius:1px}
.bar .tk{position:absolute;top:-3px;width:1px;height:14px;background:#4A5468}
.barScl{display:flex;justify-content:space-between;font-size:10px;color:#586069;margin-top:6px}

.insight{background:rgba(255,199,44,.07);border:1px solid rgba(255,199,44,.32);
 border-left:3px solid #FFC72C;border-radius:8px;padding:15px 18px;margin-top:14px}
.insightTag{display:inline-block;font-size:10px;letter-spacing:.14em;color:#FFC72C;
 border:1px solid rgba(255,199,44,.4);border-radius:3px;padding:1px 7px;margin-right:10px}
.insightText{font-size:14px;color:#E6EDF3}

.warn{background:rgba(210,153,34,.1);border:1px solid rgba(210,153,34,.4);
 border-radius:8px;padding:12px 16px;margin-top:14px;font-size:12px;color:#D29922;line-height:1.7}
.warn b{font-weight:600}

.sec{background:#131822;border:1px solid #232B3A;border-radius:10px;padding:20px 24px;margin-top:16px}
.sec h2{font-size:12px;font-weight:600;letter-spacing:.16em;color:#FFC72C;
 margin-bottom:16px;padding-bottom:9px;border-bottom:1px solid #232B3A}

.hours{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;align-items:end;height:52px}
.hours i{display:block;background:#FFC72C;border-radius:1px 1px 0 0;min-height:2px;opacity:.9}
.hours i.late{background:#E5484D}
.hours i.zero{background:#232B3A;opacity:1}
.hAxis{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;margin-top:6px}
.hAxis span{font-size:10px;color:#586069;text-align:center}
.hNote{font-size:11px;color:#8B949E;margin-top:12px}

.tl{position:relative;height:60px;margin-top:4px}
.tlLine{position:absolute;top:26px;left:0;right:0;height:1px;background:#232B3A}
.tl i{position:absolute;top:23px;width:7px;height:7px;border-radius:50%;margin-left:-3.5px}
.tl i.n{background:#39414F}
.tl i.l{background:#E5484D}
.tlLab{display:flex;justify-content:space-between;font-size:11px;color:#7D8899;margin-top:2px}

.dim{margin-bottom:16px}
.dim:last-child{margin-bottom:0}
.dimT{display:flex;justify-content:space-between;align-items:baseline;
 font-size:13px;margin-bottom:6px;gap:10px}
.dimT .n{font-weight:600}
.dimT .w{font-size:10px;color:#586069;letter-spacing:.06em}
.dimT .s{font-weight:700;font-variant-numeric:tabular-nums}
.tag{font-size:9px;letter-spacing:.1em;padding:1px 5px;border-radius:3px;margin-left:7px;
 border:1px solid #E5484D;color:#E5484D}
.dimB{height:10px;background:#1C2331;border-radius:5px;position:relative;overflow:hidden}
.dimB i{display:block;height:100%;border-radius:5px}
.dimB .nt{position:absolute;top:-2px;width:1px;height:14px;background:#586069}
.dimN{font-size:11px;color:#8B949E;margin-top:6px}
.dim.weak{background:rgba(229,72,77,.05);border-left:2px solid #E5484D;
 margin-left:-12px;padding:8px 0 8px 10px;border-radius:0 6px 6px 0}

.big3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px}
.kpiBig{background:#0E131B;border:1px solid #2A3341;border-radius:8px;padding:16px 17px}
.kpiBig .k{font-size:10px;color:#7D8899;letter-spacing:.08em;margin-bottom:7px}
.kpiBig .v{font-size:30px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.1}
.kpiBig .u{font-size:12px;color:#7D8899;font-weight:400;margin-left:3px}
.kpiBig.gold .v{color:#FFC72C}
.small{display:grid;grid-template-columns:repeat(auto-fit,minmax(126px,1fr));gap:10px 16px;
 border-top:1px solid #1E2530;padding-top:14px}
.sm{display:flex;justify-content:space-between;font-size:12px;padding:3px 0}
.sm .k{color:#7D8899}
.sm .v{font-variant-numeric:tabular-nums;color:#C9D1D9}
.sm .v.warnv{color:#E5484D}

table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;font-size:10px;color:#7D8899;letter-spacing:.1em;font-weight:500;
 padding:0 10px 9px 0;border-bottom:1px solid #232B3A}
td{padding:11px 10px 11px 0;border-bottom:1px solid #1A2029;vertical-align:top}
tr:last-child td{border-bottom:none}
.lv{display:inline-block;width:44px;text-align:center;font-size:9px;padding:2px 0;
 border-radius:3px;letter-spacing:.08em;font-weight:600}
.lv.high{background:rgba(229,72,77,.16);color:#E5484D;border:1px solid rgba(229,72,77,.35)}
.lv.mid{background:rgba(255,199,44,.14);color:#FFC72C;border:1px solid rgba(255,199,44,.32)}
.lv.low{background:rgba(139,148,158,.14);color:#8B949E;border:1px solid rgba(139,148,158,.3)}
.code{font-size:11px;letter-spacing:.05em;color:#C9D1D9}
.act{font-size:11px;color:#7D8899}
.evText{font-size:12px;color:#C9D1D9}

.ft{font-size:10.5px;color:#586069;line-height:1.9;padding:16px 4px 0;
 border-top:1px solid #232B3A;margin-top:20px}
.ft b{color:#8B949E;font-weight:500}

@media(max-width:600px){
 .scoreNum{font-size:68px}.scoreWrap{padding-right:82px}
 .hero{padding:20px;gap:20px}.sec{padding:16px 17px}
 .meta{text-align:left}.big3{grid-template-columns:1fr}
}
@media print{body{background:#fff;color:#111}.sec,.hero{background:#fff;border-color:#ccc}}
"""

TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦险分 · 个人餐饮信用报告</title>
<style>__CSS__</style></head>
<body><div class="wrap">

<div class="hd">
  <div>
    <h1>MCD RISK SCORE · 个人餐饮信用报告</h1>
    <div class="sub">MCDONALD'S CONSUMPTION CREDIT ASSESSMENT &nbsp;/&nbsp; v1.0</div>
  </div>
  <div class="meta">
    REF NO. __REF__<br>
    生成时间 __TS__<br>
    <span class="badge __BADGECLS__">__BADGE__</span>
  </div>
</div>

<div class="hero">
  <div class="scoreWrap">
    <div class="scoreNum" style="color:__COLOR__">__SCORE__</div>
    <div class="scoreLbl">麦 险 分</div>
    <div class="stamp" style="color:__COLOR__">
      <div class="r">__RATING__</div>
      <div class="b">__BAND__</div>
    </div>
  </div>
  <div class="heroR">
    <div class="dec" style="color:__COLOR__">审批结论：__DECISION__</div>
    <div class="decSub">综合分 __WEIGHTED__ / 100 · 样本 __N__ 笔订单</div>
    <div class="bar">
      <div class="fill" style="width:__PCT__%;background:__COLOR__"></div>
      <div class="tk" style="left:60%"></div>
      <div class="mk" style="left:__PCT__%"></div>
    </div>
    <div class="barScl"><span>300</span><span>660 中性</span><span>900</span></div>
  </div>
</div>

<div class="insight">
  <span class="insightTag">关键发现</span>
  <span class="insightText">__INSIGHT__</span>
</div>

__WARN__

<div class="sec">
  <h2>24 小 时 下 单 分 布 / HOURLY PATTERN</h2>
  <div class="hours">__HOURS__</div>
  <div class="hAxis">__HAXIS__</div>
  <div class="hNote">__HNOTE__</div>
</div>

<div class="sec">
  <h2>麦 龄 时 间 轴 / TENURE TIMELINE</h2>
  <div class="tl"><div class="tlLine"></div>__DOTS__</div>
  <div class="tlLab"><span>首单 __FIRST__</span><span>麦龄 __TENURE__</span><span>最近 __LAST__</span></div>
</div>

<div class="sec">
  <h2>五 维 评 分 卡 / SCORECARD</h2>
  __DIMS__
</div>

<div class="sec">
  <h2>关 键 指 标 / KEY METRICS</h2>
  <div class="big3">__BIG3__</div>
  <div class="small">__SMALL__</div>
</div>

<div class="sec">
  <h2>风 险 事 件 流 水 / RISK EVENT LOG</h2>
  <table>
    <tr><th style="width:52px">等级</th><th style="width:132px">规则码</th>
        <th>触发描述</th><th style="width:38%">处置建议</th></tr>
    __EVENTS__
  </table>
</div>

<div class="ft">
  <b>数据来源</b>：__SOURCE__<br>
  <b>方法说明</b>：本报告参照信贷评分卡思路构造——先由订单、积分、券、营养四类只读数据提取特征，
  再按五个维度分箱赋分，加权映射到 300–900 分数域。所有分值均可回溯到真实字段，缺失字段走中性分而非补零。<br>
  <b>免责声明</b>：本项目为 1024 程序员节「麦当劳程序员创意开发大赛」参赛作品，由参赛者独立开发，
  非麦当劳官方产品。报告结果仅供娱乐与自我观察，不构成医疗、营养、财务或任何专业建议；
  餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。<br>
  <b>隐私说明</b>：报告生成过程全程只读，不创建、不修改、不取消任何订单，不消耗积分，不领取优惠券。
</div>

</div></body></html>
"""

# 金属降级：评级越高越"贵"
RATING_COLOR = {
    "AAA": "#FFC72C", "AA": "#F2B824", "A": "#C9D1D9",
    "BBB": "#CD7F32", "BB": "#B06A28",
    "B": "#E5484D", "CCC": "#C0392B", "C": "#96281B",
}

LEVEL_CN = {"high": "高", "mid": "中", "low": "低"}


def _esc(s) -> str:
    return html.escape(str(s if s is not None else "—"))


def _fmt(v, nd=1, dash="—"):
    if v is None:
        return dash
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return str(v)


def _dim_color(score: int) -> str:
    if score >= 80:
        return "#FFC72C"
    if score >= 65:
        return "#E3B341"
    if score >= 50:
        return "#B8860B"
    return "#E5484D"


def build_insight(f: dict, card: dict) -> str:
    """挑一条最值得被转述的发现。全部来自真实数据，编不出来就退到短板维度。"""
    by_code = {e["code"]: e for e in card["events"]}
    if "DORMANT-POINTS" in by_code:
        pts = f["expiring_points"] or 0
        av = f["avail_points"] or 0
        pct = f"{pts / av:.0%}" if av else "—"
        return f"你有 {pts:.0f} 积分正在过期，占可用积分的 {pct}，属于典型的资产减值。"
    if "LATE-NIGHT" in by_code:
        return (f"{f['late_count']} 笔订单发生在深夜 22 点之后，"
                f"占全部订单的 {f['late_ratio']:.0%}——这是拉低自律度的主要原因。")
    if "COUPON-EXPIRY" in by_code:
        return (f"手里 {f['total_coupons']} 张券里有 {f['expiring_coupons']} 张"
                f"将在 7 天内失效，时间价值正在归零。")
    if "STREAK" in by_code:
        return f"最长连续 {f['best_streak']} 天下单，消费已形成固定节律。"
    weak = min(card["dimensions"].values(), key=lambda d: d["score"])
    return f"当前最薄弱的是「{weak['title']}」，得分 {weak['score']}。"


def build_report(f: dict, card: dict, is_mock: bool,
                 ref: str | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now()
    rating = card["rating"]
    color = RATING_COLOR.get(rating, "#C9D1D9")
    pct = max(2.0, min(100.0, (card["score"] - 300) / 600.0 * 100))

    # ---- 24 小时分布
    hist = f.get("hour_hist") or [0] * 24
    hmax = max(hist) or 1
    hours_html, axis_html = [], []
    for h in range(24):
        cnt = hist[h]
        height = max(2, int(cnt / hmax * 48)) if cnt else 2
        cls = "late" if (h >= 22 or h < 5) and cnt else ("zero" if not cnt else "")
        hours_html.append(f'<i class="{cls}" style="height:{height}px" title="{h}点 {cnt} 笔"></i>')
        axis_html.append(f"<span>{h if h in (0, 6, 12, 18, 23) else ''}</span>")
    late_total = sum(hist[22:]) + sum(hist[:5])
    if late_total:
        peak = f.get("peak_hour")
        hnote = (f"深夜时段（22:00–05:00）共 {late_total} 笔。"
                 + (f"全天下单高峰在 {peak}:00。" if peak is not None else ""))
    else:
        hnote = "无深夜时段订单，作息信号健康。"

    # ---- 麦龄时间轴
    dots = "".join(
        f'<i class="{"l" if late else "n"}" style="left:{pos * 100:.2f}%"></i>'
        for pos, late in (f.get("timeline") or [])
    )
    if not dots:
        dots = '<i class="n" style="left:50%"></i>'

    # ---- 五维（短板高亮 + 中性线刻度）
    weakest = min(card["dimensions"].values(), key=lambda d: d["score"])["key"]
    dims_html = []
    for d in card["dimensions"].values():
        dc = _dim_color(d["score"])
        weak_cls = " weak" if d["key"] == weakest else ""
        weak_tag = '<span class="tag">短板</span>' if d["key"] == weakest else ""
        dims_html.append(
            f'<div class="dim{weak_cls}">'
            f'<div class="dimT"><span class="n">{_esc(d["title"])}{weak_tag}</span>'
            f'<span><span class="s" style="color:{dc}">{d["score"]}</span>'
            f'<span class="w"> ×{int(d["weight"] * 100)}%</span></span></div>'
            f'<div class="dimB"><i style="width:{d["score"]}%;background:{dc}"></i>'
            f'<span class="nt" style="left:60%"></span></div>'
            f'<div class="dimN">{_esc(d["note"])}</div></div>'
        )

    # ---- KPI 分层
    tenure = f"{f['tenure_days']} 天" if f.get("tenure_days") else "不足"
    big3 = [
        ("订单总数", _fmt(f["order_count"], 0), "笔", True),
        ("麦龄", tenure.replace(" 天", ""), "天", True),
        ("累计消费", _fmt(f["total_amount"]), "元", False),
    ]
    big3_html = "".join(
        f'<div class="kpiBig{" gold" if gold else ""}"><div class="k">{_esc(k)}</div>'
        f'<div class="v">{_esc(v)}<span class="u">{_esc(u)}</span></div></div>'
        for k, v, u, gold in big3
    )
    small = [
        ("单均金额", f"¥{_fmt(f['avg_amount'])}", False),
        ("深夜占比", f"{f['late_ratio']:.0%}" if f["late_ratio"] is not None else "—",
         bool(f["late_ratio"] and f["late_ratio"] >= 0.2)),
        ("最长连击", f"{_fmt(f['best_streak'], 0)} 天", False),
        ("单均热量", f"{_fmt(f['avg_kcal'], 0, '未匹配')} kcal", False),
        ("在手券", f"{_fmt(f['total_coupons'], 0)} 张", bool(f["expiring_coupons"])),
        ("可用积分", _fmt(f["avail_points"], 0, "—"), bool(f["expiring_points"])),
        ("门店集中度", _fmt(f["store_hhi"], 2), False),
    ]
    small_html = "".join(
        f'<div class="sm"><span class="k">{_esc(k)}</span>'
        f'<span class="v{" warnv" if warn else ""}">{_esc(v)}</span></div>'
        for k, v, warn in small
    )

    events_html = "".join(
        f'<tr><td><span class="lv {e["level"]}">{LEVEL_CN.get(e["level"], "低")}</span></td>'
        f'<td><span class="code">{_esc(e["code"])}</span></td>'
        f'<td class="evText">{_esc(e["text"])}</td>'
        f'<td class="act">{_esc(e["action"])}</td></tr>'
        for e in card["events"]
    )

    warn = ""
    if card.get("thin_file"):
        warn = ('<div class="warn"><b>样本不足 · 白户（Thin File）</b><br>'
                '当前订单数或观察窗过短，评分仅供参考，不做判人性结论。'
                '授信业务中对薄档案客户的标准做法就是拒绝判断，本项目沿用同一纪律。</div>')

    source = ("演示数据集（固定随机种子 1024，非真实账号数据）" if is_mock
              else "麦当劳官方 MCP 只读接口：order-list / query-my-account / query-my-coupons / list-nutrition-foods")

    out = TPL
    for key, val in [
        ("__CSS__", CSS),
        ("__REF__", _esc(ref or f"MRS-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}")),
        ("__TS__", now.strftime("%Y-%m-%d %H:%M:%S")),
        ("__SCORE__", str(card["score"])),
        ("__RATING__", _esc(rating)),
        ("__BAND__", _esc(card["band"])),
        ("__DECISION__", _esc(card["decision"])),
        ("__WEIGHTED__", str(card["weighted"])),
        ("__N__", str(f["order_count"])),
        ("__PCT__", f"{pct:.1f}"),
        ("__COLOR__", color),
        ("__INSIGHT__", _esc(build_insight(f, card))),
        ("__WARN__", warn),
        ("__HOURS__", "".join(hours_html)),
        ("__HAXIS__", "".join(axis_html)),
        ("__HNOTE__", _esc(hnote)),
        ("__DOTS__", dots),
        ("__FIRST__", f["first_order"].strftime("%Y-%m-%d") if f.get("first_order") else "—"),
        ("__LAST__", f["last_order"].strftime("%Y-%m-%d") if f.get("last_order") else "—"),
        ("__TENURE__", _esc(tenure)),
        ("__DIMS__", "".join(dims_html)),
        ("__BIG3__", big3_html),
        ("__SMALL__", small_html),
        ("__EVENTS__", events_html),
        ("__SOURCE__", _esc(source)),
        ("__BADGE__", "DEMO DATA" if is_mock else "LIVE MCP"),
        ("__BADGECLS__", "demo" if is_mock else "live"),
    ]:
        out = out.replace(key, val)
    return out


def write_report(f: dict, card: dict, is_mock: bool, out_path: str | None = None) -> str:
    """写盘并返回路径。默认落到系统临时目录 —— 报告含个人数据，不进仓库。"""
    if out_path is None:
        out_path = os.path.join(
            tempfile.gettempdir(),
            f"mcd-risk-score-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html",
        )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(build_report(f, card, is_mock, now=datetime.now()))
    return out_path
