# 需求规格说明书（RequirementsSpec）

- 项目：TG-Chat-to-SQL / TG Chat Studio
- 版本：v1.2.0
- 更新日期：2026-11-05
- 状态：已实现并验证

## 1. 项目目标

把 Telegram Desktop 导出的群聊 JSON 变成可查询、可备份、可浏览的本地数据资产，并以 macOS 原生桌面应用交付：

```
Telegram 导出 JSON → 统一 SQLite（多群分区、增量去重）→ 桌面查看器 / 热力图 → CSV / Parquet
```

目标用户：需要复盘群聊、做活跃度分析、或把聊天记录交给 Excel / 数据分析工具的个人与小团队；不要求用户具备命令行能力。

## 2. 本轮范围（v1.2.0）

### 2.1 交付形态

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-01 | 双击可运行 | 产出 macOS arm64 `TG Chat Studio.app`，内置 Python 运行时；`open` 或访达双击即可启动，无需安装依赖 |
| FR-02 | 发布完整性 | GitHub Release 必须附 `.app` 压缩包、中文说明、sha256 校验值；不发没有产物的 Release |
| FR-03 | 最新系统优先 | 目标 macOS 26+（实际验证于 macOS 27.0.1），不为 macOS 15/16 做降级适配 |
| FR-04 | 默认深色 | 应用强制 `NSAppearanceNameDarkAqua`，不跟随系统浅色外观 |
| FR-05 | 真实毛玻璃 | 使用 AppKit `NSVisualEffectView` + `blendingMode=behindWindow` 采样桌面；禁止用纯色/渐变伪造玻璃 |
| FR-06 | 技术栈可替换 | 允许更换 GUI 技术栈，但必须在 SystemDesign 中给出选型理由与替代方案对比 |

### 2.2 多群与数据层

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-07 | 统一库 | 全部群组存于一个 `.db`；`chats(chat_id)` 为主键，`messages.chat_id` 分区 |
| FR-08 | 复合索引 | 至少存在 `(chat_id, date_unixtime, row_id)`、`(chat_id, id)`、`(chat_id, sender_name)` 三个索引 |
| FR-09 | 群列表与切换 | 侧栏展示群名、消息数、最近消息日期；点击即切换，消息/统计/导入记录随群变化 |
| FR-10 | 群重命名 | 支持自定义显示名，不影响原始 `original_name`；空名称被拒绝 |
| FR-11 | 每群统计与导入记录 | 每个群可独立查询统计卡、7×24 热力图、每日趋势、导入历史 |
| FR-12 | 增量去重 | 唯一键 `chat_id:message_id`；重复导入新增 0 条 |
| FR-13 | 旧库迁移 | v1 / v2 数据库首次打开自动迁移到 Schema v3，非破坏性、可回退（迁移前自动快照） |

### 2.3 大数据量

| 编号 | 需求 | 验收标准（232,707 条虚构消息实测） |
|------|------|-----------------------------------|
| FR-14 | 导入内存 | 不得全量载入 JSON；峰值 RSS ≤ 100 MB（实测 35.6 MB） |
| FR-15 | 首屏渲染 | ≤ 200 ms（实测 84.6 ms） |
| FR-16 | 滚动流畅 | 平均 ≥ 55 FPS，P95 帧耗时 ≤ 20 ms（实测 60.0 FPS / 16.7 ms） |
| FR-17 | 避免全量载入 | 前端 JS 堆 ≤ 50 MB（实测 5.2 → 8.2 MB）；DOM 消息节点与总量无关（实测 14） |
| FR-18 | 分页与虚拟滚动 | 服务端分页 + 前端虚拟滚动；深分页（OFFSET 100000）API ≤ 50 ms（实测 27.4 ms） |
| FR-19 | 优化前后对比 | 必须以同一份 20 万+ 数据给出 V1.1.0 与 V1.2.0 的对比数字，不得外推 9,441 条结论 |

### 2.4 安全与数据保护

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-20 | 备份 | 支持手动快照，并每 6 小时自动快照（间隔可用 `TGCHAT_BACKUP_INTERVAL_SECONDS` 调整）；每次快照生成 `.manifest.json`（sha256 / 大小 / 群数 / 消息数 / schema 版本） |
| FR-21 | 恢复校验 | 恢复前必须通过 sha256 + `PRAGMA integrity_check` + 去重键校验；失败即中止 |
| FR-22 | 恢复二次确认 | 必须输入 `RESTORE <快照名>` 才执行；恢复前自动创建 `pre-restore` 快照 |
| FR-23 | 保留策略 | 默认保留最近 10 个；总大小上限 2 GB；超限从最旧清理 |
| FR-24 | 删除默认关闭 | 程序启动时 `app_settings.delete_enabled = 0`，删除按钮不可用 |
| FR-25 | 显式授权 | 输入确认短语 `ENABLE DELETE` 后才能删除；授权可随时撤销 |
| FR-26 | 可审计 | `audit_log` 表 + `logs/audit.jsonl` 双写；被拒绝的删除尝试也必须记录 |
| FR-27 | 全程日志 | `logs/app.log` 按 5 MB × 5 滚动；导入、备份、恢复、授权、删除均记录 |

### 2.5 隐私

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-28 | 纯本地 | API 仅监听 `127.0.0.1`；不上传任何数据 |
| FR-29 | 示例虚构 | 仓库内所有示例/截图/测试数据由 `scripts/generate_demo_data.py` 生成，不含真实聊天内容或身份信息 |
| FR-30 | 不入库 | `.gitignore` 覆盖 `*.db`、`result.json`、`chat_data.json`、`processed_data.json` |

### 2.6 文档

| 编号 | 需求 | 验收标准 |
|------|------|----------|
| FR-31 | 文档同步 | README、RequirementsSpec、SystemDesign、APISpec、TestPlan、CHANGELOG 全部更新为 v1.2.0，中文 |
| FR-32 | 证据可复现 | 性能数字附机器型号与测量脚本；截图归档到 `docs/screenshots/` |

## 3. 非目标

- 不写回 Telegram（不做消息编辑/撤回/发送）；
- 不做多用户、服务端部署、账号体系；
- 不做高级 NLP（词向量、情感分析）；
- 不做移动端 App；
- 不做 Apple 公证（需要付费开发者凭据，见「遗留项」）。

## 4. 性能要求与实测

机器：Mac17,8 / Apple M5 Pro / 64 GB / macOS 27.0.1。
数据：232,707 条虚构消息 / 103 MB JSON / 181 MB DB。

| 指标 | 要求 | v1.1.0 | v1.2.0 |
|------|------|--------|--------|
| 导入耗时 | ≤ 5 s | 4.04 s | 3.63 s |
| 导入峰值内存 | ≤ 100 MB | 1.21 GiB | 35.6 MB |
| 首屏渲染 | ≤ 200 ms | 372.6 ms | 84.6 ms |
| 平均帧率 | ≥ 55 FPS | 60.1 FPS | 60.0 FPS |
| P95 帧耗时 | ≤ 20 ms | 16.8 ms | 16.7 ms |
| JS 堆 | ≤ 50 MB | 197.0 MB | 8.2 MB |
| DOM 消息节点 | ≤ 60 | 14–22 | 14 |
| 深分页 API | ≤ 50 ms | 82.7 ms | 27.4 ms |

## 5. 兼容性与约束

- 桌面：macOS 26+ arm64（实测 macOS 27.0.1 / Apple M5 Pro）；Intel 与 Windows 不在本轮范围；
- 源码运行：Python 3.9+，桌面壳需要 PyObjC（`requirements.txt`）；
- 数据库：v1 → v3 自动迁移，不做破坏性变更；
- 浏览器调试：Chrome / Edge / Safari 最近两个大版本。

## 6. 验收清单

- [x] FR-01 ~ FR-32 全部实现；
- [x] `python3 -m pytest tests/ -q` 全绿（30 项）；
- [x] 232,707 条数据实测并给出优化前后对比；
- [x] 真实运行截图归档（含原生窗口毛玻璃）；
- [x] `.app` 打包、签名（ad-hoc）、sha256 校验值；
- [x] GitHub Release 附带产物与中文说明。
