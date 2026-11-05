# 测试计划（TestPlan）

- 项目：TG-Chat-to-SQL
- 版本：v1.1.0
- 更新日期：2026-11-05
- 执行环境：macOS 26（Apple Silicon）、Python 3.9.6、Chrome 稳定版、SQLite 3.x

## 1. 测试目标

验证本轮六项核心能力：增量去重、CSV / Parquet 导出、可交互时间轴、分页 + 虚拟滚动、仓库门面与文档同步。

## 2. 测试范围

| 范围 | 覆盖 |
|------|------|
| 数据库 | Schema v2 建表、v1 迁移、去重键、跨群同 ID、文本实体 |
| 导入 | 首次导入、二次导入、重复实体、导入日志 |
| 导出 | CSV 编码与字段、日期过滤、Parquet 类型 |
| 热力图 | 时间轴缩放、快捷区间、统计联动、无控制台错误 |
| 查看器 | 分页跳转、虚拟节点数、滚动、搜索、回复跳转 |
| 门面 | description、topics、LICENSE、首屏真实截图 |
| 隐私 | `.gitignore`、示例数据虚构性 |

## 3. 自动化测试

### 3.1 运行命令

```bash
python -m unittest discover -s tests -v
python sql_converter/json_to_sqlite.py --json importer_gui/sample_data.json --db /tmp/tgtest.db
python sql_converter/export_data.py --db /tmp/tgtest.db --format csv --output /tmp/tgtest.csv
python sql_converter/export_data.py --db /tmp/tgtest.db --format parquet --output /tmp/tgtest.parquet
```

### 3.2 用例与结果

| 编号 | 用例 | 步骤 | 预期 | 结果 |
|------|------|------|------|------|
| T-01 | 首次导入 | 导入 3 条消息 | `imported_count=3`，总数 3 | 通过 |
| T-02 | 二次导入幂等 | 同一 JSON 再导入 | `imported_count=0`，总数仍 3，实体数不变 | 通过 |
| T-03 | 跨群相同消息 ID | 两个群各含 `id=1..3` | 总数 6，`distinct_message_keys=6` | 通过 |
| T-04 | v1 自动迁移 | 手工建 v1 表并插入数据，调用 `init_tables()` | schema=2，`message_key='42:1'`，实体关联正确 | 通过 |
| T-05 | CSV 导出 | 导出 2 条消息 | 行数 2，首行 `message_key='3003:1'`，实体 JSON 正确 | 通过 |
| T-06 | 日期过滤 | `--start/--end=2026-02-02` | 只导出 1 条 | 通过 |
| T-07 | Parquet 导出 | 导出 2 条消息 | 行数 2，含 `message_key` 列 | 通过（pyarrow 17.x） |
| T-08 | 去重校验 | 导入后 `verify_integrity()` | `ok=true`，无重复键、无孤儿实体 | 通过 |

自动化结果：`Ran 8 tests — OK`（Parquet 用例在未安装 pyarrow 时自动 skip）。

## 4. 浏览器测试（真实运行）

### 4.1 数据

- 生成 9,441 条虚构消息（150 天，12 个虚构用户）；
- 生成命令：

```bash
python scripts/generate_demo_data.py --messages 8000 --days 150 --out /tmp/demo_large.json
```

### 4.2 聊天查看器

| 编号 | 用例 | 操作 | 预期 | 实测 |
|------|------|------|------|------|
| B-01 | 首屏与总数 | 打开 `http://127.0.0.1:8091/` | 显示总消息数与页码 | `共 9,441 条 · 第 1 / 19 页` |
| B-02 | 下一页 | 点击 `›` | 页码变为 2，可视消息变化 | 页码 1 → 2，`scrollTop≈53,000` |
| B-03 | 连续翻页 | 再点 `›`，再点 `‹` | 2 → 3 → 2 | 通过 |
| B-04 | 每页条数 | 切换 1000/页 | 总页数变为 10 | 通过 |
| B-05 | 虚拟滚动 | 读取 `window.__viewer.getState()` | `renderedNodes` 远小于总数 | 约 15 个节点（总数 9,441） |
| B-06 | 滚动 | 滚轮滚动 50,000px | 页面正常、页码更新 | 通过 |
| B-07 | 控制台 | 全程观察 | 无 JS 报错 | 通过 |

### 4.3 热力图时间轴

| 编号 | 用例 | 操作 | 预期 | 实测 |
|------|------|------|------|------|
| H-01 | 默认区间 | 打开页面 | 显示「全部 150 天」 | 通过 |
| H-02 | 近 90 天 | 点击按钮 | 标签 `2026-08-07 ~ 2026-11-04 · 90 天`，统计天数 90 | 通过 |
| H-03 | 全量恢复 | 点击「全部」 | 恢复 150 天 | 通过 |
| H-04 | 滑块缩放 | 拖动 slider | 区间标签与统计同步变化 | 通过（手动 + 自动化） |
| H-05 | 控制台 | 全程观察 | 无 JS 报错 | 通过 |

## 5. 性能测试

| 指标 | 方法 | 结果 |
|------|------|------|
| 9,441 条消息首屏 | Chrome headless，`networkidle` 后计时 | 约 120–200 ms |
| 虚拟窗口节点数 | `window.__viewer.getState()` | 约 15 |
| 总滚动高度 | `chatMessages.scrollHeight` | 约 1,002,401 px（按估算/实测高度累积） |
| 翻页响应 | 点击到页码更新 | < 1 帧 + 高度校正 |

## 6. 隐私与仓库检查

| 编号 | 检查 | 结果 |
|------|------|------|
| P-01 | `.gitignore` 包含 `*.db`、`result.json`、`chat_data.json`、`processed_data.json` | 通过 |
| P-02 | 示例数据与截图不含真实身份 | 通过（全部来自虚构生成器） |
| P-03 | 仓库无真实聊天附件 | 通过 |
| P-04 | LICENSE 存在 | 通过（MIT） |
| P-05 | description / topics 已配置 | 通过 |

## 7. 回归与发布门槛

发布前必须满足：

1. `python -m unittest discover -s tests -v` 全绿；
2. `json_to_sqlite.py` 二次执行显示新增 0；
3. `verify_db.py` 校验结果通过；
4. 热力图与查看器无控制台错误；
5. README 截图为最新真实界面；
6. CHANGELOG 版本号与 README 一致。

## 8. 已知限制

- Parquet 导出需要额外安装 `pyarrow`；
- 聊天查看器一次性加载 `chat_data.json`，JSON 极大（> 100 MB）时解析时间会上升，后续可改为分片加载；
- 时间轴区间统计依赖 `processed_data.json`，需在导入后重新运行 `data_processor.py`。
