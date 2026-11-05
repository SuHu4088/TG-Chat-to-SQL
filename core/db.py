"""SQLite 数据层（Schema v3）。

V3 相对 V2 的变化：
- 新增 chats 表：群列表、重命名（display_name）、每群统计。
- import_log 增加 chat_id / duration_ms / error，导入记录可按群归属。
- 新增 audit_log：删除等敏感操作的可审计记录。
- 新增 app_settings：删除权限等开关（默认关闭）。
- 新增 (chat_id, date_unixtime) 复合索引，深分页与时间轴查询不再退化。
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

SCHEMA_VERSION = 3

_MESSAGE_COLUMNS = (
    "message_key, id, chat_id, message_type, date, date_unixtime, sender_name, "
    "sender_id, text_content, reply_to_message_id, forwarded_from, media_type, "
    "raw_json, content_hash"
)


class DatabaseManager:
    def __init__(self, db_path: str, store_raw: bool = True):
        self.db_path = db_path
        self.store_raw = store_raw
        self.conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # 连接与建表
    # ------------------------------------------------------------------
    def connect(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    @staticmethod
    def make_message_key(chat_id: str, message_id) -> str:
        return f"{chat_id}:{message_id}"

    def _table_exists(self, name: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        return cur.fetchone() is not None

    def _column_names(self, table: str) -> List[str]:
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]

    def init_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        if self._table_exists("messages"):
            columns = self._column_names("messages")
            if "message_key" not in columns:
                self._migrate_v1_to_v2()

        self._create_v3_tables()

        if self._table_exists("chat_info"):
            self._migrate_chat_info()

        self._ensure_import_log_columns()
        self._create_indexes()

        self._set_meta("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()

    def _create_v3_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT,
                chat_type TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL UNIQUE,
                id INTEGER NOT NULL,
                chat_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                date TEXT,
                date_unixtime INTEGER,
                sender_name TEXT,
                sender_id TEXT,
                text_content TEXT,
                reply_to_message_id INTEGER,
                forwarded_from TEXT,
                media_type TEXT,
                raw_json TEXT,
                content_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT,
                FOREIGN KEY (message_key) REFERENCES messages(message_key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_time TEXT,
                chat_id TEXT,
                json_file TEXT,
                total_messages INTEGER,
                imported_count INTEGER,
                skipped_count INTEGER,
                status TEXT,
                duration_ms INTEGER,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                detail TEXT,
                allowed INTEGER NOT NULL,
                actor TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO app_settings(key, value, updated_at) "
            "VALUES('delete_enabled', '0', datetime('now','localtime'))"
        )

    def _create_indexes(self):
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_chat_date
                ON messages(chat_id, date_unixtime, row_id);
            CREATE INDEX IF NOT EXISTS idx_messages_chat_msgid
                ON messages(chat_id, id);
            CREATE INDEX IF NOT EXISTS idx_messages_sender
                ON messages(chat_id, sender_name);
            CREATE INDEX IF NOT EXISTS idx_messages_date
                ON messages(date_unixtime);
            CREATE INDEX IF NOT EXISTS idx_entities_message_key
                ON text_entities(message_key);
            CREATE INDEX IF NOT EXISTS idx_import_log_chat
                ON import_log(chat_id, import_time);
            """
        )

    def _migrate_chat_info(self):
        """v2 的 chat_info → v3 的 chats，然后删除旧表。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT chat_name, chat_type, chat_id FROM chat_info")
        for chat_name, chat_type, chat_id in cursor.fetchall():
            cursor.execute(
                "INSERT OR IGNORE INTO chats(chat_id, name, chat_type) VALUES (?, ?, ?)",
                (str(chat_id), chat_name or "Unknown", chat_type or "unknown"),
            )
        cursor.execute("DROP TABLE chat_info")
        self.conn.commit()

    def _ensure_import_log_columns(self):
        columns = self._column_names("import_log")
        if "chat_id" not in columns:
            self.conn.execute("ALTER TABLE import_log ADD COLUMN chat_id TEXT")
        if "duration_ms" not in columns:
            self.conn.execute("ALTER TABLE import_log ADD COLUMN duration_ms INTEGER")
        if "error" not in columns:
            self.conn.execute("ALTER TABLE import_log ADD COLUMN error TEXT")
        self.conn.commit()

    def _migrate_v1_to_v2(self):
        """把 v1（messages.id 主键、text_entities.message_id）迁移到 v2 结构。"""
        cursor = self.conn.cursor()
        self.conn.execute("PRAGMA foreign_keys=OFF")

        has_entities = self._table_exists("text_entities")
        if has_entities:
            cursor.execute("ALTER TABLE text_entities RENAME TO text_entities_v1")
        cursor.execute("ALTER TABLE messages RENAME TO messages_v1")

        cursor.execute(
            """
            CREATE TABLE messages (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL,
                id INTEGER NOT NULL,
                chat_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                date TEXT,
                date_unixtime INTEGER,
                sender_name TEXT,
                sender_id TEXT,
                text_content TEXT,
                reply_to_message_id INTEGER,
                forwarded_from TEXT,
                media_type TEXT,
                raw_json TEXT,
                content_hash TEXT,
                UNIQUE(message_key)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT,
                FOREIGN KEY (message_key) REFERENCES messages(message_key) ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            INSERT OR IGNORE INTO messages
            (message_key, id, chat_id, message_type, date, date_unixtime, sender_name,
             sender_id, text_content, reply_to_message_id, forwarded_from, media_type, raw_json)
            SELECT
                COALESCE(chat_id, '') || ':' || id,
                id, COALESCE(chat_id, ''), message_type, date, date_unixtime, sender_name,
                sender_id, text_content, reply_to_message_id, forwarded_from, media_type, raw_json
            FROM messages_v1
            """
        )

        if has_entities:
            cursor.execute(
                """
                INSERT INTO text_entities (message_key, entity_type, entity_text)
                SELECT
                    COALESCE(m.chat_id, '') || ':' || e.message_id,
                    e.entity_type,
                    e.entity_text
                FROM text_entities_v1 e
                JOIN messages_v1 m ON m.id = e.message_id
                """
            )
            cursor.execute("DROP TABLE text_entities_v1")

        cursor.execute("DROP TABLE messages_v1")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def _set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_schema_version(self) -> int:
        try:
            cur = self.conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'")
            row = cur.fetchone()
            return int(row[0]) if row else SCHEMA_VERSION
        except sqlite3.DatabaseError:
            return SCHEMA_VERSION

    # ------------------------------------------------------------------
    # 群列表
    # ------------------------------------------------------------------
    @staticmethod
    def _chat_display_name(name: str, display_name: Optional[str]) -> str:
        return display_name or name or "未命名群组"

    def upsert_chat(self, chat_id: str, name: str, chat_type: str = "unknown"):
        """导入时写入群信息；已有群只更新原始名，不覆盖用户重命名。"""
        self.conn.execute(
            """
            INSERT INTO chats(chat_id, name, chat_type, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(chat_id) DO UPDATE SET
                name = excluded.name,
                chat_type = excluded.chat_type,
                updated_at = excluded.updated_at
            """,
            (str(chat_id), name or "Unknown", chat_type or "unknown"),
        )
        self.conn.commit()

    # 兼容旧接口
    def insert_chat_info(self, chat_name: str, chat_type: str, chat_id: str):
        self.upsert_chat(str(chat_id), chat_name, chat_type)

    def get_chat_info(self, chat_id: Optional[str] = None) -> Optional[Tuple]:
        if chat_id is None:
            row = self.conn.execute(
                "SELECT rowid, COALESCE(display_name, name), chat_type, chat_id "
                "FROM chats ORDER BY rowid LIMIT 1"
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT rowid, COALESCE(display_name, name), chat_type, chat_id "
                "FROM chats WHERE chat_id=?",
                (str(chat_id),),
            ).fetchone()
        return row

    def list_chats(self) -> List[Dict]:
        rows = self.conn.execute(
            """
            SELECT c.chat_id,
                   COALESCE(c.display_name, c.name) AS title,
                   c.name AS original_name,
                   c.chat_type,
                   COUNT(m.row_id) AS message_count,
                   MIN(m.date_unixtime) AS first_ts,
                   MAX(m.date_unixtime) AS last_ts
            FROM chats c
            LEFT JOIN messages m ON m.chat_id = c.chat_id
            GROUP BY c.chat_id
            ORDER BY message_count DESC, c.chat_id
            """
        ).fetchall()

        import_stats = {
            row[0]: {"import_count": row[1], "last_import": row[2]}
            for row in self.conn.execute(
                "SELECT chat_id, COUNT(*), MAX(import_time) FROM import_log "
                "WHERE chat_id IS NOT NULL GROUP BY chat_id"
            ).fetchall()
        }

        result = []
        for chat_id, title, original_name, chat_type, count, first_ts, last_ts in rows:
            stats = import_stats.get(chat_id, {})
            result.append(
                {
                    "chat_id": chat_id,
                    "title": title,
                    "original_name": original_name,
                    "chat_type": chat_type,
                    "message_count": count,
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "import_count": stats.get("import_count", 0),
                    "last_import": stats.get("last_import"),
                }
            )
        return result

    def rename_chat(self, chat_id: str, new_name: str):
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("群名称不能为空")
        self.conn.execute(
            "UPDATE chats SET display_name=?, updated_at=datetime('now','localtime') "
            "WHERE chat_id=?",
            (new_name, str(chat_id)),
        )
        if self.conn.total_changes == 0 and not self.conn.execute(
            "SELECT 1 FROM chats WHERE chat_id=?", (str(chat_id),)
        ).fetchone():
            raise ValueError("群不存在")
        self.conn.commit()

    def delete_chat_data(self, chat_id: str) -> Dict:
        """删除一个群的全部消息与导入记录（调用方必须先通过删除权限闸门）。"""
        chat_id = str(chat_id)
        message_count = self.count_messages(chat_id)
        entity_count = self.conn.execute(
            "SELECT COUNT(*) FROM text_entities e JOIN messages m ON m.message_key=e.message_key "
            "WHERE m.chat_id=?",
            (chat_id,),
        ).fetchone()[0]

        self.conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        self.conn.execute("DELETE FROM import_log WHERE chat_id=?", (chat_id,))
        self.conn.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
        self.conn.commit()
        return {"chat_id": chat_id, "messages_deleted": message_count, "entities_deleted": entity_count}

    # ------------------------------------------------------------------
    # 去重与查询
    # ------------------------------------------------------------------
    def get_existing_message_keys(self, chat_id: Optional[str] = None) -> set:
        if chat_id is None:
            cur = self.conn.execute("SELECT message_key FROM messages")
        else:
            cur = self.conn.execute(
                "SELECT message_key FROM messages WHERE chat_id=?", (str(chat_id),)
            )
        return {row[0] for row in cur.fetchall()}

    def get_existing_message_ids(self) -> set:
        return {row[0] for row in self.conn.execute("SELECT id FROM messages").fetchall()}

    def get_message_by_key(self, message_key: str) -> Optional[Tuple]:
        return self.conn.execute(
            "SELECT id, chat_id, date, sender_name, text_content FROM messages WHERE message_key=?",
            (message_key,),
        ).fetchone()

    def get_max_message_id(self, chat_id: Optional[str] = None) -> Optional[int]:
        if chat_id is None:
            row = self.conn.execute("SELECT MAX(id) FROM messages").fetchone()
        else:
            row = self.conn.execute(
                "SELECT MAX(id) FROM messages WHERE chat_id=?", (str(chat_id),)
            ).fetchone()
        return row[0]

    def get_message_count(self, chat_id: Optional[str] = None) -> int:
        return self.count_messages(chat_id)

    def count_messages(self, chat_id: Optional[str] = None) -> int:
        if chat_id is None:
            return self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id=?", (str(chat_id),)
        ).fetchone()[0]

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(msg: Dict) -> str:
        text = msg.get("text", "")
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            parts = []
            for item in text:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            return "".join(parts)
        return ""

    @staticmethod
    def _to_unixtime(msg: Dict) -> int:
        raw = msg.get("date_unixtime")
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
        date_str = msg.get("date")
        if date_str:
            try:
                return int(datetime.fromisoformat(date_str).timestamp())
            except ValueError:
                pass
        return 0

    @staticmethod
    def _content_hash(msg: Dict) -> str:
        payload = json.dumps(
            {
                "id": msg.get("id"),
                "date": msg.get("date"),
                "text": msg.get("text"),
                "sender": msg.get("from") or msg.get("actor"),
                "forwarded_from": msg.get("forwarded_from"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _build_row(self, msg: Dict, chat_id: str):
        message_key = self.make_message_key(chat_id, msg.get("id"))
        sender_name = msg.get("from") or msg.get("actor")
        sender_id = msg.get("from_id") or msg.get("actor_id", "")
        raw = json.dumps(msg, ensure_ascii=False) if self.store_raw else None
        return (
            message_key,
            msg.get("id"),
            chat_id,
            msg.get("type", "message"),
            msg.get("date"),
            self._to_unixtime(msg),
            sender_name,
            sender_id,
            self._extract_text(msg),
            msg.get("reply_to_message_id"),
            msg.get("forwarded_from"),
            msg.get("media_type"),
            raw,
            self._content_hash(msg),
        )

    def insert_messages_batch(self, messages: List[Dict], chat_id: Optional[str] = None) -> int:
        """批量写入；返回真实新增条数。

        优化点（相对 v1.1 的逐条 execute + 全表 key set）：
        - 先查本批次已存在的 key（500 条一次查询），只为新消息写 text_entities；
        - 消息与实体都用 executemany，减少 Python↔SQLite 往返。
        """
        cid = str(chat_id if chat_id is not None else "")
        rows = []
        seen = set()
        for msg in messages:
            row = self._build_row(msg, cid)
            if row[0] in seen:
                continue
            seen.add(row[0])
            rows.append(row)

        if not rows:
            return 0

        existing = set()
        for i in range(0, len(rows), 900):
            chunk = [row[0] for row in rows[i:i + 900]]
            placeholders = ",".join("?" for _ in chunk)
            existing.update(
                r[0]
                for r in self.conn.execute(
                    f"SELECT message_key FROM messages WHERE message_key IN ({placeholders})",
                    chunk,
                )
            )

        new_rows = [row for row in rows if row[0] not in existing]
        if not new_rows:
            return 0

        self.conn.executemany(
            f"INSERT OR IGNORE INTO messages ({_MESSAGE_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            new_rows,
        )

        entities = []
        new_keys = {row[0] for row in new_rows}
        for msg in messages:
            key = self.make_message_key(cid, msg.get("id"))
            if key not in new_keys:
                continue
            for entity in msg.get("text_entities", []) or []:
                entities.append((key, entity.get("type", ""), entity.get("text", "")))
        if entities:
            self.conn.executemany(
                "INSERT INTO text_entities(message_key, entity_type, entity_text) VALUES (?,?,?)",
                entities,
            )

        self.conn.commit()
        return len(new_rows)

    def log_import(
        self,
        json_file: str,
        total: int,
        imported: int,
        skipped: int,
        status: str = "success",
        chat_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ):
        self.conn.execute(
            """
            INSERT INTO import_log
            (import_time, chat_id, json_file, total_messages, imported_count,
             skipped_count, status, duration_ms, error)
            VALUES (datetime('now','localtime'), ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, json_file, total, imported, skipped, status, duration_ms, error),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # 分页 / 搜索 / 统计
    # ------------------------------------------------------------------
    def get_messages_page(self, chat_id: str, offset: int, limit: int) -> Dict:
        total = self.count_messages(chat_id)
        rows = self.conn.execute(
            """
            SELECT m.row_id, m.message_key, m.id, m.message_type, m.date, m.date_unixtime,
                   m.sender_name, m.sender_id, m.text_content, m.reply_to_message_id,
                   m.forwarded_from, m.media_type, m.raw_json,
                   r.sender_name AS reply_sender, r.text_content AS reply_text
            FROM messages m
            LEFT JOIN messages r ON r.chat_id = m.chat_id AND r.id = m.reply_to_message_id
            WHERE m.chat_id = ?
            ORDER BY m.date_unixtime, m.row_id
            LIMIT ? OFFSET ?
            """,
            (str(chat_id), int(limit), int(offset)),
        ).fetchall()

        items = []
        for row in rows:
            raw = None
            if row[12]:
                try:
                    raw = json.loads(row[12])
                except (TypeError, ValueError):
                    raw = None
            items.append(
                {
                    "row_id": row[0],
                    "message_key": row[1],
                    "id": row[2],
                    "type": row[3],
                    "date": row[4],
                    "date_unixtime": row[5],
                    "sender_name": row[6],
                    "sender_id": row[7],
                    "text": row[8],
                    "reply_to_message_id": row[9],
                    "forwarded_from": row[10],
                    "media_type": row[11],
                    "reply_sender": row[13],
                    "reply_text": row[14],
                    "raw": raw,
                }
            )

        return {"total": total, "offset": offset, "limit": limit, "items": items}

    def search_messages(self, chat_id: str, query: str, limit: int = 200) -> Dict:
        query = (query or "").strip()
        if not query:
            return {"total": 0, "items": []}
        pattern = f"%{query}%"
        total = self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id=? AND (text_content LIKE ? OR sender_name LIKE ?)",
            (str(chat_id), pattern, pattern),
        ).fetchone()[0]
        rows = self.conn.execute(
            """
            SELECT row_id, id, date, sender_name, text_content, message_type
            FROM messages
            WHERE chat_id=? AND (text_content LIKE ? OR sender_name LIKE ?)
            ORDER BY date_unixtime DESC
            LIMIT ?
            """,
            (str(chat_id), pattern, pattern, int(limit)),
        ).fetchall()
        return {
            "total": total,
            "items": [
                {
                    "row_id": r[0],
                    "id": r[1],
                    "date": r[2],
                    "sender_name": r[3],
                    "text": r[4],
                    "type": r[5],
                }
                for r in rows
            ],
        }

    def get_statistics(self, chat_id: Optional[str] = None) -> Dict:
        where = "" if chat_id is None else " WHERE chat_id=?"
        args = () if chat_id is None else (str(chat_id),)

        total = self.conn.execute(f"SELECT COUNT(*) FROM messages{where}", args).fetchone()[0]
        regular = self.conn.execute(
            f"SELECT COUNT(*) FROM messages{where}{' AND' if where else ' WHERE'} message_type='message'",
            args,
        ).fetchone()[0]
        service = self.conn.execute(
            f"SELECT COUNT(*) FROM messages{where}{' AND' if where else ' WHERE'} message_type='service'",
            args,
        ).fetchone()[0]
        senders = self.conn.execute(
            f"SELECT COUNT(DISTINCT sender_id) FROM messages{where}{' AND' if where else ' WHERE'} sender_id IS NOT NULL",
            args,
        ).fetchone()[0]
        replies = self.conn.execute(
            f"SELECT COUNT(*) FROM messages{where}{' AND' if where else ' WHERE'} reply_to_message_id IS NOT NULL",
            args,
        ).fetchone()[0]
        forwards = self.conn.execute(
            f"SELECT COUNT(*) FROM messages{where}{' AND' if where else ' WHERE'} forwarded_from IS NOT NULL",
            args,
        ).fetchone()[0]
        if chat_id is None:
            entities = self.conn.execute("SELECT COUNT(*) FROM text_entities").fetchone()[0]
        else:
            entities = self.conn.execute(
                "SELECT COUNT(*) FROM text_entities e JOIN messages m ON m.message_key=e.message_key "
                "WHERE m.chat_id=?",
                (str(chat_id),),
            ).fetchone()[0]

        first_ts, last_ts = self.conn.execute(
            f"SELECT MIN(date_unixtime), MAX(date_unixtime) FROM messages{where}", args
        ).fetchone()

        return {
            "total_messages": total,
            "regular_messages": regular,
            "service_messages": service,
            "unique_senders": senders,
            "reply_count": replies,
            "forward_count": forwards,
            "entity_count": entities,
            "first_ts": first_ts,
            "last_ts": last_ts,
        }

    def get_top_senders(self, chat_id: str, limit: int = 20,
                        start: Optional[str] = None, end: Optional[str] = None) -> List[Tuple]:
        clause, args = self._date_clause(start, end)
        return self.conn.execute(
            f"""
            SELECT COALESCE(sender_name, '未知用户') AS name, COUNT(*) AS cnt
            FROM messages
            WHERE chat_id=? AND message_type='message'{clause}
            GROUP BY name
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (str(chat_id), *args, int(limit)),
        ).fetchall()

    @staticmethod
    def _date_clause(start: Optional[str], end: Optional[str]):
        """按日期（YYYY-MM-DD，含首尾）过滤。"""
        clause = ""
        args: List[str] = []
        if start:
            clause += " AND substr(date, 1, 10) >= ?"
            args.append(start)
        if end:
            clause += " AND substr(date, 1, 10) <= ?"
            args.append(end)
        return clause, args

    def get_activity_heatmap(self, chat_id: str, start: Optional[str] = None,
                             end: Optional[str] = None) -> Dict:
        """7×24 活跃度，周一为第 0 行。"""
        clause, args = self._date_clause(start, end)
        rows = self.conn.execute(
            f"""
            SELECT CAST(strftime('%w', datetime(date_unixtime, 'unixepoch', 'localtime')) AS INTEGER) AS dow,
                   CAST(strftime('%H', datetime(date_unixtime, 'unixepoch', 'localtime')) AS INTEGER) AS hour,
                   COUNT(*) AS cnt
            FROM messages
            WHERE chat_id=?{clause}
            GROUP BY dow, hour
            """,
            (str(chat_id), *args),
        ).fetchall()
        data = {}
        for dow, hour, count in rows:
            index = (dow + 6) % 7  # 周日=0 → 周一=0
            data[f"{index}_{hour}"] = count
        return data

    def get_daily_summary(self, chat_id: str, start: Optional[str] = None,
                          end: Optional[str] = None) -> List[Tuple]:
        clause, args = self._date_clause(start, end)
        return self.conn.execute(
            f"""
            SELECT substr(date, 1, 10) AS day, COUNT(*) AS cnt
            FROM messages
            WHERE chat_id=? AND date IS NOT NULL{clause}
            GROUP BY day
            ORDER BY day
            """,
            (str(chat_id), *args),
        ).fetchall()

    def get_import_history(self, chat_id: Optional[str] = None) -> List[Dict]:
        if chat_id is None:
            rows = self.conn.execute(
                "SELECT id, import_time, chat_id, json_file, total_messages, imported_count, "
                "skipped_count, status, duration_ms, error FROM import_log "
                "ORDER BY import_time DESC LIMIT 100"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, import_time, chat_id, json_file, total_messages, imported_count, "
                "skipped_count, status, duration_ms, error FROM import_log "
                "WHERE chat_id=? ORDER BY import_time DESC LIMIT 100",
                (str(chat_id),),
            ).fetchall()
        keys = [
            "id", "import_time", "chat_id", "json_file", "total_messages",
            "imported_count", "skipped_count", "status", "duration_ms", "error",
        ]
        return [dict(zip(keys, row)) for row in rows]

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def verify_integrity(self) -> Dict:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT message_key) FROM messages")
        total, distinct_keys = cursor.fetchone()

        duplicate_keys = cursor.execute(
            "SELECT message_key, COUNT(*) AS cnt FROM messages "
            "GROUP BY message_key HAVING cnt > 1 LIMIT 10"
        ).fetchall()

        orphan_entities = cursor.execute(
            "SELECT COUNT(*) FROM text_entities e "
            "WHERE NOT EXISTS (SELECT 1 FROM messages m WHERE m.message_key=e.message_key)"
        ).fetchone()[0]

        chats_without_rows = cursor.execute(
            "SELECT COUNT(*) FROM chats c WHERE NOT EXISTS "
            "(SELECT 1 FROM messages m WHERE m.chat_id=c.chat_id)"
        ).fetchone()[0]

        return {
            "schema_version": self.get_schema_version(),
            "total_messages": total,
            "distinct_message_keys": distinct_keys,
            "duplicate_keys": duplicate_keys,
            "orphan_entities": orphan_entities,
            "chats_without_rows": chats_without_rows,
            "ok": distinct_keys == total and not duplicate_keys and orphan_entities == 0,
        }
