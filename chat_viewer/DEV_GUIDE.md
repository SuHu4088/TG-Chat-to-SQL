# 开发规范与注意事项

## 📋 目录

- [技术栈](#技术栈)
- [代码规范](#代码规范)
- [文件职责](#文件职责)
- [数据流说明](#数据流说明)
- [消息处理逻辑](#消息处理逻辑)
- [性能优化](#性能优化)
- [安全注意事项](#安全注意事项)
- [扩展性设计](#扩展性设计)
- [测试要点](#测试要点)
- [常见问题](#常见问题)

---

## 技术栈

| 技术 | 版本要求 | 用途 |
|------|----------|------|
| HTML5 | - | 页面结构 |
| CSS3 | - | 样式与主题（CSS Variables） |
| JavaScript (ES6+) | - | 核心逻辑 |

**不依赖任何第三方库**，所有功能均使用原生 API 实现。

---

## 代码规范

### 命名规范

- **文件名**: 小写字母 + 下划线（`app.js`, `style.css`）
- **变量**: camelCase（`userColors`, `currentFilter`）
- **常量**: UPPER_SNAKE_CASE（`AVATAR_COLORS`）
- **函数**: camelCase，动词开头（`renderMessages()`, `loadData()`）
- **CSS 类**: kebab-case（`message-bubble`, `reply-container`）
- **ID**: kebab-case（`chat-messages`, `search-input`）
- **事件处理**: on/handle 前缀（`handleSearch`, `onMessageClick`）

### 代码风格

```javascript
// ✅ 正确
const renderMessages = () => { ... };
function getUserColor(userId) { ... }

// ❌ 错误
const RenderMessages = () => { ... };
function getUsercolor(userID) { ... }
```

### CSS 规范

- 使用 CSS 变量管理主题颜色，定义在 `:root` 和 `[data-theme="dark"]` 中
- 变量命名：`--` 前缀 + kebab-case（`--bg-primary`, `--text-secondary`）
- 响应式设计使用 `@media` 查询，关键断点：768px, 480px

```css
:root {
    --bg-primary: #ffffff;
    --text-secondary: #707579;
}

[data-theme="dark"] {
    --bg-primary: #212121;
    --text-secondary: #8a96a3;
}
```

### JavaScript 规范

- 使用 IIFE（立即执行函数）封装，避免全局污染
- 使用 `const` / `let`，禁止 `var`
- 使用模板字符串，禁止字符串拼接
- 使用严格相等 `===` / `!==`
- 函数单一职责，超过 30 行考虑拆分

---

## 文件职责

### index.html
- 页面结构定义
- 语义化标签使用
- 不包含业务逻辑

### style.css
- 所有样式定义
- 主题变量
- 响应式布局
- 不包含脚本代码

### app.js
- 数据加载与解析
- 消息渲染逻辑
- 事件处理
- 搜索与筛选
- 主题切换
- 不包含内联样式（除动态计算样式外）

### chat_data.json
- 数据源，只读
- 由 Telegram 导出工具生成
- 禁止手动修改

---

## 数据流说明

```
chat_data.json
      │
      ▼
   fetch()
      │
      ▼
   state.chatData ──► state.messages
      │                      │
      ▼                      ▼
  renderStats()        renderUserList()
      │                      │
      ▼                      ▼
  renderMessages() ◄── getFilteredMessages()
      │                      ▲
      ▼                      │
  DOM 渲染 ◄─── bindEvents() ─┘
```

### 状态管理

所有状态集中在 `state` 对象中：

```javascript
const state = {
    chatData: null,           // 原始数据
    messages: [],             // 消息列表
    currentFilter: 'all',     // 当前筛选类型
    currentUserFilter: null,  // 当前筛选的用户ID
    searchQuery: '',          // 搜索关键词
    replyMap: new Map(),      // 回复映射表
    userColors: new Map()     // 用户颜色缓存
};
```

---

## 消息处理逻辑

### 消息类型判断

```
消息对象
  │
  ├── type === 'service' ──► renderServiceMessage()
  │
  ├── media_type === 'sticker' ──► renderStickerMessage()
  │
  └── 其他 ──► renderTextMessage()
                    │
                    ├── 检查 reply_to_message_id
                    ├── 检查 forwarded_from
                    ├── 检查 reactions
                    ├── 检查 edited
                    └── 解析 text_entities
```

### 文本实体处理

`text_entities` 数组中每个元素处理规则：

| type | 渲染方式 |
|------|----------|
| `plain` | 直接输出文本 |
| `emoji` | 直接输出（原生 emoji 渲染） |
| `custom_emoji` | 直接输出 |
| `bold` | `<span class="bold">` |
| `italic` | `<span class="italic">` |
| `code` | `<span class="code">` |
| `mention` / `mention_name` | `<span class="mention">` |
| `link` | `<span class="link">` |

### 用户头像颜色分配

1. 对 `userId` 字符串进行哈希计算
2. 哈希值对颜色数组长度取模
3. 相同 `userId` 始终得到相同颜色
4. 结果缓存在 `state.userColors` 中

---

## 性能优化

### 当前优化策略

1. **颜色缓存**: 用户颜色计算结果缓存，避免重复哈希
2. **搜索防抖**: 300ms 延迟触发搜索，减少重渲染
3. **事件委托**: 列表项点击事件通过父元素委托处理
4. **CSS 过渡**: 使用 `transform` 和 `opacity` 触发动画，避免重排

### 大数据量注意事项

当消息数量超过 10,000 条时：

- 建议实现虚拟滚动（Virtual Scrolling）
- 考虑分页加载
- 使用 `DocumentFragment` 批量操作 DOM
- 图片懒加载

### 渲染性能

```javascript
// ✅ 使用 innerHTML 批量渲染（单次 DOM 操作）
container.innerHTML = html;

// ❌ 避免逐条 appendChild（多次 DOM 操作）
messages.forEach(msg => {
    container.appendChild(createMessageElement(msg));
});
```

---

## 安全注意事项

### XSS 防护

**所有用户输入内容必须经过 HTML 转义**：

```javascript
// ✅ 使用 escapeHtml() 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ❌ 严禁直接插入
element.innerHTML = userInput;
```

需要转义的字段：
- `from` / `actor` — 用户名
- `text` — 消息内容
- `text_entities[].text` — 实体文本
- `action` — 服务消息类型

### 数据验证

- 检查 JSON 文件是否存在
- 验证数据结构完整性
- 处理 null / undefined 值
- 验证日期格式有效性

---

## 扩展性设计

### 添加新的消息类型

1. 在 `renderMessage()` 中添加新的判断分支
2. 创建对应的 `renderXxxMessage()` 函数
3. 更新 `applyFilters()` 添加新的筛选选项
4. 更新 HTML 中的筛选按钮

### 添加新的主题

1. 在 CSS 中添加新的主题选择器
2. 定义对应的 CSS 变量
3. 在 `toggleTheme()` 中添加新主题选项

### 添加后端支持

如需将此项目改为后端渲染：

```
可选技术栈：
├── Node.js + Express
├── Python + Flask / FastAPI
├── Go + Gin
└── 纯静态 + CDN（当前方案）
```

建议后端方案：
- 保持 `app.js` 的 API 接口不变
- 将 `fetch('chat_data.json')` 改为调用后端 API
- 后端负责数据处理和分页

---

## 测试要点

### 功能测试

- [ ] JSON 文件加载正确
- [ ] 消息类型判断准确（普通/系统/贴纸）
- [ ] 文本实体渲染正确（粗体/斜体/代码/提及/链接）
- [ ] 回复跳转功能正常
- [ ] 搜索功能准确
- [ ] 筛选功能正常
- [ ] 主题切换生效

### 边界测试

- [ ] 空消息列表处理
- [ ] null / undefined 字段处理
- [ ] 超长文本显示
- [ ] 特殊字符（HTML、JS）转义
- [ ] 中文字符头像显示
- [ ] 超长时间跨度消息

### 兼容性测试

- [ ] Chrome 最新版
- [ ] Firefox 最新版
- [ ] Edge 最新版
- [ ] Safari 最新版
- [ ] 移动端浏览器

---

## 常见问题

### Q: 直接打开 HTML 文件时数据加载失败？

**原因**: 浏览器的 CORS 策略阻止了本地文件的 fetch 请求。

**解决方案**: 使用本地 HTTP 服务器，详见 [README.md](README.md) 快速开始章节。

### Q: 中文用户名头像显示异常？

**原因**: 不同字体对中文渲染支持不同。

**解决方案**: 修改 `getInitial()` 函数，或使用 SVG 生成头像。

### Q: 搜索无结果？

**可能原因**: 
1. 搜索关键词与消息内容不匹配
2. 数据未完全加载
3. 当前有筛选条件未清除

### Q: 回复跳转找不到目标消息？

**可能原因**:
1. 目标消息在当前筛选范围外
2. 目标消息 ID 不存在
3. 数据不完整

**解决方案**: 清除所有筛选条件后重试。

### Q: 深色模式切换后刷新页面失效？

**原因**: 主题偏好存储在 localStorage 中。

**解决方案**: 检查浏览器是否禁用了 localStorage。

---

## 目录结构总览

```
TG群聊转SQL/
├── result.json              # 原始 JSON 数据（禁止修改）
├── sql_converter/           # SQL 转换模块
└── chat_viewer/             # 本模块
    ├── index.html           # 页面结构
    ├── style.css            # 样式表
    ├── app.js               # 核心逻辑
    ├── chat_data.json       # 复制的数据文件
    ├── README.md            # 使用文档
    └── DEV_GUIDE.md         # 本文档
```
