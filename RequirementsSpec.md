# 需求规格说明书（RequirementsSpec）

- 项目：TG-Chat-to-SQL
- 版本：v1.1.0
- 更新日期：2026-11-05
- 状态：已实现并验证

## 1. 项目目标

把 Telegram Desktop 导出的群聊 JSON 变成可查询、可导出、可展示的数据资产。链路为：

```
Telegram 导出 JSON → SQLite（去重、增量）→ CSV / Parquet → 热力图与时间轴 → 聊天查看器
```

目标用户：需要复盘群聊、做活跃度分析、或把聊天记录交给 Excel / 数据分析工具的个人与小团队。

## 2. 范围

### 2.1 本轮范围（v1.1.0）

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-01 | 增量导入 | 同一 JSON 重复导入，第二次 `imported_count = 0`，数据库消息总数与文本实体数不变 |
| FR-02 | 可验证去重键 | 去重键为 `chat_id:message_id`，在 `messages.message_key` 上建立 UNIQUE 约束；`verify_integrity()` 能返回重复键与孤儿实体 |
| FR-03 | 多群共存 | 两个群存在相同 Telegram 消息 ID 时，两条记录都能入库且互不覆盖 |
| FR-04 | 旧库迁移 | v1 数据库（`messages.id` 为主键）首次打开时自动迁移到 v2，保留消息与文本实体 |
| FR-05 | CSV 导出 | 支持全量导出、按 `chat_id` 过滤、按日期区间过滤；文件带 UTF-8 BOM，Excel 直接打开不乱码 |
| FR-06 | Parquet 导出 | 输出 snappy 压缩 Parquet；未安装 pyarrow 时给出明确提示而非崩溃 |
| FR-07 | 可交互时间轴 | 每日趋势图支持滑块缩放、滚轮缩放、近 7 / 30 / 90 天与全部快捷区间 |
| FR-08 | 区间联动 | 时间轴区间变化后，消息总数、统计天数、参与用户、日均、关键词、时段画像、用户榜同步按区间统计 |
| FR-09 | 分页 | 聊天查看器支持 200 / 500 / 1000 / 2000 条每页，可上一页 / 下一页跳转，页码显示当前页与总页数 |
| FR-10 | 虚拟滚动 | 任意滚动位置只渲染可视窗口 + 缓冲区的消息节点；动态高度测量后保持视觉锚点不跳动 |
| FR-11 | 离线可用 | ECharts 本地内置，页面不依赖外网 CDN |
| FR-12 | 隐私 | 真实 JSON / DB 不入库；仓库内示例数据全部为虚构内容 |
| FR-13 | 文档同步 | README、RequirementsSpec、SystemDesign、APISpec、TestPlan、CHANGELOG 同步到 v1.1.0 |

### 2.2 非目标（本轮不做）

- 不做消息编辑、删除等写回 Telegram 的操作；
- 不做服务端部署与多用户鉴权；
- 不做词向量 / 情感分析等高级 NLP；
- 不做移动端原生应用。

## 3. 性能要求

| 指标 | 要求 | 实测（9,441 条虚构消息） |
|------|------|--------------------------|
| 聊天查看器首屏 | < 500 ms | 约 120–200 ms |
| 滚动渲染节点数 | 与总量无关，只与可视高度相关 | 约 15 个消息节点 |
| 分页跳转 | 点击后立即定位到目标页首条 | 已验证 |
| 重复导入 | 不随重复次数增长 | 第二次导入 0 新增 |

## 4. 数据与隐私约束

- 去重键必须可人工验证：`SELECT COUNT(*), COUNT(DISTINCT message_key) FROM messages` 两个值应相等；
- 截图与示例只能使用 `scripts/generate_demo_data.py` 生成的虚构数据；
- `.gitignore` 必须覆盖 `*.db`、`result.json`、`chat_viewer/chat_data.json`、`processed_data.json`。

## 5. 兼容性

- Python 3.9+；
- 数据库自动兼容 v1 → v2，不做破坏性变更；
- 浏览器：Chrome / Edge / Safari 最近两个大版本。

## 6. 验收清单

- [x] FR-01 ~ FR-13 全部通过单测或浏览器实测；
- [x] `python -m unittest discover -s tests -v` 全绿；
- [x] README 首屏使用真实运行截图（虚构数据）；
- [x] 仓库 description、topics、LICENSE 齐备。
