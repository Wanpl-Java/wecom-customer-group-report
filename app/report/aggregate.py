from __future__ import annotations

import calendar
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from app.analyze.extract import infer_module
from app.models import Ticket


def resolve_period(
    period_type: str,
    *,
    days: int = 7,
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    now = now or datetime.now()
    y = year or now.year
    m = month or now.month
    q = quarter or ((now.month - 1) // 3 + 1)

    if period_type == "days":
        end = now
        start = end - timedelta(days=max(1, days))
        return start, end, f"近 {max(1, days)} 天"
    if period_type == "month":
        start = datetime(y, m, 1)
        last = calendar.monthrange(y, m)[1]
        end = datetime(y, m, last, 23, 59, 59)
        return start, end, f"{y}年{m:02d}月"
    if period_type == "quarter":
        q = max(1, min(4, q))
        start_m = (q - 1) * 3 + 1
        end_m = start_m + 2
        start = datetime(y, start_m, 1)
        last = calendar.monthrange(y, end_m)[1]
        end = datetime(y, end_m, last, 23, 59, 59)
        return start, end, f"{y}年Q{q}"
    start = datetime(y, 1, 1)
    end = datetime(y, 12, 31, 23, 59, 59)
    return start, end, f"{y}年"


def _in_window(dt: datetime | None, start: datetime, end: datetime) -> bool:
    return bool(dt and start <= dt <= end)


def filter_tickets(tickets: list[Ticket], start: datetime, end: datetime) -> list[Ticket]:
    out: list[Ticket] = []
    for t in tickets:
        od = t.opened_dt()
        if _in_window(od, start, end):
            out.append(t)
        elif t.is_open() and od is not None and od < start:
            out.append(t)
        elif od is None:
            out.append(t)
    return out


def _sat_bucket(scores: list[int]) -> dict[str, int]:
    dist = {str(i): 0 for i in range(1, 6)}
    for s in scores:
        dist[str(max(1, min(5, int(s))))] += 1
    return dist


def stats_for(items: list[Ticket], start: datetime, end: datetime) -> dict:
    new_cnt = done_cnt = open_end = sla_breach = 0
    sats: list[int] = []
    modules: Counter[str] = Counter()
    leftovers: list[dict] = []
    details: list[dict] = []

    for t in items:
        od = t.opened_dt()
        if od and _in_window(od, start, end):
            new_cnt += 1
        if t.is_done():
            cd = t.closed_dt()
            if cd is None or _in_window(cd, start, end):
                done_cnt += 1
        if t.is_open():
            open_end += 1
            age_h = (end - od).total_seconds() / 3600 if od else None
            breach = bool(age_h is not None and age_h > t.sla_hours)
            if breach:
                sla_breach += 1
            leftovers.append(
                {
                    "module": t.module or infer_module(t.summary),
                    "summary": t.summary,
                    "owner": t.owner or "-",
                    "age_days": round(age_h / 24, 1) if age_h is not None else "-",
                    "sla_breach": breach,
                }
            )
        if t.sat_score is not None:
            sats.append(t.sat_score)
        mod = t.module or infer_module(t.summary)
        modules[mod] += 1
        details.append(
            {
                "product": t.product,
                "module": mod,
                "summary": t.summary,
                "status": t.status,
                "owner": t.owner or "-",
                "opened_at": t.opened_at,
                "sat_score": t.sat_score,
            }
        )

    denom = open_end + done_cnt
    return {
        "issue_cnt": len(items),
        "new_cnt": new_cnt,
        "done_cnt": done_cnt,
        "open_end": open_end,
        "completion_rate": round(done_cnt / denom * 100, 1) if denom else 0.0,
        "sla_breach": sla_breach,
        "sat_avg": round(statistics.mean(sats), 2) if sats else None,
        "sat_n": len(sats),
        "sat_dist": _sat_bucket(sats),
        "top_modules": [{"module": m, "count": c} for m, c in modules.most_common(3)],
        "leftovers": leftovers[:50],
        "details": details,
    }


def aggregate_by_groups(
    tickets: list[Ticket],
    period_type: str,
    *,
    days: int = 7,
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
) -> dict:
    start, end, label = resolve_period(
        period_type, days=days, year=year, month=month, quarter=quarter
    )
    in_period = filter_tickets(tickets, start, end)
    grouped: dict[str, list[Ticket]] = defaultdict(list)
    for t in in_period:
        grouped[t.group_key()].append(t)

    groups: list[dict] = []
    for gname, items in grouped.items():
        customers = sorted({t.customer for t in items if t.customer})
        products = sorted({t.product for t in items if t.product})
        st = stats_for(items, start, end)
        groups.append(
            {
                "group_name": gname,
                "customer": customers[0] if len(customers) == 1 else ("、".join(customers) or "-"),
                "products": products,
                "roomid": next((t.roomid for t in items if t.roomid), ""),
                **st,
            }
        )
    groups.sort(key=lambda g: (-g["issue_cnt"], g["group_name"]))
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period_type": period_type,
        "period_label": label,
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
        "total_groups": len(groups),
        "total_tickets": len(in_period),
        "groups": groups,
    }
