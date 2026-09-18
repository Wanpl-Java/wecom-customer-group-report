from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path

LINES = ("JS", "DE", "MK", "其他")
LINE_TITLE = {
    "JS": "JumpServer",
    "DE": "DataEase",
    "MK": "MaxKB",
    "其他": "未标注产品线",
}
_LINE_RE = re.compile(r"【\s*(JS|DE|MK)\b", re.I)


def product_line(group: dict) -> str:
    """客户归属以群名前缀 【JS】/【DE】/【MK】为准，避免正文里提到别的产品被错分。"""
    name = group.get("group_name") or ""
    matched = _LINE_RE.search(name)
    if matched:
        return matched.group(1).upper()
    products = {str(p).upper() for p in (group.get("products") or [])}
    for code in ("JS", "DE", "MK"):
        if code in products:
            return code
    return "其他"


def display_name(group_name: str) -> str:
    text = re.sub(r"^【[^】]+】\s*", "", group_name or "").strip()
    return text or (group_name or "未命名客户")


def _css() -> str:
    return """
    :root {
      --bg:#f3f5f7; --card:#fff; --text:#1c2430; --muted:#667085; --line:#e6e8ee;
      --js:#1677ff; --de:#0f9f8f; --mk:#6d4aff; --other:#667085;
      --ok:#12805c; --warn:#b76e00; --bad:#c2413b;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
      background:var(--bg);color:var(--text);line-height:1.5}
    a{color:inherit;text-decoration:none}
    .wrap{max-width:1180px;margin:0 auto;padding:28px 24px 48px}
    .top{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:20px}
    .eyebrow{font-size:12px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}
    h1{margin:4px 0 6px;font-size:28px;font-weight:650}
    .sub{margin:0;color:var(--muted);font-size:14px}
    .search{min-width:260px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;font-size:14px}
    .period{display:flex;gap:8px;align-items:center;margin:0 0 18px;flex-wrap:wrap}
    .period select,.period input,.period button{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:13px}
    .period button{background:#1c2430;color:#fff;border:none;cursor:pointer}
    .chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
    .chip{padding:6px 12px;border-radius:999px;background:#fff;border:1px solid var(--line);font-size:13px;color:var(--muted)}
    .chip b{color:var(--text);margin-left:6px}
    .chip.js{border-color:#c9ddff}.chip.de{border-color:#b7ebe4}.chip.mk{border-color:#ddd4ff}
    section.line{margin-bottom:28px}
    section.line h2{display:flex;align-items:baseline;gap:10px;margin:0 0 12px;font-size:16px}
    section.line h2 span{color:var(--muted);font-weight:500;font-size:13px}
    .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
    .dot.JS{background:var(--js)}.dot.DE{background:var(--de)}.dot.MK{background:var(--mk)}.dot.其他{background:var(--other)}
    .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
    .cust{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 16px 14px}
    .cust:hover{border-color:#c5ccd6;box-shadow:0 6px 18px rgba(16,24,40,.06)}
    .cust .row{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
    .badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:#fff}
    .badge.JS{background:var(--js)}.badge.DE{background:var(--de)}.badge.MK{background:var(--mk)}.badge.其他{background:#98a2b3}
    .cust h3{margin:8px 0 2px;font-size:16px;font-weight:650}
    .cust .gname{margin:0;color:var(--muted);font-size:12px;min-height:18px}
    .metrics{display:flex;gap:14px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
    .metrics b{display:block;font-size:16px;color:var(--text);font-weight:650}
    .metrics .bad b{color:var(--bad)}.metrics .ok b{color:var(--ok)}
    .empty{color:var(--muted);font-size:13px;padding:8px 0 4px}
    .back{display:inline-block;margin-bottom:10px;color:var(--muted);font-size:13px}
    .back:hover{color:var(--text)}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
    .card h2{margin:0 0 10px;font-size:14px;color:var(--muted);font-weight:600}
    .kpi{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f0f2f5;font-size:14px}
    .kpi b{font-size:18px}
    .kpi.warn b{color:var(--warn)}.kpi.ok b{color:var(--ok)}
    .meta{margin-top:8px;color:var(--muted);font-size:12px}
    .panel{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:12px 0}
    .panel h3{margin:0;padding:14px 16px;font-size:14px;border-bottom:1px solid var(--line)}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{padding:10px 12px;border-bottom:1px solid #f0f2f5;text-align:left;vertical-align:top}
    th{color:var(--muted);font-weight:600;background:#fafbfc}
    td.bad{color:var(--bad);font-weight:700}
    .bar-wrap{display:flex;align-items:center;gap:8px;margin:6px 0}
    .bar{height:8px;background:#1c2430;border-radius:6px;min-width:2px}
    .rank{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #f0f2f5}
    .rank .n{width:22px;height:22px;border-radius:50%;background:#f2f4f7;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700}
    footer{margin-top:20px;color:var(--muted);font-size:12px}
    .ops{color:var(--muted);font-size:12px}
    """


def _sat_bars(dist: dict, n: int) -> str:
    if not n:
        return '<p class="meta">本期暂无满意度评分。</p>'
    max_n = max(dist.values()) or 1
    parts = []
    for score in ("5", "4", "3", "2", "1"):
        c = dist.get(score, 0)
        w = int(c / max_n * 140)
        parts.append(
            f'<div class="bar-wrap"><span style="width:28px;color:#667085;font-size:12px">{score}分</span>'
            f'<span class="bar" style="width:{w}px"></span><span style="color:#667085;font-size:12px">{c}</span></div>'
        )
    return "".join(parts)


def _top3(items: list[dict]) -> str:
    if not items:
        return '<p class="meta">暂无模块数据。</p>'
    return "".join(
        f'<div class="rank"><span class="n">{i}</span><span style="flex:1">{escape(x["module"])}</span>'
        f'<span style="color:#667085">{x["count"]} 次</span></div>'
        for i, x in enumerate(items, 1)
    )


def render_group_html(group: dict, meta: dict) -> str:
    sat = f"{group['sat_avg']}" if group["sat_avg"] is not None else "暂无"
    line = product_line(group)
    detail_rows = []
    for d in group.get("details") or []:
        sat_c = str(d["sat_score"]) if d.get("sat_score") is not None else "-"
        detail_rows.append(
            "<tr>"
            f"<td>{escape(d['product'])}</td><td>{escape(d['module'])}</td>"
            f"<td>{escape(d['summary'])}</td><td>{escape(d['status'])}</td>"
            f"<td>{escape(str(d['owner']))}</td><td>{escape(str(d['opened_at']))}</td>"
            f"<td>{escape(sat_c)}</td></tr>"
        )
    if not detail_rows:
        detail_rows.append('<tr><td colspan="7">本期无明细</td></tr>')

    leftover_rows = []
    for item in group.get("leftovers") or []:
        flag = "超SLA" if item["sla_breach"] else ""
        leftover_rows.append(
            "<tr>"
            f"<td>{escape(item['module'])}</td><td>{escape(item['summary'])}</td>"
            f"<td>{escape(str(item['owner']))}</td><td>{escape(str(item['age_days']))}</td>"
            f"<td class='{'bad' if flag else ''}'>{escape(flag)}</td></tr>"
        )
    if not leftover_rows:
        leftover_rows.append('<tr><td colspan="5">本期无遗留</td></tr>')

    back = meta.get("back_href") or "index.html"
    title = display_name(group["group_name"])
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{escape(title)} · {escape(meta['period_label'])}</title>
<style>{_css()}</style></head><body><div class="wrap">
<a class="back" href="{escape(back)}">← 全部客户</a>
<div class="eyebrow">{escape(line)} · {escape(LINE_TITLE[line])}</div>
<h1>{escape(title)}</h1>
<p class="sub">{escape(group['group_name'])} · 周期 {escape(meta['period_label'])}
（{escape(meta['period_start'])} ~ {escape(meta['period_end'])}）· 生成 {escape(meta['generated_at'])}</p>
<div class="grid">
  <section class="card"><h2>问题数</h2>
    <div class="kpi"><span>本期相关</span><b>{group['issue_cnt']}</b></div>
    <div class="kpi"><span>新增</span><b>{group['new_cnt']}</b></div>
    <div class="kpi ok"><span>完结</span><b>{group['done_cnt']}</b></div>
    <div class="kpi"><span>完结率</span><b>{group['completion_rate']}%</b></div>
    <div class="kpi"><span>遗留</span><b>{group['open_end']}</b></div>
    <div class="kpi warn"><span>超 SLA</span><b>{group['sla_breach']}</b></div>
  </section>
  <section class="card"><h2>满意度</h2>
    <div class="kpi"><span>平均分</span><b>{escape(sat)}</b></div>
    <div class="kpi"><span>样本量</span><b>{group['sat_n']}</b></div>
    <div style="margin-top:12px">{_sat_bars(group.get('sat_dist') or {{}}, group['sat_n'])}</div>
  </section>
  <section class="card"><h2>核心模块 Top3</h2>
    {_top3(group.get('top_modules') or [])}
  </section>
</div>
<div class="panel"><h3>未闭环</h3>
<table><thead><tr><th>模块</th><th>摘要</th><th>负责人</th><th>打开天数</th><th>标记</th></tr></thead>
<tbody>{''.join(leftover_rows)}</tbody></table></div>
<div class="panel"><h3>本期明细</h3>
<table><thead><tr><th>产品</th><th>模块</th><th>摘要</th><th>状态</th><th>负责人</th><th>开单</th><th>满意度</th></tr></thead>
<tbody>{''.join(detail_rows)}</tbody></table></div>
<footer>数据来源：企业微信会话内容存档。</footer>
</div></body></html>"""


def _card(group: dict, href: str, line: str) -> str:
    sat = f"{group['sat_avg']}" if group["sat_avg"] is not None else "-"
    name = display_name(group["group_name"])
    sla_cls = "bad" if group["sla_breach"] else ""
    blob = f"{name} {group['group_name']} {line}".lower()
    return (
        f'<a class="cust" href="{escape(href)}" data-q="{escape(blob)}">'
        f'<div class="row"><span class="badge {escape(line)}">{escape(line)}</span>'
        f'<span class="meta" style="margin:0">满意 {escape(sat)}</span></div>'
        f"<h3>{escape(name)}</h3>"
        f'<p class="gname">{escape(group["group_name"])}</p>'
        f'<div class="metrics">'
        f'<span><b>{group["issue_cnt"]}</b>问题</span>'
        f'<span><b>{group["open_end"]}</b>遗留</span>'
        f'<span class="{sla_cls}"><b>{group["sla_breach"]}</b>超SLA</span>'
        f"</div></a>"
    )


def render_index(bundle: dict, links: list[dict], *, portal: bool = False) -> str:
    buckets: dict[str, list[str]] = {code: [] for code in LINES}
    counts = {code: 0 for code in LINES}
    for i, g in enumerate(bundle["groups"]):
        href = links[i]["href"] if i < len(links) else "#"
        line = product_line(g)
        buckets[line].append(_card(g, href, line))
        counts[line] += 1

    sections = []
    for code in LINES:
        cards = buckets[code]
        body = "".join(cards) if cards else '<p class="empty">本期没有客户。</p>'
        sections.append(
            f'<section class="line" id="line-{escape(code)}">'
            f'<h2><i class="dot {escape(code)}"></i>{escape(code)}'
            f"<span>{escape(LINE_TITLE[code])} · {counts[code]}</span></h2>"
            f'<div class="cards">{body}</div></section>'
        )

    chips = "".join(
        f'<a class="chip {escape(code.lower())}" href="#line-{escape(code)}">{escape(code)}<b>{counts[code]}</b></a>'
        for code in LINES
    )
    y = (bundle.get("period_start") or "2026-01-01")[:4]
    m = (bundle.get("period_start") or "2026-01-01")[5:7]
    ptype = bundle.get("period_type") or "month"
    period_form = ""
    if portal:
        def _opt(value: str, label: str) -> str:
            sel = " selected" if ptype == value else ""
            return f'<option value="{value}"{sel}>{label}</option>'

        period_form = f"""
<form class="period" method="get" action="/">
  <select name="period">
    {_opt("month", "月度")}
    {_opt("quarter", "季度")}
    {_opt("year", "年度")}
  </select>
  <input name="year" value="{escape(y)}" size="6"/>
  <input name="month" value="{escape(str(int(m)))}" size="3"/>
  <input name="quarter" value="{(int(m) - 1) // 3 + 1}" size="2"/>
  <button type="submit">查看</button>
  <a class="ops" href="/ops">同步 / 重新出数</a>
</form>"""

    script = """
<script>
const q=document.getElementById('q');
if(q){q.addEventListener('input',()=>{
  const s=q.value.trim().toLowerCase();
  document.querySelectorAll('.cust').forEach(el=>{
    el.style.display=!s||el.dataset.q.includes(s)?'':'none';
  });
});}
</script>"""
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>客户一览 · {escape(bundle['period_label'])}</title>
<style>{_css()}</style></head><body><div class="wrap">
<div class="top">
  <div>
    <div class="eyebrow">客户成功</div>
    <h1>客户一览</h1>
    <p class="sub">{escape(bundle['period_label'])} · {bundle['total_groups']} 个客户群 ·
    问题 {bundle['total_tickets']} · {escape(bundle['period_start'])} ~ {escape(bundle['period_end'])}</p>
  </div>
  <input id="q" class="search" placeholder="搜索客户或群名"/>
</div>
{period_form}
<div class="chips">{chips}</div>
{''.join(sections)}
<footer>按群名前缀 【JS】【DE】【MK】分产品线。点卡片进入该客户报表。</footer>
</div>{script}</body></html>"""


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()[:80] or "group"


def write_reports(bundle: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch = output_dir / f"customer_groups_{_safe_name(bundle['period_label'])}_{stamp}"
    batch.mkdir(parents=True, exist_ok=True)
    meta = {
        "period_label": bundle["period_label"],
        "period_start": bundle["period_start"],
        "period_end": bundle["period_end"],
        "generated_at": bundle["generated_at"],
        "period_type": bundle["period_type"],
        "back_href": "index.html",
    }
    links = []
    for g in bundle["groups"]:
        fname = f"{_safe_name(g['group_name'])}.html"
        (batch / fname).write_text(render_group_html(g, meta), encoding="utf-8")
        links.append({"group": g["group_name"], "href": fname})
    index = batch / "index.html"
    index.write_text(render_index(bundle, links), encoding="utf-8")
    (batch / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return index
