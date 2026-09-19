from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


@dataclass
class ChatMessage:
    msgid: str
    seq: int
    action: str
    sender: str
    roomid: str
    msgtime: int  # ms
    msgtype: str
    content: str
    is_external: bool = False
    group_name: str = ""
    customer: str = ""
    raw_json: str = ""

    def sent_at(self) -> datetime:
        return datetime.fromtimestamp(self.msgtime / 1000.0)


@dataclass
class Ticket:
    product: str
    summary: str
    customer: str = ""
    group_name: str = ""
    roomid: str = ""
    module: str = ""
    status: str = "open"
    owner: str = ""
    opened_at: str = ""
    closed_at: str = ""
    first_reply_hours: float | None = None
    resolve_hours: float | None = None
    sat_score: int | None = None
    sla_hours: float = 48.0
    source_msgid: str = ""
    last_msg_ms: int = 0

    def opened_dt(self) -> datetime | None:
        return _parse_dt(self.opened_at)

    def closed_dt(self) -> datetime | None:
        return _parse_dt(self.closed_at)

    def is_open(self) -> bool:
        return self.status.lower() in {"open", "doing", "opened", "处理中", "未完结", "遗留"}

    def is_done(self) -> bool:
        return self.status.lower() in {"done", "closed", "完结", "已解决", "已完结"}

    def group_key(self) -> str:
        if self.group_name.strip():
            return self.group_name.strip()
        if self.customer.strip():
            return f"【{self.product}】{self.customer.strip()}"
        if self.roomid.strip():
            return f"群:{self.roomid.strip()}"
        return "未命名客户群"


def _parse_dt(value: str) -> datetime | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  msgid TEXT PRIMARY KEY,
  seq INTEGER NOT NULL,
  action TEXT,
  sender TEXT,
  roomid TEXT,
  msgtime INTEGER,
  msgtype TEXT,
  content TEXT,
  is_external INTEGER DEFAULT 0,
  group_name TEXT DEFAULT '',
  customer TEXT DEFAULT '',
  raw_json TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_messages_room_time ON messages(roomid, msgtime);
CREATE INDEX IF NOT EXISTS idx_messages_seq ON messages(seq);
CREATE TABLE IF NOT EXISTS groups (
  roomid TEXT PRIMARY KEY,
  group_name TEXT,
  customer TEXT,
  is_external INTEGER DEFAULT 1,
  updated_at TEXT
);
"""


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_cursor_seq(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='cursor_seq'").fetchone()
            return int(row["value"]) if row else 0

    def set_cursor_seq(self, seq: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO meta(key,value) VALUES('cursor_seq',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(seq),),
            )

    def upsert_messages(self, items: list[ChatMessage]) -> int:
        if not items:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO messages(msgid,seq,action,sender,roomid,msgtime,msgtype,content,
                                     is_external,group_name,customer,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(msgid) DO UPDATE SET
                  seq=excluded.seq,
                  content=excluded.content,
                  group_name=CASE WHEN excluded.group_name!='' THEN excluded.group_name ELSE messages.group_name END,
                  customer=CASE WHEN excluded.customer!='' THEN excluded.customer ELSE messages.customer END,
                  is_external=excluded.is_external
                """,
                [
                    (
                        m.msgid,
                        m.seq,
                        m.action,
                        m.sender,
                        m.roomid,
                        m.msgtime,
                        m.msgtype,
                        m.content,
                        1 if m.is_external else 0,
                        m.group_name,
                        m.customer,
                        m.raw_json,
                    )
                    for m in items
                ],
            )
        return len(items)

    def upsert_group(self, roomid: str, group_name: str = "", customer: str = "", is_external: bool = True) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO groups(roomid, group_name, customer, is_external, updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(roomid) DO UPDATE SET
                  group_name=CASE WHEN excluded.group_name!='' THEN excluded.group_name ELSE groups.group_name END,
                  customer=CASE WHEN excluded.customer!='' THEN excluded.customer ELSE groups.customer END,
                  is_external=excluded.is_external,
                  updated_at=excluded.updated_at
                """,
                (roomid, group_name, customer, 1 if is_external else 0, datetime.now().isoformat(timespec="seconds")),
            )

    def list_group_messages(
        self,
        *,
        external_only: bool = True,
        roomids: list[str] | None = None,
    ) -> list[ChatMessage]:
        sql = "SELECT * FROM messages WHERE roomid != '' AND IFNULL(action,'send') != 'switch'"
        params: list[Any] = []
        if external_only:
            sql += " AND is_external=1"
        if roomids:
            placeholders = ",".join("?" for _ in roomids)
            sql += f" AND roomid IN ({placeholders})"
            params.extend(roomids)
        sql += " ORDER BY roomid, msgtime"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
            rooms = conn.execute(
                "SELECT COUNT(DISTINCT roomid) c FROM messages WHERE roomid!=''"
            ).fetchone()["c"]
            external = conn.execute(
                "SELECT COUNT(*) c FROM messages WHERE is_external=1"
            ).fetchone()["c"]
            cursor = self.get_cursor_seq()
        return {
            "messages": total,
            "rooms": rooms,
            "external_messages": external,
            "cursor_seq": cursor,
        }

    @staticmethod
    def _row_to_msg(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            msgid=row["msgid"],
            seq=row["seq"],
            action=row["action"] or "send",
            sender=row["sender"] or "",
            roomid=row["roomid"] or "",
            msgtime=row["msgtime"] or 0,
            msgtype=row["msgtype"] or "text",
            content=row["content"] or "",
            is_external=bool(row["is_external"]),
            group_name=row["group_name"] or "",
            customer=row["customer"] or "",
            raw_json=row["raw_json"] or "",
        )


def ticket_asdict(t: Ticket) -> dict[str, Any]:
    return asdict(t)
