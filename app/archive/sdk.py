from __future__ import annotations

import ctypes
import json
from ctypes import POINTER, c_char_p, c_int, c_uint, c_ulonglong, c_void_p
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Slice(ctypes.Structure):
    _fields_ = [("buf", c_void_p), ("len", c_int)]


@dataclass
class EncryptedChatData:
    seq: int
    msgid: str
    publickey_ver: int
    encrypt_random_key: str
    encrypt_chat_msg: str


class FinanceSdkError(RuntimeError):
    pass


class FinanceSdk:
    """ctypes 封装官方 WeWorkFinanceSdk_C（仅 Linux 可用）。"""

    def __init__(self, library_path: Path) -> None:
        if not library_path.exists():
            raise FinanceSdkError(
                f"未找到会话存档 SDK: {library_path}\n"
                "请将官方 libWeWorkFinanceSdk_C.so 放到 lib/ 目录。"
            )
        self._lib = ctypes.CDLL(str(library_path))
        self._bind()
        self._sdk = self._lib.NewSdk()
        if not self._sdk:
            raise FinanceSdkError("NewSdk 失败")

    def _bind(self) -> None:
        lib = self._lib
        lib.NewSdk.restype = c_void_p
        lib.DestroySdk.argtypes = [c_void_p]
        lib.Init.argtypes = [c_void_p, c_char_p, c_char_p]
        lib.Init.restype = c_int
        lib.GetChatData.argtypes = [
            c_void_p,
            c_ulonglong,
            c_uint,
            c_char_p,
            c_char_p,
            c_int,
            POINTER(Slice),
        ]
        lib.GetChatData.restype = c_int
        lib.DecryptData.argtypes = [c_char_p, c_char_p, POINTER(Slice)]
        lib.DecryptData.restype = c_int
        lib.NewSlice.restype = POINTER(Slice)
        lib.FreeSlice.argtypes = [POINTER(Slice)]
        # 部分 SDK 版本提供 GetContentFromSlice；若无则直接读 Slice.buf
        if hasattr(lib, "GetContentFromSlice"):
            lib.GetContentFromSlice.argtypes = [POINTER(Slice)]
            lib.GetContentFromSlice.restype = c_char_p

    def init(self, corp_id: str, secret: str) -> None:
        ret = self._lib.Init(self._sdk, corp_id.encode(), secret.encode())
        if ret != 0:
            raise FinanceSdkError(f"Init 失败 ret={ret}")

    def get_chat_data(
        self,
        seq: int,
        limit: int,
        timeout: int,
        proxy: str = "",
        proxy_password: str = "",
    ) -> list[EncryptedChatData]:
        slice_ptr = self._lib.NewSlice()
        if not slice_ptr:
            raise FinanceSdkError("NewSlice 失败")
        try:
            ret = self._lib.GetChatData(
                self._sdk,
                c_ulonglong(seq),
                c_uint(limit),
                proxy.encode() if proxy else b"",
                proxy_password.encode() if proxy_password else b"",
                c_int(timeout),
                slice_ptr,
            )
            if ret != 0:
                raise FinanceSdkError(f"GetChatData 失败 ret={ret}")
            payload = self._slice_text(slice_ptr)
        finally:
            self._lib.FreeSlice(slice_ptr)

        data = json.loads(payload or "{}")
        errcode = data.get("errcode", 0)
        if errcode not in (0, None):
            raise FinanceSdkError(f"GetChatData 业务错误: {data}")
        out: list[EncryptedChatData] = []
        for item in data.get("chatdata") or []:
            out.append(
                EncryptedChatData(
                    seq=int(item.get("seq") or 0),
                    msgid=str(item.get("msgid") or ""),
                    publickey_ver=int(item.get("publickey_ver") or 0),
                    encrypt_random_key=str(item.get("encrypt_random_key") or ""),
                    encrypt_chat_msg=str(item.get("encrypt_chat_msg") or ""),
                )
            )
        return out

    def decrypt_data(self, encrypt_key: str, encrypt_msg: str) -> str:
        slice_ptr = self._lib.NewSlice()
        if not slice_ptr:
            raise FinanceSdkError("NewSlice 失败")
        try:
            ret = self._lib.DecryptData(
                encrypt_key.encode(),
                encrypt_msg.encode(),
                slice_ptr,
            )
            if ret != 0:
                raise FinanceSdkError(f"DecryptData 失败 ret={ret}")
            return self._slice_text(slice_ptr)
        finally:
            self._lib.FreeSlice(slice_ptr)

    def _slice_text(self, slice_ptr: Any) -> str:  # noqa: ANN401
        if hasattr(self._lib, "GetContentFromSlice"):
            raw = self._lib.GetContentFromSlice(slice_ptr)
            if raw:
                return ctypes.string_at(raw).decode("utf-8", errors="replace")
        sl = slice_ptr.contents
        if not sl.buf or sl.len <= 0:
            return ""
        return ctypes.string_at(sl.buf, sl.len).decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._sdk:
            self._lib.DestroySdk(self._sdk)
            self._sdk = None

    def __enter__(self) -> FinanceSdk:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
