# 群聊热力图可视化 (Heatmap Visualization)

## 📖 项目简介

本模块将 Telegram 群聊导出的 JSON 数据，通过热力图可视化的方式展示群聊活跃度和话题分布。帮助用户直观了解：
- **一天内**每个时段的聊天活跃度
- **一周内**每天的聊天趋势
- 各时段的热门话题关键词
- 活跃用户排行榜

## 🗂️ 目录结构

```
heatmap_visualization/
├── README.md              # 本文件 - 使用说明
├── 开发文档.md            # 详细开发文档
├── 开发规范.md            # 开发规范与注意事项
├── result.json            # 复制的原始JSON数据（源文件副本）
├── data_processor.py      # 数据处理脚本（核心）
├── processed_data.json    # 处理后的数据（运行后生成）
├── index.html             # 热力图可视化页面
└── run.py                 # 本地服务器启动脚本
```

## 🚀 快速开始

### 1. 数据处理

```bash
cd heatmap_visualization
python data_processor.py
```

运行后将从 `result.json` 读取数据，生成 `processed_data.json`。

### 2. 启动可视化服务

```bash
python run.py
```

浏览器将自动打开 `http://localhost:8090`。

或直接双击 `index.html` 在浏览器中打开（部分浏览器可能因跨域限制无法加载 JSON，建议使用服务器方式）。

## ✨ 功能特性

### 活跃度热力图
- 展示 7天 × 24小时 的消息分布
- 颜色深浅表示消息数量
- 鼠标悬停可查看具体时段消息数和热门话题

### 话题热力图
- 按凌晨/上午/下午/晚上四个时段统计热门关键词
- 直观了解不同时间段的聊天主题

### 每日趋势
- 展示每天的消息总量
- 显示每日高峰时段

### 用户排行
- 按消息数量排序
- 前3名特殊标记

## 🛠️ 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 数据处理 | Python 3.x | 解析JSON、分词、统计 |
| 可视化 | ECharts 5.x | 热力图、柱状图、折线图 |
| 前端 | HTML5 + CSS3 | 响应式布局、暗色主题 |
| 服务 | Python http.server | 本地静态服务 |

## 📊 数据格式

### 输入数据 (result.json)
Telegram 导出的标准 JSON 格式：
```json
{
  "name": "群组名称",
  "type": "private_supergroup",
  "id": 4325779281,
  "messages": [...]
}
```

### 输出数据 (processed_data.json)
```json
{
  "meta": {
    "chat_name": "群组名称",
    "total_messages": 21956,
    "generated_at": "2026-07-28T..."
  },
  "activity_heatmap": { "0_0": 15, "0_1": 8, ... },
  "topic_heatmap": { "0_0": [["关键词", 5], ...], ... },
  "daily_summary": { "2026-07-21": { "count": 1234, ... }, ... },
  "top_users": [["用户名", 2484], ...],
  "time_period_stats": { "凌晨 (0-6点)": { "message_count": 4099, ... }, ... }
}
```

## ⚙️ 自定义配置

### 修改端口
编辑 `run.py` 中的 `PORT` 变量：
```python
PORT = 9090  # 改为你想要的端口
```

### 调整分词停用词
编辑 `data_processor.py` 中的 `STOP_WORDS` 集合，添加需要过滤的词汇。

### 修改显示的用户数量
编辑 `data_processor.py` 中 `build_top_users(messages, top_n=20)` 的 `top_n` 参数。

## ❓ 常见问题

**Q: 为什么直接打开 index.html 看不到数据？**
A: 现代浏览器对本地文件的 fetch 请求有跨域限制。请使用 `python run.py` 启动本地服务器。

**Q: 如何使用新的聊天数据？**
A: 将新导出的 `result.json` 替换本文件夹中的同名文件，然后重新运行 `data_processor.py`。

**Q: 分词结果不准确怎么办？**
A: 本项目使用简单的字符分割方式进行分词。如需更精确的中文分词，可扩展 `data_processor.py` 使用 jieba 等库。

## 📝 更新日志

### v1.0.0 (2026-07-28)
- 初始版本
- 支持活跃度热力图
- 支持话题关键词统计
- 支持每日趋势分析
- 支持用户排行榜

## 📄 相关文档

- [详细开发文档](开发文档.md)
- [开发规范与注意事项](开发规范.md)
