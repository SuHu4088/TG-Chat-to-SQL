# TG 群聊记录查看器

一个基于纯前端（HTML + CSS + JavaScript）的 Telegram 群聊记录可视化查看器，无需后端服务，直接通过浏览器打开即可使用。

## ✨ 功能特性

- 🎨 **Telegram 风格界面** — 还原 Telegram 聊天界面的视觉设计
- 🌓 **深色模式** — 支持亮色/深色主题切换，自动记忆偏好
- 🔍 **全文搜索** — 支持按消息内容和用户名搜索，实时高亮
- 🏷️ **消息筛选** — 按消息类型筛选（全部/消息/系统/贴纸）
- 👥 **用户筛选** — 点击侧边栏用户可筛选特定用户的消息
- 💬 **回复跳转** — 点击回复消息可跳转到原消息位置
- ➡️ **转发标识** — 显示转发消息的来源
- 😀 **贴纸展示** — 独立展示贴纸消息及对应表情
- ❤️ **Reactions 表情** — 显示消息的表情回应
- ✏️ **编辑标记** — 显示被编辑过的消息
- 📊 **统计面板** — 实时显示消息数量、活跃用户、时间范围
- 📅 **日期分隔** — 自动按日期分组显示消息
- 🎨 **彩色头像** — 根据用户 ID 自动分配颜色，相同用户颜色一致
- 🚀 **分页 + 虚拟滚动** — 每页 200/500/1000/2000 条，任意滚动位置只渲染可视窗口；9,441 条消息时 DOM 仅约 15 个消息节点
- 🔒 **回复 O(1) 查询** — `messageById` Map 索引，替代全表 `find`

## 📁 文件结构

```
chat_viewer/
├── index.html          # 页面主结构
├── style.css           # 样式表（含深色模式变量）
├── app.js              # 核心逻辑
├── chat_data.json      # 复制的 JSON 聊天数据
├── README.md           # 本文档
└── DEV_GUIDE.md        # 开发规范文档
```

## 🚀 快速开始

### 方式一：直接打开

直接双击 `index.html` 文件用浏览器打开即可。

> ⚠️ 注意：部分浏览器（如 Chrome）由于 CORS 限制，直接打开本地文件时可能无法通过 `fetch` 加载 JSON 文件。如果遇到此问题，请使用方式二。

### 方式二：本地服务器

在 `chat_viewer/` 目录下启动一个简单的 HTTP 服务器：

```bash
# Python 3
python -m http.server 8080

# Node.js
npx serve .

# PHP
php -S localhost:8080
```

然后访问 `http://localhost:8080` 即可。

## 📝 使用说明

### 加载数据

1. 将 Telegram 导出的 JSON 文件重命名为 `chat_data.json` 放入 `chat_viewer/` 目录
2. 刷新页面即可自动加载

### 搜索消息

- 在搜索框输入关键词，支持消息内容和用户名搜索
- 搜索结果会高亮显示匹配的文本
- 按 `Enter` 确认搜索，按 `Escape` 清空搜索

### 筛选消息

- **全部** — 显示所有消息
- **消息** — 仅显示普通文本消息
- **系统** — 仅显示系统消息（创建群组、设置TTL等）
- **贴纸** — 仅显示贴纸消息

### 筛选用户

- 点击侧边栏用户列表中的用户名，筛选该用户的消息
- 再次点击取消筛选

### 回复跳转

- 点击带有引用内容的消息（左侧有蓝色竖线）
- 页面会自动跳转到原消息位置并高亮显示

### 主题切换

- 点击右上角太阳/月亮图标切换主题
- 主题偏好会自动保存到浏览器本地存储

## 📦 数据格式

本查看器支持 Telegram 导出的标准 JSON 格式：

```json
{
  "name": "群组名称",
  "type": "private_supergroup",
  "id": 4325779281,
  "messages": [
    {
      "id": 1,
      "type": "message",
      "date": "2026-07-21T22:32:03",
      "from": "用户名",
      "from_id": "user123456",
      "text": "消息内容",
      "text_entities": [...]
    }
  ]
}
```

### 支持的消息字段

| 字段 | 说明 |
|------|------|
| `id` | 消息唯一ID |
| `type` | 消息类型：`message` / `service` |
| `date` | ISO8601 日期时间 |
| `from` / `from_id` | 发送者昵称和ID |
| `actor` / `actor_id` | 操作者（服务消息） |
| `text` | 消息文本（字符串或数组） |
| `text_entities` | 文本实体列表 |
| `reply_to_message_id` | 回复目标消息ID |
| `forwarded_from` | 转发来源昵称 |
| `media_type` | 媒体类型（如 `sticker`） |
| `sticker_emoji` | 贴纸表情 |
| `reactions` | 表情回应列表 |
| `edited` | 编辑时间（如有） |

### 支持的文本实体类型

- `plain` — 纯文本
- `emoji` — 表情符号
- `bold` — 粗体
- `italic` — 斜体
- `code` — 代码
- `mention` — @提及
- `mention_name` — 可点击提及
- `link` — 链接
- `custom_emoji` — 自定义表情

### 支持的服务消息类型

- `create_channel` — 创建群组
- `set_messages_ttl` — 设置消息定时清除
- `set_photo` — 更换群头像
- `set_title` — 修改群组名称
- `invite_members` — 邀请成员
- `join_by_link` — 通过链接加入
- `leave_chat` — 离开群组

## 🛠️ 自定义配置

### 修改默认主题

在 `app.js` 的 `loadTheme()` 函数中修改默认值：

```javascript
function loadTheme() {
    const saved = localStorage.getItem('tg_viewer_theme');
    // 如果没有保存的偏好，默认使用深色模式
    if (!saved || saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
}
```

### 添加头像颜色

在 `app.js` 的 `AVATAR_COLORS` 数组中添加更多颜色：

```javascript
const AVATAR_COLORS = [
    '#e17076', '#7bcfa0', // ... 添加更多颜色
];
```

### 修改每页显示条数

目前采用全部渲染方式，如需分页可修改 `renderMessages()` 函数。

## 📱 浏览器兼容性

- Chrome / Edge 90+
- Firefox 88+
- Safari 14+

## 📄 许可

本项目仅供学习和研究使用。
