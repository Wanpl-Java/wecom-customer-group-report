from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.archive.contact_api import WecomApiError, WecomContactClient
from app.archive.crypto_util import (
    decrypt_chat_message,
    extract_text_content,
    is_likely_external_message,
    load_private_key,
)
from app.archive.sdk import FinanceSdk, FinanceSdkError
from app.config import AppConfig
from app.models import ChatMessage, Store

logger = logging.getLogger(__name__)


def _to_chat_message(msg: dict[str, Any], *, seq: int | None = None) -> ChatMessage | None:
    roomid = str(msg.get("roomid") or "").strip()
    if not roomid:
        return None
    action = str(msg.get("action") or "send")
    if action == "switch":
        return None
    content = extract_text_content(msg)
    msgid = str(msg.get("msgid") or "")
    is_ext = is_likely_external_message(msg)
    return ChatMessage(
        msgid=msgid,
        seq=int(seq if seq is not None else msg.get("_seq") or 0),
        action=action,
        sender=str(msg.get("from") or ""),
        roomid=roomid,
        msgtime=int(msg.get("msgtime") or 0),
        msgtype=str(msg.get("msgtype") or "text"),
        content=content,
        is_external=is_ext,
        group_name=str(msg.get("group_name") or ""),
        customer=str(msg.get("customer") or ""),
        raw_json=json.dumps(msg, ensure_ascii=False),
    )


def enrich_group_names(cfg: AppConfig, store: Store, roomids: set[str]) -> None:
    if not cfg.wecom.contact_secret or not cfg.wecom.corp_id:
        return
    client = WecomContactClient(cfg.wecom.corp_id, cfg.wecom.contact_secret)
    for roomid in roomids:
        try:
            info = client.get_groupchat(roomid)
        except WecomApiError as exc:
            logger.warning("解析群名失败 roomid=%s: %s", roomid, exc)
            continue
        name = str(info.get("name") or "")
        # 取群主或首个客户名作 customer 近似
        customer = ""
        for m in info.get("member_list") or []:
            if int(m.get("type") or 0) == 2:  # 外部联系人
                customer = str(m.get("name") or m.get("userid") or "")
                if customer:
                    break
        store.upsert_group(roomid, group_name=name, customer=customer, is_external=True)
        # 回写消息上的群名
        with store.connect() as conn:
            conn.execute(
                "UPDATE messages SET group_name=?, customer=?, is_external=1 WHERE roomid=?",
                (name, customer, roomid),
            )


def sync_from_sdk(cfg: AppConfig, store: Store, *, max_batches: int = 50) -> dict[str, Any]:
    if not cfg.wecom.corp_id or not cfg.wecom.archive_secret:
        raise FinanceSdkError("请在 config.yaml 配置 wecom.corp_id 与 wecom.archive_secret")

    private_key = load_private_key(cfg.private_key_path)
    cursor = store.get_cursor_seq()
    fetched = 0
    stored = 0
    max_seq = cursor
    rooms: set[str] = set()

    with FinanceSdk(cfg.library_path) as sdk:
        sdk.init(cfg.wecom.corp_id, cfg.wecom.archive_secret)
        for _ in range(max_batches):
            batch = sdk.get_chat_data(
                seq=cursor,
                limit=cfg.sdk.batch_size,
                timeout=cfg.sdk.timeout_seconds,
                proxy=cfg.sdk.proxy,
                proxy_password=cfg.sdk.proxy_password,
            )
            if not batch:
                break
            messages: list[ChatMessage] = []
            for item in batch:
                max_seq = max(max_seq, item.seq)
                try:
                    plain = decrypt_chat_message(sdk, private_key, item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("解密失败 msgid=%s seq=%s: %s", item.msgid, item.seq, exc)
                    continue
                cm = _to_chat_message(plain, seq=item.seq)
                if cm is None:
                    continue
                allow = cfg.wecom.room_allowlist
                if allow and cm.roomid not in allow:
                    continue
                if cfg.wecom.external_only and not cm.is_external:
                    # 先入库标记，后续 contact API 可能纠正；严格模式可跳过
                    # 无 _external 的群也可能是内部群，跳过
                    continue
                messages.append(cm)
                rooms.add(cm.roomid)
            stored += store.upsert_messages(messages)
            fetched += len(batch)
            cursor = max_seq
            store.set_cursor_seq(cursor)
            if len(batch) < cfg.sdk.batch_size:
                break

    enrich_group_names(cfg, store, rooms)
    return {
        "mode": "sdk",
        "fetched": fetched,
        "stored": stored,
        "cursor_seq": store.get_cursor_seq(),
        "rooms": len(rooms),
    }


def import_json_messages(cfg: AppConfig, store: Store, path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("messages") or []
    messages: list[ChatMessage] = []
    rooms: set[str] = set()
    max_seq = store.get_cursor_seq()
    for i, item in enumerate(items):
        if "content" in item and "msgid" in item and "roomid" in item:
            # 已是扁平结构
            cm = ChatMessage(
                msgid=str(item["msgid"]),
                seq=int(item.get("seq") or i + 1),
                action=str(item.get("action") or "send"),
                sender=str(item.get("sender") or item.get("from") or ""),
                roomid=str(item["roomid"]),
                msgtime=int(item.get("msgtime") or 0),
                msgtype=str(item.get("msgtype") or "text"),
                content=str(item.get("content") or ""),
                is_external=bool(item.get("is_external", True)),
                group_name=str(item.get("group_name") or ""),
                customer=str(item.get("customer") or ""),
                raw_json=json.dumps(item, ensure_ascii=False),
            )
        else:
            cm = _to_chat_message(item, seq=item.get("_seq") or item.get("seq") or i + 1)
        if cm is None:
            continue
        if cfg.wecom.external_only and not cm.is_external:
            continue
        messages.append(cm)
        rooms.add(cm.roomid)
        max_seq = max(max_seq, cm.seq)
    n = store.upsert_messages(messages)
    if max_seq:
        store.set_cursor_seq(max_seq)
    for cm in messages:
        if cm.group_name or cm.customer:
            store.upsert_group(cm.roomid, cm.group_name, cm.customer, True)
    return {"mode": "json", "stored": n, "rooms": len(rooms), "cursor_seq": store.get_cursor_seq()}


def sync_demo(cfg: AppConfig, store: Store) -> dict[str, Any]:
    sample = cfg.data_dir / "sample_messages.json"
    if not sample.exists():
        raise FileNotFoundError(f"演示数据不存在: {sample}")
    result = import_json_messages(cfg, store, sample)
    result["mode"] = "demo"
    return result


def run_sync(cfg: AppConfig, store: Store, *, json_path: Path | None = None) -> dict[str, Any]:
    mode = (cfg.mode or "demo").lower()
    if json_path:
        return import_json_messages(cfg, store, json_path)
    if mode == "sdk":
        return sync_from_sdk(cfg, store)
    if mode == "json":
        path = cfg.data_dir / "messages.json"
        return import_json_messages(cfg, store, path)
    return sync_demo(cfg, store)
