# 系统设计说明书（SystemDesign）

- 项目：TG-Chat-to-SQL / TG Chat Studio
- 版本：v1.2.0
- 更新日期：2026-11-05

## 1. 总体架构

```
Telegram 导出 JSON
        │
        ▼
core/importer.py  流式解析 + 批量去重
        │
        ▼
core/db.py  SQLite Schema v3（单库 / 多群分区 / 复合索引）
        │
        ├──────────────► core/backup.py   快照 / 校验 / 回滚
        ├──────────────► core/security.py 删除闸门 / 审计
        ▼
core/server.py  127.0.0.1 HTTP API（ThreadingHTTPServer）
        │
        ▼
app/main.py  AppKit 原生窗口（NSVisualEffectView + 透明 WKWebView）
        │
        ▼
app/web/  深色玻璃 UI / 虚拟滚动 / ECharts
```

同一套 API 同时服务桌面 App 与浏览器调试模式，不存在两套数据访问实现。命令行工具（`sql_converter/`）与 V1.1 的网页查看器仍保留，复用 `core`（或旧 `importer_gui`）以保证兼容。

## 2. 技术选型：为什么是 PyObjC + WKWebView

需求要求「真实系统半透明/毛玻璃，不许纯色假装玻璃」。这是选型的硬约束。

| 方案 | 真实系统模糊 | 体积 | 与现有 Python 数据层集成 | 结论 |
|------|--------------|------|--------------------------|------|
| Tkinter | 否 | 极小 | 直接 | 无法满足玻璃要求，弃用（V1.1 的旧界面即为此） |
| Electron | 可以用 `vibrancy` | ≥ 150 MB | 需要 Node 桥接 Python | 体积与构建链过重 |
| Tauri | macOS 可开 `vibrancy` | 中等 | 需要 Rust + 侧车进程 | 引入第二语言栈，收益不明显 |
| **PyObjC + AppKit + WKWebView** | **是**（`NSVisualEffectView.behindWindow`） | 约 25 MB | 同进程、直接 import `core` | **采用** |

关键实现：

- 内容视图自下而上为 `NSVisualEffectView`（`material=underWindowBackground`、`blendingMode=behindWindow`、`state=active`）→ 透明 `WKWebView`（`drawsBackground=false`）；
- `NSWindow` 设置 `titlebarAppearsTransparent`、`fullSizeContentView`、`opaque=false`；
- 外观强制 `NSAppearanceNameDarkAqua`；
- Web 侧 CSS 只做分层与描边，不再依赖 `backdrop-filter` 伪造玻璃；
- 文件选择走 `WKScriptMessageHandler("tgchat")` → `NSOpenPanel` → 回调 `window.__native.pickedJson(paths)`。

## 3. 数据库设计（Schema v3）

### 3.1 表结构

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `schema_meta` | `key`, `value` | `schema_version=3` |
| `chats` | `chat_id` PK, `title`, `original_name`, `chat_type` | 群主表，支持重命名与显示名 |
| `messages` | `message_key` UNIQUE, `chat_id`, `id`, `date_unixtime` | 消息主表，按 `chat_id` 分区 |
| `text_entities` | `message_key` | 文本实体按去重键关联 |
| `import_log` | `chat_id`, `duration_ms`, `status`, `error` | 每群导入记录 |
| `audit_log` | `action`, `target`, `allowed`, `actor` | 删除/授权审计 |
| `app_settings` | `key`, `value` | `delete_enabled=0` 等开关 |

### 3.2 索引

```sql
CREATE UNIQUE INDEX idx_messages_key        ON messages(message_key);
CREATE INDEX idx_messages_chat_date         ON messages(chat_id, date_unixtime, row_id);
CREATE INDEX idx_messages_chat_id           ON messages(chat_id, id);
CREATE INDEX idx_messages_chat_sender       ON messages(chat_id, sender_name);
CREATE INDEX idx_import_log_chat            ON import_log(chat_id, import_time DESC);
```

`(chat_id, date_unixtime, row_id)` 让分页排序走索引；`(chat_id, id)` 让回复链 JOIN 走索引。

### 3.3 去重键

```
message_key = f"{chat_id}:{message_id}"
```

批内先 `SELECT message_key FROM messages WHERE message_key IN (...)`（每 900 个分块），只为新键写实体与消息，再 `executemany` 插入。重复导入返回真实新增数。

### 3.4 迁移

- v1（`messages.id` 主键）→ v3：重命名为 `messages_v1`，新建 v3 表，回填 `message_key` 与 `chats`；
- v2（`chat_info`）→ v3：`chat_info` 数据导入 `chats`，`import_log` 增加 `chat_id / duration_ms / error` 列；
- 迁移前自动创建数据库快照（复用 `BackupManager`），失败可回退。

## 4. 流式导入

`iter_messages(path)` 不调用 `json.load`：

1. 正则定位 `"messages"\s*:\s*\[`，前缀用正则提取 `name / type / id`；
2. 逐条 `json.JSONDecoder.raw_decode` 解析数组元素，生成器逐条产出；
3. `import_streaming` 每 500 条一批写库，内存 O(batch)，与文件大小基本无关。

实测：103 MB JSON / 232,707 条，峰值 RSS 35.6 MB。

## 5. 前端大数据渲染

三层组合，避免「一次性把 500 条塞进 DOM」或「全量数据进内存」：

1. **服务端分页**：`GET /api/messages?chat_id&offset&limit` 只返回一页（默认 500）；
2. **虚拟滚动**：`chat-spacer` 承载总高度，`chat-window` 用 `translateY` 定位；`prefix` 前缀和 + 二分查找定位可视起点；
3. **动态高度**：窗口渲染后测量真实高度并更新前缀和，使用滚动锚点校正（`scrollTop += prefix[start] - anchorBefore`），避免跳动。

结果：DOM 中始终只有 14–19 个消息节点。

## 6. 备份与恢复

- 快照：SQLite `backup()` API；随后 `wal_checkpoint(TRUNCATE)` + `journal_mode=DELETE`，保证快照是**单文件**（否则只读校验时无法创建 `-shm`）；
- 清单：`.manifest.json` 记录 `sha256 / size_bytes / chats / messages / schema_version / created_at`；
- 校验：sha256 对比 + `PRAGMA integrity_check` + 去重键与孤儿实体校验；
- 恢复：确认短语必须为 `RESTORE <name>`；先校验快照 → 自动创建 `pre-restore` 快照 → 复制到临时文件并再次校验 → 删除 `-wal/-shm` → `os.replace` 原子替换；
- 保留：最近 10 个 + 总大小 2 GB，超限从最旧清理；
- 定期：后台线程每 6 小时检查一次（`TGCHAT_BACKUP_INTERVAL_SECONDS` 可覆盖），若最新快照早于间隔则创建 `auto` 快照；空库跳过。

## 7. 删除权限闸门

```
启动 → app_settings.delete_enabled = 0
     → UI 删除按钮禁用
用户输入 ENABLE DELETE → grant_delete() → 审计 delete.grant
删除请求 → require_delete() → 写 audit_log + logs/audit.jsonl
撤销 → revoke_delete() → 审计 delete.revoke
```

被拒绝的删除尝试同样写审计，字段包含 `action / target / allowed=0 / actor / created_at`。

## 8. 打包

`scripts/build_app.py` 调用 PyInstaller：

```
--windowed --target-arch arm64 --icon build/AppIcon.icns
--add-data app/web:app/web
--hidden-import objc/AppKit/WebKit
--exclude-module tkinter/matplotlib/numpy/pandas
```

产物：`dist/TG Chat Studio.app`（约 25 MB，ad-hoc 签名）。入口 `app/main.py` 通过 `_find_web_root()` 同时支持源码运行与 `sys._MEIPASS` / `Contents/Resources` 打包路径。

## 9. 日志

| 文件 | 用途 | 滚动 |
|------|------|------|
| `logs/app.log` | 启动、导入、备份、恢复、API 错误 | 5 MB × 5 |
| `logs/audit.jsonl` | 审计事件（JSON Lines） | 不滚动，便于外部采集 |

数据目录：`~/Library/Application Support/TGChatToSQL`（可用 `TGCHAT_DATA_DIR` 覆盖），日志位于其下 `logs/`。

## 10. 关键指标（232,707 条虚构消息）

| 指标 | v1.1.0 | v1.2.0 |
|------|--------|--------|
| 导入峰值 RSS | 1.21 GiB | 35.6 MB |
| 导入耗时 | 4.04 s | 3.63 s |
| 首屏 | 372.6 ms | 84.6 ms |
| JS 堆 | 197.0 MB | 8.2 MB |
| DOM 节点 | 14–22 | 14 |
| 深分页 API | 82.7 ms | 27.4 ms |

## 11. 风险与限制

- ad-hoc 签名 + 未公证：用户首次打开需右键打开或移除 quarantine；
- SQLite 单文件库在多进程并发写入时依赖 `check_same_thread=False` + 进程内 `RLock`，不支持多进程同时写；
- 深分页仍是 OFFSET 实现，20 万条下 27 ms 可接受，百万级建议改 keyset 分页；
- 热力图接口一次返回全区间数据，区间过大时响应体较大（当前 730 天约 1 MB）。
