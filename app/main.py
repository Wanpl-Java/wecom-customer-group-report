from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

from app.analyze.extract import messages_to_tickets
from app.archive.sync import run_sync
from app.config import AppConfig, get_config, load_config
from app.models import Store
from app.report.aggregate import aggregate_by_groups
from app.report.render import write_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("wecom-report")


def _store(cfg: AppConfig) -> Store:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    return Store(cfg.db_path)


def cmd_sync(cfg: AppConfig, args: argparse.Namespace) -> int:
    store = _store(cfg)
    path = Path(args.json) if getattr(args, "json", None) else None
    result = run_sync(cfg, store, json_path=path)
    logger.info("同步完成: %s", result)
    logger.info("库统计: %s", store.stats())
    return 0


def cmd_report(cfg: AppConfig, args: argparse.Namespace) -> int:
    store = _store(cfg)
    messages = store.list_group_messages(
        external_only=cfg.wecom.external_only,
        roomids=cfg.wecom.room_allowlist or None,
    )
    if not messages:
        logger.error("库中无外部群消息，请先执行 sync / demo")
        return 1
    tickets = messages_to_tickets(messages, cfg.analyze)
    logger.info("抽取问题 %s 条（来自消息 %s 条）", len(tickets), len(messages))
    bundle = aggregate_by_groups(
        tickets,
        args.period,
        days=args.days,
        year=args.year,
        month=args.month,
        quarter=args.quarter,
    )
    if not bundle["groups"]:
        logger.error("周期 %s 无客户群聚合结果", bundle["period_label"])
        return 1
    index = write_reports(bundle, cfg.output_dir)
    logger.info(
        "已生成 %s 个客户群报表（%s）→ %s",
        bundle["total_groups"],
        bundle["period_label"],
        index,
    )
    if args.open:
        webbrowser.open(index.as_uri())
    print(str(index))
    return 0


def cmd_demo(cfg: AppConfig, args: argparse.Namespace) -> int:
    # 强制演示模式
    cfg.mode = "demo"
    rc = cmd_sync(cfg, argparse.Namespace(json=None))
    if rc != 0:
        return rc
    return cmd_report(cfg, args)


def cmd_stats(cfg: AppConfig, _args: argparse.Namespace) -> int:
    store = _store(cfg)
    print(store.stats())
    return 0


def cmd_serve(cfg: AppConfig, args: argparse.Namespace) -> int:
    import uvicorn

    from app.web import create_app

    app = create_app(cfg)
    host = args.host or cfg.server.host
    port = args.port or cfg.server.port
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="企微外部客户群会话存档 → 月/季/年 HTML 报表")
    p.add_argument("--config", default=None, help="配置文件路径")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sync", help="同步会话存档 / 导入 JSON")
    s.add_argument("--json", default=None, help="从 JSON 文件导入消息")
    s.set_defaults(func=cmd_sync)

    r = sub.add_parser("report", help="按客户群生成 HTML 报表")
    r.add_argument("--period", choices=["days", "month", "quarter", "year"], default="month")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--year", type=int, default=None)
    r.add_argument("--month", type=int, default=None)
    r.add_argument("--quarter", type=int, default=None)
    r.add_argument("--open", action="store_true")
    r.set_defaults(func=cmd_report)

    d = sub.add_parser("demo", help="导入演示消息并出报表")
    d.add_argument("--period", choices=["days", "month", "quarter", "year"], default="month")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--year", type=int, default=2026)
    d.add_argument("--month", type=int, default=9)
    d.add_argument("--quarter", type=int, default=3)
    d.add_argument("--open", action="store_true")
    d.set_defaults(func=cmd_demo)

    st = sub.add_parser("stats", help="查看本地库统计")
    st.set_defaults(func=cmd_stats)

    sv = sub.add_parser("serve", help="启动 Web 控制台")
    sv.add_argument("--host", default=None)
    sv.add_argument("--port", type=int, default=None)
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    get_config.cache_clear()
    cfg = load_config(args.config)
    from datetime import datetime

    now = datetime.now()
    if hasattr(args, "year") and args.year is None:
        args.year = now.year
    if hasattr(args, "month") and args.month is None:
        args.month = now.month
    if hasattr(args, "quarter") and args.quarter is None:
        args.quarter = (now.month - 1) // 3 + 1
    return args.func(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
