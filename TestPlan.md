# 测试计划（TestPlan）

- 项目：TG-Chat-to-SQL / TG Chat Studio
- 版本：v1.2.0
- 更新日期：2026-11-05
- 执行环境：Mac17,8 / Apple M5 Pro / 64 GB / macOS 27.0.1、Python 3.11.18（arm64 venv）、Chrome 稳定版、SQLite 3.x
- 数据集：`232,707` 条虚构消息（103 MB JSON / 181 MB DB）与 5 个群共 10,398 条虚构消息

## 1. 测试目标

验证 V1.2.0 的九项能力：多群统一库、20 万条性能、新 UI、`.app` 打包、深色毛玻璃、备份回滚、删除权限、审计日志、文档同步。

## 2. 测试范围

| 范围 | 覆盖 |
|------|------|
| 数据层 | Schema v3、复合索引、v1/v2 → v3 迁移、多群隔离、去重键 |
| 导入 | 流式解析、内存峰值、多群连续导入、重复导入 |
| 性能 | 首屏、FPS、JS 堆、DOM 节点、深分页 API |
| 桌面 | `.app` 启动、arm64 架构、深色外观、系统毛玻璃、文件选择桥 |
| 备份 | 快照、清单、校验、二次确认、pre-restore、保留策略 |
| 安全 | 默认关闭、授权短语、撤销、拒绝与放行的审计 |
| UI | 群列表/切换/重命名/删除、5 个 tab、空态、错误提示 |
| 文档 | 六份文档与 README 版本号一致、性能数字可复现 |

## 3. 自动化测试

### 3.1 运行

```bash
python3 -m pytest tests/ -q
# 或
python3 -m unittest discover -s tests -v
```

### 3.2 用例清单

| 编号 | 用例 | 预期 | 结果 |
|------|------|------|------|
| T-01 | 去重键按群隔离 | `100:1` 与 `200:1` 不冲突 | 通过 |
| T-02 | 跨群相同消息 ID | 两群各 1 条，内容互不覆盖 | 通过 |
| T-03 | 重复导入幂等 | 第二次新增 0 | 通过 |
| T-04 | 完整性校验 | `ok=true`，重复键 0 | 通过 |
| T-05 | 群列表计数 | 两群分别 3 / 0 条 | 通过 |
| T-06 | 群重命名 | `title` 更新，空名称抛 `ValueError` | 通过 |
| T-07 | 群删除 | 返回 `messages_deleted=1`，群列表为空 | 通过 |
| T-08 | 流式多群导入 | 40 + 25 条分别入库，chat_id 正确 | 通过 |
| T-09 | 生成器不整体载入 | `iter_messages` 逐条产出 30 条 | 通过 |
| T-10 | 重复导入跳过计数 | `imported=0, skipped=20` | 通过 |
| T-11 | 导入日志含耗时 | `status=success`，`duration_ms≥0` | 通过 |
| T-12 | 删除默认关闭 | `is_delete_enabled()==False` | 通过 |
| T-13 | 授权短语大小写敏感 | 小写被拒绝，`ENABLE DELETE` 通过 | 通过 |
| T-14 | 未授权删除被拦截 | 抛 `DeletePermissionError` | 通过 |
| T-15 | 授权后可删除 | `require_delete` 放行 | 通过 |
| T-16 | 撤销后重新拦截 | 撤销后再次抛错 | 通过 |
| T-17 | 拒绝尝试写审计 | `audit_log` 含 `allowed=0` 记录 | 通过 |
| T-18 | 审计 JSONL | `logs/audit.jsonl` 含 `delete.grant` | 通过 |
| T-19 | 快照清单 | `messages=20`、`schema_version=3`、sha256 64 位 | 通过 |
| T-20 | 校验能发现损坏 | 追加字节后 `ok=false`，错误含 sha256 | 通过 |
| T-21 | 恢复确认短语 | 短语不匹配抛 `PermissionError` | 通过 |
| T-22 | 恢复往返 | 删除后恢复回到 20 条，生成 pre-restore | 通过 |
| T-23 | 保留策略 | 连续 5 个快照后只留 3 个 | 通过 |
| T-24 | 缺失快照 | 抛 `FileNotFoundError` | 通过 |
| T-25 ~ T-30 | V1.1 兼容用例 | CSV / Parquet / 日期过滤 / v1→v3 迁移 | 通过 |

自动执行结果：`30 passed`。

## 4. 性能实测

脚本：`scripts/bench_studio.py`（Playwright + 系统 Chrome，1440×900）。命令：

```bash
python3 scripts/bench_studio.py --url http://127.0.0.1:8765 --json
```

| 指标 | v1.1.0 | v1.2.0 | 判定 |
|------|--------|--------|------|
| 导入耗时（232,707 条） | 4.04 s | 3.63 s | 通过 |
| 导入峰值 RSS | 1.21 GiB | 35.6 MB | 通过（≤100 MB） |
| 首屏渲染 | 372.6 ms | 84.6 / 105.3 ms（两次） | 通过（≤200 ms） |
| 平均帧率 | 60.1 FPS | 60.0 FPS | 通过（≥55） |
| P95 帧耗时 | 16.8 ms | 16.7 ms | 通过（≤20 ms） |
| JS 堆 | 197.0 MB | 5.2 → 8.2 MB | 通过（≤50 MB） |
| DOM 消息节点 | 14–22 | 14 | 通过（≤60） |
| 深分页 API（OFFSET 100000） | 82.7 ms | 27.4 ms | 通过（≤50 ms） |
| 重复导入（0 新增） | — | 1.77 s | 通过 |

深分页补充说明：`122.4 ms` 是界面端到端（含 Playwright 调用与渲染），仅 API 为 `27.4 ms`，两个数字都记录，避免混用。

## 5. 桌面端测试

| 编号 | 用例 | 步骤 | 结果 |
|------|------|------|------|
| D-01 | `.app` 可双击启动 | `open "dist/TG Chat Studio.app"` | 通过 |
| D-02 | arm64 架构 | `lipo -info` 入口可执行文件 | 通过（arm64） |
| D-03 | 内置运行时 | 不依赖系统 Python 启动 | 通过 |
| D-04 | 深色外观 | 系统设为浅色时仍为深色 | 通过 |
| D-05 | 真实毛玻璃 | 窗口后能透出桌面/其他应用内容 | 通过（NSVisualEffectView） |
| D-06 | 文件选择桥 | 原生面板选择 JSON 后触发导入 | 通过 |
| D-07 | 数据目录 | `~/Library/Application Support/TGChatToSQL` 生成库与日志 | 通过 |
| D-08 | 日志滚动 | `logs/app.log` 记录启动/导入/退出 | 通过 |

## 6. UI 验收

截图归档：`docs/screenshots/*-v1.2.0.png`。

| 页面 | 检查项 |
|------|--------|
| 聊天记录 | 多群列表、群切换、服务消息中文化、分页、虚拟滚动 |
| 热力图 | 7×24 全格显示（含 0 值）、每日趋势 X 轴标签、区间按钮 |
| 导入记录 | 按群过滤、耗时、新增/跳过、失败原因 |
| 备份与恢复 | 创建、列表、校验、恢复确认输入 |
| 权限与审计 | 默认关闭、授权、撤销、审计表 |

## 7. 已知限制与不测项

- 未做 Apple 公证，Gatekeeper 首次打开提示不在自动化范围；
- 未在 Intel Mac、macOS 15/16 上测试（按需求只面向最新系统）；
- 未做多进程并发写库测试；
- 恢复流程会替换数据库文件，测试中使用临时数据库，不对真实库执行破坏性恢复。

## 8. 回归清单

每次发版前执行：

```bash
python3 -m pytest tests/ -q
python3 scripts/bench_studio.py --url http://127.0.0.1:8765 --json
python3 scripts/shot_studio.py --url http://127.0.0.1:8765 --out /tmp/shots
python3 scripts/build_app.py
shasum -a 256 "dist/TG Chat Studio.app/Contents/MacOS/TG Chat Studio"
```
