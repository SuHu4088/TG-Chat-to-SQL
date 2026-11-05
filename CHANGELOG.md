# 更新日志（CHANGELOG）

本文件记录所有值得注意的变更。版本号遵循 `主版本.次版本.修订号`。

## v1.2.0（2026-11-05）

### 新增

- **macOS 原生桌面应用**：`app/main.py` 使用 PyObjC（AppKit + WebKit），`NSVisualEffectView`（`behindWindow`）+ 透明 `WKWebView` 实现真实系统毛玻璃；强制深色外观。
- **`TG Chat Studio.app`（arm64）**：`scripts/build_app.py` 通过 PyInstaller 打包，内置 Python 运行时，双击即可运行；纯代码生成应用图标（`scripts/make_icon.py`）。
- **统一多群库（Schema v3）**：新增 `chats` 表；`messages.chat_id` 分区；`(chat_id, date_unixtime, row_id)` / `(chat_id, id)` / `(chat_id, sender_name)` 复合索引。
- **群管理**：群列表、切换、重命名、受控删除、每群统计、每群导入记录。
- **备份与回滚**：`core/backup.py` 支持手动快照、`.manifest.json`（sha256/大小/群数/消息数/schema）、恢复前完整性校验、`RESTORE <name>` 二次确认、恢复前自动 `pre-restore` 快照、保留策略（最近 10 个 / 总 2 GB）。
- **删除权限闸门**：`core/security.py`，`delete_enabled` 默认 0；`ENABLE DELETE` 授权；可撤销；`audit_log` 表 + `logs/audit.jsonl` 双写，被拒绝的尝试也记录。
- **本地 HTTP API**：`core/server.py`，仅监听 `127.0.0.1`；桌面 App、浏览器调试、Playwright 验收共用。
- **流式导入**：`core/importer.py` 逐条 `raw_decode`，批量 500 条去重写入；导入峰值内存从 1.21 GiB 降到 35.6 MB。
- **中文文档套件升级**：README、RequirementsSpec、SystemDesign、APISpec、TestPlan、CHANGELOG 全部更新到 v1.2.0。
- **实测脚本**：`scripts/bench_viewer.py`（旧基线）、`scripts/bench_studio.py`（新界面）、`scripts/shot_studio.py`（截图与状态导出）。
- **自动化测试**：新增 `tests/test_core_v12.py`，覆盖多群隔离、流式导入、删除闸门、审计、备份/恢复/保留策略。

### 变更

- 默认数据目录改为 `~/Library/Application Support/TGChatToSQL`（可用 `TGCHAT_DATA_DIR` 覆盖）。
- 日志统一到 `core/logging_setup.py`，`logs/app.log` 按 5 MB × 5 滚动。
- 聊天查看器改为「服务端分页 + 前端虚拟滚动」，容器拆分为 `chat-spacer`（总高度）与 `chat-window`（`translateY` 窗口），修复一次渲染 503 条的问题。
- 服务消息中文化（邀请成员、改名、离开群组等），不再显示空文本。
- 热力图 7×24 网格补齐 0 值单元格；每日趋势 X 轴按天数自适应显示日期刻度。
- 群名生成器修复参数覆盖 bug，重新生成的多群演示数据群名正确。

### 修复

- 修复备份快照继承 WAL 模式导致只读校验 `unable to open database file` 的问题：快照生成后执行 `wal_checkpoint(TRUNCATE)` + `journal_mode=DELETE`，并清理 `-wal/-shm`。
- 修复备份清单生成失败时残留半成品 `.db` 文件的问题。
- 修复 API 层删除权限异常与二次确认异常未映射为 `403 / 400` 的问题。
- 修复虚拟滚动因容器高度链错误导致的“全量渲染”（503 节点 → 14 节点）。
- 修复 `loadMessages()` 调用未定义的 `rebuildUnits()` 导致页面空白。

### 性能（232,707 条虚构消息 / M5 Pro / 64 GB / macOS 27.0.1）

| 指标 | v1.1.0 | v1.2.0 |
|------|--------|--------|
| 导入耗时 | 4.04 s | 3.63 s |
| 导入峰值 RSS | 1.21 GiB | 35.6 MB |
| 首屏渲染 | 372.6 ms | 84.6 ms |
| 平均帧率 | 60.1 FPS | 60.0 FPS |
| P95 帧耗时 | 16.8 ms | 16.7 ms |
| JS 堆 | 197.0 MB | 8.2 MB |
| DOM 节点 | 14–22 | 14 |
| 深分页 API | 82.7 ms | 27.4 ms |

### 已知限制

- `.app` 为 ad-hoc 签名、未公证，首次打开需右键或移除 quarantine；
- 仅支持 macOS arm64，未适配 Intel 与 macOS 15/16；
- 深分页仍为 OFFSET 实现，百万级数据建议改 keyset 分页。

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
