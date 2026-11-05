# 系统设计说明书（SystemDesign）

- 项目：TG-Chat-to-SQL
- 版本：v1.1.0
- 更新日期：2026-11-05

## 1. 总体架构

```
Telegram 导出 JSON
        │
        ├──────────────┐
        ▼              ▼
 importer_gui    sql_converter
 (GUI/增量)      (CLI/增量/导出)
        │              │
        └──────┬───────┘
               ▼
        SQLite Schema v2
        messages.message_key UNIQUE
               │
       ┌───────┴────────┐
       ▼                ▼
 heatmap_visualization  chat_viewer
 data_processor.py     纯前端 + 虚拟滚动
       │                │
       ▼                ▼
 processed_data.json   chat_data.json
       │                │
       ▼                ▼
 ECharts 页面（时间轴） Telegram 风格 UI
```

各模块可独立运行；GUI 与 CLI 共用同一套 `DatabaseManager` 与 `JSONImporter`，避免两套 schema 漂移。

## 2. 数据库设计（Schema v2）

### 2.1 表结构

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `schema_meta` | `key`, `value` | 记录 `schema_version=2` |
| `chat_info` | `chat_id` UNIQUE | 多群信息，按 `chat_id` upsert |
| `messages` | `message_key` UNIQUE, `id`, `chat_id` | 消息主表；`row_id` 为自增物理主键 |
| `text_entities` | `message_key` FK | 文本实体改为按去重键关联 |
| `import_log` | `import_time`, `total_messages`, `imported_count`, `skipped_count` | 每次导入留痕 |

### 2.2 去重键

```
message_key = f"{chat_id}:{message_id}"
```

UNIQUE 索引使 `INSERT OR IGNORE` 天然幂等。实体只在 `cursor.rowcount == 1` 时插入，避免“消息被忽略、实体却重复写入”。

### 2.3 v1 → v2 迁移流程

1. `PRAGMA foreign_keys=OFF`；
2. `text_entities` → `text_entities_v1`，`messages` → `messages_v1`；
3. 新建 v2 表；
4. 回填 `message_key = COALESCE(chat_id,'') || ':' || id`；
5. 文本实体通过 `messages_v1.id` 关联回填 `message_key`；
6. 删除旧表，恢复外键。

迁移在 `DatabaseManager.init_tables()` 中自动执行，使用事务性 DDL，失败不会留下半迁移状态。

## 3. 增量导入流程

```
读取 JSON
  → 取群组 chat_id
  → upsert chat_info
  → SELECT 该群已存在的 message_key 集合
  → 过滤旧消息
  → 每 500 条一批 INSERT OR IGNORE
      ├─ rowcount=0：跳过，不写实体
      └─ rowcount=1：写 text_entities
  → 以真实新增数计算 skipped
  → 写 import_log
```

关键点：`imported` 取自数据库真实插入数，不取自“过滤后条数”，因此同批次内重复键也能被正确计数。

## 4. 导出设计

`sql_converter/export_data.py`：

- 以只读 URI 打开数据库（`mode=ro`），不影响导入进程；
- 消息查询按 `date_unixtime, id` 排序；
- 文本实体先一次性加载为 `{message_key: [{type,text}]}`，再序列化为 JSON 字符串；
- CSV 使用 `utf-8-sig` + `csv.DictWriter` 流式写出；
- Parquet 使用 `pyarrow.Table.from_pylist` + snappy 压缩；pyarrow 缺失时抛出可读错误。

日期过滤：`--start` 当天 00:00 起（含），`--end` 次日 00:00 止（不含），对用户表现为“结束日期包含当天”。

## 5. 热力图与时间轴

### 5.1 数据聚合

`data_processor.py` 输出：

- `activity_heatmap`：`weekday_hour -> count`；
- `topic_heatmap`：`weekday_hour -> {keyword: count}`；
- `daily_summary`：每日消息数；
- `daily_details`：每小时计数、关键词、参与用户、**`user_message_counts`**（v1.1 新增，用于区间内精确用户排行）；
- `top_users`、`time_period_stats`。

### 5.2 时间轴实现

- ECharts 每日趋势图增加 `inside` + `slider` 两个 `dataZoom`；
- `datazoom` 事件经 120 ms 防抖后，将百分比映射为日期索引；
- 全局状态 `timelineRange = {startIndex, endIndex, startDate, endDate}`；
- 区间变化触发：统计卡片、关键词、小时画像、时段话题、用户榜重算；
- 快捷按钮通过 `dispatchAction({type:'dataZoom', start, end})` 驱动，保持与手动缩放一致；
- 覆盖全部日期时自动退化为 `timelineRange = null`，避免“全选但仍显示筛选”。

## 6. 聊天查看器虚拟滚动

### 6.1 数据结构

```
units[]    每个消息一个单元（含是否显示日期分隔）
heights[]  每个单元的估算/实测高度
prefix[]   前缀和，prefix[i] 为第 i 个单元的顶部偏移
```

### 6.2 渲染算法

1. 根据 `scrollTop` 二分查找 `prefix`，定位可视起点；
2. 渲染 `[起点 - 600px, 终点 + 600px]` 的单元；
3. 窗口容器绝对定位，`translateY(prefix[start])`；
4. 画布高度设为 `prefix[n]`，撑开滚动条；
5. 渲染后用 `getBoundingClientRect()` 实测高度，更新 `heights` 与 `prefix`；
6. 若可视锚点上方高度变化，重设 `scrollTop` 保持视觉位置；
7. 关闭浏览器滚动锚定（`overflow-anchor: none`）与全局平滑滚动，避免程序化跳页被干扰。

### 6.3 分页

分页不是额外加载层，而是“滚动定位快捷方式”：

- `pageCount = ceil(units.length / pageSize)`；
- `goToPage(n)` 把 `scrollTop` 设到 `prefix[(n-1)*pageSize]`；
- 记录 `pendingAnchorIndex`，高度测量完成后重新锚定到该索引，防止动态高度把页码拉回上一页；
- 页码由顶部可视索引反推，滚动时实时更新。

### 6.4 性能要点

- 回复查询从 `Array.find` 改为 `Map`，避免 O(n²)；
- 消息点击事件改为容器级事件委托，窗口重渲染不重复绑定；
- 搜索输入 300 ms 防抖；
- 渲染节点数与总消息数解耦。

## 7. 错误处理与日志

- GUI 导入在后台线程执行，异常回写状态栏并写入 `import_log.status`；
- CLI 导出失败返回非 0：`1` 文件不存在、`2` 完整性校验失败、`3` 导出失败（含 pyarrow 缺失）；
- `verify_db.py` 输出 schema 版本、重复键、孤儿实体，可直接用于 CI；
- 浏览器侧通过 `console.error` 暴露数据加载失败，并在页面显示可读错误。

## 8. 安全与隐私

- 全本地处理，无网络上报；
- 真实数据文件由 `.gitignore` 排除；
- 截图与示例数据来自固定种子的虚构生成器；
- 文档与截图中不出现真实成员昵称、群名或消息内容。
