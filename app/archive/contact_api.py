from __future__ import annotations

import time
from typing import Any

import httpx


class WecomApiError(RuntimeError):
    pass


class WecomContactClient:
    """客户联系 / 通讯录辅助：解析外部客户群名称。"""

    def __init__(self, corp_id: str, secret: str) -> None:
        self.corp_id = corp_id
        self.secret = secret
        self._token: str | None = None
        self._expires_at = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params={"corpid": self.corp_id, "corpsecret": self.secret})
            data = resp.json()
        if data.get("errcode", 0) != 0:
            raise WecomApiError(f"gettoken 失败: {data}")
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 7200))
        return self._token

    def get_groupchat(self, chat_id: str) -> dict[str, Any]:
        token = self._ensure_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/externalcontact/groupchat/get"
        with httpx.Client(timeout=20) as client:
            resp = client.post(url, params={"access_token": token}, json={"chat_id": chat_id, "need_name": 1})
            data = resp.json()
        if data.get("errcode", 0) != 0:
            raise WecomApiError(f"groupchat/get 失败: {data}")
        return data.get("group_chat") or {}
