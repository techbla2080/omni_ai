// ============================================================================
// OmniAI - Core Chat Application
// ============================================================================

const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000' 
    : '';

var conversationId = null;
var isStreaming = false;
var attachedFiles = [];
var lastFailedMessage = null;

// ============================================================================
// #25 — AI MODE SYSTEM STATE
// ============================================================================

var currentMode = 'normal';

const MODE_PLACEHOLDERS = {
    'normal': 'Message OmniAI...',
    'email': '📧 Email mode — ask about your inbox',
    'calendar': '📅 Calendar mode — ask about your schedule',
    'code': '🧑‍💻 Code mode — ask for code or debugging help'
};

// ============================================================================
// MARKDOWN + SYNTAX HIGHLIGHTING SETUP
// ============================================================================

function setupMarked() {
    if (typeof marked === 'undefined') return;
    marked.setOptions({
        highlight: function(code, lang) {
            if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            if (typeof hljs !== 'undefined') {
                return hljs.highlightAuto(code).value;
            }
            return code;
        },
        breaks: true,
        gfm: true
    });
}

function renderMarkdown(text) {
    if (typeof marked === 'undefined') return escapeHtml(text);
    setupMarked();
    return marked.parse(text);
}

function highlightCodeBlocks(element) {
    if (typeof hljs === 'undefined') return;
    element.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('messageInput');
    if (input) input.focus();
    setupMarked();
    loadConversations();
    
    if (!document.getElementById('sidebarOverlay') && !document.querySelector('.sidebar-overlay')) {
        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        overlay.id = 'sidebarOverlay';
        overlay.onclick = toggleSidebar;
        document.body.appendChild(overlay);
    }

    // Initialize mode pills UI to normal by default
    updateModePillUI('normal');

    // Gmail init
    setTimeout(() => {
        injectGmailButton();
        initGmail();
    }, 1500);
});

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function useSuggestion(text) {
    document.getElementById('messageInput').value = text;
    sendMessage();
}

function hideWelcome() {
    const welcome = document.getElementById('welcome');
    if (welcome) welcome.style.display = 'none';
}

function showWelcome() {
    const welcome = document.getElementById('welcome');
    if (welcome) welcome.style.display = 'block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) container.scrollTop = container.scrollHeight;
}

// ============================================================================
// COPY HELPER
// ============================================================================

function copyToClipboard(text, button, originalLabel) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    textarea.style.top = '0';
    textarea.style.left = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
        document.execCommand('copy');
        button.innerHTML = '✅ Copied!';
    } catch (e) {
        button.innerHTML = '❌ Failed';
    }
    document.body.removeChild(textarea);
    setTimeout(() => { button.innerHTML = originalLabel; }, 2000);
}

// ============================================================================
// #20 — User initials helper
// ============================================================================

function getUserInitial() {
    try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        const raw = user.name || user.email || '?';
        const parts = raw.trim().split(/\s+/);
        let initials = parts[0][0].toUpperCase();
        if (parts.length > 1) initials += parts[parts.length - 1][0].toUpperCase();
        return initials;
    } catch (e) {
        return '?';
    }
}

// ============================================================================
// #25 — AI MODE SYSTEM
// ============================================================================

function updateModePillUI(mode) {
    const validModes = ['normal', 'email', 'calendar', 'code'];
    if (!validModes.includes(mode)) mode = 'normal';

    currentMode = mode;

    // Update active pill
    document.querySelectorAll('.mode-pill').forEach(pill => {
        if (pill.dataset.mode === mode) {
            pill.classList.add('active');
        } else {
            pill.classList.remove('active');
        }
    });

    // Update input placeholder
    const input = document.getElementById('messageInput');
    if (input && MODE_PLACEHOLDERS[mode]) {
        input.placeholder = MODE_PLACEHOLDERS[mode];
    }

    // Update input container glow class
    const inputContainer = document.querySelector('.input-container');
    if (inputContainer) {
        inputContainer.classList.remove(
            'mode-normal-active',
            'mode-email-active',
            'mode-calendar-active',
            'mode-code-active'
        );
        if (mode !== 'normal') {
            inputContainer.classList.add(`mode-${mode}-active`);
        }
    }
}

async function switchMode(mode) {
    const validModes = ['normal', 'email', 'calendar', 'code'];
    if (!validModes.includes(mode)) return;
    if (mode === currentMode) return;

    // Update UI immediately for responsiveness
    updateModePillUI(mode);

    // If there's an existing conversation, persist the mode change to backend
    if (conversationId) {
        try {
            const response = await authFetch(
                `/api/v1/chat/conversations/${conversationId}/mode`,
                {
                    method: 'PATCH',
                    body: JSON.stringify({ mode: mode })
                }
            );
            if (!response.ok) {
                console.error('Failed to update mode on server');
            }
        } catch (e) {
            console.error('Mode switch error:', e);
        }
    }

    // Add a subtle system message in chat if mode changed (only if conversation exists)
    if (conversationId) {
        addModeChangeNotice(mode);
    }
}

function addModeChangeNotice(mode) {
    const modeLabels = {
        'normal': '💬 Normal mode',
        'email': '📧 Email mode',
        'calendar': '📅 Calendar mode',
        'code': '🧑‍💻 Code mode'
    };
    const container = document.getElementById('messagesContainer');
    if (!container) return;

    const notice = document.createElement('div');
    notice.className = 'mode-change-notice';
    notice.innerHTML = `<span>Switched to ${modeLabels[mode]}</span>`;
    container.appendChild(notice);
    scrollToBottom();
}

// ============================================================================
// MEMORY INDICATOR — #17
// ============================================================================

function updateMemoryIndicator(count = null) {
    let indicator = document.getElementById('memoryIndicator');
    if (!indicator) {
        const wrapper = document.querySelector('.input-wrapper');
        if (!wrapper) return;
        indicator = document.createElement('div');
        indicator.id = 'memoryIndicator';
        indicator.className = 'memory-indicator';
        wrapper.insertBefore(indicator, wrapper.firstChild);
    }

    if (count === 0 || !conversationId) {
        indicator.style.display = 'none';
        return;
    }

    const messages = document.querySelectorAll('.message').length;
    if (messages < 2) {
        indicator.style.display = 'none';
        return;
    }

    indicator.style.display = 'flex';
    indicator.innerHTML = `
        <span class="memory-dot"></span>
        <span class="memory-text">🧠 Remembering ${messages} messages</span>
    `;
}

// ============================================================================
// GMAIL INTEGRATION — #24 #25 #26 #27
// ============================================================================

var gmailConnected = false;
var gmailEmail = '';

async function initGmail() {
    try {
        const response = await authFetch('/api/v1/gmail/status');
        if (response.ok) {
            const data = await response.json();
            gmailConnected = data.connected;
            gmailEmail = data.email || '';
            updateGmailButton();
        }
    } catch (e) {
        console.log('Gmail status check failed:', e);
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('gmail_connected') === 'true') {
        const email = params.get('gmail_email') || '';
        gmailConnected = true;
        gmailEmail = email;
        updateGmailButton();
        addAssistantMessage(`✅ Gmail connected! (${email})\n\nYou can now:\n- "Show my unread emails"\n- "Search emails from [name]"\n- "Send email to [address]"\n- "Summarize my inbox"`);
        window.history.replaceState({}, '', '/');
    }
    if (params.get('gmail_error')) {
        addAssistantMessage(`❌ Gmail connection failed: ${params.get('gmail_error')}. Please try again.`);
        window.history.replaceState({}, '', '/');
    }
}

function updateGmailButton() {
    let btn = document.getElementById('gmailBtn');
    if (!btn) return;
    if (gmailConnected) {
        btn.innerHTML = `📧 ${gmailEmail || 'Gmail'}`;
        btn.title = 'Gmail connected — click to disconnect';
        btn.classList.add('gmail-connected');
    } else {
        btn.innerHTML = `📧 Connect Gmail`;
        btn.title = 'Connect your Gmail account';
        btn.classList.remove('gmail-connected');
    }
}

function injectGmailButton() {
    const inputContainer = document.querySelector('.input-container');
    if (!inputContainer || document.getElementById('gmailBtn')) return;
    const btn = document.createElement('button');
    btn.id = 'gmailBtn';
    btn.className = 'gmail-btn';
    btn.innerHTML = '📧 Connect Gmail';
    btn.title = 'Connect Gmail';
    btn.onclick = handleGmailButtonClick;
    const sendBtn = document.getElementById('sendButton');
    if (sendBtn) inputContainer.insertBefore(btn, sendBtn);
    else inputContainer.appendChild(btn);
}

async function handleGmailButtonClick() {
    if (gmailConnected) {
        if (confirm(`Disconnect Gmail (${gmailEmail})?`)) await disconnectGmail();
    } else {
        await connectGmail();
    }
}

async function connectGmail() {
    try {
        const response = await authFetch('/api/v1/gmail/connect');
        if (response.ok) {
            const data = await response.json();
            window.location.href = data.auth_url;
        } else {
            addAssistantMessage('❌ Could not start Gmail connection. Please try again.');
        }
    } catch (e) {
        addAssistantMessage('❌ Gmail connection error: ' + e.message);
    }
}

async function disconnectGmail() {
    try {
        await authFetch('/api/v1/gmail/disconnect', { method: 'DELETE' });
        gmailConnected = false;
        gmailEmail = '';
        updateGmailButton();
        addAssistantMessage('Gmail disconnected.');
    } catch (e) {
        addAssistantMessage('❌ Could not disconnect Gmail.');
    }
}

function detectGmailIntent(message) {
    const emailPatterns = [
        /show.*(my )?(email|inbox|mail|message)/i,
        /check.*(my )?(email|inbox|mail)/i,
        /unread.*(email|mail|message)/i,
        /read.*(my )?(email|mail)/i,
        /what.*email/i,
        /any.*(email|mail).*(from|about)/i,
        /email.*(from|about|today|week|yesterday)/i,
        /send.*email/i,
        /compose.*email/i,
        /write.*email/i,
        /reply.*email/i,
        /search.*(email|inbox|mail)/i,
        /find.*(email|mail).*(from|about)/i,
        /summarize.*(my )?(inbox|email)/i,
        /urgent.*(email|mail)/i,
        /inbox/i,
    ];
    return emailPatterns.some(p => p.test(message));
}

function detectSendIntent(message) {
    return /send.*email|compose.*email|write.*email|draft.*email/i.test(message);
}

function detectSearchIntent(message) {
    return /search.*email|find.*email|look.*email|email.*from|email.*about/i.test(message);
}

// #26 — new: detect when user wants to SEE/LIST emails (vs ask about them)
function detectShowListIntent(message) {
    return /^(show|list|check|get|display|give me|see).*(email|inbox|mail|message)/i.test(message) ||
           /(unread|new|recent).*(email|mail|message)/i.test(message) ||
           /^inbox$/i.test(message);
}

async function handleGmailMessage(message) {
    if (!gmailConnected) {
        addAssistantMessage(`To use Gmail features, connect your Gmail account first.\n\nClick the **📧 Connect Gmail** button below!`);
        return true;
    }
    if (detectSendIntent(message)) { await handleSendEmailIntent(message); return true; }
    if (detectSearchIntent(message)) { await handleSearchEmailIntent(message); return true; }
    if (detectShowListIntent(message)) { await handleShowEmailsIntent(message); return true; }
    await handleAskEmailIntent(message);
    return true;
}

// #26 — new: render actual email cards for show/list intents
async function handleShowEmailsIntent(message) {
    addTypingIndicator('📧 Loading your emails...');
    try {
        const isUnread = /unread|new/i.test(message);
        const endpoint = isUnread ? '/api/v1/gmail/unread' : '/api/v1/gmail/inbox';
        const response = await authFetch(`${endpoint}?max_results=10`);
        removeTypingIndicator();
        if (response.ok) {
            const data = await response.json();
            const emails = data.emails || [];
            if (emails.length === 0) {
                addAssistantMessage(isUnread ? 'No unread emails. Inbox zero! 🎉' : 'Your inbox is empty.');
            } else {
                const title = isUnread
                    ? `Unread Emails${data.unread_count ? ` (${data.unread_count} total unread)` : ''}`
                    : 'Your Inbox';
                displayEmailCards(emails, title);
            }
        } else {
            addAssistantMessage('❌ Could not load emails. Please try again.');
        }
    } catch (e) {
        removeTypingIndicator();
        addAssistantMessage('❌ Gmail error: ' + e.message);
    }
}

async function handleAskEmailIntent(message) {
    addTypingIndicator('📧 Reading your emails...');
    try {
        const response = await authFetch('/api/v1/gmail/ask', {
            method: 'POST',
            body: JSON.stringify({ query: message, max_results: 5 })
        });
        removeTypingIndicator();
        if (response.ok) {
            const data = await response.json();
            addAssistantMessage(data.response);
        } else {
            addAssistantMessage('❌ Could not read emails. Please try again.');
        }
    } catch (e) {
        removeTypingIndicator();
        addAssistantMessage('❌ Gmail error: ' + e.message);
    }
}

async function handleSearchEmailIntent(message) {
    addTypingIndicator('🔍 Searching your emails...');
    try {
        let query = message.replace(/search.*email|find.*email|look.*for/gi, '').trim();
        if (!query) query = 'in:inbox';
        const response = await authFetch(`/api/v1/gmail/search?q=${encodeURIComponent(query)}&max_results=5`);
        removeTypingIndicator();
        if (response.ok) {
            const data = await response.json();
            if (data.emails.length === 0) addAssistantMessage(`No emails found for "${query}".`);
            else displayEmailCards(data.emails, `Search results for "${query}"`);
        } else {
            addAssistantMessage('❌ Email search failed.');
        }
    } catch (e) {
        removeTypingIndicator();
        addAssistantMessage('❌ Search error: ' + e.message);
    }
}

function displayEmailCards(emails, title = 'Your Emails') {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    const emailCardsHtml = emails.map(email => `
        <div class="email-card ${email.is_unread ? 'unread' : ''}">
            <div class="email-card-header">
                <div class="email-from">${escapeHtml(email.from)}</div>
                <div class="email-date">${escapeHtml(email.date)}</div>
            </div>
            <div class="email-subject">${escapeHtml(email.subject)}</div>
            <div class="email-snippet">${escapeHtml(email.snippet)}</div>
            <div class="email-actions">
                <button class="email-action-btn" onclick="replyToEmail('${email.id}', '${escapeHtml(email.from).replace(/'/g, "\\'")}', '${escapeHtml(email.subject).replace(/'/g, "\\'")}')">↩ Reply</button>
                ${email.is_unread ? `<button class="email-action-btn" onclick="markRead('${email.id}', this)">✓ Mark Read</button>` : ''}
            </div>
        </div>
    `).join('');
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content">
            <div class="email-list-header">📧 ${escapeHtml(title)} (${emails.length})</div>
            <div class="email-list">${emailCardsHtml}</div>
        </div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
}

async function markRead(messageId, button) {
    try {
        await authFetch(`/api/v1/gmail/read/${messageId}`, { method: 'POST' });
        button.textContent = '✓ Read';
        button.disabled = true;
        const card = button.closest('.email-card');
        if (card) card.classList.remove('unread');
    } catch (e) {
        console.error('Mark read error:', e);
    }
}

async function handleSendEmailIntent(message) {
    showComposeForm(message);
}

function showComposeForm(prefillMessage = '') {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    const formId = 'compose-' + Date.now();
    let toHint = '';
    const toMatch = prefillMessage.match(/to\s+([\w.@]+)/i);
    if (toMatch) toHint = toMatch[1];
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content">
            <div class="compose-form" id="${formId}">
                <div class="compose-header">✉️ Compose Email</div>
                <div class="compose-field">
                    <label>To:</label>
                    <input type="email" class="compose-input" id="${formId}-to" placeholder="recipient@email.com" value="${toHint}">
                </div>
                <div class="compose-field">
                    <label>Subject:</label>
                    <input type="text" class="compose-input" id="${formId}-subject" placeholder="Email subject">
                </div>
                <div class="compose-field">
                    <label>Message:</label>
                    <textarea class="compose-textarea" id="${formId}-body" rows="5" placeholder="Write your email here..."></textarea>
                </div>
                <div class="compose-actions">
                    <button class="compose-send-btn" onclick="sendComposedEmail('${formId}')">📤 Send Email</button>
                    <button class="compose-cancel-btn" onclick="this.closest('.message').remove()">✖ Cancel</button>
                    <button class="compose-ai-btn" onclick="aiDraftEmail('${formId}', '${escapeHtml(prefillMessage).replace(/'/g, "\\'")}')">✨ AI Draft</button>
                </div>
            </div>
        </div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
    setTimeout(() => {
        const toField = document.getElementById(`${formId}-to`);
        if (toField && !toHint) toField.focus();
        else { const s = document.getElementById(`${formId}-subject`); if (s) s.focus(); }
    }, 100);
}

async function aiDraftEmail(formId, originalMessage) {
    const toField = document.getElementById(`${formId}-to`);
    const subjectField = document.getElementById(`${formId}-subject`);
    const bodyField = document.getElementById(`${formId}-body`);
    const to = toField ? toField.value : '';
    const subject = subjectField ? subjectField.value : '';
    const prompt = `Draft a professional email${to ? ` to ${to}` : ''}${subject ? ` about "${subject}"` : ''}. Original request: "${originalMessage}". Return only the email body text, no subject line.`;
    bodyField.value = 'Drafting...';
    bodyField.disabled = true;
    try {
        const response = await authFetch('/api/v1/chat', {
            method: 'POST',
            body: JSON.stringify({ message: prompt, conversation_id: null })
        });
        const data = await response.json();
        bodyField.value = data.response || '';
    } catch (e) {
        bodyField.value = '';
    } finally {
        bodyField.disabled = false;
        bodyField.focus();
    }
}

async function sendComposedEmail(formId) {
    const to = document.getElementById(`${formId}-to`)?.value?.trim();
    const subject = document.getElementById(`${formId}-subject`)?.value?.trim();
    const body = document.getElementById(`${formId}-body`)?.value?.trim();
    if (!to || !subject || !body) { alert('Please fill in all fields.'); return; }
    const sendBtn = document.querySelector(`#${formId} .compose-send-btn`);
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '⏳ Sending...'; }
    try {
        const response = await authFetch('/api/v1/gmail/send', {
            method: 'POST',
            body: JSON.stringify({ to, subject, body })
        });
        if (response.ok) {
            const form = document.getElementById(formId);
            if (form) form.innerHTML = `<div class="compose-success">✅ Email sent to ${escapeHtml(to)}!</div>`;
        } else {
            const data = await response.json();
            alert('Failed to send: ' + (data.detail || 'Unknown error'));
            if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '📤 Send Email'; }
        }
    } catch (e) {
        alert('Error: ' + e.message);
        if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '📤 Send Email'; }
    }
}

async function replyToEmail(messageId, from, subject) {
    const replySubject = subject.startsWith('Re:') ? subject : `Re: ${subject}`;
    showComposeForm('');
    setTimeout(() => {
        const forms = document.querySelectorAll('.compose-form');
        const lastForm = forms[forms.length - 1];
        if (lastForm) {
            const formId = lastForm.id;
            const toField = document.getElementById(`${formId}-to`);
            const subjectField = document.getElementById(`${formId}-subject`);
            if (toField) toField.value = from;
            if (subjectField) subjectField.value = replySubject;
        }
    }, 100);
}

// ============================================================================
// CONVERSATIONS MANAGEMENT
// ============================================================================

async function loadConversations() {
    try {
        const response = await authFetch('/api/v1/chat/conversations?limit=50');
        if (!response.ok) return;
        const data = await response.json();
        const conversations = data.conversations || data;
        const container = document.getElementById('conversationsList');
        if (!container) return;
        if (!conversations || conversations.length === 0) {
            container.innerHTML = `<div class="empty-state">No conversations yet.<br>Start chatting to create one!</div>`;
            return;
        }
        container.innerHTML = conversations.map(conv => `
            <div class="conversation-item ${conv.id === conversationId ? 'active' : ''}" 
                 onclick="loadConversation('${conv.id}')">
                <div class="conversation-title" ondblclick="renameConversation('${conv.id}', this)">
                    ${escapeHtml(conv.title || 'New Conversation')}
                </div>
                <div class="conversation-meta">${new Date(conv.updated_at).toLocaleDateString()}</div>
                <div class="conversation-actions">
                    <button class="conv-action-btn" onclick="event.stopPropagation(); renameConversation('${conv.id}', this.closest('.conversation-item').querySelector('.conversation-title'))" title="Rename">✏️</button>
                    <button class="conv-action-btn" onclick="event.stopPropagation(); showExportMenu('${conv.id}', this)" title="Export">📥</button>
                    <button class="conv-action-btn" onclick="event.stopPropagation(); deleteConversation('${conv.id}')" title="Delete">🗑️</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading conversations:', error);
    }
}

async function loadConversation(id) {
    try {
        const response = await authFetch('/api/v1/chat/conversations/' + id);
        if (!response.ok) return;
        const data = await response.json();
        conversationId = id;

        // #25: Load conversation mode and update UI
        const convMode = data.mode || 'normal';
        updateModePillUI(convMode);

        const container = document.getElementById('messagesContainer');
        container.innerHTML = '';
        hideWelcome();
        if (data.messages && data.messages.length > 0) {
            data.messages.forEach(msg => {
                if (msg.role === 'user') addUserMessage(msg.content, msg.id, false);
                else addAssistantMessage(msg.content, msg.id);
            });
        }
        loadConversations();
        closeSidebarOnMobile();
        scrollToBottom();
        updateMemoryIndicator();
    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

function newChat() { startNewConversation(); }

function startNewConversation() {
    conversationId = null;
    lastFailedMessage = null;
    const container = document.getElementById('messagesContainer');
    if (container) container.innerHTML = '';
    showWelcome();
    loadConversations();
    closeSidebarOnMobile();
    updateMemoryIndicator(0);

    // #25: Reset mode to normal on new chat
    updateModePillUI('normal');

    const input = document.getElementById('messageInput');
    if (input) input.focus();
}

async function deleteConversation(id) {
    if (!confirm('Delete this conversation?')) return;
    try {
        await authFetch('/api/v1/chat/conversations/' + id, { method: 'DELETE' });
        if (id === conversationId) startNewConversation();
        else loadConversations();
    } catch (error) {
        console.error('Error deleting conversation:', error);
    }
}

async function renameConversation(id, element) {
    const currentTitle = element.textContent.trim();
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'title-input';
    input.value = currentTitle;
    element.textContent = '';
    element.appendChild(input);
    input.focus();
    input.select();
    const saveTitle = async () => {
        const newTitle = input.value.trim() || currentTitle;
        element.textContent = newTitle;
        if (newTitle !== currentTitle) {
            try {
                await authFetch('/api/v1/chat/conversations/' + id + '/title', {
                    method: 'PATCH',
                    body: JSON.stringify({ title: newTitle })
                });
                loadConversations();
            } catch (error) {
                console.error('Error renaming:', error);
                element.textContent = currentTitle;
            }
        }
    };
    input.addEventListener('blur', saveTitle);
    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') input.blur(); });
    input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { input.value = currentTitle; input.blur(); } });
}

// ============================================================================
// MESSAGE DISPLAY
// ============================================================================

function addUserMessage(text, messageId = null, scroll = true) {
    hideWelcome();
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    if (messageId) messageDiv.dataset.messageId = messageId;
    const initial = getUserInitial();
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar user avatar-initials">${initial}</div>
            <div class="sender-name">You</div>
        </div>
        <div class="message-content">${escapeHtml(text)}</div>
        <div class="message-edit-actions">
            <button class="edit-msg-btn" onclick="editMessage(this)" title="Edit message">✏️</button>
            <button class="delete-msg-btn" onclick="deleteMessage('${messageId}', this)" title="Delete message">🗑️</button>
        </div>
    `;
    container.appendChild(messageDiv);
    if (scroll) scrollToBottom();
}

function addAssistantMessage(text, messageId = null, isHtml = false) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    if (messageId) messageDiv.dataset.messageId = messageId;
    const renderedContent = isHtml ? text : renderMarkdown(text);
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content markdown-body">${renderedContent}</div>
        ${messageId ? `
        <div class="message-actions">
            <button class="regenerate-btn" onclick="regenerateResponse('${messageId}')">🔄 Regenerate</button>
        </div>
        <div class="feedback-buttons">
            <button class="feedback-btn thumbs-up" onclick="submitFeedback('${messageId}', 1)" title="Good response">👍 Helpful</button>
            <button class="feedback-btn thumbs-down" onclick="submitFeedback('${messageId}', -1)" title="Bad response">👎 Not helpful</button>
        </div>
        ` : ''}
    `;
    container.appendChild(messageDiv);
    const contentDiv = messageDiv.querySelector('.message-content');
    if (contentDiv) highlightCodeBlocks(contentDiv);
    scrollToBottom();
    setTimeout(addRunButtons, 100);
}

// ============================================================================
// LOADING INDICATOR — #16
// ============================================================================

function addTypingIndicator(statusText = 'Thinking...') {
    removeTypingIndicator();
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = 'typing-indicator';
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="loading-state">
            <div class="loading-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
            <span class="loading-status" id="loadingStatus">${escapeHtml(statusText)}</span>
        </div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
}

function updateLoadingStatus(text) {
    const statusEl = document.getElementById('loadingStatus');
    if (statusEl) statusEl.textContent = text;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

// ============================================================================
// ERROR MESSAGE — #16
// ============================================================================

function addErrorMessage(errorText, retriable = true) {
    removeTypingIndicator();
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant error-message';
    messageDiv.id = 'error-message';
    const retryBtns = retriable ? `
        <div class="error-actions">
            <button class="retry-btn-inline" onclick="retryLastMessage()" title="Retry">🔄 Retry</button>
        </div>
        <div class="retry-below">
            <button class="retry-btn-below" onclick="retryLastMessage()">🔄 Try again</button>
        </div>
    ` : '';
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant error-avatar">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="error-content">
            <div class="error-icon">⚠️</div>
            <div class="error-text">${escapeHtml(errorText)}</div>
            ${retryBtns}
        </div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
}

function retryLastMessage() {
    if (!lastFailedMessage) return;
    const errMsg = document.getElementById('error-message');
    if (errMsg) errMsg.remove();
    const input = document.getElementById('messageInput');
    if (input) { input.value = lastFailedMessage; sendMessage(); }
}

// ============================================================================
// REAL STREAMING
// ============================================================================

function createStreamingMessage() {
    removeTypingIndicator();
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    const contentId = 'stream-' + Date.now();
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content markdown-body" id="${contentId}">
            <span class="streaming-cursor"></span>
        </div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
    return { messageDiv, contentId };
}

function finalizeStreamingMessage(messageDiv, contentId, fullText, messageId) {
    const contentDiv = document.getElementById(contentId);
    if (!contentDiv) return;
    contentDiv.innerHTML = renderMarkdown(fullText);
    highlightCodeBlocks(contentDiv);
    if (messageId) {
        messageDiv.dataset.messageId = messageId;
        const actionsHtml = `
            <div class="message-actions">
                <button class="regenerate-btn" onclick="regenerateResponse('${messageId}')">🔄 Regenerate</button>
            </div>
            <div class="feedback-buttons">
                <button class="feedback-btn thumbs-up" onclick="submitFeedback('${messageId}', 1)">👍 Helpful</button>
                <button class="feedback-btn thumbs-down" onclick="submitFeedback('${messageId}', -1)">👎 Not helpful</button>
            </div>
        `;
        messageDiv.insertAdjacentHTML('beforeend', actionsHtml);
    }
    setTimeout(addRunButtons, 100);
    scrollToBottom();
    updateMemoryIndicator();
}

function streamAssistantMessage(text, messageId = null) {
    removeTypingIndicator();
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    if (messageId) messageDiv.dataset.messageId = messageId;
    const contentId = 'content-' + Date.now();
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content markdown-body" id="${contentId}"></div>
        ${messageId ? `
        <div class="message-actions">
            <button class="regenerate-btn" onclick="regenerateResponse('${messageId}')">🔄 Regenerate</button>
        </div>
        <div class="feedback-buttons">
            <button class="feedback-btn thumbs-up" onclick="submitFeedback('${messageId}', 1)">👍 Helpful</button>
            <button class="feedback-btn thumbs-down" onclick="submitFeedback('${messageId}', -1)">👎 Not helpful</button>
        </div>
        ` : ''}
    `;
    container.appendChild(messageDiv);
    const contentDiv = document.getElementById(contentId);
    let index = 0;
    let rawText = '';
    const cursor = document.createElement('span');
    cursor.className = 'streaming-cursor';
    contentDiv.appendChild(cursor);
    function typeNextChar() {
        if (index < text.length) {
            rawText += text[index];
            index++;
            contentDiv.textContent = rawText;
            contentDiv.appendChild(cursor);
            scrollToBottom();
            let delay = 15;
            if (text[index - 1] === ' ') delay = 5;
            else if (['.', '!', '?', ','].includes(text[index - 1])) delay = 60;
            setTimeout(typeNextChar, delay);
        } else {
            cursor.remove();
            contentDiv.innerHTML = renderMarkdown(rawText);
            highlightCodeBlocks(contentDiv);
            isStreaming = false;
            setTimeout(addRunButtons, 100);
            scrollToBottom();
            updateMemoryIndicator();
        }
    }
    isStreaming = true;
    typeNextChar();
}

function streamTextIntoElement(text, element) {
    let index = 0;
    let rawText = '';
    element.style.opacity = '1';
    function typeNextChar() {
        if (index < text.length) {
            rawText += text[index];
            index++;
            element.textContent = rawText;
            let delay = 15;
            if (text[index - 1] === ' ') delay = 5;
            else if (['.', '!', '?'].includes(text[index - 1])) delay = 80;
            setTimeout(typeNextChar, delay);
        } else {
            element.innerHTML = renderMarkdown(rawText);
            highlightCodeBlocks(element);
        }
    }
    typeNextChar();
}

function addFileMessage(files) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    const fileList = files.map(f => `📎 ${escapeHtml(f.filename)}`).join('<br>');
    const initial = getUserInitial();
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar user avatar-initials">${initial}</div>
            <div class="sender-name">You</div>
        </div>
        <div class="message-content">${fileList}</div>
    `;
    container.appendChild(messageDiv);
    scrollToBottom();
}

// ============================================================================
// FILE UPLOAD
// ============================================================================

function triggerFileUpload() {
    const input = document.getElementById('fileInput');
    if (input) input.click();
}

function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    files.forEach(file => {
        if (!attachedFiles.find(f => f.name === file.name)) attachedFiles.push(file);
    });
    displayAttachedFiles();
    event.target.value = '';
}

function displayAttachedFiles() {
    var container = document.getElementById('attachedFilesContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'attachedFilesContainer';
        container.className = 'attached-files-container';
        const inputArea = document.querySelector('.input-area');
        if (inputArea) inputArea.insertBefore(container, inputArea.firstChild);
    }
    if (attachedFiles.length === 0) {
        container.innerHTML = '';
        container.style.display = 'none';
        return;
    }
    container.style.display = 'flex';
    container.innerHTML = attachedFiles.map((file, index) => `
        <div class="attached-file">
            <span class="file-icon">📎</span>
            <span class="file-name">${escapeHtml(file.name)}</span>
            <button class="remove-file" onclick="removeAttachedFile(${index})">×</button>
        </div>
    `).join('');
}

function removeAttachedFile(index) {
    attachedFiles.splice(index, 1);
    displayAttachedFiles();
}

async function uploadFiles() {
    if (attachedFiles.length === 0) return null;
    const uploadedFiles = [];
    for (const file of attachedFiles) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const token = getAccessToken();
            const headers = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE}/api/v1/files/upload`, {
                method: 'POST', headers, body: formData
            });
            if (response.ok) {
                const data = await response.json();
                uploadedFiles.push({ file_id: data.file_id, filename: file.name });
            }
        } catch (error) {
            console.error('Upload error:', error);
        }
    }
    return uploadedFiles.length > 0 ? uploadedFiles : null;
}

// ============================================================================
// CODE EXECUTION
// ============================================================================

function detectCodeExecution(message) {
    const explicitPatterns = [
        /^run[:\s]/i, /^execute[:\s]/i, /run this code/i, /execute this code/i,
        /run the following/i, /please run/i, /can you run/i, /^\/run\s/i
    ];
    if (explicitPatterns.some(p => p.test(message))) return true;
    if (/```[\s\S]*```/.test(message)) return true;
    const lines = message.trim().split('\n');
    const isQuestion = /^(what|how|why|when|where|who|can|could|would|should|explain|tell|help|write|create|build|make|show|give|suggest|describe|compare)/i.test(message);
    if (isQuestion) return false;
    const pythonPatterns = [
        /^print\s*\(/, /^import\s+\w/, /^from\s+\w+\s+import/, /^def\s+\w+\s*\(/,
        /^class\s+\w+/, /^for\s+\w+\s+in\s+/, /^while\s+/, /^if\s+.+:/,
        /^\w+\s*=\s*.+/, /^\[.*\]$/, /^\{.*\}$/, /^len\s*\(/, /^sum\s*\(/,
        /^range\s*\(/, /^sorted\s*\(/, /^input\s*\(/, /^open\s*\(/, /^try\s*:/, /^with\s+/,
    ];
    const firstLine = lines[0].trim();
    if (pythonPatterns.some(p => p.test(firstLine))) return true;
    if (lines.length >= 3) {
        let codeLineCount = 0;
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed === '') continue;
            if (pythonPatterns.some(p => p.test(trimmed)) ||
                /^\s+/.test(line) || trimmed.endsWith(':') || trimmed.startsWith('#') ||
                trimmed.startsWith('return ') || trimmed.startsWith('elif ') ||
                trimmed.startsWith('else:') || trimmed.startsWith('except') ||
                trimmed.startsWith('finally:')) {
                codeLineCount++;
            }
        }
        if (codeLineCount >= lines.length * 0.6) return true;
    }
    return false;
}

function extractCodeFromMessage(message) {
    const pythonBlock = message.match(/```python\s*([\s\S]*?)\s*```/);
    if (pythonBlock) return pythonBlock[1].trim();
    const codeBlock = message.match(/```\s*([\s\S]*?)\s*```/);
    if (codeBlock) return codeBlock[1].trim();
    const runMatch = message.match(/(?:^\/run\s+|^run[:\s]+|^execute[:\s]+)([\s\S]*)/i);
    if (runMatch) return runMatch[1].trim();
    const phraseMatch = message.match(/(?:run this code|execute this code|run the following|please run|can you run)[:\s]*([\s\S]*)/i);
    if (phraseMatch && phraseMatch[1].trim()) return phraseMatch[1].trim();
    return message.trim();
}

async function executeCode(code) {
    try {
        const response = await authFetch('/api/v1/code/execute', {
            method: 'POST',
            body: JSON.stringify({ code: code, extract_from_message: false })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Code execution failed');
        }
        return await response.json();
    } catch (error) {
        console.error('Code execution error:', error);
        return { success: false, output: '', error: error.message, execution_time: 0 };
    }
}

function formatCodeResult(result) {
    const statusIcon = result.success ? '✅' : '❌';
    const statusText = result.success ? 'Success' : 'Error';
    const timeText = `${(result.execution_time * 1000).toFixed(1)}ms`;
    let html = `
        <div class="code-result ${result.success ? 'success' : 'error'}">
            <div class="code-result-header">
                <span class="code-result-status">${statusIcon} ${statusText}</span>
                <span class="code-result-time">⏱️ ${timeText}</span>
            </div>
    `;
    if (result.output) {
        html += `<div class="code-result-section"><div class="code-result-label">OUTPUT:</div><pre class="code-result-output">${escapeHtml(result.output)}</pre></div>`;
    }
    if (result.error) {
        html += `<div class="code-result-section"><div class="code-result-label">Error:</div><pre class="code-result-error">${escapeHtml(result.error)}</pre></div>`;
    }
    if (result.image) {
        html += `<div class="code-result-section"><div class="code-result-label">📊 Plot:</div><img src="data:image/png;base64,${result.image}" style="max-width:100%; border-radius:8px; margin-top:8px; display:block;" alt="matplotlib plot" /></div>`;
    }
    if (!result.output && !result.error && result.success && !result.image) {
        html += `<div class="code-result-section"><div class="code-result-output empty">Code executed successfully (no output)</div></div>`;
    }
    html += '</div>';
    return html;
}

function addRunButtons() {
    document.querySelectorAll('.message-content pre').forEach(pre => {
        if (pre.querySelector('.run-code-btn')) return;
        const codeElement = pre.querySelector('code') || pre;
        const code = codeElement.textContent;
        const isPythonLike = 
            code.includes('print(') || code.includes('def ') || code.includes('class ') ||
            code.includes('import ') || code.includes('for ') || code.includes('while ') ||
            code.includes('if ') || code.includes(' = ') || /^\s*\w+\s*=/.test(code);
        if (isPythonLike && code.trim().length > 0) {
            const copyBtn = document.createElement('button');
            copyBtn.className = 'copy-code-btn';
            copyBtn.innerHTML = '📋 Copy';
            copyBtn.onclick = (e) => { e.stopPropagation(); copyToClipboard(codeElement.textContent, copyBtn, '📋 Copy'); };
            const runBtn = document.createElement('button');
            runBtn.className = 'run-code-btn';
            runBtn.innerHTML = '▶️ Run';
            runBtn.onclick = async (e) => {
                e.stopPropagation();
                runBtn.disabled = true;
                runBtn.innerHTML = '⏳ Running...';
                const result = await executeCode(code);
                const existingResult = pre.parentElement.querySelector('.code-result');
                if (existingResult) existingResult.remove();
                const resultDiv = document.createElement('div');
                resultDiv.innerHTML = formatCodeResult(result);
                pre.insertAdjacentElement('afterend', resultDiv.firstElementChild);
                runBtn.disabled = false;
                runBtn.innerHTML = '▶️ Run';
            };
            pre.style.position = 'relative';
            pre.appendChild(copyBtn);
            pre.appendChild(runBtn);
        }
    });
}

// ============================================================================
// EXPORT CONVERSATIONS
// ============================================================================

async function exportConversation(convId, format = 'md') {
    try {
        const response = await authFetch('/api/v1/chat/conversations/' + convId + '/export?format=' + format);
        if (!response.ok) throw new Error('Export failed');
        const disposition = response.headers.get('Content-Disposition');
        let filename = `conversation.${format}`;
        if (disposition) {
            const match = disposition.match(/filename="(.+)"/);
            if (match) filename = match[1];
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Export error:', error);
        alert('Failed to export conversation.');
    }
}

async function exportAllConversations() {
    try {
        const response = await authFetch('/api/v1/chat/conversations/export/all');
        if (!response.ok) throw new Error('Bulk export failed');
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `omniai_backup_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Bulk export error:', error);
        alert('Failed to export conversations.');
    }
}

function showExportMenu(convId, buttonElement) {
    const existing = document.querySelector('.export-menu');
    if (existing) existing.remove();
    const menu = document.createElement('div');
    menu.className = 'export-menu';
    menu.innerHTML = `
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'md')">📝 Markdown (.md)</div>
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'txt')">📄 Plain Text (.txt)</div>
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'json')">📦 JSON (.json)</div>
    `;
    const rect = buttonElement.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = `${rect.bottom + 5}px`;
    menu.style.left = `${rect.left}px`;
    menu.style.zIndex = '1000';
    document.body.appendChild(menu);
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target) && e.target !== buttonElement) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 10);
}

// ============================================================================
// EDIT & DELETE MESSAGES
// ============================================================================

function editMessage(buttonElement) {
    const messageDiv = buttonElement.closest('.message');
    const contentDiv = messageDiv.querySelector('.message-content');
    const messageId = messageDiv.dataset.messageId;
    const originalText = contentDiv.textContent;
    contentDiv.innerHTML = `
        <textarea class="edit-textarea" rows="3">${escapeHtml(originalText)}</textarea>
        <div class="edit-actions">
            <button class="edit-save-btn" onclick="saveEdit('${messageId}', this)">💾 Save & Retry</button>
            <button class="edit-cancel-btn" onclick="cancelEdit(this, '${escapeHtml(originalText).replace(/'/g, "\\'")}')">✖ Cancel</button>
        </div>
    `;
    const textarea = contentDiv.querySelector('.edit-textarea');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}

async function saveEdit(messageId, buttonElement) {
    const messageDiv = buttonElement.closest('.message');
    const textarea = messageDiv.querySelector('.edit-textarea');
    const newContent = textarea.value.trim();
    if (!newContent) return;
    const contentDiv = messageDiv.querySelector('.message-content');
    contentDiv.textContent = newContent;
    if (messageId && messageId !== 'null') {
        try {
            await authFetch('/api/v1/messages/' + messageId, { method: 'PUT', body: JSON.stringify({ content: newContent }) });
            await authFetch('/api/v1/messages/' + messageId + '/and-after', { method: 'DELETE' });
        } catch (error) { console.error('Edit save error:', error); }
    }
    let nextSibling = messageDiv.nextElementSibling;
    while (nextSibling) {
        const toRemove = nextSibling;
        nextSibling = nextSibling.nextElementSibling;
        toRemove.remove();
    }
    addTypingIndicator();
    try {
        const response = await authFetch('/api/v1/chat', {
            method: 'POST',
            body: JSON.stringify({ message: newContent, conversation_id: conversationId, mode: currentMode })
        });
        const data = await response.json();
        if (response.ok) streamAssistantMessage(data.response, data.message_id);
        else { removeTypingIndicator(); addErrorMessage(data.detail || 'Unknown error'); }
    } catch (error) { removeTypingIndicator(); addErrorMessage('Could not connect to server.'); }
}

function cancelEdit(buttonElement, originalText) {
    const contentDiv = buttonElement.closest('.message-content');
    contentDiv.textContent = originalText;
}

async function deleteMessage(messageId, buttonElement) {
    if (!confirm('Delete this message?')) return;
    const messageDiv = buttonElement.closest('.message');
    if (messageId && messageId !== 'null') {
        try {
            await authFetch('/api/v1/messages/' + messageId, { method: 'DELETE' });
        } catch (error) { console.error('Delete error:', error); }
    }
    messageDiv.style.opacity = '0';
    messageDiv.style.transition = 'opacity 0.3s';
    setTimeout(() => messageDiv.remove(), 300);
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') { e.preventDefault(); startNewConversation(); }
    if ((e.ctrlKey || e.metaKey) && e.key === '/') { e.preventDefault(); const s = document.getElementById('searchBox'); if (s) s.focus(); }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') { e.preventDefault(); if (typeof toggleTheme === 'function') toggleTheme(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') { e.preventDefault(); if (conversationId) exportConversation(conversationId, 'md'); }
    if (e.key === 'Escape') {
        const exportMenu = document.querySelector('.export-menu'); if (exportMenu) exportMenu.remove();
        const modal = document.querySelector('.modal-overlay'); if (modal) modal.remove();
        const sidebar = document.querySelector('.sidebar'); if (sidebar && sidebar.classList.contains('open')) toggleSidebar();
    }
    if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) { e.preventDefault(); toggleShortcutsHelp(); }
});

function toggleShortcutsHelp() {
    const existing = document.querySelector('.shortcuts-modal');
    if (existing) { existing.remove(); return; }
    const modal = document.createElement('div');
    modal.className = 'shortcuts-modal modal-overlay';
    modal.innerHTML = `
        <div class="shortcuts-content">
            <h3>Keyboard Shortcuts</h3>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>N</kbd></span> <span>New conversation</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>/</kbd></span> <span>Search conversations</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>E</kbd></span> <span>Export conversation</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd></span> <span>Toggle dark mode</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Esc</kbd></span> <span>Close menus</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>?</kbd></span> <span>Show this help</span></div>
            <button class="shortcuts-close-btn" onclick="this.closest('.modal-overlay').remove()">Close</button>
        </div>
    `;
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
}

// ============================================================================
// FULL-TEXT SEARCH
// ============================================================================

var searchDebounceTimer = null;

async function searchAllMessages(query) {
    if (!query || query.trim().length < 2) { hideSearchResults(); return; }
    try {
        const response = await authFetch('/api/v1/search?q=' + encodeURIComponent(query) + '&limit=10');
        if (!response.ok) return;
        const data = await response.json();
        displaySearchResults(data.results, query);
    } catch (error) { console.error('Search error:', error); }
}

function displaySearchResults(results, query) {
    hideSearchResults();
    if (results.length === 0) return;
    const dropdown = document.createElement('div');
    dropdown.className = 'search-results-dropdown';
    dropdown.id = 'searchResultsDropdown';
    results.forEach(result => {
        const item = document.createElement('div');
        item.className = 'search-result-item';
        item.innerHTML = `
            <div class="search-result-title">${escapeHtml(result.conversation_title || 'Untitled')}</div>
            <div class="search-result-preview">${highlightSearchTerm(result.content_preview, query)}</div>
            <div class="search-result-meta">${result.role} · ${result.timestamp ? new Date(result.timestamp).toLocaleDateString() : ''}</div>
        `;
        item.onclick = () => { loadConversation(result.conversation_id); hideSearchResults(); };
        dropdown.appendChild(item);
    });
    const searchInput = document.getElementById('searchBox');
    if (searchInput) {
        searchInput.parentElement.style.position = 'relative';
        searchInput.parentElement.appendChild(dropdown);
    }
}

function hideSearchResults() {
    const existing = document.getElementById('searchResultsDropdown');
    if (existing) existing.remove();
}

function highlightSearchTerm(text, term) {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return escapeHtml(text).replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>');
}

function handleSearchInput(event) {
    const query = event.target.value.trim();
    clearTimeout(searchDebounceTimer);
    if (query.length < 2) { hideSearchResults(); return; }
    searchDebounceTimer = setTimeout(() => searchAllMessages(query), 300);
}

// ============================================================================
// MOBILE SIDEBAR TOGGLE
// ============================================================================

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('show', sidebar.classList.contains('open'));
    } else {
        sidebar.classList.toggle('hidden');
    }
}

function closeSidebarOnMobile() {
    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    }
}

// ============================================================================
// THEME TOGGLE
// ============================================================================

function toggleTheme() {
    const isLight = document.body.classList.contains('light-mode');
    const newTheme = isLight ? 'dark' : 'light';
    if (newTheme === 'light') document.body.classList.add('light-mode');
    else document.body.classList.remove('light-mode');
    localStorage.setItem('theme', newTheme);
    const themeIcon = document.getElementById('themeIcon');
    if (themeIcon) themeIcon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
}

(function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'light') document.body.classList.add('light-mode');
    const themeIcon = document.getElementById('themeIcon');
    if (themeIcon) themeIcon.textContent = savedTheme === 'dark' ? '🌙' : '☀️';
})();

// ============================================================================
// SEND MESSAGE — Real SSE streaming with Gmail detection + #25 Mode support + #26 fix
// ============================================================================

async function sendMessage() {
    if (isStreaming) return;
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message && attachedFiles.length === 0) return;

    // Gmail intent detection — #24 #25 #26 #27
    // Works in both Normal mode and Email mode — Email mode just means AI is also focused
    if (message && detectGmailIntent(message)) {
        input.value = '';
        input.style.height = 'auto';
        addUserMessage(message);
        await handleGmailMessage(message);
        return;
    }

    if (message) lastFailedMessage = message;

    var uploadedFilesList = null;
    if (attachedFiles.length > 0) {
        uploadedFilesList = await uploadFiles();
        if (uploadedFilesList === null) return;
        addFileMessage(uploadedFilesList);
        attachedFiles = [];
        displayAttachedFiles();
    }
    
    if (message) {
        addUserMessage(message);
        input.value = '';
        input.style.height = 'auto';
    } else if (!uploadedFilesList) return;
    
    if (message && detectCodeExecution(message)) {
        const code = extractCodeFromMessage(message);
        if (code) {
            addTypingIndicator('Running code...');
            const codeResult = await executeCode(code);
            removeTypingIndicator();
            const resultHtml = formatCodeResult(codeResult);
            const responseHtml = `I ran your code:\n\n<div class="code-block-wrapper"><pre><code>${escapeHtml(code)}</code></pre><button class="copy-code-btn" onclick="copyCode(this)" title="Copy code">📋 Copy</button></div>\n\n${resultHtml}`;
            addAssistantMessage(responseHtml, null, true);
            return;
        }
    }
    
    const sendButton = document.getElementById('sendButton');
    if (sendButton) sendButton.disabled = true;
    isStreaming = true;
    addTypingIndicator('Thinking...');

    try {
        const token = getAccessToken();
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const requestBody = {
            message: message || "I uploaded some files. Please analyze them.",
            conversation_id: conversationId,
            mode: currentMode  // #25: Send current mode with every message
        };
        if (uploadedFilesList && uploadedFilesList.length > 0) {
            requestBody.file_ids = uploadedFilesList.map(f => f.file_id);
        }
        const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
            method: 'POST', headers, body: JSON.stringify(requestBody)
        });
        if (!response.ok) throw new Error(`Server error ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamStarted = false;
        let messageDiv = null;
        let contentId = null;
        let rawText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;
                let event;
                try { event = JSON.parse(jsonStr); } catch { continue; }
                if (event.type === 'conversation_id') {
                    conversationId = event.conversation_id;
                    // #25: If backend returned a mode, sync the UI (in case it differs)
                    if (event.mode && event.mode !== currentMode) {
                        updateModePillUI(event.mode);
                    }
                } else if (event.type === 'status') {
                    const statusMap = {
                        'Searching web...': '🔍 Searching web...',
                        'Generating response...': '⚡ Generating...',
                        'Reading files...': '📄 Reading files...',
                    };
                    updateLoadingStatus(statusMap[event.message] || event.message);
                } else if (event.type === 'token') {
                    if (!streamStarted) {
                        const created = createStreamingMessage();
                        messageDiv = created.messageDiv;
                        contentId = created.contentId;
                        streamStarted = true;
                    }
                    rawText += event.token;
                    const contentDiv = document.getElementById(contentId);
                    if (contentDiv) {
                        contentDiv.textContent = rawText;
                        const cursor = contentDiv.querySelector('.streaming-cursor');
                        if (!cursor) {
                            const c = document.createElement('span');
                            c.className = 'streaming-cursor';
                            contentDiv.appendChild(c);
                        }
                        scrollToBottom();
                    }
                } else if (event.type === 'done') {
                    finalizeStreamingMessage(messageDiv, contentId, event.full_response || rawText, event.message_id);
                    conversationId = event.conversation_id || conversationId;
                    // #25: Sync mode from backend on done event
                    if (event.mode && event.mode !== currentMode) {
                        updateModePillUI(event.mode);
                    }
                    lastFailedMessage = null;
                    loadConversations();
                } else if (event.type === 'error') {
                    addErrorMessage(event.error || 'Something went wrong.');
                }
            }
        }
    } catch (error) {
        console.error('Stream error:', error);
        removeTypingIndicator();
        try {
            addTypingIndicator('Reconnecting...');
            const response = await authFetch('/api/v1/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: message || "I uploaded some files.",
                    conversation_id: conversationId,
                    mode: currentMode  // #25
                })
            });
            const data = await response.json();
            if (response.ok) {
                conversationId = data.conversation_id;
                if (data.mode) updateModePillUI(data.mode);
                streamAssistantMessage(data.response, data.message_id);
                lastFailedMessage = null;
                loadConversations();
            } else {
                addErrorMessage(data.detail || 'Server returned an error.');
            }
        } catch (fallbackError) {
            addErrorMessage('Could not connect to server. Check your connection and try again.');
        }
    } finally {
        isStreaming = false;
        if (sendButton) sendButton.disabled = false;
    }
}

// ============================================================================
// REGENERATE RESPONSE
// ============================================================================

async function regenerateResponse(messageId) {
    if (!conversationId || !messageId) return;
    const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
    if (!messageDiv) return;
    const contentDiv = messageDiv.querySelector('.message-content');
    const originalContent = contentDiv.innerHTML;
    contentDiv.style.opacity = '0.5';
    const buttons = messageDiv.querySelectorAll('.regenerate-btn');
    buttons.forEach(btn => btn.disabled = true);
    try {
        const response = await authFetch('/api/v1/chat/regenerate', {
            method: 'POST',
            body: JSON.stringify({ conversation_id: conversationId, message_id: messageId })
        });
        if (!response.ok) throw new Error('Regeneration failed');
        const data = await response.json();
        contentDiv.innerHTML = '';
        streamTextIntoElement(data.response, contentDiv);
    } catch (error) {
        console.error('Regeneration error:', error);
        contentDiv.innerHTML = originalContent;
        contentDiv.style.opacity = '1';
        alert('Failed to regenerate: ' + error.message);
    } finally {
        buttons.forEach(btn => btn.disabled = false);
    }
}

// ============================================================================
// FEEDBACK
// ============================================================================

async function submitFeedback(messageId, rating) {
    if (!conversationId || !messageId) return;
    try {
        const response = await authFetch('/api/v1/feedback', {
            method: 'POST',
            body: JSON.stringify({ message_id: messageId, conversation_id: conversationId, rating: rating })
        });
        if (!response.ok) throw new Error('Feedback failed');
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const thumbsUpBtn = messageDiv.querySelector('.thumbs-up');
            const thumbsDownBtn = messageDiv.querySelector('.thumbs-down');
            if (thumbsUpBtn) thumbsUpBtn.classList.remove('active');
            if (thumbsDownBtn) thumbsDownBtn.classList.remove('active');
            if (rating === 1 && thumbsUpBtn) thumbsUpBtn.classList.add('active');
            else if (thumbsDownBtn) thumbsDownBtn.classList.add('active');
        }
    } catch (error) { console.error('Feedback error:', error); }
}

// ============================================================================
// COPY CODE
// ============================================================================

function copyCode(button) {
    const wrapper = button.closest('.code-block-wrapper') || button.closest('pre');
    const codeEl = wrapper.querySelector('code') || wrapper.querySelector('pre');
    const code = codeEl ? codeEl.textContent : '';
    copyToClipboard(code, button, '📋 Copy');
}