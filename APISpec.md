# API 规格说明书（APISpec）

- 项目：TG-Chat-to-SQL
- 版本：v1.1.0
- 更新日期：2026-11-05

本项目对外提供三类接口：命令行、Python 模块、前端数据 / 调试接口。所有接口均在本地运行。

## 1. 命令行接口

### 1.1 `sql_converter/json_to_sqlite.py`

增量导入 Telegram JSON。

```bash
python sql_converter/json_to_sqlite.py --json result.json --db telegram_chat.db
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--json` | `result.json` | Telegram 导出 JSON 路径 |
| `--db` | `telegram_chat.db` | 目标 SQLite 路径；不存在时自动创建并建表 |

退出码：

| 码 | 含义 |
|----|------|
| 0 | 导入成功且完整性校验通过 |
| 1 | JSON 文件不存在 |
| 2 | 完整性校验失败（存在重复键或孤儿实体） |

输出包含：群组名称、群组 ID、去重键、JSON 总数、新增、跳过重复、数据库总计、schema 版本、校验结果。

### 1.2 `sql_converter/export_data.py`

```bash
python sql_converter/export_data.py \
  --db telegram_chat.db \
  --format csv|parquet \
  --output messages.csv \
  [--chat-id 1234567890] \
  [--start 2026-01-01] \
  [--end 2026-03-01]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--db` | `telegram_chat.db` | 数据库路径，必须存在 |
| `--format` | `csv` | `csv` 或 `parquet` |
| `--output` | 自动命名 | 输出路径；默认 `export_<时间戳>.<格式>` |
| `--chat-id` | 空 | 只导出指定群组 |
| `--start` | 空 | 起始日期 `YYYY-MM-DD`（含） |
| `--end` | 空 | 结束日期 `YYYY-MM-DD`（含） |

退出码：`0` 成功，`1` 数据库不存在，`3` 导出失败（含未安装 pyarrow）。

### 1.3 `sql_converter/verify_db.py`

```bash
python sql_converter/verify_db.py --db telegram_chat.db
```

输出群组信息、统计、去重校验、发送者 TOP10。退出码 `0` 通过，`2` 校验失败，`1` 文件不存在。

### 1.4 `heatmap_visualization/data_processor.py`

```bash
python heatmap_visualization/data_processor.py \
  --input result.json \
  --output heatmap_visualization/processed_data.json \
  [--top-users 20]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | `result.json` | 输入 JSON |
| `--output` | `processed_data.json` | 输出聚合 JSON |
| `--top-users` | `20` | 活跃用户排行数量 |

## 2. Python 模块接口

### 2.1 `importer_gui.db_manager.DatabaseManager`

```python
from db_manager import DatabaseManager

db = DatabaseManager(db_path)
db.connect()
db.init_tables()   # 建表 + v1 自动迁移
```

| 方法 | 返回 | 说明 |
|------|------|------|
| `make_message_key(chat_id, message_id)` | `str` | 静态方法，生成 `chat_id:message_id` |
| `get_schema_version()` | `int` | 当前 schema 版本（v2 = 2） |
| `get_existing_message_keys(chat_id=None)` | `set[str]` | 指定群或全库的已有去重键 |
| `insert_messages_batch(messages, chat_id=None)` | `int` | 批量 `INSERT OR IGNORE`，返回真实新增数 |
| `insert_chat_info(name, type, chat_id)` | `None` | 按 `chat_id` upsert |
| `get_statistics()` | `dict` | 消息 / 用户 / 回复 / 转发 / 实体统计 |
| `verify_integrity()` | `dict` | 去重与孤儿实体校验 |
| `get_import_history()` | `list[tuple]` | 最近 50 条导入日志 |
| `log_import(file, total, imported, skipped, status)` | `None` | 写入导入日志 |

`get_existing_message_ids()` 仅为兼容旧代码保留，新代码应使用 `get_existing_message_keys()`。

`verify_integrity()` 返回：

```json
{
  "schema_version": 2,
  "total_messages": 9441,
  "distinct_message_keys": 9441,
  "duplicate_keys": [],
  "orphan_entities": 0,
  "ok": true
}
```

### 2.2 `importer_gui.importer.JSONImporter`

| 方法 | 说明 |
|------|------|
| `load_json(path)` | 读取 JSON |
| `analyze_json(data)` | 预览群名、类型、ID、消息数 |
| `filter_new_messages(messages, existing_keys, chat_id)` | 返回 `(new_messages, skipped)` |
| `import_to_database(db, path, progress_callback=None, chat_id_override=None)` | 完整增量导入流程 |

`import_to_database` 返回：

```json
{
  "chat_name": "深夜代码俱乐部 · 演示",
  "chat_id": "1234567890",
  "total_in_json": 9441,
  "imported_count": 9441,
  "skipped_count": 0,
  "skipped_before_insert": 0,
  "is_new_db": true,
  "dedupe_key": "chat_id:message_id"
}
```

## 3. 数据库接口

### 3.1 核心表

```sql
CREATE TABLE messages (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_key TEXT NOT NULL UNIQUE,
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
    content_hash TEXT
);

CREATE TABLE text_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_key TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_text TEXT,
    FOREIGN KEY (message_key) REFERENCES messages(message_key) ON DELETE CASCADE
);
```

### 3.2 索引

```sql
CREATE UNIQUE INDEX uq_messages_message_key ON messages(message_key);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_sender_id ON messages(sender_id);
CREATE INDEX idx_messages_date ON messages(date_unixtime);
CREATE INDEX idx_entities_message_key ON text_entities(message_key);
```

### 3.3 常用查询

```sql
-- 消息去重自检
SELECT COUNT(*) AS total, COUNT(DISTINCT message_key) AS keys FROM messages;

-- 按日期聚合
SELECT substr(date, 1, 10) AS day, COUNT(*) FROM messages GROUP BY day ORDER BY day;

-- 回复链（显式指定 chat_id，避免跨群同 ID 歧义）
SELECT m1.text_content, m2.text_content AS reply_text
FROM messages m1
LEFT JOIN messages m2
  ON m1.chat_id = m2.chat_id AND m1.reply_to_message_id = m2.id
WHERE m1.chat_id = ? AND m1.reply_to_message_id IS NOT NULL;

-- 某消息的文本实体
SELECT e.entity_type, e.entity_text
FROM text_entities e
WHERE e.message_key = ?;
```

## 4. 前端数据接口

### 4.1 `heatmap_visualization/processed_data.json`

```json
{
  "meta": {
    "chat_name": "string",
    "chat_type": "string",
    "chat_id": "string|number",
    "total_messages": 9441,
    "generated_at": "ISO8601",
    "source_file": "demo_large.json"
  },
  "activity_heatmap": { "0_0": 3, "0_1": 5 },
  "topic_heatmap": { "0_0": { "部署": 2 } },
  "daily_summary": { "2026-06-08": 61 },
  "daily_details": {
    "2026-06-08": {
      "hour_counts": [0, 0, "... 共24项"],
      "keywords": { "SQLite": 4 },
      "message_count": 61,
      "user_count": 12,
      "users": ["阿岚", "小北"],
      "user_message_counts": { "阿岚": 8, "小北": 6 }
    }
  },
  "top_users": [["阿岚", 1200]],
  "time_period_stats": {
    "晚上 (18-24点)": { "message_count": 3000, "top_keywords": [["部署", 90]] }
  }
}
```

### 4.2 聊天查看器 `chat_data.json`

直接复用 Telegram 导出结构：

```json
{
  "name": "群名",
  "type": "private_group",
  "id": 1234567890,
  "messages": [
    {
      "id": 1,
      "type": "message",
      "date": "2026-06-08T20:00:00",
      "date_unixtime": "1780000000",
      "from": "阿岚",
      "from_id": "user_alan",
      "text": "文本",
      "text_entities": [{"type": "plain", "text": "文本"}],
      "reply_to_message_id": 2,
      "forwarded_from": "开源日报",
      "media_type": "sticker",
      "sticker_emoji": "🚀",
      "reactions": [{"emoji": "👍", "count": 3}]
    }
  ]
}
```

### 4.3 调试接口

`window.__viewer`（聊天查看器）：

| 方法 / 字段 | 返回 | 说明 |
|-------------|------|------|
| `getState()` | `{total, raw, renderedStart, renderedEnd, renderedNodes, pageSize, totalHeight, prefixAt100, prefixAt500, pendingAnchorIndex}` | 用于验证虚拟滚动只渲染少量节点 |
| `goToPage(n)` | `void` | 跳转到第 n 页 |
| `scrollToMessage(id)` | `void` | 清空筛选并跳转到指定消息 |
| `applyFilters()` | `void` | 重新应用当前筛选 |

`window.__heatmap`（热力图）：

| 方法 / 字段 | 说明 |
|-------------|------|
| `getState()` | 返回 `selectedDate / selectedDow / timelineRange / zoomStart / zoomEnd` |
| `timelinePreset(days)` | `7 / 30 / 90 / 'all'` |
| `clearTimelineRange()` | 清除时间轴区间 |
| `getTimelineDates()` | 当前区间内的日期数组 |
| `selectDate(date)` / `clearDateFilter()` | 日期下钻 |
| `selectDow(dow)` / `clearDowFilter()` | 星期下钻 |

## 5. 版本与兼容

- 数据 schema：v1 → v2 自动迁移，v2 为当前唯一写入格式；
- CLI 参数向后兼容：`json_to_sqlite.py` 不带参数时仍使用 `result.json` / `telegram_chat.db`；
- `get_existing_message_ids()` 保留但标记为兼容接口；
- 前端数据格式在 v1.1 中只新增 `user_message_counts`，旧字段不变。
