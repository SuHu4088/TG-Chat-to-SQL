# TG群聊SQL导入工具

## 📖 项目概述

一款带图形界面的 Telegram 群聊数据导入工具，支持从 Telegram 导出的 JSON 文件自动导入到 SQLite 数据库中。具备**智能去重**、**增量导入**、**进度显示**等核心功能。

---

## 📁 项目结构

```
importer_gui/
├── main.py              # GUI 主程序入口
├── db_manager.py        # 数据库管理模块
├── importer.py          # JSON导入核心逻辑（含去重）
├── test_import.py       # 测试脚本
├── sample_data.json     # 示例JSON文件
├── telegram_chat.db     # SQLite数据库（运行时生成）
└── README.md            # 本文档
```

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 仅使用标准库（tkinter, sqlite3, json），无需额外安装依赖

### 启动程序

```bash
cd importer_gui
python main.py
```

### 使用步骤

1. **选择数据库路径**
   - 可使用默认路径或点击「浏览...」自定义
   - 首次使用会自动创建数据库和表结构

2. **选择JSON文件**
   - 点击「选择JSON」按钮
   - 选择从 Telegram 导出的 `.json` 文件
   - 程序会自动预览文件信息

3. **开始导入**
   - 点击「🚀 开始导入」按钮
   - 程序自动识别新消息并导入，已存在的消息会自动跳过

4. **查看结果**
   - 导入进度实时显示
   - 数据统计、导入历史可在对应标签页查看

---

## ✨ 核心功能

### 1. 智能去重

- **基于消息ID去重**：每条 Telegram 消息有唯一 ID，程序通过比对数据库中已有 ID 来判断是否重复
- **INSERT OR IGNORE**：使用 SQLite 原生机制，防止重复插入
- **二次导入零影响**：同一个 JSON 文件可反复导入，不会产生重复数据

```python
# 去重逻辑示例
existing_ids = db.get_existing_message_ids()  # 获取所有已有ID
new_messages, skipped = filter_new_messages(messages, existing_ids)
# 只有 new_messages 会被导入
```

### 2. 增量导入

- 支持导入多个 JSON 文件（不同时间段的导出）
- 每个文件只导入数据库中不存在的新消息
- 自动记录每次导入的详细日志

### 3. 数据统计

实时展示数据库状态：
- 消息总数 / 普通消息 / 服务消息
- 独立用户数
- 回复 / 转发数量
- 文本实体数量

### 4. 导入历史

完整的导入日志记录：
- 导入时间
- JSON 文件名
- 消息总数 / 已导入数 / 跳过数
- 导入状态

---

## 🗄️ 数据库设计

### 表结构

#### chat_info - 群组信息
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| chat_name | TEXT | 群组名称 |
| chat_type | TEXT | 群组类型 |
| chat_id | TEXT | 群组原始ID |

#### messages - 消息表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 消息ID（来自Telegram） |
| chat_id | TEXT | 发送者ID |
| message_type | TEXT | message / service |
| date | TEXT | ISO8601日期 |
| date_unixtime | INTEGER | Unix时间戳 |
| sender_name | TEXT | 发送者昵称 |
| sender_id | TEXT | 发送者原始ID |
| text_content | TEXT | 消息文本 |
| reply_to_message_id | INTEGER | 回复目标ID |
| forwarded_from | TEXT | 转发来源 |
| media_type | TEXT | 媒体类型 |
| raw_json | TEXT | 原始JSON |

#### text_entities - 文本实体
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| message_id | INTEGER FK | 关联消息 |
| entity_type | TEXT | plain/emoji/bold/code等 |
| entity_text | TEXT | 实体文本 |

#### import_log - 导入日志
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| import_time | TEXT | 导入时间 |
| json_file | TEXT | JSON文件名 |
| total_messages | INTEGER | JSON中消息总数 |
| imported_count | INTEGER | 实际导入数 |
| skipped_count | INTEGER | 跳过（重复）数 |
| status | TEXT | success / failed |

### 索引
```sql
CREATE INDEX idx_messages_sender_id ON messages(sender_id);
CREATE INDEX idx_messages_date ON messages(date_unixtime);
CREATE INDEX idx_entities_message_id ON text_entities(message_id);
```

---

## 📘 开发文档

### 模块说明

#### `db_manager.py` - 数据库管理
- `DatabaseManager` 类封装所有 SQLite 操作
- 支持连接管理、表初始化、CRUD 操作
- WAL 模式提升并发性能
- 外键约束保证数据完整性

#### `importer.py` - 导入逻辑
- `JSONImporter` 类处理 JSON 解析和导入
- 静态方法设计，便于测试和复用
- 支持进度回调、批量插入
- 完整的去重逻辑实现

#### `main.py` - GUI界面
- 基于 tkinter 的现代化暗色主题界面
- 多标签页设计：导入数据 / 数据统计 / 导入历史
- 异步导入（后台线程），不阻塞UI
- 实时进度显示和状态反馈

### 开发规范

#### 代码风格
- Python PEP 8 规范
- 类型注解（Type Hints）
- 模块化设计，单一职责
- 中文注释说明业务逻辑

#### 文件组织
```
importer_gui/
├── 核心代码
│   ├── main.py          # 入口 + UI
│   ├── db_manager.py    # 数据层
│   └── importer.py      # 业务逻辑
├── 测试
│   └── test_import.py   # 单元/集成测试
├── 数据
│   ├── *.json           # 输入文件（不修改）
│   └── *.db             # 输出数据库
└── 文档
    └── README.md
```

#### 命名约定
- 类：`PascalCase` (如 `DatabaseManager`)
- 函数/方法：`snake_case` (如 `insert_messages_batch`)
- 常量：`UPPER_CASE`
- 私有成员：前缀 `_`

---

## ⚠️ 注意事项

### 文件安全
1. **原始JSON文件**：`result.json` 和 `新导出的JSON_result.json` 为原始文件，**禁止修改/删除**
2. **数据备份**：重要数据库建议定期备份
3. **编码格式**：所有文件使用 UTF-8 编码

### 数据库操作
1. **并发导入**：程序使用 WAL 模式，支持多线程读取
2. **数据完整性**：外键约束确保 text_entities 不会孤立存在
3. **性能优化**：批量插入（每500条一批），定期提交事务

### 已知限制
1. 不支持跨数据库合并（不同群组的数据）
2. 单文件大小受限于内存（建议 < 100MB）
3. GUI 基于 tkinter，在高 DPI 屏幕上可能需要调整缩放

---

## 🔧 扩展指南

### 添加新的统计维度
在 `db_manager.py` 的 `get_statistics()` 方法中添加新的 SQL 查询。

### 自定义导入逻辑
继承 `JSONImporter` 类并重写 `filter_new_messages()` 方法。

### 添加导出功能
使用 `db_manager.py` 的查询方法获取数据，添加导出为 CSV/Excel/JSON 的功能。

---

## 📝 更新日志

### v1.0.0 (2026-07-28)
- 初始版本发布
- 支持 Telegram JSON → SQLite 导入
- 实现智能去重和增量导入
- 提供暗色主题 GUI 界面
- 完善的数据统计和导入历史功能
