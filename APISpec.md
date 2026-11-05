# API 规格说明书（APISpec）

- 项目：TG-Chat-to-SQL / TG Chat Studio
- 版本：v1.2.0
- 更新日期：2026-11-05

本项目的接口分四层：本地 HTTP API（桌面 App 与浏览器共用）、Python core 模块、命令行工具、前端调试接口。所有接口只在本地运行，HTTP 仅监听 `127.0.0.1`。

## 1. 本地 HTTP API

- 基地址：`http://127.0.0.1:<随机端口>`（桌面 App）或 `--port` 指定（调试）；
- 编码：请求与响应均为 UTF-8 JSON；
- 错误格式：`{"error": "说明"}`，HTTP 状态码 `400 / 403 / 404 / 500`。

启动：

```bash
python3 -m core.server --port 8765 --db ~/Library/Application\ Support/TGChatToSQL/telegram_chat.db
```

### 1.1 只读接口

| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/api/state` | — | `version / data_dir / db_path / delete_enabled / web_root` |
| GET | `/api/chats` | — | `{"chats":[{chat_id,title,original_name,chat_type,message_count,first_ts,last_ts,import_count,last_import}]}` |
| GET | `/api/messages` | `chat_id`, `offset`, `limit≤2000` | `{chat_id,offset,limit,total,items[]}` |
| GET | `/api/search` | `chat_id`, `q`, `limit≤500` | `{items[],total}` |
| GET | `/api/imports` | `chat_id?` | `{"items":[{chat_id,import_time,total_messages,imported_count,skipped_count,duration_ms,status,error}]}` |
| GET | `/api/backups` | — | `{"items":[manifest]}` |
| GET | `/api/security` | — | `{"delete_enabled":bool}` |
| GET | `/api/audit` | `limit` | `{"items":[{created_at,action,target,allowed,actor}]}` |
| GET | `/api/verify` | — | `{schema_version,total_messages,distinct_message_keys,duplicate_keys,orphan_entities,chats_without_rows,ok}` |
| GET | `/api/chats/<chat_id>/stats` | — | 统计对象（消息数、用户数、时间范围等） |
| GET | `/api/chats/<chat_id>/heatmap` | `start?`, `end?` | `{activity, daily[], top_users[], stats, range}` |
| GET | `/api/jobs/<job_id>` | — | `{id,status,progress,result,error}` |

`items[]` 消息字段：`message_key / chat_id / id / type / date / date_unixtime / sender_name / sender_id / text / reply_to_message_id / reply_sender / reply_text / forwarded_from / media_type / raw`。

### 1.2 写入接口

| 方法 | 路径 | 请求体 | 返回 |
|------|------|--------|------|
| POST | `/api/chats/rename` | `{"chat_id":"...","name":"新名称"}` | `{"ok":true}` |
| POST | `/api/chats/delete` | `{"chat_id":"...","confirm":"DELETE"}` | `{"ok":true,"result":{messages_deleted,entities_deleted}}` |
| POST | `/api/import` | `{"path":"/abs/result.json","chat_id?":"..."}` | `{"job_id":"..."}`（后台任务） |
| POST | `/api/backups` | `{"label":"manual"}` | `manifest` |
| POST | `/api/backups/verify` | `{"name":"...db"}` | `{ok,errors[],expected_sha256,actual_sha256,integrity_check,schema_version,messages,chats}` |
| POST | `/api/backups/restore` | `{"name":"...db","confirm":"RESTORE ...db"}` | `{"ok":true,"result":{restored,pre_restore_snapshot,messages,chats}}` |
| POST | `/api/security/grant` | `{"phrase":"ENABLE DELETE"}` | `{"delete_enabled":true}` |
| POST | `/api/security/revoke` | `{}` | `{"delete_enabled":false}` |

### 1.3 状态码约定

| 场景 | 状态码 |
|------|--------|
| 未授权删除 / 授权短语错误 | `403` |
| 二次确认短语错误（`RESTORE` / `DELETE`） | `400` |
| 快照不存在 | `404`（由通用异常映射为 `500` 的场景已在上层捕获为 `400`） |
| 参数或路径非法 | `400` |
| 其他未处理异常 | `500`，并写入 `logs/app.log` 堆栈 |

## 2. Python core 模块

### 2.1 `core.db.DatabaseManager`

```python
db = DatabaseManager(db_path, store_raw=True)
db.connect()            # check_same_thread=False + WAL + synchronous=NORMAL
db.init_tables()        # 建表、检测旧库并迁移到 Schema v3

db.make_message_key(chat_id, message_id) -> "chat_id:message_id"
db.upsert_chat(chat_id, name, chat_type)
db.list_chats() -> list[dict]
db.rename_chat(chat_id, new_name)          # 空名称抛 ValueError
db.delete_chat_data(chat_id) -> {messages_deleted, entities_deleted}
db.insert_messages_batch(messages, chat_id) -> int   # 返回真实新增数
db.get_messages_page(chat_id, offset, limit) -> {items,total,...}
db.search_messages(chat_id, keyword, limit)
db.get_statistics(chat_id)
db.get_top_senders(chat_id, limit, start, end)
db.get_activity_heatmap(chat_id, start, end) -> {"week_hour": count}
db.get_daily_summary(chat_id, start, end) -> [(date, count)]
db.get_import_history(chat_id=None)
db.verify_integrity() -> {schema_version,total_messages,distinct_message_keys,duplicate_keys,orphan_entities,chats_without_rows,ok}
```

### 2.2 `core.importer`

```python
iter_messages(json_path)                       # 生成器，流式解析，不 json.load 全文件
read_metadata(json_path) -> {name,type,id}
count_messages_stream(json_path) -> int
import_streaming(db, json_path, progress_callback=None,
                 chat_id_override=None, batch_size=500)
# -> {chat_id,name,total,imported_count,skipped_count,duration_ms,dedupe_key}
```

### 2.3 `core.backup.BackupManager`

```python
BackupManager(db_path, backup_dir, keep=10, max_total_mb=2048)
.create(label) -> manifest          # 单文件快照 + .manifest.json
.list() -> [manifest]
.verify(name) -> {ok,errors[]}
.restore(name, confirm) -> {...}    # confirm 必须为 "RESTORE <name>"
.prune() -> removed[]
```

### 2.4 `core.security.SecurityManager`

```python
GRANT_PHRASE = "ENABLE DELETE"
.is_delete_enabled() -> bool        # 默认 False
.grant_delete(phrase)               # 短语错误抛 DeletePermissionError
.revoke_delete()
.require_delete(action, target)     # 未授权抛 DeletePermissionError，并写审计
.audit(action, target, allowed, actor="local")
.get_audit_log(limit=200)
```

### 2.5 `core.server`

```python
create_server(db_path, host="127.0.0.1", port=0) -> (ThreadingHTTPServer, AppState)
serve_forever(db_path, host, port)
```

`AppState` 持有 `db / security / backups / lock / jobs`；导入在后台线程使用独立连接，避免 SQLite 跨线程问题。

## 3. 命令行接口

### 3.1 `sql_converter/json_to_sqlite.py`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--json` | `result.json` | Telegram 导出 JSON |
| `--db` | `telegram_chat.db` | 目标库，不存在时自动建表 |

退出码：`0` 成功；`1` JSON 不存在；`2` 完整性校验失败。

### 3.2 `sql_converter/export_data.py`

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--db` | `telegram_chat.db` | 数据库路径 |
| `--format` | `csv` | `csv` / `parquet` |
| `--output` | 自动命名 | 输出路径 |
| `--chat-id` | 全部 | 按群过滤 |
| `--start` / `--end` | 不限 | 日期区间（含端点） |

### 3.3 其他

```bash
python3 -m core.server --port 8765 --db <path>
python3 scripts/generate_demo_data.py --messages 232000 --days 730 --out /tmp/bench/big.json
python3 scripts/generate_demo_data.py --chats 5 --messages 1800 --out /tmp/multi/demo_chat_1.json
python3 scripts/bench_studio.py --url http://127.0.0.1:8765 --json
python3 scripts/build_app.py
```

## 4. 前端调试接口

桌面 App 与浏览器共用 `window.__studio`：

| 方法 | 说明 |
|------|------|
| `getState()` | 当前群、页码、总数、渲染节点数、删除权限、tab |
| `selectChat(chat_id)` | 切换群 |
| `switchView(name)` | 切换 `messages / heatmap / imports / backups / security` |
| `goToPage(page)` | 跳页 |
| `loadMessages()` | 重新加载当前页 |
| `loadHeatmap(range)` | 加载热力图区间 |

原生桥：`window.__native.pickedJson(paths)` 由 AppKit 文件选择回调调用；浏览器模式下退化为输入路径。

## 5. 兼容性说明

- `/api/*` 为本项目内部接口，未做版本前缀；破坏性变更会提升 `__version__` 并在 CHANGELOG 标注；
- V1.1 的 `chat_viewer`、`heatmap_visualization` 为纯静态页面，不依赖本 API，仍可独立使用；
- `sql_converter` 的 CLI 参数保持向后兼容。
