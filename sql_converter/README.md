# TG群聊转SQL 开发文档

## 📁 项目结构

```
TG-Chat-to-SQL/
├── sql_converter/               # 命令行工具
│   ├── json_to_sqlite.py        # JSON → SQLite 增量导入
│   ├── export_data.py           # SQLite → CSV / Parquet
│   ├── verify_db.py             # 去重与完整性校验
│   └── README.md                # 本文档
```

## 🗄️ 数据库设计（Schema v2）

### 表结构

#### chat_info - 群组信息表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| chat_name | TEXT NOT NULL | 群组名称 |
| chat_type | TEXT NOT NULL | 群组类型（private_supergroup 等） |
| chat_id | TEXT NOT NULL UNIQUE | 群组ID |

#### messages - 消息表
| 字段 | 类型 | 说明 |
|------|------|------|
| row_id | INTEGER PK | 自增物理主键 |
| message_key | TEXT UNIQUE | 去重键 `chat_id:message_id` |
| id | INTEGER | Telegram 群内消息 ID |
| chat_id | TEXT | 群组 ID |
| message_type | TEXT | 消息类型：`message` / `service` |
| date | TEXT | 日期时间 ISO8601 格式 |
| date_unixtime | INTEGER | Unix时间戳 |
| sender_name | TEXT | 发送者昵称（可为null） |
| sender_id | TEXT | 发送者ID（格式：user数字ID） |
| text_content | TEXT | 消息文本内容 |
| reply_to_message_id | INTEGER | 回复目标消息ID（群内序号） |
| forwarded_from | TEXT | 转发来源昵称 |
| media_type | TEXT | 媒体类型（sticker等） |
| raw_json | TEXT | 原始JSON完整数据（兜底字段） |
| content_hash | TEXT | 内容哈希，用于辅助校验 |

#### text_entities - 文本实体表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| message_key | TEXT FK | 关联 `messages.message_key` |
| entity_type | TEXT | 实体类型：plain / emoji / bold / code 等 |
| entity_text | TEXT | 实体文本内容 |

### 索引
```sql
CREATE UNIQUE INDEX uq_messages_message_key ON messages(message_key);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_sender_id ON messages(sender_id);
CREATE INDEX idx_messages_date ON messages(date_unixtime);
CREATE INDEX idx_entities_message_key ON text_entities(message_key);
```

## 🛠️ 快速开始

### 运行转换（增量导入）
```bash
cd sql_converter
python json_to_sqlite.py --json ../result.json --db telegram_chat.db
```

重复执行同一命令会显示 `新增 0 / 跳过重复 N`，数据库总数不变。

### 导出 CSV / Parquet
```bash
python export_data.py --db telegram_chat.db --format csv --output messages.csv
python export_data.py --db telegram_chat.db --format parquet --output messages.parquet \
  --start 2026-01-01 --end 2026-03-01
```

Parquet 需要 `pip install pyarrow`；未安装时会给出明确提示并返回退出码 3。

### 校验数据库
```bash
python verify_db.py --db telegram_chat.db
```

### 连接数据库查询
```python
import sqlite3

conn = sqlite3.connect('sql_converter/telegram_chat.db')
cursor = conn.cursor()

# 获取某个用户的所有消息
cursor.execute("""
    SELECT sender_name, text_content, date 
    FROM messages 
    WHERE sender_name = ? 
    ORDER BY date_unixtime
""", ('用户名',))

# 查找包含关键词的消息
cursor.execute("""
    SELECT * FROM messages 
    WHERE text_content LIKE ? 
    ORDER BY date_unixtime
""", ('%关键词%',))

# 获取某时间段的消息
cursor.execute("""
    SELECT * FROM messages 
    WHERE date_unixtime BETWEEN ? AND ?
    ORDER BY date_unixtime
""", (起始时间戳, 结束时间戳))

# 查询回复链（显式带 chat_id，避免跨群同 ID 歧义）
cursor.execute("""
    SELECT m1.id, m1.text_content, m2.text_content AS reply_text
    FROM messages m1
    LEFT JOIN messages m2
      ON m1.chat_id = m2.chat_id AND m1.reply_to_message_id = m2.id
    WHERE m1.chat_id = ? AND m1.reply_to_message_id IS NOT NULL
    LIMIT 100
""", ('群组ID',))

conn.close()
```

### SQL 常用查询示例

#### 1. 统计每个用户的发言频率
```sql
SELECT sender_name, COUNT(*) AS message_count
FROM messages
WHERE sender_name IS NOT NULL
GROUP BY sender_name
ORDER BY message_count DESC;
```

#### 2. 按日期统计消息量
```sql
SELECT substr(date, 1, 10) AS day, COUNT(*) AS count
FROM messages
GROUP BY day
ORDER BY day;
```

#### 3. 查找某人的所有回复
```sql
SELECT m.date, m.sender_name, m.text_content, m.reply_to_message_id
FROM messages m
WHERE m.sender_name = '某某' 
  AND m.reply_to_message_id IS NOT NULL
ORDER BY m.date_unixtime;
```

#### 4. 获取完整的消息上下文（含实体）
```sql
SELECT m.message_key, m.id, m.sender_name, m.text_content, 
       m.date, m.media_type,
       GROUP_CONCAT(e.entity_type || ':' || e.entity_text, ' | ') AS entities
FROM messages m
LEFT JOIN text_entities e ON m.message_key = e.message_key
WHERE m.chat_id = ? AND m.id = 12345
GROUP BY m.message_key;
```

#### 5. 查找转发消息及来源
```sql
SELECT date, sender_name, text_content, forwarded_from
FROM messages
WHERE forwarded_from IS NOT NULL
ORDER BY date_unixtime;
```

## 📋 JSON 数据字段说明（Telegram 导出格式）

### 顶层结构
```json
{
  "name": "群组名称",
  "type": "private_supergroup",
  "id": 4325779281,
  "messages": [...]
}
```

### 消息对象字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 消息唯一ID |
| type | str | `message` / `service` |
| date | str | ISO8601 日期时间 |
| date_unixtime | str | Unix时间戳（字符串） |
| from | str/null | 发送者昵称 |
| from_id | str | 发送者ID |
| actor | str | 操作者（服务消息） |
| actor_id | str | 操作者ID（服务消息） |
| text | str/array | 消息文本 |
| text_entities | array | 文本实体列表 |
| reply_to_message_id | int | 回复目标ID |
| forwarded_from | str/null | 转发来源 |
| media_type | str | 媒体类型 |
| action | str | 服务动作（服务消息） |
| title | str | 群组标题（服务消息） |

### text_entities 类型
- `plain` - 纯文本
- `emoji` - 表情符号
- `bold` - 粗体
- `code` - 代码
- `link` - 链接
- `mention` - @提及
- `mention_name` - 可点击提及

## ⚠️ 注意事项

1. **原始JSON文件**: `result.json` 为原始文件，禁止修改/删除。所有操作在 `sql_converter/` 中完成
2. **编码**: 所有文件使用 UTF-8 编码
3. **消息ID**: SQLite中 `id` 字段直接使用Telegram导出的消息ID，便于溯源
4. **文本实体**: 复杂文本（含格式/链接/表情）存储在 `text_entities` 表中，`text_content` 仅为纯文本部分
5. **扩展**: `raw_json` 字段保存了完整的原始JSON对象，便于后续扩展字段时回溯

## 🔧 后续开发建议

- **全文检索**: 可基于 SQLite FTS5 扩展添加全文搜索能力
- **数据分析**: 统计活跃时段、话题热度、社交网络分析
- **可视化**: 将查询结果导出为图表或仪表盘
- **消息导出**: 按时间段或关键词筛选导出为其他格式
