import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'importer_gui'))

from db_manager import DatabaseManager  # noqa: E402
from importer import JSONImporter  # noqa: E402


def write_chat(path, chat_id, messages):
    data = {
        'name': f'测试群 {chat_id}',
        'type': 'private_group',
        'id': chat_id,
        'messages': messages,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def sample_messages():
    return [
        {
            'id': 1,
            'type': 'message',
            'date': '2026-01-01T10:00:00',
            'date_unixtime': '1767252000',
            'from': '甲',
            'from_id': 'user_a',
            'text': '第一条 SQLite 消息',
            'text_entities': [{'type': 'plain', 'text': '第一条 SQLite 消息'}],
        },
        {
            'id': 2,
            'type': 'message',
            'date': '2026-01-01T10:01:00',
            'date_unixtime': '1767252060',
            'from': '乙',
            'from_id': 'user_b',
            'text': '回复',
            'reply_to_message_id': 1,
            'text_entities': [{'type': 'plain', 'text': '回复'}],
        },
        {
            'id': 3,
            'type': 'service',
            'date': '2026-01-01T10:02:00',
            'date_unixtime': '1767252120',
            'actor': '甲',
            'actor_id': 'user_a',
            'action': 'join_by_link',
        },
    ]


class ImporterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, 'test.db')
        self.db = DatabaseManager(self.db_path)
        self.db.connect()
        self.db.init_tables()

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_incremental_import_is_idempotent(self):
        json_path = write_chat(os.path.join(self.tmp, 'chat.json'), 1001, sample_messages())

        first = JSONImporter.import_to_database(self.db, json_path)
        self.assertEqual(first['imported_count'], 3)
        self.assertEqual(first['skipped_count'], 0)

        stats_after_first = self.db.get_statistics()

        second = JSONImporter.import_to_database(self.db, json_path)
        self.assertEqual(second['imported_count'], 0)
        self.assertEqual(second['skipped_count'], 3)

        stats_after_second = self.db.get_statistics()
        self.assertEqual(stats_after_first, stats_after_second)
        self.assertEqual(self.db.verify_integrity()['ok'], True)

    def test_same_message_id_in_two_chats(self):
        path_a = write_chat(os.path.join(self.tmp, 'a.json'), 1001, sample_messages())
        path_b = write_chat(os.path.join(self.tmp, 'b.json'), 2002, sample_messages())

        JSONImporter.import_to_database(self.db, path_a)
        JSONImporter.import_to_database(self.db, path_b)

        self.assertEqual(self.db.get_message_count(), 6)
        integrity = self.db.verify_integrity()
        self.assertTrue(integrity['ok'])
        self.assertEqual(integrity['distinct_message_keys'], 6)

    def test_v1_database_migrates_to_v2(self):
        self.db.close()
        old_path = os.path.join(self.tmp, 'old.db')
        conn = sqlite3.connect(old_path)
        conn.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL, message_type TEXT NOT NULL,
                date TEXT, date_unixtime INTEGER, sender_name TEXT, sender_id TEXT,
                text_content TEXT, reply_to_message_id INTEGER, forwarded_from TEXT,
                media_type TEXT, raw_json TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE text_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL, entity_text TEXT
            )
        ''')
        conn.execute("INSERT INTO messages VALUES (1, '42', 'message', '2026-01-01T00:00:00', 1, '甲', 'u1', 'hi', NULL, NULL, NULL, '{}')")
        conn.execute("INSERT INTO text_entities (message_id, entity_type, entity_text) VALUES (1, 'plain', 'hi')")
        conn.commit()
        conn.close()

        migrated = DatabaseManager(old_path)
        migrated.connect()
        migrated.init_tables()
        self.assertEqual(migrated.get_schema_version(), 2)
        row = migrated.conn.execute('SELECT message_key, id, chat_id, text_content FROM messages').fetchone()
        self.assertEqual(row, ('42:1', 1, '42', 'hi'))
        entity = migrated.conn.execute('SELECT message_key, entity_text FROM text_entities').fetchone()
        self.assertEqual(entity, ('42:1', 'hi'))
        migrated.close()


if __name__ == '__main__':
    unittest.main()
