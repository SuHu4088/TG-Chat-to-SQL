"""
SQLite 数据库管理（Schema v2）

去重键：message_key = "{chat_id}:{message_id}"
- Telegram 的消息 ID 只是“群内序号”，不同群会出现相同 ID；
- 因此不能把 messages.id 当作全局主键，必须使用复合键；
- message_key 上建立 UNIQUE 索引，重复导入由 SQLite 直接拒绝。
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple


SCHEMA_VERSION = 2


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # 连接与建表
    # ------------------------------------------------------------------
    def connect(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        if self._table_exists('messages'):
            columns = self._column_names('messages')
            if 'message_key' not in columns:
                self._migrate_v1_to_v2()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_name TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                chat_id TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_info_chat_id
            ON chat_info(chat_id)
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
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
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT,
                FOREIGN KEY (message_key) REFERENCES messages(message_key) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_time TEXT,
                json_file TEXT,
                total_messages INTEGER,
                imported_count INTEGER,
                skipped_count INTEGER,
                status TEXT
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_unixtime)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_message_key ON messages(message_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_message_key ON text_entities(message_key)')

        self._set_meta('schema_version', str(SCHEMA_VERSION))
        self.conn.commit()

    def _migrate_v1_to_v2(self):
        """把 v1（messages.id 主键、text_entities.message_id）迁移到 v2。"""
        cursor = self.conn.cursor()
        self.conn.execute("PRAGMA foreign_keys=OFF")

        has_entities = self._table_exists('text_entities')
        if has_entities:
            cursor.execute('ALTER TABLE text_entities RENAME TO text_entities_v1')
        cursor.execute('ALTER TABLE messages RENAME TO messages_v1')

        cursor.execute('''
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
        ''')
        cursor.execute('''
            CREATE TABLE text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT,
                FOREIGN KEY (message_key) REFERENCES messages(message_key) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            INSERT OR IGNORE INTO messages
            (message_key, id, chat_id, message_type, date, date_unixtime, sender_name,
             sender_id, text_content, reply_to_message_id, forwarded_from, media_type, raw_json)
            SELECT
                COALESCE(chat_id, '') || ':' || id,
                id, COALESCE(chat_id, ''), message_type, date, date_unixtime, sender_name,
                sender_id, text_content, reply_to_message_id, forwarded_from, media_type, raw_json
            FROM messages_v1
        ''')

        if has_entities:
            cursor.execute('''
                INSERT INTO text_entities (message_key, entity_type, entity_text)
                SELECT
                    COALESCE(m.chat_id, '') || ':' || e.message_id,
                    e.entity_type,
                    e.entity_text
                FROM text_entities_v1 e
                JOIN messages_v1 m ON m.id = e.message_id
            ''')
            cursor.execute('DROP TABLE text_entities_v1')

        cursor.execute('DROP TABLE messages_v1')
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
    # 群组信息
    # ------------------------------------------------------------------
    def get_chat_info(self, chat_id: Optional[str] = None) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        if chat_id is None:
            cursor.execute('SELECT id, chat_name, chat_type, chat_id FROM chat_info ORDER BY id LIMIT 1')
        else:
            cursor.execute(
                'SELECT id, chat_name, chat_type, chat_id FROM chat_info WHERE chat_id = ?',
                (str(chat_id),),
            )
        return cursor.fetchone()

    def insert_chat_info(self, chat_name: str, chat_type: str, chat_id: str):
        cursor = self.conn.cursor()
        cursor.execute(
            '''
            INSERT INTO chat_info (chat_name, chat_type, chat_id)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_name = excluded.chat_name,
                chat_type = excluded.chat_type
            ''',
            (chat_name or 'Unknown', chat_type or 'unknown', str(chat_id)),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # 去重与查询
    # ------------------------------------------------------------------
    def get_existing_message_keys(self, chat_id: Optional[str] = None) -> set:
        cursor = self.conn.cursor()
        if chat_id is None:
            cursor.execute('SELECT message_key FROM messages')
        else:
            cursor.execute('SELECT message_key FROM messages WHERE chat_id = ?', (str(chat_id),))
        return {row[0] for row in cursor.fetchall()}

    def get_existing_message_ids(self) -> set:
        """兼容旧调用；新代码请使用 get_existing_message_keys。"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM messages')
        return {row[0] for row in cursor.fetchall()}

    def get_message_by_key(self, message_key: str) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT id, chat_id, date, sender_name, text_content FROM messages WHERE message_key = ?',
            (message_key,),
        )
        return cursor.fetchone()

    def get_max_message_id(self, chat_id: Optional[str] = None) -> Optional[int]:
        cursor = self.conn.cursor()
        if chat_id is None:
            cursor.execute('SELECT MAX(id) FROM messages')
        else:
            cursor.execute('SELECT MAX(id) FROM messages WHERE chat_id = ?', (str(chat_id),))
        result = cursor.fetchone()[0]
        return result

    def get_message_count(self, chat_id: Optional[str] = None) -> int:
        cursor = self.conn.cursor()
        if chat_id is None:
            cursor.execute('SELECT COUNT(*) FROM messages')
        else:
            cursor.execute('SELECT COUNT(*) FROM messages WHERE chat_id = ?', (str(chat_id),))
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(msg: Dict) -> str:
        text = msg.get('text', '')
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            parts = []
            for item in text:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and 'text' in item:
                    parts.append(item['text'])
            return ''.join(parts)
        return ''

    @staticmethod
    def _to_unixtime(msg: Dict) -> int:
        raw = msg.get('date_unixtime')
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
        date_str = msg.get('date')
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
                'id': msg.get('id'),
                'date': msg.get('date'),
                'text': msg.get('text'),
                'sender': msg.get('from') or msg.get('actor'),
                'forwarded_from': msg.get('forwarded_from'),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode('utf-8')).hexdigest()

    def insert_messages_batch(self, messages: List[Dict], chat_id: Optional[str] = None) -> int:
        """批量插入；返回真实新增条数（已存在的消息不会重复写实体）。"""
        cursor = self.conn.cursor()
        inserted = 0

        for msg in messages:
            chat_id_value = str(chat_id if chat_id is not None else msg.get('chat_id') or '')
            message_id = msg.get('id')
            message_key = self.make_message_key(chat_id_value, message_id)

            sender_name = msg.get('from') or msg.get('actor')
            sender_id = msg.get('from_id') or msg.get('actor_id', '')

            cursor.execute('''
                INSERT OR IGNORE INTO messages
                (message_key, id, chat_id, message_type, date, date_unixtime, sender_name,
                 sender_id, text_content, reply_to_message_id, forwarded_from, media_type,
                 raw_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_key,
                message_id,
                chat_id_value,
                msg.get('type', 'message'),
                msg.get('date'),
                self._to_unixtime(msg),
                sender_name,
                sender_id,
                self._extract_text(msg),
                msg.get('reply_to_message_id'),
                msg.get('forwarded_from'),
                msg.get('media_type'),
                json.dumps(msg, ensure_ascii=False),
                self._content_hash(msg),
            ))

            if cursor.rowcount == 0:
                continue

            inserted += 1
            for entity in msg.get('text_entities', []) or []:
                cursor.execute('''
                    INSERT INTO text_entities (message_key, entity_type, entity_text)
                    VALUES (?, ?, ?)
                ''', (message_key, entity.get('type', ''), entity.get('text', '')))

        self.conn.commit()
        return inserted

    def log_import(self, json_file: str, total: int, imported: int, skipped: int, status: str = 'success'):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO import_log (import_time, json_file, total_messages, imported_count, skipped_count, status)
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
        ''', (json_file, total, imported, skipped, status))
        self.conn.commit()

    # ------------------------------------------------------------------
    # 统计与校验
    # ------------------------------------------------------------------
    def get_import_history(self) -> List[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM import_log ORDER BY import_time DESC LIMIT 50')
        return cursor.fetchall()

    def get_statistics(self) -> Dict:
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM messages')
        total_messages = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM messages WHERE message_type = ?', ('message',))
        regular_messages = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM messages WHERE message_type = ?', ('service',))
        service_messages = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(DISTINCT sender_id) FROM messages WHERE sender_id IS NOT NULL')
        unique_senders = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM messages WHERE reply_to_message_id IS NOT NULL')
        reply_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM messages WHERE forwarded_from IS NOT NULL')
        forward_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM text_entities')
        entity_count = cursor.fetchone()[0]

        return {
            'total_messages': total_messages,
            'regular_messages': regular_messages,
            'service_messages': service_messages,
            'unique_senders': unique_senders,
            'reply_count': reply_count,
            'forward_count': forward_count,
            'entity_count': entity_count
        }

    def verify_integrity(self) -> Dict:
        """可用于 CI / 手工验证的去重校验。"""
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*), COUNT(DISTINCT message_key) FROM messages')
        total, distinct_keys = cursor.fetchone()

        cursor.execute('''
            SELECT message_key, COUNT(*) AS cnt
            FROM messages
            GROUP BY message_key
            HAVING cnt > 1
            LIMIT 10
        ''')
        duplicate_keys = cursor.fetchall()

        cursor.execute('''
            SELECT COUNT(*) FROM text_entities e
            WHERE NOT EXISTS (
                SELECT 1 FROM messages m WHERE m.message_key = e.message_key
            )
        ''')
        orphan_entities = cursor.fetchone()[0]

        return {
            'schema_version': self.get_schema_version(),
            'total_messages': total,
            'distinct_message_keys': distinct_keys,
            'duplicate_keys': duplicate_keys,
            'orphan_entities': orphan_entities,
            'ok': distinct_keys == total and not duplicate_keys and orphan_entities == 0,
        }
