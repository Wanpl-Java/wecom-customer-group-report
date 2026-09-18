from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.archive.sdk import EncryptedChatData, FinanceSdk, FinanceSdkError


def load_private_key(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"私钥不存在: {path}")
    data = path.read_bytes()
    return serialization.load_pem_private_key(data, password=None)


def decrypt_random_key(private_key, encrypt_random_key_b64: str) -> bytes:
    raw = base64.b64decode(encrypt_random_key_b64)
    return private_key.decrypt(raw, padding.PKCS1v15())


def decrypt_chat_message(
    sdk: FinanceSdk,
    private_key,
    item: EncryptedChatData,
) -> dict[str, Any]:
    random_key = decrypt_random_key(private_key, item.encrypt_random_key)
    plain = sdk.decrypt_data(random_key.decode("utf-8", errors="ignore"), item.encrypt_chat_msg)
    # 有的 SDK 要求 random_key 以 bytes 原文传入；若失败再试 latin-1
    if not plain:
        plain = sdk.decrypt_data(random_key.decode("latin-1"), item.encrypt_chat_msg)
    msg = json.loads(plain)
    if item.msgid and msg.get("msgid") and item.msgid != msg.get("msgid"):
        raise FinanceSdkError(f"msgid 不一致 envelope={item.msgid} body={msg.get('msgid')}")
    msg["_seq"] = item.seq
    msg["_publickey_ver"] = item.publickey_ver
    return msg


def extract_text_content(msg: dict[str, Any]) -> str:
    msgtype = (msg.get("msgtype") or "").lower()
    if msgtype == "text":
        return str((msg.get("text") or {}).get("content") or msg.get("content_text") or "")
    if msgtype == "markdown":
        return str((msg.get("info") or {}).get("content") or "")
    if msgtype in {"image", "file", "emotion"}:
        return f"[{msgtype}]"
    # 兜底
    if msg.get("content_text"):
        return str(msg["content_text"])
    return ""


def is_likely_external_message(msg: dict[str, Any]) -> bool:
    msgid = str(msg.get("msgid") or "")
    if msgid.endswith("_external"):
        return True
    # 外部联系人 id 常以 wm / wo 等开头且 roomid 非空
    sender = str(msg.get("from") or "")
    roomid = str(msg.get("roomid") or "")
    if roomid and (sender.startswith("wm") or sender.startswith("wo")):
        return True
    return bool(roomid and "_external" in msgid)
