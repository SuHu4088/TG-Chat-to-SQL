(function () {
    'use strict';

    const AVATAR_COLORS = [
        '#e17076', '#7bcfa0', '#a29bfe', '#fd79a8', '#00b894',
        '#e67e22', '#3498db', '#9b59b6', '#f39c12', '#1abc9c',
        '#e74c3c', '#2ecc71', '#34495e', '#16a085', '#c0392b',
        '#d35400', '#2980b9', '#8e44ad', '#27ae60', '#f1c40f'
    ];

    const state = {
        chatData: null,
        messages: [],
        currentFilter: 'all',
        currentUserFilter: null,
        searchQuery: '',
        selectedMessageId: null,
        replyMap: new Map(),
        userColors: new Map(),
        filteredMessages: [],
        renderedCount: 0,
        batchSize: 50,
        lastRenderedDate: '',
        lastRenderedUserId: null
    };

    function init() {
        loadTheme();
        loadData();
        bindEvents();
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
            buildReplyMap();
            renderStats();
            renderUserList();
            renderChatInfo();
            
            const loadingState = document.getElementById('loadingState');
            if (loadingState) loadingState.style.display = 'none';
            
            renderMessages();
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

    function buildReplyMap() {
        const map = new Map();
        state.messages.forEach(msg => {
            if (msg.reply_to_message_id) {
                map.set(msg.id, msg.reply_to_message_id);
            }
        });
        state.replyMap = map;
    }

    function getReplyText(messageId) {
        const replyMsg = state.messages.find(m => m.id === messageId);
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
        for (let i = 0; i < userId.length; i++) {
            hash = userId.charCodeAt(i) + ((hash << 5) - hash);
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
            if (m.from) users.add(m.from_id);
            if (m.actor) users.add(m.actor_id);
        });

        let dateRange = '-';
        if (msgs.length > 0) {
            const first = msgs[0].date;
            const last = msgs[msgs.length - 1].date;
            dateRange = `${formatDateOnly(first)} ~ ${formatDateOnly(last)}`;
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
            const id = msg.from_id || msg.actor_id;
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
            <div class="user-item" data-user-id="${id}" data-user-name="${escapeHtml(info.name)}">
                <div class="user-avatar" style="background: ${getUserColor(id)};">
                    ${getInitial(info.name)}
                </div>
                <div class="user-info">
                    <div class="user-name">${escapeHtml(info.name)}</div>
                    <div class="user-count">${info.count} 条消息</div>
                </div>
            </div>
        `).join('');

        container.querySelectorAll('.user-item').forEach(item => {
            item.addEventListener('click', () => {
                const userId = item.dataset.userId;
                if (state.currentUserFilter === userId) {
                    state.currentUserFilter = null;
                    item.classList.remove('active');
                } else {
                    state.currentUserFilter = userId;
                    container.querySelectorAll('.user-item').forEach(i => i.classList.remove('active'));
                    item.classList.add('active');
                }
                applyFilters();
            });
        });
    }

    function renderMessages() {
        const container = document.getElementById('chatMessages');
        state.filteredMessages = getFilteredMessages();
        state.renderedCount = 0;
        
        const total = state.filteredMessages.length;
        document.getElementById('messageCounter').textContent = `0 / ${total} 条消息`;
        
        if (total === 0) {
            container.innerHTML = '<div class="no-results">没有找到匹配的消息</div>';
            return;
        }

        container.innerHTML = '';
        renderBatch();
    }

    function renderBatch() {
        const container = document.getElementById('chatMessages');
        const total = state.filteredMessages.length;
        const start = state.renderedCount;
        const end = Math.min(start + state.batchSize, total);
        
        let html = '';
        let lastDate = state.lastRenderedDate || '';
        let lastUserId = state.lastRenderedUserId || null;

        for (let i = start; i < end; i++) {
            const msg = state.filteredMessages[i];
            try {
                const msgDate = msg.date ? new Date(msg.date) : new Date();
                const dateStr = msgDate.toDateString();
                
                if (dateStr !== lastDate) {
                    html += `<div class="date-divider"><span>${formatDateOnly(msg.date)}</span></div>`;
                    lastDate = dateStr;
                    lastUserId = null;
                }

                html += renderMessage(msg, lastUserId === getUserId(msg));
                lastUserId = getUserId(msg);
            } catch (err) {
                console.error('Error rendering message', msg.id, err);
                html += `<div class="message"><div class="message-content"><div class="message-bubble"><div class="message-text" style="color:var(--text-tertiary);font-style:italic;">[消息 #${msg.id} 渲染错误]</div></div></div></div>`;
            }
        }

        state.lastRenderedDate = lastDate;
        state.lastRenderedUserId = lastUserId;
        
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        while (tempDiv.firstChild) {
            container.appendChild(tempDiv.firstChild);
        }

        state.renderedCount = end;
        document.getElementById('messageCounter').textContent = `${end} / ${total} 条消息`;
        
        const progressFill = document.getElementById('progressFill');
        if (progressFill) {
            progressFill.style.width = (end / total * 100) + '%';
        }

        if (end < total) {
            requestAnimationFrame(renderBatch);
        } else {
            document.getElementById('messageCounter').textContent = `${total} 条消息`;
            const progressFill = document.getElementById('progressFill');
            if (progressFill) progressFill.style.width = '100%';
            bindMessageEvents();
            bindScrollHandler();
        }
    }

    function bindScrollHandler() {
        const container = document.getElementById('chatMessages');
        if (!container) return;
        
        if (container._scrollHandler) {
            container.removeEventListener('scroll', container._scrollHandler);
        }
        
        container._scrollHandler = () => {
            if (state.renderedCount < state.filteredMessages.length) {
                const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
                if (scrollBottom < 500) {
                    renderBatch();
                }
            }
        };
        container.addEventListener('scroll', container._scrollHandler);
    }

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
                            <span class="sender-name" data-user-id="${userId}">${escapeHtml(sender)}</span>
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
                            <span class="sender-name" data-user-id="${userId}">${escapeHtml(sender)}</span>
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

    function bindMessageEvents() {
        document.querySelectorAll('.sender-name').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const userId = el.dataset.userId;
                const userName = el.dataset.userName || el.textContent;
                filterByUser(userId, userName);
            });
        });

        document.querySelectorAll('.reply-container').forEach(el => {
            el.addEventListener('click', () => {
                const replyToId = parseInt(el.dataset.replyTo);
                scrollToMessage(replyToId);
            });
        });
    }

    function filterByUser(userId, userName) {
        if (state.currentUserFilter === userId) {
            state.currentUserFilter = null;
        } else {
            state.currentUserFilter = userId;
        }

        document.querySelectorAll('.user-item').forEach(item => {
            if (item.dataset.userId === state.currentUserFilter) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });

        applyFilters();
    }

    function scrollToMessage(messageId) {
        const container = document.getElementById('chatMessages');
        
        if (state.currentUserFilter) {
            state.currentUserFilter = null;
            document.querySelectorAll('.user-item').forEach(i => i.classList.remove('active'));
        }
        if (state.searchQuery) {
            state.searchQuery = '';
            document.getElementById('searchInput').value = '';
        }
        if (state.currentFilter !== 'all') {
            state.currentFilter = 'all';
            document.querySelectorAll('.filter-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.filter === 'all');
            });
        }

        renderMessages();

        setTimeout(() => {
            const target = container.querySelector(`[data-id="${messageId}"]`);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                target.classList.add('highlighted');
                setTimeout(() => target.classList.remove('highlighted'), 1500);
            } else {
                showToast('消息 #' + messageId + ' 不在当前筛选范围内');
            }
        }, 100);
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
            animation: fadeIn 0.3s ease;
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

    function applyFilters() {
        renderMessages();
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
    }

    window.addEventListener('DOMContentLoaded', init);
})();
