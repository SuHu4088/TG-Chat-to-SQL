import csv
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'importer_gui'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'sql_converter'))

from db_manager import DatabaseManager  # noqa: E402
from importer import JSONImporter  # noqa: E402
import export_data  # noqa: E402


class ExportTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, 'test.db')
        data = {
            'name': '导出测试群',
            'type': 'private_group',
            'id': 3003,
            'messages': [
                {
                    'id': 1, 'type': 'message', 'date': '2026-02-01T09:00:00',
                    'date_unixtime': '1770000000', 'from': '甲', 'from_id': 'u1',
                    'text': 'hello SQLite',
                    'text_entities': [{'type': 'bold', 'text': 'SQLite'}],
                },
                {
                    'id': 2, 'type': 'message', 'date': '2026-02-02T10:00:00',
                    'date_unixtime': '1770086400', 'from': '乙', 'from_id': 'u2',
                    'text': 'second',
                },
            ],
        }
        json_path = os.path.join(self.tmp, 'chat.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        db = DatabaseManager(self.db_path)
        db.connect()
        db.init_tables()
        JSONImporter.import_to_database(db, json_path)
        db.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_csv_export(self):
        output = os.path.join(self.tmp, 'out.csv')
        conn = sqlite3.connect(self.db_path)
        count = export_data.export_csv(conn, output)
        conn.close()

        self.assertEqual(count, 2)
        with open(output, encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['message_key'], '3003:1')
        self.assertEqual(rows[0]['text_content'], 'hello SQLite')
        self.assertIn('"type": "bold"', rows[0]['text_entities'])

    def test_date_filter(self):
        output = os.path.join(self.tmp, 'filtered.csv')
        conn = sqlite3.connect(self.db_path)
        count = export_data.export_csv(conn, output, start='2026-02-02', end='2026-02-02')
        conn.close()
        self.assertEqual(count, 1)

    def test_parquet_export(self):
        try:
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest('pyarrow 未安装')

        output = os.path.join(self.tmp, 'out.parquet')
        conn = sqlite3.connect(self.db_path)
        count = export_data.export_parquet(conn, output)
        conn.close()

        self.assertEqual(count, 2)
        table = pq.read_table(output)
        self.assertEqual(table.num_rows, 2)
        self.assertIn('message_key', table.column_names)


if __name__ == '__main__':
    unittest.main()
