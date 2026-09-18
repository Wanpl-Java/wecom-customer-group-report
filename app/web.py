from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.analyze.extract import messages_to_tickets
from app.archive.sync import run_sync
from app.config import AppConfig
from app.models import Store
from app.report.aggregate import aggregate_by_groups
from app.report.render import render_group_html, render_index, write_reports

_lock = threading.Lock()
_last_job: dict[str, Any] = {}
_bundle_cache: dict[tuple, tuple[float, dict]] = {}


def create_app(cfg: AppConfig) -> FastAPI:
    app = FastAPI(title="企微客户群报表", version="1.0.0")
    root = Path(__file__).resolve().parent.parent
    static_dir = root / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/reports", StaticFiles(directory=str(cfg.output_dir)), name="reports")

    def store() -> Store:
        return Store(cfg.db_path)

    def load_bundle(period: str, year: int, month: int, quarter: int, days: int) -> dict:
        key = (period, year, month, quarter, days)
        hit = _bundle_cache.get(key)
        if hit and time.time() - hit[0] < 120:
            return hit[1]
        messages = store().list_group_messages(
            external_only=cfg.wecom.external_only,
            roomids=cfg.wecom.room_allowlist or None,
        )
        tickets = messages_to_tickets(messages, cfg.analyze) if messages else []
        bundle = aggregate_by_groups(
            tickets, period, days=days, year=year, month=month, quarter=quarter
        )
        _bundle_cache[key] = (time.time(), bundle)
        return bundle

    def period_query(period: str, year: int, month: int, quarter: int, days: int) -> str:
        return urlencode(
            {"period": period, "year": year, "month": month, "quarter": quarter, "days": days}
        )

    @app.get("/", response_class=HTMLResponse)
    def home(
        period: str = Query("month"),
        year: int = Query(datetime.now().year),
        month: int = Query(datetime.now().month),
        quarter: int = Query((datetime.now().month - 1) // 3 + 1),
        days: int = Query(7),
    ) -> str:
        bundle = load_bundle(period, year, month, quarter, days)
        links = []
        for g in bundle["groups"]:
            q = urlencode(
                {
                    "name": g["group_name"],
                    "roomid": g.get("roomid") or "",
                    "period": period,
                    "year": year,
                    "month": month,
                    "quarter": quarter,
                    "days": days,
                }
            )
            links.append({"href": f"/customer?{q}"})
        return render_index(bundle, links, portal=True)

    @app.get("/customer", response_class=HTMLResponse)
    def customer_page(
        name: str = Query(...),
        roomid: str = Query(""),
        period: str = Query("month"),
        year: int = Query(datetime.now().year),
        month: int = Query(datetime.now().month),
        quarter: int = Query(1),
        days: int = Query(7),
    ) -> str:
        bundle = load_bundle(period, year, month, quarter, days)
        group = next(
            (
                g
                for g in bundle["groups"]
                if g["group_name"] == name and (not roomid or (g.get("roomid") or "") == roomid)
            ),
            None,
        )
        if group is None:
            raise HTTPException(404, "该周期没有这个客户")
        qs = period_query(period, year, month, quarter, days)
        meta = {
            "period_label": bundle["period_label"],
            "period_start": bundle["period_start"],
            "period_end": bundle["period_end"],
            "generated_at": bundle["generated_at"],
            "period_type": bundle["period_type"],
            "back_href": f"/?{qs}",
        }
        return render_group_html(group, meta)

    @app.get("/ops", response_class=HTMLResponse)
    def ops() -> str:
        st = store().stats()
        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>企微客户群报表</title>
<style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:0;background:#0f1419;color:#e7ecf1}}
main{{max-width:880px;margin:40px auto;padding:0 20px}}
.card{{background:#1a222c;border:1px solid #2a3542;border-radius:14px;padding:24px;margin-bottom:16px}}
h1{{margin-top:0}} label{{display:block;margin:10px 0 4px;color:#9aa7b5}}
input,select,button{{padding:8px 12px;border-radius:8px;border:1px solid #2a3542;background:#121820;color:#e7ecf1}}
button{{background:#3d9cf0;border:none;cursor:pointer;font-weight:600}}
.meta{{color:#9aa7b5;font-size:13px}}
a{{color:#3d9cf0}}
</style></head><body><main>
<p><a href="/">← 客户一览</a></p>
<h1>同步与出数</h1>
<p class="meta">模式：{cfg.mode} · 消息 {st.get('messages')} · 群 {st.get('rooms')} · 游标 seq={st.get('cursor_seq')}</p>
<div class="card">
  <h2>1. 同步存档</h2>
  <form method="post" action="/api/sync"><button type="submit">立即同步</button></form>
  <p class="meta">sdk 模式需 Linux + libWeWorkFinanceSdk_C.so + RSA 私钥；demo 模式导入样例消息。</p>
</div>
<div class="card">
  <h2>2. 生成报表</h2>
  <form method="post" action="/api/report">
    <label>周期</label>
    <select name="period">
      <option value="month">月度</option>
      <option value="quarter">季度</option>
      <option value="year">年度</option>
      <option value="days">近N天</option>
    </select>
    <label>年</label><input name="year" value="{datetime.now().year}"/>
    <label>月</label><input name="month" value="{datetime.now().month}"/>
    <label>季度(1-4)</label><input name="quarter" value="{(datetime.now().month-1)//3+1}"/>
    <label>近N天</label><input name="days" value="7"/>
    <div style="margin-top:14px"><button type="submit">生成 HTML</button></div>
  </form>
</div>
<div class="card">
  <h2>3. 最近任务</h2>
  <pre id="job" class="meta">{_last_job or "尚无"}</pre>
  <p><a href="/reports/" target="_blank">打开报表目录</a>（需服务器开启目录索引时可浏览；推荐用下方返回的 index 链接）</p>
</div>
</main></body></html>"""

    @app.get("/api/stats")
    def api_stats() -> dict[str, Any]:
        return store().stats()

    @app.post("/api/sync")
    def api_sync() -> JSONResponse:
        with _lock:
            try:
                result = run_sync(cfg, store())
                _bundle_cache.clear()
                _last_job.clear()
                _last_job.update({"action": "sync", "ok": True, **result, "at": datetime.now().isoformat()})
                return JSONResponse({"ok": True, **result})
            except Exception as exc:  # noqa: BLE001
                _last_job.clear()
                _last_job.update({"action": "sync", "ok": False, "error": str(exc)})
                raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/report")
    def api_report(
        period: str = Form("month"),
        year: int = Form(datetime.now().year),
        month: int = Form(datetime.now().month),
        quarter: int = Form(1),
        days: int = Form(7),
    ) -> HTMLResponse:
        with _lock:
            messages = store().list_group_messages(
                external_only=cfg.wecom.external_only,
                roomids=cfg.wecom.room_allowlist or None,
            )
            if not messages:
                raise HTTPException(400, "无消息，请先同步")
            tickets = messages_to_tickets(messages, cfg.analyze)
            bundle = aggregate_by_groups(
                tickets, period, days=days, year=year, month=month, quarter=quarter
            )
            if not bundle["groups"]:
                raise HTTPException(400, f"周期 {bundle['period_label']} 无数据")
            index = write_reports(bundle, cfg.output_dir)
            rel = index.relative_to(cfg.output_dir).as_posix()
            url = f"/reports/{rel}"
            _last_job.clear()
            _last_job.update(
                {
                    "action": "report",
                    "ok": True,
                    "period": bundle["period_label"],
                    "groups": bundle["total_groups"],
                    "index": url,
                    "at": datetime.now().isoformat(),
                }
            )
            return HTMLResponse(
                f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>完成</title></head>
<body style="font-family:sans-serif;background:#0f1419;color:#e7ecf1;padding:40px">
<h2>已生成 {bundle['total_groups']} 个客户群报表（{bundle['period_label']}）</h2>
<p><a style="color:#3d9cf0" href="{url}" target="_blank">打开索引 HTML</a></p>
<p><a style="color:#9aa7b5" href="/">返回</a></p>
</body></html>"""
            )

    @app.get("/api/last")
    def api_last() -> dict[str, Any]:
        return _last_job

    return app
