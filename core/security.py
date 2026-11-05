"""删除权限闸门与审计日志。

默认策略：程序启动时**没有删除能力**。用户必须在界面/CLI 中显式输入确认短语
`ENABLE DELETE` 才会打开开关；开关可随时撤销。每一次删除尝试（无论允许与否）
都会写入 audit_log 表与 logs/audit.jsonl。
"""

import json
import os
from datetime import datetime
from typing import Dict, List

from .db import DatabaseManager
from .logging_setup import get_logger
from . import paths

log = get_logger("security")

GRANT_PHRASE = "ENABLE DELETE"
DELETE_KEY = "delete_enabled"


class DeletePermissionError(PermissionError):
    pass


class SecurityManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.audit_file = os.path.join(paths.log_dir(), "audit.jsonl")

    # ------------------------------------------------------------------
    # 开关
    # ------------------------------------------------------------------
    def is_delete_enabled(self) -> bool:
        row = self.db.conn.execute(
            "SELECT value FROM app_settings WHERE key=?", (DELETE_KEY,)
        ).fetchone()
        return bool(row and row[0] == "1")

    def _set_enabled(self, enabled: bool):
        self.db.conn.execute(
            "INSERT INTO app_settings(key, value, updated_at) VALUES (?, ?, datetime('now','localtime')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (DELETE_KEY, "1" if enabled else "0"),
        )
        self.db.conn.commit()

    def grant_delete(self, phrase: str, actor: str = "local") -> Dict:
        if phrase != GRANT_PHRASE:
            self.audit("delete.grant", "settings", "确认短语不正确", allowed=False, actor=actor)
            raise DeletePermissionError(f"确认短语不正确，请输入 {GRANT_PHRASE}")
        self._set_enabled(True)
        self.audit("delete.grant", "settings", "删除权限已开启", allowed=True, actor=actor)
        log.warning("删除权限已开启 actor=%s", actor)
        return {"delete_enabled": True}

    def revoke_delete(self, actor: str = "local") -> Dict:
        self._set_enabled(False)
        self.audit("delete.revoke", "settings", "删除权限已撤销", allowed=True, actor=actor)
        log.warning("删除权限已撤销 actor=%s", actor)
        return {"delete_enabled": False}

    # ------------------------------------------------------------------
    # 闸门
    # ------------------------------------------------------------------
    def require_delete(self, action: str, target: str, actor: str = "local") -> None:
        allowed = self.is_delete_enabled()
        self.audit(action, target, "删除操作", allowed=allowed, actor=actor)
        if not allowed:
            log.error("拒绝删除操作 action=%s target=%s", action, target)
            raise DeletePermissionError(
                "删除权限未开启。请先在「权限与审计」中显式授权（ENABLE DELETE）。"
            )

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------
    def audit(self, action: str, target: str, detail: str, allowed: bool, actor: str = "local"):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.conn.execute(
            "INSERT INTO audit_log(created_at, action, target, detail, allowed, actor) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (created_at, action, target, detail, 1 if allowed else 0, actor),
        )
        self.db.conn.commit()
        record = {
            "created_at": created_at,
            "action": action,
            "target": target,
            "detail": detail,
            "allowed": allowed,
            "actor": actor,
        }
        try:
            with open(self.audit_file, "a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:  # 审计文件不可写时仍保留数据库记录
            log.error("写入审计文件失败: %s", exc)

    def get_audit_log(self, limit: int = 200) -> List[Dict]:
        rows = self.db.conn.execute(
            "SELECT id, created_at, action, target, detail, allowed, actor "
            "FROM audit_log ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        keys = ["id", "created_at", "action", "target", "detail", "allowed", "actor"]
        return [dict(zip(keys, row)) for row in rows]
