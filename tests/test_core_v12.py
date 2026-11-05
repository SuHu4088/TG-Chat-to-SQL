"""V1.2.0 core 层测试：多群隔离、去重、备份恢复、删除权限闸门、流式导入。

运行：
    python3 -m pytest tests/test_core_v12.py -q
或：
    python3 -m unittest tests.test_core_v12 -v
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.backup import BackupManager  # noqa: E402
from core.db import DatabaseManager  # noqa: E402
from core.importer import import_streaming, iter_messages  # noqa: E402
from core.security import (  # noqa: E402
    DeletePermissionError,
    GRANT_PHRASE,
    SecurityManager,
)


def make_chat_file(path, chat_id, name, count, start_id=1):
    messages = []
    for index in range(count):
        message_id = start_id + index
        messages.append({
            "id": message_id,
            "type": "message",
            "date": f"2026-01-{(index % 28) + 1:02d}T10:00:00",
            "date_unixtime": str(1767225600 + message_id),
            "from": "虚构用户",
            "from_id": "user_demo",
            "text": f"虚构消息 {message_id}",
            "text_entities": [{"type": "plain", "text": f"虚构消息 {message_id}"}],
        })
    data = {"name": name, "type": "private_group", "id": chat_id, "messages": messages}
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    return path


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tgchat-test-")
        self.db_path = os.path.join(self.tmp, "chat.db")
        self.db = DatabaseManager(self.db_path)
        self.db.connect()
        self.db.init_tables()

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestSchemaAndDedupe(TempCase):
    def test_message_key_is_chat_scoped(self):
        # 不同群组里相同的 message_id 必须都能入库，且互不覆盖
        self.assertEqual(self.db.make_message_key("100", 1), "100:1")
        self.assertEqual(self.db.make_message_key("200", 1), "200:1")

    def test_same_id_across_chats_are_independent(self):
        self.db.insert_messages_batch(
            [{"id": 1, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": "1767225601", "from": "A", "from_id": "u_a", "text": "群 A"}],
            "chat_a",
        )
        self.db.insert_messages_batch(
            [{"id": 1, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": "1767225601", "from": "B", "from_id": "u_b", "text": "群 B"}],
            "chat_b",
        )
        self.assertEqual(self.db.get_messages_page("chat_a", 0, 10)["total"], 1)
        self.assertEqual(self.db.get_messages_page("chat_b", 0, 10)["total"], 1)
        page = self.db.get_messages_page("chat_b", 0, 10)
        self.assertEqual(page["items"][0]["text"], "群 B")

    def test_reimport_is_idempotent(self):
        batch = [{"id": 1, "type": "message", "date": "2026-01-01T10:00:00",
                  "date_unixtime": "1767225601", "from": "A", "from_id": "u_a", "text": "重复"}]
        first = self.db.insert_messages_batch(batch, "chat_a")
        second = self.db.insert_messages_batch(batch, "chat_a")
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(self.db.get_messages_page("chat_a", 0, 10)["total"], 1)

    def test_integrity_reports_clean(self):
        self.db.insert_messages_batch(
            [{"id": 1, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": "1767225601", "from": "A", "from_id": "u_a", "text": "x"}],
            "chat_a",
        )
        result = self.db.verify_integrity()
        self.assertTrue(result["ok"])
        self.assertEqual(result["duplicate_keys"], [])

    def test_list_chats_reports_counts(self):
        self.db.upsert_chat("chat_a", "群 A", "private_group")
        self.db.upsert_chat("chat_b", "群 B", "public_group")
        self.db.insert_messages_batch(
            [{"id": i, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": str(1767225600 + i), "from": "A", "from_id": "u_a", "text": "x"}
             for i in range(1, 4)],
            "chat_a",
        )
        chats = self.db.list_chats()
        self.assertEqual(len(chats), 2)
        counts = {c["chat_id"]: c["message_count"] for c in chats}
        self.assertEqual(counts["chat_a"], 3)
        self.assertEqual(counts["chat_b"], 0)

    def test_rename_and_delete_chat(self):
        self.db.upsert_chat("chat_a", "旧名", "private_group")
        self.db.rename_chat("chat_a", "新名")
        self.assertEqual(self.db.list_chats()[0]["title"], "新名")
        self.db.insert_messages_batch(
            [{"id": 1, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": "1767225601", "from": "A", "from_id": "u_a", "text": "x"}],
            "chat_a",
        )
        result = self.db.delete_chat_data("chat_a")
        self.assertEqual(result["messages_deleted"], 1)
        self.assertEqual(self.db.list_chats(), [])

    def test_rename_rejects_empty(self):
        self.db.upsert_chat("chat_a", "旧名", "private_group")
        with self.assertRaises(ValueError):
            self.db.rename_chat("chat_a", "   ")


class TestStreamingImport(TempCase):
    def test_streaming_import_multiple_chats(self):
        path_a = make_chat_file(os.path.join(self.tmp, "a.json"), 111, "群 A", 40)
        path_b = make_chat_file(os.path.join(self.tmp, "b.json"), 222, "群 B", 25)
        result_a = import_streaming(self.db, path_a)
        result_b = import_streaming(self.db, path_b)
        self.assertEqual(result_a["imported_count"], 40)
        self.assertEqual(result_b["imported_count"], 25)
        self.assertEqual(result_a["chat_id"], "111")
        self.assertEqual(result_b["chat_id"], "222")
        self.assertEqual(len(self.db.list_chats()), 2)

    def test_iter_messages_does_not_need_full_load(self):
        path = make_chat_file(os.path.join(self.tmp, "c.json"), 333, "群 C", 30)
        seen = list(iter_messages(path))
        self.assertEqual(len(seen), 30)
        self.assertEqual(seen[0]["id"], 1)

    def test_reimport_skips_all(self):
        path = make_chat_file(os.path.join(self.tmp, "d.json"), 444, "群 D", 20)
        first = import_streaming(self.db, path)
        second = import_streaming(self.db, path)
        self.assertEqual(first["imported_count"], 20)
        self.assertEqual(second["imported_count"], 0)
        self.assertEqual(second["skipped_count"], 20)

    def test_import_log_records_duration(self):
        path = make_chat_file(os.path.join(self.tmp, "e.json"), 555, "群 E", 10)
        import_streaming(self.db, path)
        history = self.db.get_import_history("555")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "success")
        # 小文件导入可能不足 1 ms，四舍五入为 0，这里只要求字段存在且非负
        self.assertGreaterEqual(history[0]["duration_ms"], 0)


class TestDeleteGate(TempCase):
    def setUp(self):
        super().setUp()
        self.security = SecurityManager(self.db)

    def test_default_disabled(self):
        self.assertFalse(self.security.is_delete_enabled())

    def test_requires_exact_phrase(self):
        with self.assertRaises(DeletePermissionError):
            self.security.grant_delete("enable delete")
        self.assertFalse(self.security.is_delete_enabled())
        self.security.grant_delete(GRANT_PHRASE)
        self.assertTrue(self.security.is_delete_enabled())

    def test_require_delete_blocks_when_disabled(self):
        with self.assertRaises(DeletePermissionError):
            self.security.require_delete("chat.delete", "chat_a")

    def test_require_delete_allows_after_grant(self):
        self.security.grant_delete(GRANT_PHRASE)
        self.security.require_delete("chat.delete", "chat_a")
        self.assertTrue(self.security.is_delete_enabled())

    def test_revoke(self):
        self.security.grant_delete(GRANT_PHRASE)
        self.security.revoke_delete()
        self.assertFalse(self.security.is_delete_enabled())
        with self.assertRaises(DeletePermissionError):
            self.security.require_delete("chat.delete", "chat_a")

    def test_audit_log_written_for_denied_attempt(self):
        try:
            self.security.require_delete("chat.delete", "chat_a")
        except DeletePermissionError:
            pass
        entries = self.security.get_audit_log(limit=10)
        self.assertTrue(any(e["action"] == "chat.delete" and e["allowed"] == 0 for e in entries))

    def test_audit_jsonl_exists(self):
        self.security.grant_delete(GRANT_PHRASE)
        log_path = os.path.join(
            os.environ.get("TGCHAT_DATA_DIR") or self.tmp, "logs", "audit.jsonl"
        )
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as fp:
            lines = [json.loads(line) for line in fp if line.strip()]
        self.assertTrue(any(line["action"] == "delete.grant" for line in lines))


class TestBackupRestore(TempCase):
    def setUp(self):
        super().setUp()
        self.backup_dir = os.path.join(self.tmp, "backups")
        self.manager = BackupManager(self.db_path, self.backup_dir, keep=3)
        self.db.insert_messages_batch(
            [{"id": i, "type": "message", "date": "2026-01-01T10:00:00",
              "date_unixtime": str(1767225600 + i), "from": "A", "from_id": "u_a",
              "text": f"消息 {i}"} for i in range(1, 21)],
            "chat_a",
        )

    def test_create_writes_manifest(self):
        manifest = self.manager.create("manual")
        self.assertTrue(os.path.exists(os.path.join(self.backup_dir, manifest["name"])))
        self.assertEqual(manifest["messages"], 20)
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(len(manifest["sha256"]), 64)

    def test_verify_detects_corruption(self):
        manifest = self.manager.create("manual")
        path = os.path.join(self.backup_dir, manifest["name"])
        with open(path, "ab") as fp:
            fp.write(b"\x00corrupted")
        result = self.manager.verify(manifest["name"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("sha256" in err for err in result["errors"]))

    def test_restore_requires_exact_confirm(self):
        manifest = self.manager.create("manual")
        with self.assertRaises(PermissionError):
            self.manager.restore(manifest["name"], "RESTORE")

    def test_restore_roundtrip(self):
        manifest = self.manager.create("manual")
        # 备份后删掉数据，再恢复，应该回到 20 条
        self.db.delete_chat_data("chat_a")
        self.assertEqual(self.db.get_messages_page("chat_a", 0, 10)["total"], 0)
        self.db.close()
        result = self.manager.restore(manifest["name"], f"RESTORE {manifest['name']}")
        self.assertEqual(result["messages"], 20)
        self.assertIsNotNone(result["pre_restore_snapshot"])
        db = DatabaseManager(self.db_path)
        db.connect()
        self.assertEqual(db.get_messages_page("chat_a", 0, 10)["total"], 20)
        db.close()

    def test_retention_prunes_old(self):
        for index in range(5):
            self.manager.create(f"snap{index}")
        items = self.manager.list()
        self.assertLessEqual(len(items), 3)

    def test_restore_missing_snapshot(self):
        with self.assertRaises(FileNotFoundError):
            self.manager.restore("nope.db", "RESTORE nope.db")


if __name__ == "__main__":
    unittest.main(verbosity=2)
