"""数据库快照、完整性校验、恢复与保留策略。

- 快照使用 SQLite 官方 backup API（不会拷贝到一半的 WAL 状态）；
- 每个快照附带 `.manifest.json`（sha256、消息数、群数、schema 版本）；
- 恢复前必须通过 `PRAGMA integrity_check` + 去重键校验；
- 恢复需要两次确认（确认短语中必须包含快照文件名）；
- 恢复前自动为当前库再做一次 `pre-restore` 快照，可回退；
- 保留策略：默认保留最近 10 个，且总大小不超过 2 GB，超限从最旧开始清理。
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from .db import DatabaseManager
from .logging_setup import get_logger

log = get_logger("backup")

DEFAULT_KEEP = 10
DEFAULT_MAX_TOTAL_MB = 2048


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupManager:
    def __init__(self, db_path: str, backup_dir: str,
                 keep: int = DEFAULT_KEEP, max_total_mb: int = DEFAULT_MAX_TOTAL_MB):
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.keep = keep
        self.max_total_bytes = max_total_mb * 1024 * 1024
        os.makedirs(backup_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    def create(self, label: str = "manual") -> Dict:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_") or "manual"
        name = f"{timestamp}-{safe_label}.db"
        target = os.path.join(self.backup_dir, name)

        source = sqlite3.connect(self.db_path, timeout=30)
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
            # backup API 会继承源库的 WAL 模式；快照必须是单文件，
            # 否则只读打开时无法创建 -shm，校验会失败。
            dest.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            dest.execute("PRAGMA journal_mode=DELETE")
            dest.commit()
        finally:
            dest.close()
            source.close()

        try:
            manifest = self._build_manifest(target, name, label)
        except Exception:
            # 生成清单失败时不要留下半成品快照
            if os.path.exists(target):
                os.remove(target)
            raise

        # 清单已生成，快照不再需要 WAL 边车文件
        for suffix in ("-wal", "-shm"):
            sidecar = target + suffix
            if os.path.exists(sidecar):
                os.remove(sidecar)

        manifest_path = target + ".manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)

        self.prune()
        log.info("创建快照 %s（%d 字节）", name, manifest["size_bytes"])
        return manifest

    def _build_manifest(self, path: str, name: str, label: str) -> Dict:
        # 用读写模式打开：只读模式在 WAL 库上无法创建 -shm，会直接报错
        conn = sqlite3.connect(path)
        try:
            schema_version = 0
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                schema_version = int(row[0]) if row else 0
            except sqlite3.DatabaseError:
                schema_version = 0
            chats = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
            messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        finally:
            conn.close()

        return {
            "name": name,
            "label": label,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": os.path.getsize(path),
            "sha256": sha256_file(path),
            "schema_version": schema_version,
            "chats": chats,
            "messages": messages,
        }

    # ------------------------------------------------------------------
    # 列表 / 清理
    # ------------------------------------------------------------------
    def list(self) -> List[Dict]:
        items = []
        for name in sorted(os.listdir(self.backup_dir)):
            if not name.endswith(".db"):
                continue
            path = os.path.join(self.backup_dir, name)
            manifest_path = path + ".manifest.json"
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as fp:
                        items.append(json.load(fp))
                    continue
                except (OSError, ValueError):
                    pass
            items.append(
                {
                    "name": name,
                    "label": "unknown",
                    "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "size_bytes": os.path.getsize(path),
                }
            )
        items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return items

    def prune(self):
        items = self.list()
        total = sum(item.get("size_bytes", 0) for item in items)
        removed = []
        while len(items) > self.keep or (total > self.max_total_bytes and len(items) > 1):
            oldest = items.pop()
            path = os.path.join(self.backup_dir, oldest["name"])
            manifest_path = path + ".manifest.json"
            for candidate in (manifest_path, path):
                if os.path.exists(candidate):
                    os.remove(candidate)
            total -= oldest.get("size_bytes", 0)
            removed.append(oldest["name"])
        if removed:
            log.info("快照清理：%s", ", ".join(removed))
        return removed

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def verify(self, name: str) -> Dict:
        path = os.path.join(self.backup_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"快照不存在: {name}")

        result = {"name": name, "ok": False, "errors": []}
        manifest_path = path + ".manifest.json"
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as fp:
                manifest = json.load(fp)
            actual = sha256_file(path)
            result["expected_sha256"] = manifest.get("sha256")
            result["actual_sha256"] = actual
            if actual != manifest.get("sha256"):
                result["errors"].append("sha256 与清单不一致，快照可能被修改或损坏")

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            result["integrity_check"] = integrity
            if integrity != "ok":
                result["errors"].append(f"integrity_check: {integrity}")

            db = DatabaseManager(path)
            db.conn = conn
            check = db.verify_integrity()
            result["schema_version"] = check["schema_version"]
            result["messages"] = check["total_messages"]
            result["chats"] = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
            if not check["ok"]:
                result["errors"].append("去重键/实体完整性校验失败")
        except sqlite3.DatabaseError as exc:
            result["errors"].append(str(exc))
        finally:
            conn.close()

        result["ok"] = not result["errors"]
        return result

    # ------------------------------------------------------------------
    # 恢复
    # ------------------------------------------------------------------
    def restore(self, name: str, confirm: str) -> Dict:
        """恢复快照。调用本方法前必须先关闭当前数据库连接。

        confirm 必须等于 `RESTORE <name>`，作为二次确认。
        """
        path = os.path.join(self.backup_dir, name)
        if confirm != f"RESTORE {name}":
            raise PermissionError(f"二次确认失败，请输入：RESTORE {name}")

        verification = self.verify(name)
        if not verification["ok"]:
            raise ValueError("恢复前校验未通过：" + "; ".join(verification["errors"]))

        # 恢复前为当前库留一份可回退快照
        pre_restore = None
        if os.path.exists(self.db_path):
            pre_restore = self.create("pre-restore")

        # 先复制到临时文件，校验通过后原子替换
        fd, temp_path = tempfile.mkstemp(suffix=".db", dir=self.backup_dir)
        os.close(fd)
        shutil.copy2(path, temp_path)
        temp_verification = BackupManager(temp_path, self.backup_dir).verify(
            os.path.basename(temp_path)
        )
        if not temp_verification["ok"]:
            os.remove(temp_path)
            raise ValueError("临时副本校验未通过，已中止恢复")

        # 清掉当前库的 WAL/SHM，避免旧数据混入
        for suffix in ("-wal", "-shm"):
            sidecar = self.db_path + suffix
            if os.path.exists(sidecar):
                os.remove(sidecar)
        os.replace(temp_path, self.db_path)

        log.warning("已从快照恢复数据库: %s", name)
        return {
            "restored": name,
            "pre_restore_snapshot": pre_restore["name"] if pre_restore else None,
            "messages": temp_verification.get("messages"),
            "chats": temp_verification.get("chats"),
        }
