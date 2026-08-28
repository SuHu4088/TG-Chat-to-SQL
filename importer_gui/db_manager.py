import sqlite3
import json
import os
from typing import Optional, List, Dict, Tuple


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_tables(self):
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_name TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                chat_id TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
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
                raw_json TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT,
                FOREIGN KEY (message_id) REFERENCES messages(id)
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

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_unixtime)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_message_id ON text_entities(message_id)')

        self.conn.commit()

    def get_existing_message_ids(self) -> set:
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM messages')
        return {row[0] for row in cursor.fetchall()}

    def get_max_message_id(self) -> Optional[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT MAX(id) FROM messages')
        result = cursor.fetchone()[0]
        return result

    def get_message_count(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM messages')
        return cursor.fetchone()[0]

    def get_chat_info(self) -> Optional[Tuple]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM chat_info LIMIT 1')
        return cursor.fetchone()

    def insert_chat_info(self, chat_name: str, chat_type: str, chat_id: str):
        cursor = self.conn.cursor()
        existing = self.get_chat_info()
        if existing is None:
            cursor.execute('''
                INSERT INTO chat_info (chat_name, chat_type, chat_id)
                VALUES (?, ?, ?)
            ''', (chat_name, chat_type, chat_id))
        else:
            cursor.execute('''
                UPDATE chat_info 
                SET chat_name = ?, chat_type = ?
                WHERE id = ?
            ''', (chat_name, chat_type, existing[0]))
        self.conn.commit()

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

    def insert_messages_batch(self, messages: List[Dict]) -> int:
        cursor = self.conn.cursor()
        count = 0

        for msg in messages:
            sender_name = msg.get('from') or msg.get('actor')
            sender_id = msg.get('from_id') or msg.get('actor_id', '')

            cursor.execute('''
                INSERT OR IGNORE INTO messages 
                (id, chat_id, message_type, date, date_unixtime, sender_name, sender_id,
                 text_content, reply_to_message_id, forwarded_from, media_type, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                msg['id'],
                str(sender_id),
                msg['type'],
                msg.get('date'),
                int(msg.get('date_unixtime', 0)),
                sender_name,
                sender_id,
                self._extract_text(msg),
                msg.get('reply_to_message_id'),
                msg.get('forwarded_from'),
                msg.get('media_type'),
                json.dumps(msg, ensure_ascii=False)
            ))

            entities = msg.get('text_entities', [])
            if entities:
                for entity in entities:
                    cursor.execute('''
                        INSERT INTO text_entities (message_id, entity_type, entity_text)
                        VALUES (?, ?, ?)
                    ''', (msg['id'], entity.get('type', ''), entity.get('text', '')))

            count += 1

        self.conn.commit()
        return count

    def log_import(self, json_file: str, total: int, imported: int, skipped: int, status: str = 'success'):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO import_log (import_time, json_file, total_messages, imported_count, skipped_count, status)
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
        ''', (json_file, total, imported, skipped, status))
        self.conn.commit()

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
