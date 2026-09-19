from __future__ import annotations

import re
from collections import defaultdict

from app.config import AnalyzeConfig
from app.models import ChatMessage, Ticket

MODULE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("认证/LDAP/SSO", ("ldap", "sso", "认证", "登录", "oauth", "saml", "ad域", "域控")),
    ("客户端连接", ("客户端", "连接卡顿", "razor", "win11", "mstsc", "rdp", "ssh连接", "连不上")),
    ("证书/SSL/TLS", ("证书", "ssl", "tls", "https")),
    ("资产/账号/权限", ("资产", "账号", "权限", "授权", "导入")),
    ("发布机/水印", ("发布机", "水印", "远程应用")),
    ("审计/录像", ("审计", "录像", "会话回放", "命令过滤")),
    ("集群/高可用", ("集群", "高可用", "ha", "节点")),
    ("升级/迁移", ("升级", "迁移", "版本")),
    ("报表/导出", ("报表", "导出")),
    ("数据库对接", ("oracle", "达梦", "mysql", "数据库")),
]

ISSUE_HINTS = (
    "问题",
    "故障",
    "报错",
    "失败",
    "无法",
    "不能",
    "异常",
    "超时",
    "卡顿",
    "咨询",
    "帮忙",
    "支持",
    "怎么",
    "如何",
    "error",
    "bug",
)

DONE_HINTS = ("已解决", "已完结", "搞定", "处理好了", "关闭问题", "#done", "感谢", "谢谢", "可以了", "没问题", "解决了", "辛苦了", "麻烦了", "好嘞", "收到谢谢", "好的谢谢")
DOING_HINTS = ("处理中", "跟进中", "排查中", "看一下", "#doing")
OPEN_HINTS = ("遗留", "未解决", "待确认", "#open")
CLOSING_ACK = {"谢谢", "感谢", "可以了", "没问题", "解决了", "辛苦了", "好嘞", "麻烦你了"}


def infer_module(text: str) -> str:
    low = (text or "").lower()
    for name, keys in MODULE_KEYWORDS:
        for k in keys:
            if k.lower() in low:
                return name
    return "其他"


def infer_product(text: str, default: str = "JS") -> str:
    up = (text or "").upper()
    for p in ("JS", "DE", "MK"):
        if p in up or f"【{p}】" in (text or ""):
            return p
    if "JUMPSERVER" in up or "堡垒" in (text or "") or "跳板" in (text or ""):
        return "JS"
    return default


def _sat(text: str) -> int | None:
    m = re.search(r"(?:满意度|sat)\s*[=:：]?\s*([1-5])", text, re.I)
    return int(m.group(1)) if m else None


def _status(text: str) -> str:
    if any(h in text for h in DONE_HINTS):
        return "done"
    if any(h in text for h in DOING_HINTS):
        return "doing"
    if any(h in text for h in OPEN_HINTS):
        return "open"
    return ""


def _looks_like_issue(text: str) -> bool:
    if len(text.strip()) < 4:
        return False
    if _status(text) or _sat(text) is not None:
        return True
    return any(h in text.lower() for h in ISSUE_HINTS)


def _is_staff(sender: str, staff_ids: list[str]) -> bool:
    if not staff_ids:
        # 无配置时：不以 wm/wo 开头的视为员工
        return not (sender.startswith("wm") or sender.startswith("wo"))
    return sender in staff_ids


def messages_to_tickets(messages: list[ChatMessage], cfg: AnalyzeConfig) -> list[Ticket]:
    """
    按群聚合聊天，用启发式从客户提问/员工闭环话术抽取支持问题。
    """
    by_room: dict[str, list[ChatMessage]] = defaultdict(list)
    for m in messages:
        if m.msgtype not in {"text", "markdown"} and not m.content:
            continue
        if not m.content or m.content.startswith("["):
            continue
        by_room[m.roomid].append(m)

    tickets: list[Ticket] = []
    for roomid, msgs in by_room.items():
        msgs = sorted(msgs, key=lambda x: x.msgtime)
        group_name = next((m.group_name for m in msgs if m.group_name), "")
        customer = next((m.customer for m in msgs if m.customer), "")
        open_ticket: Ticket | None = None
        has_staff_reply = False

        for m in msgs:
            text = m.content.strip()
            staff = _is_staff(m.sender, cfg.staff_userids)
            st = _status(text)
            sat = _sat(text)
            ack = any(a in text for a in CLOSING_ACK)

            # 员工已回复后客户发收尾致谢 -> 关闭当前 open 单（显式闭环）
            if open_ticket and not staff and has_staff_reply and ack:
                open_ticket.last_msg_ms = m.msgtime
                open_ticket.status = "done"
                open_ticket.closed_at = m.sent_at().strftime("%Y-%m-%d %H:%M")
                od = open_ticket.opened_dt()
                if od:
                    open_ticket.resolve_hours = round((m.sent_at() - od).total_seconds() / 3600, 1)
                open_ticket = None
                has_staff_reply = False
                continue

            if not staff and _looks_like_issue(text) and not ack:
                # 新问题
                product = infer_product(text, cfg.default_product)
                summary = re.sub(r"(?:满意度|sat)\s*[=:：]?\s*[1-5]", "", text, flags=re.I)
                summary = re.sub(r"(已解决|已完结|处理中|跟进中|遗留|#\w+)", "", summary).strip()
                summary = summary[:180] or text[:180]
                open_ticket = Ticket(
                    product=product,
                    summary=summary,
                    customer=customer or _guess_customer(group_name),
                    group_name=group_name or f"群:{roomid}",
                    roomid=roomid,
                    module=infer_module(text),
                    status=st or "open",
                    owner=m.sender if staff else "",
                    opened_at=m.sent_at().strftime("%Y-%m-%d %H:%M"),
                    sat_score=sat,
                    sla_hours=cfg.sla_hours,
                    source_msgid=m.msgid,
                    last_msg_ms=m.msgtime,
                )
                if open_ticket.status == "done":
                    open_ticket.closed_at = open_ticket.opened_at
                tickets.append(open_ticket)
                continue

            if open_ticket and staff:
                open_ticket.last_msg_ms = m.msgtime
                has_staff_reply = True
                if not open_ticket.owner:
                    open_ticket.owner = m.sender
                if st:
                    open_ticket.status = st
                if sat is not None:
                    open_ticket.sat_score = sat
                if st == "done":
                    open_ticket.closed_at = m.sent_at().strftime("%Y-%m-%d %H:%M")
                    od = open_ticket.opened_dt()
                    if od:
                        open_ticket.resolve_hours = round((m.sent_at() - od).total_seconds() / 3600, 1)
                    open_ticket = None
                    has_staff_reply = False
                elif sat is not None and "满意" in text:
                    # 闭环满意度短句
                    open_ticket.status = "done"
                    open_ticket.closed_at = m.sent_at().strftime("%Y-%m-%d %H:%M")
                    open_ticket = None
                    has_staff_reply = False

            elif staff and (st == "done" or sat is not None) and _looks_like_issue(text):
                product = infer_product(text, cfg.default_product)
                tickets.append(
                    Ticket(
                        product=product,
                        summary=text[:180],
                        customer=customer or _guess_customer(group_name),
                        group_name=group_name or f"群:{roomid}",
                        roomid=roomid,
                        module=infer_module(text),
                        status=st or "done",
                        owner=m.sender,
                        opened_at=m.sent_at().strftime("%Y-%m-%d %H:%M"),
                        closed_at=m.sent_at().strftime("%Y-%m-%d %H:%M") if (st == "done" or sat) else "",
                        sat_score=sat,
                        sla_hours=cfg.sla_hours,
                        source_msgid=m.msgid,
                        last_msg_ms=m.msgtime,
                    )
                )

    return tickets


def _guess_customer(group_name: str) -> str:
    text = group_name or ""
    text = re.sub(r"^【[^】]+】", "", text).strip()
    for suffix in ("JumpServer", "支持群", "集群", "对接", "POC", "UAT", "生产群"):
        text = text.replace(suffix, "")
    return text.strip() or ""
