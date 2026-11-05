# 更新日志（CHANGELOG）

本文件记录所有值得注意的变更。版本号遵循 `主版本.次版本.修订号`。

## v1.1.0（2026-11-05）

### 新增

- **Schema v2 与可验证去重键**：新增 `messages.message_key = chat_id:message_id`，在数据库层建立 UNIQUE 约束；支持多群相同 Telegram 消息 ID 共存。
- **v1 → v2 自动迁移**：旧数据库首次打开时自动重命名旧表、回填去重键并重建文本实体关联。
- **CSV / Parquet 导出**：新增 `sql_converter/export_data.py`，支持群组过滤、日期区间过滤；CSV 带 UTF-8 BOM，Parquet 使用 snappy 压缩。
- **可交互时间轴**：每日趋势图新增滑块缩放与滚轮缩放，新增「近 7 / 30 / 90 天 / 全部」快捷区间。
- **时间轴区间联动**：消息总数、统计天数、参与用户、日均、关键词、时段画像、用户榜按区间同步重算。
- **`daily_details[date].user_message_counts`**：为区间内用户排行提供精确计数，替代原先的比例估算。
- **聊天查看器分页 + 虚拟滚动**：每页 200 / 500 / 1000 / 2000 条，只渲染可视窗口；动态高度测量与滚动锚点校正。
- **本地 ECharts**：`heatmap_visualization/vendor/echarts.min.js`，页面离线可用。
- **演示数据生成器**：`scripts/generate_demo_data.py`，固定随机种子，生成完全虚构的聊天数据。
- **自动化测试**：`tests/test_importer.py`、`tests/test_exporter.py`，覆盖幂等导入、跨群 ID、v1 迁移、CSV / Parquet 导出。
- **中文文档套件**：`RequirementsSpec.md`、`SystemDesign.md`、`APISpec.md`、`TestPlan.md`、`CHANGELOG.md`，并重写 README。
- **仓库门面**：description、topics、LICENSE、真实运行截图。

### 变更

- `json_to_sqlite.py` 改为复用 GUI 的 `DatabaseManager` / `JSONImporter`，消除两套 schema 漂移。
- `verify_db.py` 改为调用 `verify_integrity()`，输出 schema 版本、重复键、孤儿实体。
- `data_processor.py` 支持 `--input / --output / --top-users`，便于脚本化。
- 聊天查看器回复查询从 `Array.find` 改为 `Map`，消除 O(n²)。
- 消息点击改为容器级事件委托，虚拟列表重渲染不再重复绑事件。
- 移除虚拟列表元素的淡入动画与全局 `scroll-behavior: smooth`，避免翻页跳转被动画干扰。

### 修复

- 修复 CLI 重复导入时 `text_entities` 被重复写入的问题。
- 修复消息被 `INSERT OR IGNORE` 忽略后仍写入实体的逻辑缺陷。
- 修复多群合并时相同消息 ID 互相覆盖的问题。
- 修复翻页后页码被动态高度校正拉回第 1 页的问题。

### 文档

- README 首屏改用真实运行截图（虚构演示数据），并补充时间轴、虚拟滚动的操作说明。
- 更新数据库设计、索引、常用 SQL 示例（回复链查询显式带 `chat_id`）。

## v1.0.0（2026-08-28）

### 新增

- JSON → SQLite 转换（命令行 + tkinter GUI）。
- 基于消息 ID 的去重与增量导入。
- 暗色主题 GUI、导入进度、数据统计、导入历史。
- 7×24 活跃度热力图、关键词、时段画像、用户排行。
- Telegram 风格聊天查看器（搜索、用户筛选、回复跳转、深色模式）。
- Windows 独立可执行文件（Release）。
