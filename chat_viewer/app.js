(function () {
    'use strict';

    const AVATAR_COLORS = [
        '#e17076', '#7bcfa0', '#a29bfe', '#fd79a8', '#00b894',
        '#e67e22', '#3498db', '#9b59b6', '#f39c12', '#1abc9c',
        '#e74c3c', '#2ecc71', '#34495e', '#16a085', '#c0392b',
        '#d35400', '#2980b9', '#8e44ad', '#27ae60', '#f1c40f'
    ];

    const OVERSCAN_PX = 600;
    const MIN_ITEM_HEIGHT = 48;

    const state = {
        chatData: null,
        messages: [],
        messageById: new Map(),
        currentFilter: 'all',
        currentUserFilter: null,
        searchQuery: '',
        selectedMessageId: null,
        userColors: new Map(),

        filteredMessages: [],
        units: [],
        heights: [],
        prefix: [0],
        renderedStart: -1,
        renderedEnd: -1,
        totalHeight: 0,

        pageSize: 500,
        currentPage: 1,
        pendingAnchorIndex: null,
        isAdjustingScroll: false,
        resizeTimer: null
    };

    function init() {
        loadTheme();
        buildMessageIndex();
        bindEvents();
        loadData();
    }

    function loadTheme() {
        const saved = localStorage.getItem('tg_viewer_theme');
        if (saved === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        if (current === 'dark') {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('tg_viewer_theme', 'light');
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('tg_viewer_theme', 'dark');
        }
    }

    async function loadData() {
        try {
            const response = await fetch('chat_data.json');
            if (!response.ok) throw new Error('Failed to load data');
            state.chatData = await response.json();
            state.messages = state.chatData.messages || [];
            buildMessageIndex();
            renderStats();
            renderUserList();
            renderChatInfo();

            const container = document.getElementById('chatMessages');
            container.innerHTML = `
                <div class="virtual-canvas" id="virtualCanvas">
                    <div class="virtual-window" id="virtualWindow"></div>
                </div>
            `;
            applyFilters();
        } catch (error) {
            console.error('Error loading data:', error);
            showError('加载数据失败：' + error.message);
        }
    }

    function showError(msg) {
        const container = document.getElementById('chatMessages');
        container.innerHTML = `
            <div class="loading-state">
                <div style="font-size: 48px;">⚠️</div>
                <p style="color: var(--text-secondary); margin-top: 12px;">${msg}</p>
                <p style="color: var(--text-tertiary); font-size: 13px; margin-top: 8px;">请确保 chat_data.json 文件存在于同一目录</p>
            </div>
        `;
    }

    function buildMessageIndex() {
        state.messageById = new Map();
        state.messages.forEach(msg => state.messageById.set(msg.id, msg));
    }

    function getReplyText(messageId) {
        const replyMsg = state.messageById.get(messageId);
        if (!replyMsg) return null;
        return {
            sender: replyMsg.from || replyMsg.actor || '未知用户',
            text: getPlainText(replyMsg),
            type: replyMsg.type
        };
    }

    function getPlainText(msg) {
        if (!msg.text) return '';
        if (typeof msg.text === 'string') return msg.text;
        if (Array.isArray(msg.text)) {
            return msg.text.map(item => {
                if (typeof item === 'string') return item;
                return item.text || '';
            }).join('');
        }
        return '';
    }

    function getUserColor(userId) {
        if (state.userColors.has(userId)) {
            return state.userColors.get(userId);
        }
        let hash = 0;
        const key = String(userId || '');
        for (let i = 0; i < key.length; i++) {
            hash = key.charCodeAt(i) + ((hash << 5) - hash);
        }
        const color = AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
        state.userColors.set(userId, color);
        return color;
    }

    function getInitial(name) {
        if (!name) return '?';
        const trimmed = name.trim();
        if (!trimmed) return '?';
        if (/[\u4e00-\u9fff]/.test(trimmed.charAt(0))) {
            return trimmed.charAt(0);
        }
        const parts = trimmed.split(/\s+/);
        return parts[0].charAt(0).toUpperCase();
    }

    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now - date;
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        if (days === 0) return time;
        if (days === 1) return '昨天 ' + time;
        if (days < 7) return days + '天前';
        return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' ' + time;
    }

    function formatDateOnly(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long'
        });
    }

    function formatTime(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    function renderChatInfo() {
        const data = state.chatData;
        document.getElementById('groupName').textContent = data.name || '未知群组';
        document.getElementById('chatTitle').textContent = data.name || '聊天记录';
        document.getElementById('groupMeta').textContent = `${data.type || 'group'} · ${data.id || ''}`;

        document.getElementById('groupIconText').textContent = getInitial(data.name || '?');
        const iconColor = getUserColor('group_' + data.id);
        document.getElementById('groupIcon').style.background = `linear-gradient(135deg, ${iconColor}, ${adjustColor(iconColor, -30)})`;
    }

    function adjustColor(hex, amount) {
        const num = parseInt(hex.replace('#', ''), 16);
        const r = Math.min(255, Math.max(0, (num >> 16) + amount));
        const g = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amount));
        const b = Math.min(255, Math.max(0, (num & 0x0000FF) + amount));
        return '#' + (g | (b << 0) | (r << 16)).toString(16).padStart(6, '0');
    }

    function renderStats() {
        const msgs = state.messages;
        const total = msgs.length;
        const messages = msgs.filter(m => m.type === 'message').length;
        const services = msgs.filter(m => m.type === 'service').length;

        const users = new Set();
        msgs.forEach(m => {
            const id = getUserId(m);
            if (id !== 'unknown') users.add(id);
        });

        let dateRange = '-';
        if (msgs.length > 0) {
            const first = msgs[0].date;
            const last = msgs[msgs.length - 1].date;
            dateRange = `${String(first).slice(0, 10)} ~ ${String(last).slice(0, 10)}`;
        }

        document.getElementById('statTotal').textContent = total.toLocaleString();
        document.getElementById('statMessage').textContent = messages.toLocaleString();
        document.getElementById('statService').textContent = services.toLocaleString();
        document.getElementById('statUsers').textContent = users.size.toLocaleString();
        document.getElementById('statRange').textContent = dateRange;
    }

    function renderUserList() {
        const userMap = new Map();
        state.messages.forEach(msg => {
            const id = getUserId(msg);
            const name = msg.from || msg.actor || '未知用户';
            if (!userMap.has(id)) {
                userMap.set(id, { name, count: 0 });
            }
            userMap.get(id).count++;
        });

        const sorted = Array.from(userMap.entries())
            .sort((a, b) => b[1].count - a[1].count)
            .slice(0, 50);

        const container = document.getElementById('userListContent');
        container.innerHTML = sorted.map(([id, info]) => `
            <div class="user-item" data-user-id="${escapeHtml(id)}">
                <div class="user-avatar" style="background: ${getUserColor(id)};">
                    ${getInitial(info.name)}
                </div>
                <div class="user-info">
                    <div class="user-name">${escapeHtml(info.name)}</div>
                    <div class="user-count">${info.count} 条消息</div>
                </div>
            </div>
        `).join('');
    }

    // ------------------------------------------------------------------
    // 过滤 / 虚拟列表
    // ------------------------------------------------------------------
    function getUserId(msg) {
        return msg.from_id || msg.actor_id || 'unknown';
    }

    function getFilteredMessages() {
        let msgs = state.messages;

        if (state.currentFilter === 'message') {
            msgs = msgs.filter(m => m.type === 'message' && !m.media_type);
        } else if (state.currentFilter === 'service') {
            msgs = msgs.filter(m => m.type === 'service');
        } else if (state.currentFilter === 'sticker') {
            msgs = msgs.filter(m => m.media_type === 'sticker');
        }

        if (state.currentUserFilter) {
            msgs = msgs.filter(m => getUserId(m) === state.currentUserFilter);
        }

        if (state.searchQuery) {
            const query = state.searchQuery.toLowerCase();
            msgs = msgs.filter(m => {
                const text = getPlainText(m).toLowerCase();
                const name = (m.from || m.actor || '').toLowerCase();
                return text.includes(query) || name.includes(query);
            });
        }

        return msgs;
    }

    function estimateUnitHeight(msg, showDate, sameUser) {
        let h = showDate ? 48 : 0;
        if (msg.type === 'service') {
            h += 54;
        } else if (msg.media_type === 'sticker') {
            h += 124;
        } else {
            h += sameUser ? 72 : 98;
            if (msg.reply_to_message_id) h += 36;
            if (msg.forwarded_from) h += 26;
            if (msg.reactions && msg.reactions.length) h += 28;
            const text = getPlainText(msg);
            if (text.length > 120) h += 24;
            if (text.length > 300) h += 24;
        }
        return Math.max(h, MIN_ITEM_HEIGHT);
    }

    function buildUnits(messages) {
        const units = [];
        let lastDate = '';
        let lastUserId = null;

        messages.forEach(msg => {
            let dateKey = '';
            if (msg.date) {
                const dt = new Date(msg.date);
                dateKey = isNaN(dt.getTime()) ? String(msg.date) : dt.toDateString();
            }
            const showDate = dateKey !== lastDate;
            if (showDate) {
                lastDate = dateKey;
                lastUserId = null;
            }

            const userId = getUserId(msg);
            const sameUser = !showDate && lastUserId === userId;
            units.push({
                msg,
                showDate,
                dateLabel: showDate ? formatDateOnly(msg.date) : '',
                sameUser,
                height: estimateUnitHeight(msg, showDate, sameUser)
            });
            lastUserId = userId;
        });

        state.units = units;
        state.heights = units.map(u => u.height);
        buildPrefix();
    }

    function buildPrefix() {
        const prefix = [0];
        let total = 0;
        for (let i = 0; i < state.heights.length; i++) {
            total += state.heights[i];
            prefix.push(total);
        }
        state.prefix = prefix;
        state.totalHeight = total;
    }

    function findIndexAtOffset(offset) {
        const n = state.units.length;
        if (n === 0) return -1;
        if (offset <= 0) return 0;
        if (offset >= state.totalHeight) return n - 1;
        let lo = 0;
        let hi = n - 1;
        while (lo < hi) {
            const mid = Math.ceil((lo + hi) / 2);
            if (state.prefix[mid] <= offset) lo = mid;
            else hi = mid - 1;
        }
        return lo;
    }

    function renderVirtualWindow(force) {
        const container = document.getElementById('chatMessages');
        const canvas = document.getElementById('virtualCanvas');
        const win = document.getElementById('virtualWindow');
        if (!canvas || !win) return;

        if (state.units.length === 0) {
            canvas.style.height = '0px';
            win.innerHTML = '';
            document.getElementById('messageCounter').textContent = '0 条消息';
            document.getElementById('progressFill').style.width = '0%';
            const empty = document.getElementById('emptyState');
            if (empty) empty.remove();
            canvas.insertAdjacentHTML('afterend', '<div class="no-results" id="emptyState">没有找到匹配的消息</div>');
            return;
        }
        const empty = document.getElementById('emptyState');
        if (empty) empty.remove();

        const viewTop = container.scrollTop;
        const viewBottom = viewTop + container.clientHeight;
        const start = findIndexAtOffset(Math.max(0, viewTop - OVERSCAN_PX));
        let end = findIndexAtOffset(viewBottom + OVERSCAN_PX) + 1;
        end = Math.min(end, state.units.length);

        if (!force && start === state.renderedStart && end === state.renderedEnd) {
            updatePager();
            return;
        }

        const anchorIndex = findIndexAtOffset(viewTop);
        const anchorOffset = viewTop - state.prefix[anchorIndex];
        const pendingAnchor = state.pendingAnchorIndex;

        let html = '';
        for (let i = start; i < end; i++) {
            const unit = state.units[i];
            html += `<div class="virtual-item" data-index="${i}" data-offset="${state.prefix[i]}">`;
            if (unit.showDate) {
                html += `<div class="date-divider"><span>${unit.dateLabel}</span></div>`;
            }
            html += renderMessage(unit.msg, unit.sameUser);
            html += '</div>';
        }

        win.innerHTML = html;
        win.style.transform = `translateY(${state.prefix[start]}px)`;
        canvas.style.height = state.totalHeight + 'px';
        state.renderedStart = start;
        state.renderedEnd = end;

        measureRenderedItems(anchorIndex, anchorOffset, pendingAnchor);
        updatePager();
    }

    function measureRenderedItems(anchorIndex, anchorOffset, pendingAnchor) {
        const win = document.getElementById('virtualWindow');
        const canvas = document.getElementById('virtualCanvas');
        const container = document.getElementById('chatMessages');
        if (!win || !canvas || !container) return;

        let changed = false;
        let changedAboveAnchor = false;

        win.querySelectorAll('.virtual-item').forEach(el => {
            const index = Number(el.dataset.index);
            const measured = Math.round(el.getBoundingClientRect().height);
            if (measured <= 0) return;
            if (Math.abs(measured - state.heights[index]) > 1) {
                if (index < anchorIndex) changedAboveAnchor = true;
                state.heights[index] = measured;
                changed = true;
            }
        });

        if (!changed) return;

        buildPrefix();
        canvas.style.height = state.totalHeight + 'px';
        const start = state.renderedStart;
        if (start >= 0) {
            win.style.transform = `translateY(${state.prefix[start]}px)`;
        }

        if (changedAboveAnchor && !state.isAdjustingScroll) {
            state.isAdjustingScroll = true;
            container.scrollTop = state.prefix[anchorIndex] + anchorOffset;
            requestAnimationFrame(() => {
                state.isAdjustingScroll = false;
                renderVirtualWindow(true);
            });
        }

        if (pendingAnchor !== null && pendingAnchor >= 0) {
            state.isAdjustingScroll = true;
            container.scrollTop = state.prefix[pendingAnchor];
            state.pendingAnchorIndex = null;
            requestAnimationFrame(() => {
                state.isAdjustingScroll = false;
            });
        }
    }

    function applyFilters() {
        state.filteredMessages = getFilteredMessages();
        buildUnits(state.filteredMessages);
        state.renderedStart = -1;
        state.renderedEnd = -1;

        const container = document.getElementById('chatMessages');
        if (container) container.scrollTop = 0;
        state.currentPage = 1;
        state.pendingAnchorIndex = null;
        renderVirtualWindow(true);
    }

    function updatePager() {
        const counter = document.getElementById('messageCounter');
        const pageInfo = document.getElementById('pageInfo');
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const progressFill = document.getElementById('progressFill');
        const container = document.getElementById('chatMessages');
        if (!counter || !container) return;

        const total = state.units.length;
        const pages = Math.max(1, Math.ceil(total / state.pageSize));
        const topIndex = Math.max(0, findIndexAtOffset(container.scrollTop));
        const currentPage = total === 0 ? 1 : Math.min(pages, Math.floor(topIndex / state.pageSize) + 1);
        state.currentPage = currentPage;

        counter.textContent = `共 ${total.toLocaleString()} 条 · 第 ${currentPage} / ${pages} 页`;
        if (pageInfo) pageInfo.textContent = `${currentPage} / ${pages}`;
        if (prevBtn) prevBtn.disabled = currentPage <= 1;
        if (nextBtn) nextBtn.disabled = currentPage >= pages;

        if (progressFill) {
            const maxScroll = container.scrollHeight - container.clientHeight;
            const ratio = maxScroll > 0 ? (container.scrollTop / maxScroll) : 0;
            progressFill.style.width = (ratio * 100) + '%';
        }
    }

    function goToPage(page) {
        const container = document.getElementById('chatMessages');
        if (!container || state.units.length === 0) return;
        const pages = Math.max(1, Math.ceil(state.units.length / state.pageSize));
        const targetPage = Math.max(1, Math.min(pages, page));
        const targetIndex = Math.min(state.units.length - 1, (targetPage - 1) * state.pageSize);
        state.currentPage = targetPage;
        state.pendingAnchorIndex = targetIndex;
        container.scrollTop = state.prefix[targetIndex];
        renderVirtualWindow(true);
    }

    // ------------------------------------------------------------------
    // 消息渲染
    // ------------------------------------------------------------------
    function renderMessage(msg, isSameUser) {
        if (msg.type === 'service') {
            return renderServiceMessage(msg);
        }
        if (msg.media_type === 'sticker') {
            return renderStickerMessage(msg, isSameUser);
        }
        return renderTextMessage(msg, isSameUser);
    }

    function renderServiceMessage(msg) {
        const actionTexts = {
            'create_channel': '创建了群组',
            'set_messages_ttl': msg.period ? `设置消息定时清除：${formatPeriod(msg.period)}` : '取消了消息定时清除',
            'set_photo': '更换了群头像',
            'set_title': `修改群组名称为「${msg.title}」`,
            'invite_members': '邀请了新成员',
            'join_by_link': '通过链接加入群组',
            'join_by_request': '通过申请加入群组',
            'leave_chat': '离开了群组',
            'kick_member': '移除了成员',
            'invite_user': '邀请了成员'
        };

        const actionText = actionTexts[msg.action] || msg.action || '系统消息';
        const actor = msg.actor || '系统';

        return `
            <div class="message" data-id="${msg.id}">
                <div class="message-content" style="max-width: 100%;">
                    <div class="message-bubble service-bubble">
                        <div class="service-text">
                            <strong>${escapeHtml(actor)}</strong> ${escapeHtml(actionText)}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function formatPeriod(seconds) {
        if (!seconds) return '永久';
        if (seconds < 60) return seconds + '秒';
        if (seconds < 3600) return Math.floor(seconds / 60) + '分钟';
        if (seconds < 86400) return Math.floor(seconds / 3600) + '小时';
        return Math.floor(seconds / 86400) + '天';
    }

    function renderStickerMessage(msg, isSameUser) {
        const sender = msg.from || '未知用户';
        const userId = getUserId(msg);

        return `
            <div class="message ${isSameUser ? 'message-same-user' : ''}" data-id="${msg.id}">
                <div class="message-avatar" style="background: ${getUserColor(userId)};">
                    ${getInitial(sender)}
                </div>
                <div class="message-content">
                    ${!isSameUser ? `
                        <div class="message-header">
                            <span class="sender-name" data-user-id="${escapeHtml(userId)}">${escapeHtml(sender)}</span>
                        </div>
                    ` : ''}
                    <div class="sticker-message">
                        <div class="sticker-emoji">${escapeHtml(msg.sticker_emoji || '😀')}</div>
                        <div class="sticker-file-name">${escapeHtml(msg.file_name || 'sticker')}</div>
                    </div>
                    <div class="message-meta">
                        <span>${formatTime(msg.date)}</span>
                    </div>
                </div>
            </div>
        `;
    }

    function renderTextMessage(msg, isSameUser) {
        const sender = msg.from || '未知用户';
        const userId = getUserId(msg);
        const text = getPlainText(msg);
        const hasText = text && text.trim().length > 0;

        let replyHtml = '';
        if (msg.reply_to_message_id) {
            const replyInfo = getReplyText(msg.reply_to_message_id);
            if (replyInfo) {
                replyHtml = `
                    <div class="reply-container" data-reply-to="${msg.reply_to_message_id}">
                        <div class="reply-sender">${escapeHtml(replyInfo.sender)}</div>
                        <div class="reply-text">${escapeHtml(replyInfo.text || '（贴纸/媒体）')}</div>
                    </div>
                `;
            }
        }

        let forwardedHtml = '';
        if (msg.forwarded_from || msg.forwarded_from_id) {
            const from = msg.forwarded_from || '未知来源';
            forwardedHtml = `
                <div class="forwarded-badge">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/>
                    </svg>
                    <span>转发自 ${escapeHtml(from)}</span>
                </div>
            `;
        }

        const reactionsHtml = msg.reactions && msg.reactions.length > 0 ? `
            <div class="reactions-container">
                ${msg.reactions.map(r => `
                    <div class="reaction">
                        <span>${escapeHtml(r.emoji)}</span>
                        <span class="reaction-count">${r.count}</span>
                    </div>
                `).join('')}
            </div>
        ` : '';

        const editedHtml = msg.edited ? '<span class="edited-badge">✏️ 已编辑</span>' : '';
        const formattedText = hasText ? formatTextContent(msg) : '';

        return `
            <div class="message ${isSameUser ? 'message-same-user' : ''}" data-id="${msg.id}">
                <div class="message-avatar" style="background: ${getUserColor(userId)};">
                    ${getInitial(sender)}
                </div>
                <div class="message-content">
                    ${!isSameUser ? `
                        <div class="message-header">
                            <span class="sender-name" data-user-id="${escapeHtml(userId)}">${escapeHtml(sender)}</span>
                        </div>
                    ` : ''}
                    <div class="message-bubble">
                        ${forwardedHtml}
                        ${replyHtml}
                        <div class="message-text">${formattedText}</div>
                        ${reactionsHtml}
                        <div class="message-meta">
                            ${editedHtml}
                            <span>${formatTime(msg.date)}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function formatTextContent(msg) {
        if (!msg.text_entities || !Array.isArray(msg.text_entities) || msg.text_entities.length === 0) {
            return escapeHtml(getPlainText(msg));
        }

        const searchHighlight = state.searchQuery;
        let html = '';

        msg.text_entities.forEach(entity => {
            let text = entity.text || '';
            text = escapeHtml(text);

            if (searchHighlight && text.toLowerCase().includes(searchHighlight.toLowerCase())) {
                const regex = new RegExp(`(${escapeRegex(searchHighlight)})`, 'gi');
                text = text.replace(regex, '<span class="search-result">$1</span>');
            }

            switch (entity.type) {
                case 'bold':
                    html += `<span class="bold">${text}</span>`;
                    break;
                case 'italic':
                    html += `<span class="italic">${text}</span>`;
                    break;
                case 'code':
                    html += `<span class="code">${text}</span>`;
                    break;
                case 'mention':
                case 'mention_name':
                    html += `<span class="mention">${text}</span>`;
                    break;
                case 'link':
                    html += `<span class="link">${text}</span>`;
                    break;
                case 'custom_emoji':
                    html += `<span class="custom-emoji">${text}</span>`;
                    break;
                case 'emoji':
                case 'plain':
                default:
                    html += text;
                    break;
            }
        });

        return html;
    }

    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    // ------------------------------------------------------------------
    // 交互
    // ------------------------------------------------------------------
    function handleMessageClick(e) {
        const senderEl = e.target.closest('.sender-name');
        if (senderEl) {
            e.stopPropagation();
            filterByUser(senderEl.dataset.userId);
            return;
        }

        const replyEl = e.target.closest('.reply-container');
        if (replyEl) {
            e.stopPropagation();
            scrollToMessage(parseInt(replyEl.dataset.replyTo, 10));
        }
    }

    function filterByUser(userId) {
        if (state.currentUserFilter === userId) {
            state.currentUserFilter = null;
        } else {
            state.currentUserFilter = userId;
        }

        document.querySelectorAll('.user-item').forEach(item => {
            item.classList.toggle('active', item.dataset.userId === state.currentUserFilter);
        });
        applyFilters();
    }

    function scrollToMessage(messageId) {
        if (!messageId) return;

        state.currentUserFilter = null;
        state.searchQuery = '';
        const searchInput = document.getElementById('searchInput');
        if (searchInput) searchInput.value = '';
        state.currentFilter = 'all';
        document.querySelectorAll('.user-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.filter-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.filter === 'all');
        });

        applyFilters();

        const index = state.units.findIndex(u => u.msg.id === messageId);
        if (index < 0) {
            showToast('消息 #' + messageId + ' 不在当前数据范围内');
            return;
        }

        const container = document.getElementById('chatMessages');
        container.scrollTop = Math.max(0, state.prefix[index] - container.clientHeight / 2);
        renderVirtualWindow(true);

        setTimeout(() => {
            const target = container.querySelector(`[data-id="${messageId}"]`);
            if (target) {
                target.classList.add('highlighted');
                setTimeout(() => target.classList.remove('highlighted'), 1500);
            }
        }, 80);
    }

    function showToast(msg) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            padding: 10px 20px;
            border-radius: 8px;
            box-shadow: var(--shadow-lg);
            z-index: 10000;
            font-size: 14px;
        `;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    function handleSearch() {
        const searchInput = document.getElementById('searchInput');
        state.searchQuery = searchInput.value.trim();
        applyFilters();
    }

    function bindEvents() {
        document.getElementById('themeToggle').addEventListener('click', toggleTheme);
        document.getElementById('searchBtn').addEventListener('click', handleSearch);

        const searchInput = document.getElementById('searchInput');
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handleSearch();
            if (e.key === 'Escape') {
                searchInput.value = '';
                state.searchQuery = '';
                applyFilters();
            }
        });

        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                state.searchQuery = searchInput.value.trim();
                applyFilters();
            }, 300);
        });

        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.currentFilter = btn.dataset.filter;
                applyFilters();
            });
        });

        document.getElementById('scrollTop').addEventListener('click', () => {
            document.getElementById('chatMessages').scrollTo({ top: 0, behavior: 'smooth' });
        });

        document.getElementById('scrollBottom').addEventListener('click', () => {
            const container = document.getElementById('chatMessages');
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        });

        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        if (prevBtn) prevBtn.addEventListener('click', () => goToPage(currentPageNumber() - 1));
        if (nextBtn) nextBtn.addEventListener('click', () => goToPage(currentPageNumber() + 1));
        if (pageSizeSelect) pageSizeSelect.addEventListener('change', () => {
            state.pageSize = parseInt(pageSizeSelect.value, 10) || 500;
            goToPage(1);
        });

        document.getElementById('chatMessages').addEventListener('click', handleMessageClick);

        document.getElementById('userListContent').addEventListener('click', (e) => {
            const item = e.target.closest('.user-item');
            if (!item) return;
            filterByUser(item.dataset.userId);
        });

        document.getElementById('chatMessages').addEventListener('scroll', () => {
            if (state.isAdjustingScroll) return;
            window.requestAnimationFrame(() => {
                if (!state.isAdjustingScroll) renderVirtualWindow(false);
            });
        });

        window.addEventListener('resize', () => {
            clearTimeout(state.resizeTimer);
            state.resizeTimer = setTimeout(() => renderVirtualWindow(true), 150);
        });
    }

    function currentPageNumber() {
        const container = document.getElementById('chatMessages');
        if (!container || state.units.length === 0) return 1;
        const topIndex = Math.max(0, findIndexAtOffset(container.scrollTop));
        return Math.floor(topIndex / state.pageSize) + 1;
    }

    window.__viewer = {
        getState: function () {
            return {
                total: state.units.length,
                raw: state.messages.length,
                renderedStart: state.renderedStart,
                renderedEnd: state.renderedEnd,
                renderedNodes: state.units.length ? state.renderedEnd - state.renderedStart : 0,
                pageSize: state.pageSize,
                totalHeight: state.totalHeight,
                prefixAt100: state.prefix[100],
                prefixAt500: state.prefix[500],
                pendingAnchorIndex: state.pendingAnchorIndex
            };
        },
        goToPage: goToPage,
        scrollToMessage: scrollToMessage,
        applyFilters: applyFilters
    };

    window.addEventListener('DOMContentLoaded', init);
})();
