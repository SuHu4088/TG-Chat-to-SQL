/* TG Chat Studio — V1.2.0
 * 多群切换 / 服务端分页 + 虚拟滚动 / 热力图 / 备份恢复 / 删除权限审计
 */
(function () {
  'use strict';

  const state = {
    chats: [],
    currentChatId: null,
    view: 'messages',
    page: 1,
    pageSize: 500,
    total: 0,
    messages: [],
    units: [],
    heights: [],
    prefix: [0],
    renderedStart: -1,
    renderedEnd: -1,
    dataDir: '',
    deleteEnabled: false,
    searchQuery: '',
    heatmap: null,
    heatRange: { start: '', end: '' },
    charts: {},
    jobs: {},
    isLoading: false,
  };

  const el = (id) => document.getElementById(id);
  const canvas = el('chatCanvas');
  const spacer = el('chatSpacer');
  const win = el('chatWindow');
  const emptyMsg = el('emptyMessages');

  const SERVICE_LABELS = {
    join_by_link: '通过邀请链接加入群组',
    join_by_request: '通过入群申请加入',
    invite_members: '邀请了新成员',
    set_title: '修改群名为',
    leave_chat: '离开了群组',
    remove_members: '移除了成员',
    pin_message: '置顶了一条消息',
    migrate_to_supergroup: '群组升级为超级群',
    create_group: '创建了群组',
    create_channel: '创建了频道',
  };

  // ------------------------------------------------------------------
  // 工具
  // ------------------------------------------------------------------
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function fmtNumber(n) {
    if (n == null) return '—';
    if (n >= 100000000) return (n / 100000000).toFixed(1) + ' 亿';
    if (n >= 10000) return (n / 10000).toFixed(1) + ' 万';
    return String(n);
  }

  function fmtBytes(n) {
    if (!n) return '—';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let v = n;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return v.toFixed(v >= 10 || i === 0 ? 0 : 1) + ' ' + units[i];
  }

  function fmtDate(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  function toast(message, isError) {
    const node = el('toast');
    node.textContent = message;
    node.className = 'toast' + (isError ? ' error' : '');
    clearTimeout(node._timer);
    node._timer = setTimeout(() => node.classList.add('hidden'), 3200);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    let payload = {};
    try { payload = await response.json(); } catch (e) { payload = {}; }
    if (!response.ok) throw new Error(payload.error || ('请求失败 ' + response.status));
    return payload;
  }

  function openModal(title, text, opts) {
    return new Promise((resolve) => {
      const modal = el('modal');
      el('modalTitle').textContent = title;
      el('modalText').textContent = text;
      const input = el('modalInput');
      const config = opts || {};
      input.classList.toggle('hidden', !config.input);
      input.value = '';
      input.placeholder = config.placeholder || '';
      el('modalConfirm').textContent = config.confirmText || '确认';
      modal.classList.remove('hidden');
      if (config.input) input.focus();

      function cleanup(result) {
        modal.classList.add('hidden');
        el('modalConfirm').onclick = null;
        el('modalCancel').onclick = null;
        input.onkeydown = null;
        resolve(result);
      }
      el('modalConfirm').onclick = () => cleanup(config.input ? input.value : true);
      el('modalCancel').onclick = () => cleanup(null);
      input.onkeydown = (event) => {
        if (event.key === 'Enter') cleanup(input.value);
        if (event.key === 'Escape') cleanup(null);
      };
    });
  }

  // ------------------------------------------------------------------
  // 群列表
  // ------------------------------------------------------------------
  async function loadChats(selectFirst) {
    const data = await api('/api/chats');
    state.chats = data.chats || [];
    renderChats();
    if ((!state.currentChatId || selectFirst) && state.chats.length) {
      selectChat(state.chats[0].chat_id);
    } else if (!state.chats.length) {
      renderEmptyChat();
    }
  }

  function renderChats() {
    const list = el('chatList');
    const query = (el('chatSearch').value || '').trim().toLowerCase();
    el('chatCount').textContent = String(state.chats.length);
    const filtered = state.chats.filter((chat) =>
      !query || chat.title.toLowerCase().includes(query)
    );
    if (!filtered.length) {
      list.innerHTML = '<div class="db-status" style="padding:18px 4px">没有匹配的群组</div>';
      return;
    }
    list.innerHTML = filtered.map((chat) => {
      const initials = (chat.title || '?').slice(0, 1);
      const sub = `${fmtNumber(chat.message_count)} 条 · ${chat.first_ts ? fmtDate(chat.first_ts) : '无数据'}`;
      return `
        <div class="chat-item ${chat.chat_id === state.currentChatId ? 'active' : ''}" data-chat="${escapeHtml(chat.chat_id)}">
          <div class="chat-avatar">${escapeHtml(initials)}</div>
          <div class="chat-meta">
            <div class="name">${escapeHtml(chat.title)}</div>
            <div class="sub">${sub}</div>
          </div>
        </div>`;
    }).join('');
    list.querySelectorAll('.chat-item').forEach((node) => {
      node.addEventListener('click', () => selectChat(node.dataset.chat));
    });
  }

  function currentChat() {
    return state.chats.find((chat) => chat.chat_id === state.currentChatId) || null;
  }

  function selectChat(chatId) {
    if (state.currentChatId === chatId) return;
    state.currentChatId = chatId;
    state.page = 1;
    state.searchQuery = '';
    el('messageSearch').value = '';
    el('btnDeleteChat').disabled = false;
    renderChats();
    renderChatHeader();
    if (state.view === 'messages') loadMessages();
    if (state.view === 'heatmap') loadHeatmap();
    if (state.view === 'imports') loadImports();
  }

  function renderChatHeader() {
    const chat = currentChat();
    if (!chat) return;
    el('chatTitle').textContent = chat.title;
    const range = chat.first_ts && chat.last_ts
      ? `${fmtDate(chat.first_ts)} ~ ${fmtDate(chat.last_ts)}`
      : '暂无消息';
    el('chatSubtitle').textContent = `${fmtNumber(chat.message_count)} 条消息 · ${range} · 导入 ${chat.import_count} 次`;
    el('btnDeleteChat').title = state.deleteEnabled ? '删除群组' : '删除权限默认关闭';
  }

  function renderEmptyChat() {
    el('chatTitle').textContent = '还没有群组';
    el('chatSubtitle').textContent = '点击左下角「导入 JSON」开始';
    spacer.style.height = '100%';
    win.innerHTML = '';
    emptyMsg.textContent = '导入 Telegram 导出的 JSON 后，这里会显示聊天记录';
    emptyMsg.classList.remove('hidden');
  }

  // ------------------------------------------------------------------
  // 聊天记录：分页 + 虚拟滚动
  // ------------------------------------------------------------------
  async function loadMessages() {
    if (!state.currentChatId) return renderEmptyChat();
    state.isLoading = true;
    try {
      const offset = (state.page - 1) * state.pageSize;
      const data = await api(`/api/messages?chat_id=${encodeURIComponent(state.currentChatId)}&offset=${offset}&limit=${state.pageSize}`);
      state.messages = data.items || [];
      state.total = data.total || 0;
      buildUnits();
      canvas.scrollTop = 0;
      state.renderedStart = -1;
      state.renderedEnd = -1;
      updatePager();
      renderWindow(true);
      emptyMsg.classList.toggle('hidden', state.messages.length > 0);
    } catch (error) {
      toast(error.message, true);
    } finally {
      state.isLoading = false;
    }
  }

  function estimateHeight(unit) {
    if (unit.type === 'date') return 42;
    const msg = unit.msg;
    if (!msg) return 60;
    if (msg.type === 'service') return 34;
    if (msg.media_type === 'sticker') return 96;
    let height = 64;
    if (msg.reply_to_message_id) height += 30;
    if (msg.forwarded_from) height += 20;
    const text = msg.text || '';
    const lines = Math.ceil(text.length / 54);
    height += Math.max(0, lines - 1) * 20;
    if (msg.raw && msg.raw.reactions) height += 26;
    return Math.min(height, 480);
  }

  function buildUnits() {
    const units = [];
    let lastDate = '';
    state.messages.forEach((msg) => {
      const day = (msg.date || '').slice(0, 10);
      if (day && day !== lastDate) {
        units.push({ type: 'date', label: day });
        lastDate = day;
      }
      units.push({ type: 'message', msg });
    });
    units.forEach((unit) => { unit.est = estimateHeight(unit); });
    state.units = units;
    state.heights = units.map((unit) => unit.est);
    rebuildPrefix();
    spacer.style.height = Math.max(state.prefix[state.prefix.length - 1], 1) + 'px';
  }

  function rebuildPrefix() {
    state.prefix = [0];
    for (let i = 0; i < state.heights.length; i += 1) {
      state.prefix.push(state.prefix[i] + state.heights[i]);
    }
  }

  function findIndexAtOffset(offset) {
    const prefix = state.prefix;
    let low = 0;
    let high = prefix.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (prefix[mid] <= offset) low = mid + 1;
      else high = mid;
    }
    return Math.max(0, Math.min(low - 1, state.units.length - 1));
  }

  function renderMessage(unit) {
    if (unit.type === 'date') {
      return `<div class="date-sep">${escapeHtml(unit.label)}</div>`;
    }
    const msg = unit.msg;
    if (!msg) return '';
    if (msg.type === 'service') {
      const raw = msg.raw || {};
      const actor = raw.actor || msg.sender_name || '';
      const label = SERVICE_LABELS[raw.action] || msg.text || '服务消息';
      const detail = raw.title ? `「${raw.title}」` : '';
      return `<div class="service-msg">${escapeHtml(actor)} ${escapeHtml(label)}${escapeHtml(detail)}</div>`;
    }

    let body = '';
    if (msg.forwarded_from) {
      body += `<div class="fwd">转发自 ${escapeHtml(msg.forwarded_from)}</div>`;
    }
    if (msg.reply_to_message_id && msg.reply_text) {
      const who = msg.reply_sender ? escapeHtml(msg.reply_sender) : '原消息';
      body += `<div class="reply-quote">${who}：${escapeHtml((msg.reply_text || '').slice(0, 120))}</div>`;
    }
    if (msg.media_type === 'sticker') {
      const emoji = (msg.raw && msg.raw.sticker_emoji) || '🙂';
      body += `<div class="sticker">${escapeHtml(emoji)}</div>`;
    } else {
      body += `<div>${escapeHtml(msg.text || '')}</div>`;
    }
    if (msg.raw && msg.raw.reactions) {
      const chips = msg.raw.reactions.map((reaction) => {
        const count = reaction.count != null ? reaction.count : '';
        return `<span style="margin-right:6px">${escapeHtml(reaction.emoji || '·')} ${count}</span>`;
      }).join('');
      body += `<div class="msg-meta">${chips}</div>`;
    }

    const meta = msg.raw && msg.raw.edited ? '已编辑 · ' : '';
    const time = fmtTime(msg.date);
    return `
      <div class="msg-row">
        <div class="msg-top"><span class="who">${escapeHtml(msg.sender_name || '未知用户')}</span><span>${meta}${time}</span></div>
        <div class="bubble">${body}</div>
      </div>`;
  }

  function renderWindow(force) {
    if (!state.units.length) {
      win.innerHTML = '';
      spacer.style.height = '100%';
      return;
    }
    const scrollTop = canvas.scrollTop;
    const viewport = canvas.clientHeight || 600;
    const start = findIndexAtOffset(Math.max(0, scrollTop - 500));
    const end = Math.min(
      state.units.length,
      findIndexAtOffset(scrollTop + viewport + 500) + 2
    );
    if (!force && start === state.renderedStart && end === state.renderedEnd) return;
    state.renderedStart = start;
    state.renderedEnd = end;

    win.style.transform = `translateY(${state.prefix[start]}px)`;
    win.innerHTML = state.units.slice(start, end).map((unit, offset) =>
      `<div class="virtual-item" data-index="${start + offset}">${renderMessage(unit)}</div>`
    ).join('');

    requestAnimationFrame(() => measureWindow(start));
  }

  function measureWindow(start) {
    const nodes = win.querySelectorAll('.virtual-item');
    if (!nodes.length) return;
    const anchorBefore = state.prefix[start];
    let changed = false;
    nodes.forEach((node, offset) => {
      const index = start + offset;
      const measured = Math.ceil(node.getBoundingClientRect().height);
      if (measured > 0 && Math.abs(measured - state.heights[index]) > 1) {
        state.heights[index] = measured;
        changed = true;
      }
    });
    if (changed) {
      rebuildPrefix();
      spacer.style.height = Math.max(state.prefix[state.prefix.length - 1], 1) + 'px';
      // 动态高度变化时保持可视锚点，避免滚动跳动
      canvas.scrollTop += state.prefix[start] - anchorBefore;
    }
  }

  function updatePager() {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    state.page = Math.min(Math.max(1, state.page), totalPages);
    el('pageInfo').textContent = `${state.page} / ${totalPages}`;
    el('prevPage').disabled = state.page <= 1;
    el('nextPage').disabled = state.page >= totalPages;
  }

  function goToPage(page) {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    const target = Math.min(Math.max(1, page), totalPages);
    if (target === state.page) return;
    state.page = target;
    loadMessages();
  }

  async function searchMessages(query) {
    if (!state.currentChatId) return;
    state.searchQuery = query.trim();
    if (!state.searchQuery) {
      loadMessages();
      return;
    }
    try {
      const data = await api(`/api/search?chat_id=${encodeURIComponent(state.currentChatId)}&q=${encodeURIComponent(state.searchQuery)}&limit=200`);
      state.messages = data.items || [];
      state.total = data.total || 0;
      state.units = [];
      state.heights = [];
      const units = [];
      (data.items || []).forEach((msg) => {
        units.push({ type: 'message', msg, est: estimateHeight({ type: 'message', msg }) });
      });
      units.forEach((unit) => { unit.est = estimateHeight(unit); });
      state.units = units;
      state.heights = units.map((unit) => unit.est);
      rebuildPrefix();
      spacer.style.height = Math.max(state.prefix[state.prefix.length - 1], 1) + 'px';
      canvas.scrollTop = 0;
      state.renderedStart = -1;
      state.renderedEnd = -1;
      el('pageInfo').textContent = `${data.total} 条匹配`;
      el('prevPage').disabled = true;
      el('nextPage').disabled = true;
      renderWindow(true);
      emptyMsg.classList.toggle('hidden', (data.items || []).length > 0);
    } catch (error) {
      toast(error.message, true);
    }
  }

  // ------------------------------------------------------------------
  // 热力图
  // ------------------------------------------------------------------
  async function loadHeatmap(range) {
    if (!state.currentChatId) return;
    const params = [];
    if (range && range.start) params.push('start=' + encodeURIComponent(range.start));
    if (range && range.end) params.push('end=' + encodeURIComponent(range.end));
    const data = await api(`/api/chats/${encodeURIComponent(state.currentChatId)}/heatmap${params.length ? '?' + params.join('&') : ''}`);
    state.heatmap = data;
    state.heatRange = range || { start: '', end: '' };
    renderHeatStats(data);
    renderActivityChart(data);
    renderDailyChart(data);
    renderUsers(data);
  }

  async function refreshHeatRange(range) {
    if (!state.currentChatId) return;
    const params = [];
    if (range.start) params.push('start=' + encodeURIComponent(range.start));
    if (range.end) params.push('end=' + encodeURIComponent(range.end));
    const data = await api(`/api/chats/${encodeURIComponent(state.currentChatId)}/heatmap?${params.join('&')}`);
    renderHeatStats(data);
    renderActivityChart(data);
    renderUsers(data);
  }

  function renderHeatStats(data) {
    const daily = data.daily || [];
    const messages = daily.reduce((sum, item) => sum + item.count, 0);
    const days = daily.length;
    const avg = days ? Math.round(messages / days) : 0;
    const users = (data.stats && data.stats.unique_senders) || 0;
    el('heatStats').innerHTML = `
      <div class="stat-card"><div class="label">区间消息</div><div class="value">${fmtNumber(messages)}</div></div>
      <div class="stat-card"><div class="label">统计天数</div><div class="value">${days}</div></div>
      <div class="stat-card"><div class="label">日均消息</div><div class="value mint">${fmtNumber(avg)}</div></div>
      <div class="stat-card"><div class="label">参与用户</div><div class="value">${users}</div></div>`;
  }

  function renderActivityChart(data) {
    if (!state.charts.activity) state.charts.activity = echarts.init(el('activityChart'), null, { renderer: 'canvas' });
    const hours = Array.from({ length: 24 }, (_, i) => String(i));
    const weeks = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    const points = Array.from({ length: 7 }, (_, week) =>
      Array.from({ length: 24 }, (_, hour) => [hour, week, (data.activity || {})[`${week}_${hour}`] || 0])
    ).flat();
    evenColors(state.charts.activity, points);
    state.charts.activity.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        backgroundColor: 'rgba(24,24,31,0.95)', borderColor: 'rgba(255,255,255,0.12)',
        textStyle: { color: '#f5f5f7', fontSize: 12 },
        formatter: (p) => `${weeks[p.value[1]]} ${hours[p.value[0]]}:00 · ${p.value[2]} 条`,
      },
      grid: { left: 46, right: 18, top: 14, bottom: 28 },
      xAxis: { type: 'category', data: hours, axisLabel: { color: 'rgba(235,235,245,0.5)', fontSize: 10 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false }, splitArea: { show: false } },
      yAxis: { type: 'category', data: weeks, axisLabel: { color: 'rgba(235,235,245,0.6)', fontSize: 11 }, axisLine: { show: false }, axisTick: { show: false }, splitArea: { show: false } },
      visualMap: { show: false, min: 0, max: Math.max(1, ...points.map((p) => p[2])), inRange: { color: ['rgba(124,156,255,0.10)', 'rgba(124,156,255,0.45)', 'rgba(124,156,255,0.95)', 'rgba(99,226,183,0.95)'] } },
      series: [{ type: 'heatmap', data: points, itemStyle: { borderWidth: 2, borderColor: 'rgba(24,24,31,0.55)', borderRadius: 4 }, emphasis: { itemStyle: { borderColor: 'rgba(255,255,255,0.5)' } } }],
    });
  }

  function evenColors(chart, points) {
    // 动态标题不需要单独处理
    return points;
  }

  function renderDailyChart(data) {
    if (!state.charts.daily) state.charts.daily = echarts.init(el('dailyChart'), null, { renderer: 'canvas' });
    const daily = data.daily || [];
    const dates = daily.map((d) => d.date);
    const counts = daily.map((d) => d.count);
    state.charts.daily.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(24,24,31,0.95)', borderColor: 'rgba(255,255,255,0.12)', textStyle: { color: '#f5f5f7', fontSize: 12 } },
      grid: { left: 48, right: 18, top: 18, bottom: 64 },
      xAxis: { type: 'category', data: dates, axisLabel: { color: 'rgba(235,235,245,0.45)', fontSize: 10, interval: Math.max(0, Math.ceil(dates.length / 10) - 1) }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }, axisTick: { show: false } },
      yAxis: { type: 'value', axisLabel: { color: 'rgba(235,235,245,0.45)', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', xAxisIndex: 0, height: 16, bottom: 12, filterMode: 'none', borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.04)', fillerColor: 'rgba(124,156,255,0.18)', handleStyle: { color: '#7c9cff' }, textStyle: { color: 'rgba(235,235,245,0.4)', fontSize: 9 } },
      ],
      series: [{
        type: 'line', data: counts, smooth: true, symbol: 'none',
        lineStyle: { width: 2, color: '#7c9cff' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(124,156,255,0.32)' }, { offset: 1, color: 'rgba(124,156,255,0.02)' }]) },
      }],
    }, true);

    state.charts.daily.off('datazoom');
    state.charts.daily.on('datazoom', debounce(() => {
      const dates = (data.daily || []).map((d) => d.date);
      if (!dates.length) return;
      const option = state.charts.daily.getOption();
      const zoom = option.dataZoom && option.dataZoom[0];
      if (!zoom) return;
      const startIndex = Math.floor((zoom.start || 0) / 100 * (dates.length - 1));
      const endIndex = Math.ceil((zoom.end == null ? 100 : zoom.end) / 100 * (dates.length - 1));
      const range = { start: dates[startIndex], end: dates[endIndex] };
      refreshHeatRange(range);
    }, 220));
  }

  function renderUsers(data) {
    const users = data.top_users || [];
    if (!users.length) {
      el('userList').innerHTML = '<div class="hint">暂无数据</div>';
      return;
    }
    el('userList').innerHTML = users.map((user, index) => `
      <div class="user-row">
        <span class="rank">${index + 1}</span>
        <span class="name">${escapeHtml(user.name)}</span>
        <span class="count">${fmtNumber(user.count)}</span>
      </div>`).join('');
  }

  // ------------------------------------------------------------------
  // 导入记录 / 备份 / 权限
  // ------------------------------------------------------------------
  async function loadImports() {
    const data = await api(`/api/imports?chat_id=${encodeURIComponent(state.currentChatId || '')}`);
    const items = data.items || [];
    const table = el('importTable');
    if (!items.length) {
      table.innerHTML = '<tr><td class="hint">还没有导入记录</td></tr>';
      return;
    }
    table.innerHTML = `
      <thead><tr><th>时间</th><th>文件</th><th>总数</th><th>新增</th><th>跳过</th><th>耗时</th><th>状态</th></tr></thead>
      <tbody>${items.map((item) => `
        <tr>
          <td class="mono">${escapeHtml(item.import_time || '')}</td>
          <td>${escapeHtml(item.json_file || '')}</td>
          <td class="mono">${fmtNumber(item.total_messages)}</td>
          <td class="mono">${fmtNumber(item.imported_count)}</td>
          <td class="mono">${fmtNumber(item.skipped_count)}</td>
          <td class="mono">${item.duration_ms != null ? (item.duration_ms / 1000).toFixed(2) + ' s' : '—'}</td>
          <td>${item.status === 'success' ? '<span class="badge on">成功</span>' : '<span class="badge">失败</span>'}</td>
        </tr>`).join('')}</tbody>`;
  }

  async function loadBackups() {
    const data = await api('/api/backups');
    const items = data.items || [];
    const table = el('backupTable');
    if (!items.length) {
      table.innerHTML = '<tr><td class="hint">还没有快照</td></tr>';
      return;
    }
    table.innerHTML = `
      <thead><tr><th>创建时间</th><th>类型</th><th>消息</th><th>大小</th><th>操作</th></tr></thead>
      <tbody>${items.map((item) => `
        <tr>
          <td class="mono">${escapeHtml(item.created_at || '')}</td>
          <td>${escapeHtml(item.label || '')}</td>
          <td class="mono">${fmtNumber(item.messages)}</td>
          <td class="mono">${fmtBytes(item.size_bytes)}</td>
          <td>
            <button class="mini-btn" data-verify="${escapeHtml(item.name)}">校验</button>
            <button class="mini-btn danger" data-restore="${escapeHtml(item.name)}">恢复</button>
          </td>
        </tr>`).join('')}</tbody>`;
    table.querySelectorAll('[data-verify]').forEach((button) => {
      button.addEventListener('click', async () => {
        const result = await api('/api/backups/verify', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: button.dataset.verify }),
        });
        toast(result.ok ? `校验通过 · ${result.messages} 条消息` : `校验失败：${result.errors.join('；')}`, !result.ok);
      });
    });
    table.querySelectorAll('[data-restore]').forEach((button) => {
      button.addEventListener('click', () => restoreSnapshot(button.dataset.restore));
    });
  }

  async function restoreSnapshot(name) {
    const confirm = await openModal(
      '恢复数据库快照',
      `将把当前数据库替换为 ${name}。恢复前会自动保存当前库的 pre-restore 快照，且必须先通过完整性校验。`,
      { input: true, placeholder: `输入 RESTORE ${name}`, confirmText: '恢复' }
    );
    if (confirm == null) return;
    try {
      const result = await api('/api/backups/restore', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, confirm }),
      });
      toast(`已恢复 ${result.result.restored}，回退快照：${result.result.pre_restore_snapshot}`);
      await loadChats(true);
      await refreshStatus();
      if (state.view === 'backups') loadBackups();
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function loadSecurity() {
    const [security, audit] = await Promise.all([
      api('/api/security'),
      api('/api/audit?limit=200'),
    ]);
    state.deleteEnabled = !!security.delete_enabled;
    const badge = el('deleteBadge');
    badge.textContent = state.deleteEnabled ? '已开启' : '已关闭';
    badge.className = 'badge' + (state.deleteEnabled ? ' on' : '');
    renderChatHeader();

    const table = el('auditTable');
    const items = audit.items || [];
    if (!items.length) {
      table.innerHTML = '<tr><td class="hint">暂无审计记录</td></tr>';
      return;
    }
    table.innerHTML = `
      <thead><tr><th>时间</th><th>动作</th><th>目标</th><th>结果</th><th>说明</th></tr></thead>
      <tbody>${items.map((item) => `
        <tr>
          <td class="mono">${escapeHtml(item.created_at || '')}</td>
          <td>${escapeHtml(item.action || '')}</td>
          <td>${escapeHtml(item.target || '')}</td>
          <td>${item.allowed ? '<span class="badge on">允许</span>' : '<span class="badge">拒绝</span>'}</td>
          <td>${escapeHtml(item.detail || '')}</td>
        </tr>`).join('')}</tbody>`;
  }

  async function refreshStatus() {
    try {
      const result = await api('/api/verify');
      el('dbStatus').textContent = result.ok
        ? `完整 · ${fmtNumber(result.total_messages)} 条 · Schema v${result.schema_version}`
        : `校验异常 · 重复键 ${result.duplicate_keys.length}`;
    } catch (error) {
      el('dbStatus').textContent = '校验失败';
    }
  }

  // ------------------------------------------------------------------
  // 导入
  // ------------------------------------------------------------------
  function pickJson() {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.tgchat) {
      window.webkit.messageHandlers.tgchat.postMessage({ action: 'pick_json' });
      return;
    }
    openModal('导入 Telegram JSON', '浏览器调试模式：请输入 result.json 的绝对路径。', {
      input: true, placeholder: '/Users/you/result.json', confirmText: '导入',
    }).then((path) => {
      if (path) startImport(path);
    });
  }

  async function startImport(path) {
    try {
      const data = await api('/api/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      toast('开始导入：' + path);
      pollJob(data.job_id);
    } catch (error) {
      toast(error.message, true);
    }
  }

  function pollJob(jobId) {
    const timer = setInterval(async () => {
      try {
        const job = await api('/api/jobs/' + jobId);
        el('dbStatus').textContent = job.message + (job.processed ? ` · ${fmtNumber(job.processed)} 条` : '');
        if (job.status === 'done') {
          clearInterval(timer);
          toast(job.message);
          await loadChats(false);
          if (job.result) {
            state.currentChatId = job.result.chat_id;
            renderChats();
            renderChatHeader();
            if (state.view === 'messages') loadMessages();
            if (state.view === 'imports') loadImports();
          }
          refreshStatus();
        } else if (job.status === 'failed') {
          clearInterval(timer);
          toast(job.error || '导入失败', true);
        }
      } catch (error) {
        clearInterval(timer);
        toast(error.message, true);
      }
    }, 700);
  }

  // ------------------------------------------------------------------
  // 交互绑定
  // ------------------------------------------------------------------
  function debounce(fn, wait) {
    let timer = null;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, wait);
    };
  }

  function bindEvents() {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => switchView(tab.dataset.view));
    });

    el('chatSearch').addEventListener('input', renderChats);
    canvas.addEventListener('scroll', () => requestAnimationFrame(() => renderWindow(false)));
    window.addEventListener('resize', () => {
      Object.values(state.charts).forEach((chart) => chart.resize());
      renderWindow(true);
    });

    el('pageSizeSelect').addEventListener('change', (event) => {
      state.pageSize = Number(event.target.value);
      state.page = 1;
      loadMessages();
    });
    el('prevPage').addEventListener('click', () => goToPage(state.page - 1));
    el('nextPage').addEventListener('click', () => goToPage(state.page + 1));

    el('messageSearch').addEventListener('input', debounce((event) => {
      searchMessages(event.target.value);
    }, 300));

    el('btnImport').addEventListener('click', pickJson);
    el('btnNewBackup').addEventListener('click', createBackup);
    el('btnCreateBackup').addEventListener('click', createBackup);

    el('btnRename').addEventListener('click', async () => {
      const chat = currentChat();
      if (!chat) return;
      const name = await openModal('重命名群组', '只修改显示名，不改变 chat_id，不影响去重键。', {
        input: true, placeholder: chat.title, confirmText: '保存',
      });
      if (!name) return;
      try {
        await api('/api/chats/rename', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chat.chat_id, name }),
        });
        toast('已重命名');
        await loadChats(false);
      } catch (error) { toast(error.message, true); }
    });

    el('btnDeleteChat').addEventListener('click', async () => {
      const chat = currentChat();
      if (!chat) return;
      if (!state.deleteEnabled) {
        toast('删除权限默认关闭，请先到「权限与审计」开启', true);
        return;
      }
      const confirm = await openModal(
        '删除群组',
        `将永久删除「${chat.title}」的 ${fmtNumber(chat.message_count)} 条消息与导入记录。此操作不可撤销。`,
        { input: true, placeholder: '输入 DELETE 以确认', confirmText: '删除' }
      );
      if (confirm == null) return;
      try {
        await api('/api/chats/delete', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chat.chat_id, confirm }),
        });
        toast('已删除');
        state.currentChatId = null;
        await loadChats(true);
        await refreshStatus();
        if (state.view === 'security') loadSecurity();
      } catch (error) { toast(error.message, true); }
    });

    el('btnGrantDelete').addEventListener('click', async () => {
      try {
        await api('/api/security/grant', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phrase: el('grantPhrase').value }),
        });
        el('grantPhrase').value = '';
        toast('删除权限已开启');
        await loadSecurity();
      } catch (error) { toast(error.message, true); }
    });

    el('btnRevokeDelete').addEventListener('click', async () => {
      try {
        await api('/api/security/revoke', { method: 'POST' });
        toast('删除权限已撤销');
        await loadSecurity();
      } catch (error) { toast(error.message, true); }
    });

    el('rangePills').querySelectorAll('button').forEach((button) => {
      button.addEventListener('click', () => {
        el('rangePills').querySelectorAll('button').forEach((node) => node.classList.remove('active'));
        button.classList.add('active');
        const days = Number(button.dataset.days);
        if (!days || !state.heatmap || !state.heatmap.daily.length) {
          loadHeatmap({ start: '', end: '' });
          return;
        }
        const dates = state.heatmap.daily.map((item) => item.date);
        const start = dates[Math.max(0, dates.length - days)];
        loadHeatmap({ start, end: dates[dates.length - 1] });
      });
    });
  }

  async function createBackup() {
    try {
      const manifest = await api('/api/backups', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'manual' }),
      });
      toast(`已创建快照 ${manifest.name}`);
      if (state.view === 'backups') loadBackups();
    } catch (error) { toast(error.message, true); }
  }

  function switchView(view) {
    state.view = view;
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.view === view);
    });
    document.querySelectorAll('.view').forEach((node) => node.classList.add('hidden'));
    const target = el('view-' + view);
    if (target) target.classList.remove('hidden');
    if (view === 'messages') loadMessages();
    if (view === 'heatmap') loadHeatmap(state.heatRange);
    if (view === 'imports') loadImports();
    if (view === 'backups') loadBackups();
    if (view === 'security') loadSecurity();
  }

  // ------------------------------------------------------------------
  // 原生桥：文件选择
  // ------------------------------------------------------------------
  window.__native = {
    pickedJson: function (paths) {
      const list = Array.isArray(paths) ? paths : [paths];
      list.filter(Boolean).forEach((path) => startImport(path));
    },
    unifiedLog: function () {},
  };

  window.__studio = {
    getState: () => ({
      chats: state.chats.length,
      currentChatId: state.currentChatId,
      view: state.view,
      page: state.page,
      pageSize: state.pageSize,
      total: state.total,
      renderedNodes: win.querySelectorAll('.virtual-item').length,
      deleteEnabled: state.deleteEnabled,
      units: state.units.length,
    }),
    selectChat,
    switchView,
    goToPage,
    loadMessages,
    loadHeatmap,
  };

  async function init() {
    bindEvents();
    try {
      const appState = await api('/api/state');
      state.dataDir = appState.data_dir;
      state.deleteEnabled = !!appState.delete_enabled;
      el('versionLabel').textContent = 'v' + appState.version;
    } catch (error) {
      toast(error.message, true);
    }
    await loadChats(true);
    refreshStatus();
    if (state.view === 'messages' && state.currentChatId) loadMessages();
  }

  init();
})();
