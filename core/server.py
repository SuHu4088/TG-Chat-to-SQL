"""本地 HTTP API + 静态页面服务。

桌面 App、浏览器调试、Playwright 自动化都走同一套接口，保证“测的就是跑的”。
"""

import json
import mimetypes
import os
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import __version__, paths
from .backup import BackupManager
from .db import DatabaseManager
from .importer import import_streaming
from .logging_setup import get_logger, setup_logging
from .security import DeletePermissionError, SecurityManager

log = get_logger("server")

WEB_ROOT = os.environ.get(
    "TGCHAT_WEB_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "web"),
)


class AppState:
    def __init__(self, db_path: Optional[str] = None):
        setup_logging()
        self.db_path = db_path or paths.default_db_path()
        self.db = DatabaseManager(self.db_path)
        self.db.connect()
        self.db.init_tables()
        self.security = SecurityManager(self.db)
        self.backups = BackupManager(self.db_path, paths.backup_dir())
        self.lock = threading.RLock()
        self.jobs: Dict[str, Dict] = {}
        self.backup_interval = int(os.environ.get("TGCHAT_BACKUP_INTERVAL_SECONDS", 6 * 3600))
        self._auto_backup_stop = threading.Event()

    # ------------------------------------------------------------------
    # 定期快照：按间隔自动创建，已有同间隔内快照则跳过
    # ------------------------------------------------------------------
    def start_auto_snapshot(self):
        def loop():
            while not self._auto_backup_stop.is_set():
                try:
                    if self._needs_snapshot():
                        with self.lock:
                            manifest = self.backups.create("auto")
                        log.info("自动快照完成：%s", manifest["name"])
                except Exception:
                    log.exception("自动快照失败")
                self._auto_backup_stop.wait(self.backup_interval)

        threading.Thread(target=loop, name="auto-snapshot", daemon=True).start()

    def stop_auto_snapshot(self):
        self._auto_backup_stop.set()

    def _needs_snapshot(self) -> bool:
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) < 8192:
            return False
        items = self.backups.list()
        if not items:
            return True
        newest = items[0].get("created_at") or ""
        try:
            newest_ts = datetime.strptime(newest, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            return True
        return (time.time() - newest_ts) >= self.backup_interval


    # ------------------------------------------------------------------
    def reopen(self):
        self.db.close()
        self.db = DatabaseManager(self.db_path)
        self.db.connect()
        self.db.init_tables()
        self.security = SecurityManager(self.db)

    def start_import(self, json_path: str, chat_id: Optional[str] = None) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "status": "running",
            "started_at": time.time(),
            "processed": 0,
            "message": "准备导入",
            "result": None,
            "error": None,
        }
        self.jobs[job_id] = job

        def worker():
            # 后台线程使用独立连接，避免与请求线程共享 sqlite3 连接
            worker_db = DatabaseManager(self.db_path)
            worker_db.connect()
            worker_db.init_tables()
            try:
                def progress(processed, _total, message):
                    job["processed"] = processed
                    job["message"] = message

                result = import_streaming(
                    worker_db, json_path, progress_callback=progress, chat_id_override=chat_id
                )
                job["result"] = result
                job["status"] = "done"
                job["message"] = (
                    f"完成：新增 {result['imported_count']:,} 条，"
                    f"跳过 {result['skipped_count']:,} 条"
                )
            except Exception as exc:  # 保留完整错误给前端
                job["status"] = "failed"
                job["error"] = str(exc)
                job["message"] = "导入失败"
                log.exception("导入任务失败")
            finally:
                worker_db.close()

        threading.Thread(target=worker, daemon=True).start()
        return job_id


def _json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler, message, status=400):
    _json_response(handler, {"error": message}, status=status)


def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TGChatStudio/" + __version__

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        # --------------------------------------------------------------
        def _body(self) -> Dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError:
                return {}

        def do_GET(self):
            parsed = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}

            try:
                if parsed.path.startswith("/api/"):
                    self._handle_api_get(parsed.path, query)
                else:
                    self._serve_static(parsed.path)
            except Exception as exc:
                log.exception("GET %s 失败", parsed.path)
                _error(self, str(exc), status=500)

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                self._handle_api_post(parsed.path, self._body())
            except DeletePermissionError as exc:
                log.warning("拒绝删除操作: %s", exc)
                _error(self, str(exc), status=403)
            except PermissionError as exc:
                log.warning("二次确认失败: %s", exc)
                _error(self, str(exc), status=400)
            except Exception as exc:
                log.exception("POST %s 失败", parsed.path)
                _error(self, str(exc), status=500)

        # --------------------------------------------------------------
        def _handle_api_get(self, path: str, query: Dict):
            with state.lock:
                if path == "/api/state":
                    return _json_response(self, {
                        "version": __version__,
                        "data_dir": paths.data_dir(),
                        "db_path": state.db_path,
                        "delete_enabled": state.security.is_delete_enabled(),
                        "web_root": WEB_ROOT,
                    })
                if path == "/api/chats":
                    return _json_response(self, {"chats": state.db.list_chats()})
                if path == "/api/messages":
                    chat_id = query.get("chat_id", "")
                    offset = int(query.get("offset", 0))
                    limit = min(int(query.get("limit", 500)), 2000)
                    return _json_response(self, state.db.get_messages_page(chat_id, offset, limit))
                if path == "/api/search":
                    return _json_response(
                        self,
                        state.db.search_messages(
                            query.get("chat_id", ""), query.get("q", ""),
                            min(int(query.get("limit", 200)), 500),
                        ),
                    )
                if path == "/api/imports":
                    return _json_response(
                        self, {"items": state.db.get_import_history(query.get("chat_id") or None)}
                    )
                if path == "/api/backups":
                    return _json_response(self, {"items": state.backups.list()})
                if path == "/api/security":
                    return _json_response(self, {"delete_enabled": state.security.is_delete_enabled()})
                if path == "/api/audit":
                    return _json_response(
                        self, {"items": state.security.get_audit_log(int(query.get("limit", 200)))}
                    )
                if path == "/api/verify":
                    result = state.db.verify_integrity()
                    return _json_response(self, result)

                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[0] == "api" and parts[1] == "chats":
                    chat_id = parts[2]
                    if parts[3] == "stats":
                        return _json_response(self, state.db.get_statistics(chat_id))
                    if parts[3] == "heatmap":
                        return _json_response(
                            self,
                            self._heatmap_payload(chat_id, query.get("start"), query.get("end")),
                        )
                if path.startswith("/api/jobs/"):
                    job_id = path.rsplit("/", 1)[-1]
                    job = state.jobs.get(job_id)
                    if not job:
                        return _error(self, "任务不存在", status=404)
                    return _json_response(self, job)
            _error(self, "接口不存在", status=404)

        def _heatmap_payload(self, chat_id: str, start: Optional[str] = None,
                             end: Optional[str] = None) -> Dict:
            activity = state.db.get_activity_heatmap(chat_id, start, end)
            daily = state.db.get_daily_summary(chat_id, start, end)
            top = state.db.get_top_senders(chat_id, 15, start, end)
            stats = state.db.get_statistics(chat_id)
            return {
                "chat_id": chat_id,
                "range": {"start": start or "", "end": end or ""},
                "activity": activity,
                "daily": [{"date": d, "count": c} for d, c in daily],
                "top_users": [{"name": n, "count": c} for n, c in top],
                "stats": stats,
            }

        # --------------------------------------------------------------
        def _handle_api_post(self, path: str, body: Dict):
            with state.lock:
                if path == "/api/chats/rename":
                    state.db.rename_chat(body.get("chat_id", ""), body.get("name", ""))
                    return _json_response(self, {"ok": True})

                if path == "/api/chats/delete":
                    chat_id = body.get("chat_id", "")
                    confirm = body.get("confirm", "")
                    if confirm != "DELETE":
                        return _error(self, "删除需要输入 DELETE 二次确认")
                    state.security.require_delete("chat.delete", chat_id)
                    result = state.db.delete_chat_data(chat_id)
                    return _json_response(self, {"ok": True, "result": result})

                if path == "/api/import":
                    json_path = body.get("path", "")
                    if not os.path.exists(json_path):
                        return _error(self, f"文件不存在：{json_path}")
                    job_id = state.start_import(json_path, body.get("chat_id") or None)
                    return _json_response(self, {"job_id": job_id})

                if path == "/api/backups":
                    manifest = state.backups.create(body.get("label", "manual"))
                    return _json_response(self, manifest)

                if path == "/api/backups/verify":
                    result = state.backups.verify(body.get("name", ""))
                    return _json_response(self, result)

                if path == "/api/backups/restore":
                    name = body.get("name", "")
                    confirm = body.get("confirm", "")
                    # 恢复前关闭连接，恢复后重开
                    state.db.close()
                    try:
                        result = state.backups.restore(name, confirm)
                    finally:
                        state.reopen()
                    return _json_response(self, {"ok": True, "result": result})

                if path == "/api/security/grant":
                    try:
                        state.security.grant_delete(body.get("phrase", ""))
                    except DeletePermissionError as exc:
                        return _error(self, str(exc), status=403)
                    return _json_response(self, {"delete_enabled": True})

                if path == "/api/security/revoke":
                    state.security.revoke_delete()
                    return _json_response(self, {"delete_enabled": False})

            _error(self, "接口不存在", status=404)

        # --------------------------------------------------------------
        def _serve_static(self, path: str):
            if path in ("/", ""):
                path = "/index.html"
            relative = path.lstrip("/")
            if ".." in relative:
                return _error(self, "非法路径", status=400)
            full = os.path.join(WEB_ROOT, relative)
            if not os.path.exists(full):
                full = os.path.join(WEB_ROOT, "index.html")
                if not os.path.exists(full):
                    return _error(self, "页面不存在", status=404)
            content_type, _ = mimetypes.guess_type(full)
            with open(full, "rb") as fp:
                body = fp.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(db_path: Optional[str] = None, host: str = "127.0.0.1",
                  port: int = 0) -> Tuple[ThreadingHTTPServer, AppState]:
    state = AppState(db_path)
    state.start_auto_snapshot()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.daemon_threads = True
    return server, state


def serve_forever(db_path: Optional[str] = None, port: int = 0, host: str = "127.0.0.1"):
    server, state = create_server(db_path, host, port)
    log.info("API 服务启动：http://%s:%d", host, server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        state.db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    serve_forever(args.db, args.port, args.host)
