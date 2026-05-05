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
// #37 — CUSTOM SYSTEM PROMPT STATE
// ============================================================================

// Whether the user has a custom system prompt set on the server.
// Updated on init() and after save/clear in the settings panel.
// Used to show/hide the "Custom prompt active" badge in the input area.
var customPromptActive = false;

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

    updateModePillUI('normal');

    setTimeout(() => {
        injectGmailButton();
        initGmail();
    }, 1500);

    setTimeout(() => {
        injectCalendarButton();
        initCalendar();
    }, 1600);
    
    // #37 — Settings: inject gear icon, fetch current custom prompt state
    setTimeout(() => {
        injectSettingsButton();
        initSettings();
    }, 1700);
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

    document.querySelectorAll('.mode-pill').forEach(pill => {
        if (pill.dataset.mode === mode) {
            pill.classList.add('active');
        } else {
            pill.classList.remove('active');
        }
    });

    const input = document.getElementById('messageInput');
    if (input && MODE_PLACEHOLDERS[mode]) {
        input.placeholder = MODE_PLACEHOLDERS[mode];
    }

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

    updateModePillUI(mode);

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
// #37 — CUSTOM SYSTEM PROMPTS — Settings panel + badge
// User can save a custom system prompt that prepends to every chat.
// Stored on the server at users.preferences.custom_system_prompt.
// ============================================================================

const CUSTOM_PROMPT_MAX_CHARS = 2000;

/**
 * Inject the gear icon into the sidebar header.
 * Sits next to the "New Chat" button. Visible only when sidebar is rendered.
 */
function injectSettingsButton() {
    if (document.getElementById('settingsBtn')) return;
    
    // Find a stable anchor — try sidebar header area first, fall back to top-bar
    const sidebar = document.getElementById('sidebar');
    const newChatBtn = sidebar ? sidebar.querySelector('button') : null;
    
    const btn = document.createElement('button');
    btn.id = 'settingsBtn';
    btn.className = 'settings-btn';
    btn.innerHTML = '⚙️';
    btn.title = 'Settings — customize AI behavior';
    btn.onclick = openSettingsPanel;
    btn.style.cssText = `
        background: transparent;
        border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.12));
        color: var(--text-primary, #f0f0f0);
        font-size: 18px;
        cursor: pointer;
        padding: 6px 10px;
        border-radius: 8px;
        margin-left: 8px;
        transition: background 0.15s ease, border-color 0.15s ease;
        line-height: 1;
    `;
    btn.onmouseenter = () => {
        btn.style.background = 'rgba(255, 255, 255, 0.06)';
    };
    btn.onmouseleave = () => {
        btn.style.background = 'transparent';
    };
    
    // Try a few common anchor locations so we adapt to whatever the HTML uses
    if (newChatBtn && newChatBtn.parentElement) {
        newChatBtn.parentElement.appendChild(btn);
        return;
    }
    
    const sidebarHeader = sidebar ? sidebar.querySelector('.sidebar-header') : null;
    if (sidebarHeader) {
        sidebarHeader.appendChild(btn);
        return;
    }
    
    // Last resort: float it bottom-right of viewport
    btn.style.position = 'fixed';
    btn.style.bottom = '20px';
    btn.style.right = '20px';
    btn.style.zIndex = '500';
    document.body.appendChild(btn);
}

/**
 * On page load, fetch the current custom prompt state so we know
 * whether to show the badge.
 */
async function initSettings() {
    try {
        const response = await authFetch('/api/v1/settings/system-prompt');
        if (response.ok) {
            const data = await response.json();
            customPromptActive = !!data.is_set;
            updateCustomPromptBadge();
        }
    } catch (e) {
        // Anonymous user or auth issue — leave badge off, no harm done
        console.log('Settings init: not authenticated or endpoint unavailable');
    }
}

/**
 * Show/hide the "Custom prompt active" badge in the input area.
 * Sits next to the memory indicator (#17) so they stack vertically.
 */
function updateCustomPromptBadge() {
    let badge = document.getElementById('customPromptBadge');
    
    if (!customPromptActive) {
        if (badge) badge.style.display = 'none';
        return;
    }
    
    if (!badge) {
        const wrapper = document.querySelector('.input-wrapper');
        if (!wrapper) return;
        badge = document.createElement('div');
        badge.id = 'customPromptBadge';
        badge.style.cssText = `
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11.5px;
            opacity: 0.75;
            padding: 4px 10px;
            margin-bottom: 6px;
            color: var(--accent-primary, #d97706);
            background: var(--bg-tertiary, rgba(217, 119, 6, 0.08));
            border-radius: 12px;
            width: fit-content;
            cursor: pointer;
            transition: opacity 0.15s ease;
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
        `;
        badge.onmouseenter = () => { badge.style.opacity = '1'; };
        badge.onmouseleave = () => { badge.style.opacity = '0.75'; };
        badge.onclick = openSettingsPanel;
        badge.title = 'Click to view or edit your custom prompt';
        wrapper.insertBefore(badge, wrapper.firstChild);
    }
    
    badge.innerHTML = `<span>✨</span><span>Custom prompt active</span><span style="opacity: 0.5;">·</span><span style="text-decoration: underline; opacity: 0.85;">edit</span>`;
    badge.style.display = 'flex';
}

/**
 * Open the settings panel modal. Loads current prompt from server,
 * shows textarea + char counter + save/clear/cancel buttons.
 */
async function openSettingsPanel() {
    // Remove any existing panel first
    const existing = document.querySelector('.settings-panel-overlay');
    if (existing) existing.remove();
    
    // ----- Overlay -----
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay settings-panel-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(4px);
        -webkit-backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 16px;
        animation: settingsFadeIn 0.18s ease-out;
    `;
    
    // ----- Panel -----
    const panel = document.createElement('div');
    panel.className = 'settings-panel';
    panel.style.cssText = `
        background: var(--bg-secondary, #1a1a1a);
        color: var(--text-primary, #f0f0f0);
        border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.08));
        border-radius: 16px;
        max-width: 620px;
        width: 100%;
        max-height: 90vh;
        overflow-y: auto;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        animation: settingsSlideUp 0.22s cubic-bezier(0.16, 1, 0.3, 1);
    `;
    
    // ----- Header -----
    const header = document.createElement('div');
    header.style.cssText = `
        padding: 24px 28px 16px;
        border-bottom: 1px solid var(--border-primary, rgba(255, 255, 255, 0.06));
        display: flex;
        align-items: center;
        justify-content: space-between;
    `;
    header.innerHTML = `
        <div>
            <div style="font-size: 18px; font-weight: 600; line-height: 1.3;">Settings</div>
            <div style="font-size: 13px; opacity: 0.65; margin-top: 4px;">Customize how OmniAI responds to you</div>
        </div>
        <button id="settingsCloseBtn" style="
            background: transparent;
            border: none;
            color: var(--text-primary, #f0f0f0);
            font-size: 22px;
            cursor: pointer;
            opacity: 0.6;
            padding: 4px 10px;
            border-radius: 6px;
            transition: opacity 0.15s, background 0.15s;
        " title="Close (Esc)">✕</button>
    `;
    
    // ----- Body — Custom System Prompt section -----
    const body = document.createElement('div');
    body.style.cssText = `padding: 24px 28px;`;
    body.innerHTML = `
        <div style="margin-bottom: 18px;">
            <div style="font-size: 14.5px; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                <span>✨ Custom system prompt</span>
                <span style="font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 4px; background: var(--accent-primary, #d97706); color: white; letter-spacing: 0.05em;">PRO</span>
            </div>
            <div style="font-size: 12.5px; opacity: 0.7; line-height: 1.5;">
                Tell OmniAI how to behave — your tone, style, expertise focus. Applied to every chat across all modes.
            </div>
        </div>
        
        <textarea id="customPromptInput" placeholder="Examples:
- Always respond in Hinglish, casual tone
- You're my Indian tax consultant. GST-first thinking.
- Be brutally honest. No fluff. No 'I hope this helps' endings.
- Format all code in Python with type hints" style="
            width: 100%;
            min-height: 180px;
            max-height: 320px;
            background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
            color: var(--text-primary, #f0f0f0);
            border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.12));
            border-radius: 10px;
            padding: 12px 14px;
            font-size: 13.5px;
            font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
            line-height: 1.55;
            resize: vertical;
            box-sizing: border-box;
            outline: none;
            transition: border-color 0.15s;
        "></textarea>
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; font-size: 12px;">
            <div id="settingsHint" style="opacity: 0.55;">
                Tip: Be specific. The more concrete your instructions, the better.
            </div>
            <div id="settingsCharCount" style="opacity: 0.7; font-variant-numeric: tabular-nums;">
                0 / ${CUSTOM_PROMPT_MAX_CHARS}
            </div>
        </div>
        
        <div id="settingsStatusMessage" style="
            margin-top: 14px;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            display: none;
        "></div>
    `;
    
    // ----- Footer / actions -----
    const footer = document.createElement('div');
    footer.style.cssText = `
        padding: 16px 28px 22px;
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        flex-wrap: wrap;
        border-top: 1px solid var(--border-primary, rgba(255, 255, 255, 0.06));
        background: var(--bg-tertiary, rgba(255, 255, 255, 0.02));
    `;
    
    const clearBtn = document.createElement('button');
    clearBtn.id = 'settingsClearBtn';
    clearBtn.textContent = 'Clear prompt';
    clearBtn.style.cssText = `
        background: transparent;
        color: var(--text-primary, #f0f0f0);
        border: 1px solid rgba(239, 68, 68, 0.4);
        padding: 9px 16px;
        border-radius: 8px;
        font-size: 13.5px;
        font-weight: 500;
        font-family: inherit;
        cursor: pointer;
        margin-right: auto;
        opacity: 0.85;
        transition: background 0.15s, opacity 0.15s;
    `;
    clearBtn.onmouseenter = () => {
        clearBtn.style.background = 'rgba(239, 68, 68, 0.08)';
        clearBtn.style.opacity = '1';
    };
    clearBtn.onmouseleave = () => {
        clearBtn.style.background = 'transparent';
        clearBtn.style.opacity = '0.85';
    };
    
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'settingsCancelBtn';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = `
        background: transparent;
        color: var(--text-primary, #f0f0f0);
        border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.15));
        padding: 9px 18px;
        border-radius: 8px;
        font-size: 13.5px;
        font-weight: 500;
        font-family: inherit;
        cursor: pointer;
        transition: background 0.15s;
    `;
    cancelBtn.onmouseenter = () => { cancelBtn.style.background = 'rgba(255, 255, 255, 0.06)'; };
    cancelBtn.onmouseleave = () => { cancelBtn.style.background = 'transparent'; };
    
    const saveBtn = document.createElement('button');
    saveBtn.id = 'settingsSaveBtn';
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = `
        background: var(--accent-primary, #d97706);
        color: white;
        border: none;
        padding: 9px 20px;
        border-radius: 8px;
        font-size: 13.5px;
        font-weight: 600;
        font-family: inherit;
        cursor: pointer;
        transition: opacity 0.15s;
    `;
    saveBtn.onmouseenter = () => { saveBtn.style.opacity = '0.9'; };
    saveBtn.onmouseleave = () => { saveBtn.style.opacity = '1'; };
    
    footer.appendChild(clearBtn);
    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);
    
    // ----- Inject keyframes (once) -----
    if (!document.getElementById('settingsPanelKeyframes')) {
        const styleTag = document.createElement('style');
        styleTag.id = 'settingsPanelKeyframes';
        styleTag.textContent = `
            @keyframes settingsFadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes settingsSlideUp {
                from { opacity: 0; transform: translateY(12px); }
                to { opacity: 1; transform: translateY(0); }
            }
            #customPromptInput:focus {
                border-color: var(--accent-primary, #d97706) !important;
            }
        `;
        document.head.appendChild(styleTag);
    }
    
    // ----- Assemble -----
    panel.appendChild(header);
    panel.appendChild(body);
    panel.appendChild(footer);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    
    // ----- Wire up state and handlers -----
    const textarea = document.getElementById('customPromptInput');
    const charCount = document.getElementById('settingsCharCount');
    const statusMsg = document.getElementById('settingsStatusMessage');
    const closeBtn = document.getElementById('settingsCloseBtn');
    
    function showStatus(message, type) {
        statusMsg.textContent = message;
        statusMsg.style.display = 'block';
        if (type === 'success') {
            statusMsg.style.background = 'rgba(34, 197, 94, 0.12)';
            statusMsg.style.color = '#22c55e';
            statusMsg.style.border = '1px solid rgba(34, 197, 94, 0.3)';
        } else if (type === 'error') {
            statusMsg.style.background = 'rgba(239, 68, 68, 0.12)';
            statusMsg.style.color = '#ef4444';
            statusMsg.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        } else {
            statusMsg.style.background = 'rgba(255, 255, 255, 0.04)';
            statusMsg.style.color = 'var(--text-primary, #f0f0f0)';
            statusMsg.style.border = '1px solid rgba(255, 255, 255, 0.08)';
        }
    }
    
    function hideStatus() {
        statusMsg.style.display = 'none';
    }
    
    function updateCharCount() {
        const len = textarea.value.length;
        charCount.textContent = `${len} / ${CUSTOM_PROMPT_MAX_CHARS}`;
        if (len > CUSTOM_PROMPT_MAX_CHARS) {
            charCount.style.color = '#ef4444';
            saveBtn.disabled = true;
            saveBtn.style.opacity = '0.5';
            saveBtn.style.cursor = 'not-allowed';
        } else {
            charCount.style.color = '';
            saveBtn.disabled = false;
            saveBtn.style.opacity = '1';
            saveBtn.style.cursor = 'pointer';
        }
    }
    
    textarea.addEventListener('input', () => {
        updateCharCount();
        hideStatus();
    });
    
    // Load current value from server
    showStatus('Loading...', 'info');
    try {
        const response = await authFetch('/api/v1/settings/system-prompt');
        if (response.ok) {
            const data = await response.json();
            textarea.value = data.prompt || '';
            updateCharCount();
            hideStatus();
            // If nothing set yet, show clearBtn as disabled-looking
            if (!data.is_set) {
                clearBtn.style.opacity = '0.4';
                clearBtn.style.cursor = 'default';
                clearBtn.disabled = true;
            }
        } else if (response.status === 401) {
            showStatus('Please log in to save your custom prompt.', 'error');
            saveBtn.disabled = true;
            saveBtn.style.opacity = '0.5';
            clearBtn.disabled = true;
            clearBtn.style.opacity = '0.4';
        } else {
            showStatus('Could not load current prompt. You can still create a new one below.', 'error');
        }
    } catch (e) {
        showStatus('Could not connect to server. ' + e.message, 'error');
    }
    
    // Focus the textarea after loading
    // #38 — Render the memory section below the custom prompt section
    await renderMemorySection(body);
    setTimeout(() => textarea.focus(), 100);
    
    // ----- Save handler -----
    saveBtn.onclick = async () => {
        const prompt = textarea.value.trim();
        if (!prompt) {
            showStatus('Prompt cannot be empty. Use "Clear prompt" to remove your existing one.', 'error');
            return;
        }
        if (prompt.length > CUSTOM_PROMPT_MAX_CHARS) {
            showStatus(`Prompt is too long. Maximum is ${CUSTOM_PROMPT_MAX_CHARS} characters.`, 'error');
            return;
        }
        
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        saveBtn.style.opacity = '0.7';
        showStatus('Saving...', 'info');
        
        try {
            const response = await authFetch('/api/v1/settings/system-prompt', {
                method: 'PUT',
                body: JSON.stringify({ prompt: prompt })
            });
            
            if (response.ok) {
                customPromptActive = true;
                updateCustomPromptBadge();
                showStatus('✓ Saved. Your custom prompt is now active in every chat.', 'success');
                clearBtn.disabled = false;
                clearBtn.style.opacity = '0.85';
                clearBtn.style.cursor = 'pointer';
                setTimeout(() => {
                    overlay.remove();
                }, 900);
            } else {
                let errMsg = 'Could not save prompt.';
                try {
                    const errData = await response.json();
                    if (errData.detail) errMsg = errData.detail;
                } catch (e) { /* swallow */ }
                showStatus('❌ ' + errMsg, 'error');
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save';
                saveBtn.style.opacity = '1';
            }
        } catch (e) {
            showStatus('❌ Network error: ' + e.message, 'error');
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
            saveBtn.style.opacity = '1';
        }
    };
    
    // ----- Clear handler -----
    clearBtn.onclick = async () => {
        if (clearBtn.disabled) return;
        if (!confirm('Clear your custom prompt? OmniAI will go back to default behavior.')) return;
        
        clearBtn.disabled = true;
        clearBtn.textContent = 'Clearing...';
        showStatus('Clearing...', 'info');
        
        try {
            const response = await authFetch('/api/v1/settings/system-prompt', {
                method: 'DELETE'
            });
            
            if (response.ok) {
                textarea.value = '';
                updateCharCount();
                customPromptActive = false;
                updateCustomPromptBadge();
                showStatus('✓ Cleared. OmniAI is back to default behavior.', 'success');
                clearBtn.style.opacity = '0.4';
                clearBtn.style.cursor = 'default';
                clearBtn.textContent = 'Clear prompt';
                setTimeout(() => {
                    overlay.remove();
                }, 900);
            } else {
                showStatus('❌ Could not clear prompt.', 'error');
                clearBtn.disabled = false;
                clearBtn.textContent = 'Clear prompt';
            }
        } catch (e) {
            showStatus('❌ Network error: ' + e.message, 'error');
            clearBtn.disabled = false;
            clearBtn.textContent = 'Clear prompt';
        }
    };
    
    // ----- Dismiss handlers -----
    const dismiss = () => overlay.remove();
    cancelBtn.onclick = dismiss;
    closeBtn.onclick = dismiss;
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) dismiss();
    });
    
    // Esc to close — handled by the existing global Escape handler that
    // closes any .modal-overlay
}

// ============================================================================
// CALENDAR INTEGRATION — #29
// ============================================================================

var calendarConnected = false;
var calendarEmail = '';

async function initCalendar() {
    try {
        const response = await authFetch('/api/v1/calendar/status');
        if (response.ok) {
            const data = await response.json();
            calendarConnected = data.connected;
            calendarEmail = data.email || '';
            updateCalendarButton();
        }
    } catch (e) {
        console.log('Calendar status check failed:', e);
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('calendar_connected') === 'true') {
        const email = params.get('calendar_email') || '';
        calendarConnected = true;
        calendarEmail = email;
        updateCalendarButton();
        addAssistantMessage(`✅ Google Calendar connected! (${email})\n\nYou can now:\n- "What's on my calendar today?"\n- "Book a meeting tomorrow at 3pm"\n- "Find me a free slot this week"\n- "What's my schedule like?"`);
        window.history.replaceState({}, '', '/');
    }
    if (params.get('calendar_error')) {
        addAssistantMessage(`❌ Calendar connection failed: ${params.get('calendar_error')}. Please try again.`);
        window.history.replaceState({}, '', '/');
    }
}

function updateCalendarButton() {
    let btn = document.getElementById('calendarBtn');
    if (!btn) return;
    if (calendarConnected) {
        btn.innerHTML = `📅 ${calendarEmail || 'Calendar'}`;
        btn.title = 'Calendar connected — click to disconnect';
        btn.classList.add('calendar-connected');
    } else {
        btn.innerHTML = `📅 Connect Calendar`;
        btn.title = 'Connect your Google Calendar';
        btn.classList.remove('calendar-connected');
    }
}

function injectCalendarButton() {
    const inputContainer = document.querySelector('.input-container');
    if (!inputContainer || document.getElementById('calendarBtn')) return;
    const btn = document.createElement('button');
    btn.id = 'calendarBtn';
    btn.className = 'calendar-btn';
    btn.innerHTML = '📅 Connect Calendar';
    btn.title = 'Connect Google Calendar';
    btn.onclick = handleCalendarButtonClick;
    const sendBtn = document.getElementById('sendButton');
    if (sendBtn) inputContainer.insertBefore(btn, sendBtn);
    else inputContainer.appendChild(btn);
}

async function handleCalendarButtonClick() {
    if (calendarConnected) {
        if (confirm(`Disconnect Calendar (${calendarEmail})?`)) await disconnectCalendar();
    } else {
        await connectCalendar();
    }
}

async function connectCalendar() {
    try {
        const response = await authFetch('/api/v1/calendar/connect');
        if (response.ok) {
            const data = await response.json();
            window.location.href = data.auth_url;
        } else {
            addAssistantMessage('❌ Could not start Calendar connection. Please try again.');
        }
    } catch (e) {
        addAssistantMessage('❌ Calendar connection error: ' + e.message);
    }
}

async function disconnectCalendar() {
    try {
        await authFetch('/api/v1/calendar/disconnect', { method: 'DELETE' });
        calendarConnected = false;
        calendarEmail = '';
        updateCalendarButton();
        addAssistantMessage('Calendar disconnected.');
    } catch (e) {
        addAssistantMessage('❌ Could not disconnect Calendar.');
    }
}

// ============================================================================
// CALENDAR VIEW UI — #32 + FREE SLOTS — #33
// ============================================================================

function detectCalendarIntent(message) {
    if (!message || typeof message !== 'string') return null;
    
    const text = message.toLowerCase().trim();
    
    if (/free.{0,5}(slot|time|hour|window)|find.{0,5}(time|slot|window)|when.{0,5}(am i free|can i|are we free|do i have time)|suggest.{0,5}(time|slot|meeting)|book.{0,5}(time|slot)|schedule.{0,5}(time|slot|meeting)/i.test(text)) {
        let duration = 30;
        const minMatch = text.match(/(\d+)\s*(min|minute)/i);
        const hourMatch = text.match(/(\d+(?:\.\d+)?)\s*(hr|hour)/i);
        if (hourMatch) {
            duration = Math.round(parseFloat(hourMatch[1]) * 60);
        } else if (minMatch) {
            duration = parseInt(minMatch[1]);
        }
        
        let range = 'week';
        if (/today/i.test(text)) range = 'today';
        else if (/tomorrow/i.test(text)) range = 'tomorrow';
        else if (/this month|coming month/i.test(text)) range = 'month';
        
        return { action: 'free_slots', range: range, duration: duration };
    }
    
    if (/today's schedule|today's event|today's meeting|on today/i.test(text)) {
        return { action: 'fetch', range: 'today' };
    }
    if (/\btoday\b/i.test(text) && /(calendar|schedule|event|meeting|appointment|plan|busy)/i.test(text)) {
        return { action: 'fetch', range: 'today' };
    }
    if (/tomorrow's|tomorrow.{0,5}(schedule|event|meeting)|on tomorrow/i.test(text)) {
        return { action: 'fetch', range: 'tomorrow' };
    }
    if (/\btomorrow\b/i.test(text) && /(calendar|schedule|event|meeting|appointment|plan|busy)/i.test(text)) {
        return { action: 'fetch', range: 'tomorrow' };
    }
    if (/this week|week's events|weekly|next 7 days|coming week|upcoming week|this week's/i.test(text)) {
        return { action: 'fetch', range: 'week' };
    }
    if (/this month|month's events|next 30 days|coming month|monthly view/i.test(text)) {
        return { action: 'fetch', range: 'month' };
    }
    
    if (/\b(calendar|schedule|events?|meetings?|appointments?|agenda)\b/i.test(text)) {
        return { action: 'fetch', range: 'week' };
    }
    if (/what.{0,5}(on|happening|going on|planned|coming up)/i.test(text)) {
        return { action: 'fetch', range: 'week' };
    }
    if (/(am i|are we) (busy|booked)/i.test(text)) {
        return { action: 'fetch', range: 'week' };
    }
    
    return null;
}

function renderEventCard(event) {
    const startStr = event.start || '';
    const endStr = event.end || '';
    
    let timeDisplay = '';
    let dateDisplay = '';
    try {
        if (event.is_all_day) {
            const startDate = new Date(startStr);
            dateDisplay = startDate.toLocaleDateString('en-IN', { 
                weekday: 'short', month: 'short', day: 'numeric' 
            });
            timeDisplay = 'All day';
        } else {
            const startDate = new Date(startStr);
            const endDate = new Date(endStr);
            dateDisplay = startDate.toLocaleDateString('en-IN', { 
                weekday: 'short', month: 'short', day: 'numeric' 
            });
            const startTime = startDate.toLocaleTimeString('en-IN', { 
                hour: 'numeric', minute: '2-digit', hour12: true 
            });
            const endTime = endDate.toLocaleTimeString('en-IN', { 
                hour: 'numeric', minute: '2-digit', hour12: true 
            });
            timeDisplay = `${startTime} – ${endTime}`;
        }
    } catch (e) {
        timeDisplay = startStr;
    }
    
    let attendeesHTML = '';
    if (event.attendees && event.attendees.length > 0) {
        const visibleAttendees = event.attendees.slice(0, 3);
        const extraCount = event.attendees.length - 3;
        attendeesHTML = `
            <div class="event-attendees">
                <span class="event-icon">👥</span>
                ${visibleAttendees.map(a => 
                    `<span class="attendee-pill">${escapeHtml(a.name || a.email || '')}</span>`
                ).join('')}
                ${extraCount > 0 ? `<span class="attendee-pill">+${extraCount} more</span>` : ''}
            </div>
        `;
    }
    
    const meetButton = event.meet_link 
        ? `<a href="${event.meet_link}" target="_blank" class="event-meet-btn">📹 Join Meet</a>` 
        : '';
    
    const calLink = event.html_link 
        ? `<a href="${event.html_link}" target="_blank" class="event-cal-link">View in Calendar →</a>` 
        : '';
    
    const locationHTML = event.location 
        ? `<div class="event-location"><span class="event-icon">📍</span>${escapeHtml(event.location)}</div>` 
        : '';
    
    let descHTML = '';
    if (event.description) {
        const truncated = event.description.length > 150 
            ? event.description.substring(0, 150) + '...' 
            : event.description;
        descHTML = `<div class="event-description">${escapeHtml(truncated)}</div>`;
    }
    
    return `
        <div class="event-card">
            <div class="event-header">
                <div class="event-date-time">
                    <span class="event-date">${dateDisplay}</span>
                    <span class="event-time">${timeDisplay}</span>
                </div>
                ${meetButton}
            </div>
            <div class="event-title">${escapeHtml(event.summary || '(no title)')}</div>
            ${locationHTML}
            ${descHTML}
            ${attendeesHTML}
            ${calLink}
        </div>
    `;
}

function displayEventCards(eventsData) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    const events = eventsData.events || [];
    const range = eventsData.range || 'upcoming';
    
    let headerText = '';
    if (range === 'today') headerText = `📅 Today's Events (${events.length})`;
    else if (range === 'tomorrow') headerText = `📅 Tomorrow's Events (${events.length})`;
    else if (range === 'week') headerText = `📅 This Week (${events.length} events)`;
    else if (range === 'month') headerText = `📅 This Month (${events.length} events)`;
    else headerText = `📅 Your Events (${events.length})`;
    
    let cardsHTML = '';
    if (events.length === 0) {
        cardsHTML = `
            <div class="event-empty">
                <div class="event-empty-icon">🎉</div>
                <div class="event-empty-text">No events scheduled. You're free!</div>
            </div>
        `;
    } else {
        cardsHTML = events.map(renderEventCard).join('');
    }
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content">
            <div class="events-container">
                <div class="events-header">${headerText}</div>
                ${cardsHTML}
            </div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

function displayFreeSlotCards(slotData) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    const slots = slotData.slots || [];
    const duration = slotData.duration_minutes || 30;
    const range = slotData.range || 'week';
    
    const rangeLabel = {
        'today': 'today',
        'tomorrow': 'tomorrow',
        'week': 'this week',
        'month': 'this month'
    }[range] || 'in your range';
    
    let headerText = `🕐 Free Slots (${duration} min) ${rangeLabel}`;
    
    let cardsHTML = '';
    if (slots.length === 0) {
        cardsHTML = `
            <div class="event-empty">
                <div class="event-empty-icon">😅</div>
                <div class="event-empty-text">No free slots of ${duration} min found ${rangeLabel}. Try a shorter duration or larger range.</div>
            </div>
        `;
    } else {
        cardsHTML = slots.map((slot, idx) => `
            <div class="slot-card" data-slot-idx="${idx}">
                <div class="slot-info">
                    <div class="slot-day">${escapeHtml(slot.day_label)}</div>
                    <div class="slot-time">${escapeHtml(slot.time_label)} – ${escapeHtml(slot.end_time_label)}</div>
                    <div class="slot-duration">${slot.duration_minutes} min</div>
                </div>
                <button class="slot-book-btn" 
                        onclick="bookSlot('${escapeHtml(slot.start)}', '${escapeHtml(slot.end)}', this)">
                    📅 Book This
                </button>
            </div>
        `).join('');
    }
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">✦</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content">
            <div class="events-container">
                <div class="events-header">${headerText}</div>
                ${cardsHTML}
            </div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

async function bookSlot(start, end, button) {
    const title = prompt('Event title?', 'Quick meeting');
    if (!title) return;
    
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = '⏳ Booking...';
    
    // #35 — Free slots are pre-checked for emptiness, so conflict check is
    // unlikely to find anything, but we still pass through the same path
    // for consistency. If for some reason a conflict appears (e.g., user
    // booked from another tab between the slot search and this click),
    // the modal will show.
    const eventPayload = {
        summary: title,
        start: start,
        end: end,
        add_meet: true
    };
    
    const result = await attemptCreateEventWithConflictCheck(eventPayload, {
        onSuccess: (ev) => {
            button.textContent = '✅ Booked!';
            button.classList.add('booked');
            const card = button.closest('.slot-card');
            if (card) {
                card.style.opacity = '0.6';
                card.classList.add('slot-booked');
            }
            
            let confirmText = `✅ Booked "${escapeHtml(title)}"`;
            if (ev.html_link) {
                confirmText += ` — <a href="${ev.html_link}" target="_blank" class="event-cal-link">View in Calendar →</a>`;
            }
            if (ev.meet_link) {
                confirmText += `<br/>📹 <a href="${ev.meet_link}" target="_blank" class="event-cal-link">${escapeHtml(ev.meet_link)}</a>`;
            }
            addAssistantMessage(confirmText, null, true);
        },
        onCancel: () => {
            button.disabled = false;
            button.textContent = originalText;
        },
        onError: (errMsg) => {
            button.disabled = false;
            button.textContent = originalText;
            alert('Failed to book: ' + errMsg);
        }
    });
}

async function handleCalendarMessage(message) {
    if (!calendarConnected) {
        addAssistantMessage(`To use Calendar features, connect your Google Calendar first.\n\nClick the **📅 Connect Calendar** button below!`);
        return true;
    }
    
    const intent = detectCalendarIntent(message);
    
    if (intent && intent.action === 'free_slots') {
        addTypingIndicator(`🕐 Finding free ${intent.duration}-min slots...`);
        try {
            const url = `/api/v1/calendar/free-slots?duration=${intent.duration}&range=${intent.range}&max_suggestions=10`;
            const response = await authFetch(url);
            removeTypingIndicator();
            
            if (response.ok) {
                const data = await response.json();
                displayFreeSlotCards(data);
            } else {
                addAssistantMessage('❌ Could not find free slots. Please try again.');
            }
        } catch (e) {
            removeTypingIndicator();
            addAssistantMessage('❌ Calendar error: ' + e.message);
        }
        return true;
    }
    
    const range = (intent && intent.range) ? intent.range : 'week';
    
    addTypingIndicator('📅 Loading your calendar...');
    
    try {
        const response = await authFetch(`/api/v1/calendar/events?range=${range}`);
        removeTypingIndicator();
        
        if (response.ok) {
            const data = await response.json();
            displayEventCards(data);
        } else {
            addAssistantMessage('❌ Could not load calendar events. Please try again.');
        }
        return true;
    } catch (e) {
        removeTypingIndicator();
        addAssistantMessage('❌ Calendar error: ' + e.message);
        return true;
    }
}

// ============================================================================
// #35 — CONFLICT-AWARE EVENT CREATION
// Centralised create-event flow that runs the conflict pre-check, shows
// the warning modal if conflicts exist, and creates the event (with
// force_create=true) when the user confirms.
// ============================================================================

/**
 * Attempt to create a calendar event, with automatic conflict detection.
 *
 * @param {Object} eventPayload - same shape as POST /api/v1/calendar/events body
 *                                (summary, start, end, description?, location?,
 *                                 attendees?, add_meet?, timezone?)
 * @param {Object} callbacks
 *   @param {Function} callbacks.onSuccess - called with the created event object
 *   @param {Function} callbacks.onCancel  - called when user cancels at the modal
 *   @param {Function} callbacks.onError   - called with an error message string
 */
async function attemptCreateEventWithConflictCheck(eventPayload, callbacks) {
    const { onSuccess, onCancel, onError } = callbacks || {};
    
    try {
        // First attempt — without force_create, so the backend runs its
        // pre-check and may return 409 with the conflicts list.
        const response = await authFetch('/api/v1/calendar/events', {
            method: 'POST',
            body: JSON.stringify({
                ...eventPayload,
                force_create: false
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.success && onSuccess) onSuccess(data.event || {});
            return;
        }
        
        if (response.status === 409) {
            // Conflicts found — show modal, let user decide
            const errBody = await response.json();
            const detail = errBody.detail || {};
            const conflicts = detail.conflicts || [];
            const proposed = detail.proposed || {
                summary: eventPayload.summary,
                start: eventPayload.start,
                end: eventPayload.end
            };
            
            showConflictModal(conflicts, proposed, {
                onConfirm: async () => {
                    // User chose "Create anyway" — re-send with force_create=true
                    try {
                        const retryResponse = await authFetch('/api/v1/calendar/events', {
                            method: 'POST',
                            body: JSON.stringify({
                                ...eventPayload,
                                force_create: true
                            })
                        });
                        if (retryResponse.ok) {
                            const data = await retryResponse.json();
                            if (data.success && onSuccess) onSuccess(data.event || {});
                        } else {
                            const errData = await retryResponse.json();
                            if (onError) onError(errData.detail || 'Unknown error');
                        }
                    } catch (e) {
                        if (onError) onError(e.message);
                    }
                },
                onCancel: () => {
                    addAssistantMessage('Event creation cancelled.');
                    if (onCancel) onCancel();
                }
            });
            return;
        }
        
        // Some other non-OK status
        const errData = await response.json().catch(() => ({}));
        if (onError) onError(errData.detail || `Server returned ${response.status}`);
        
    } catch (e) {
        if (onError) onError(e.message);
    }
}

/**
 * Render the conflict warning modal and wire up its buttons.
 *
 * Uses inline styles (cssText) so no styles.css change is required.
 * Colors use existing CSS custom properties where available with
 * sensible fallbacks for both dark and light mode.
 */
function showConflictModal(conflicts, proposed, callbacks) {
    const { onConfirm, onCancel } = callbacks || {};
    
    // Remove any existing conflict modal so we never stack them
    const existing = document.querySelector('.conflict-modal-overlay');
    if (existing) existing.remove();
    
    // ----- Overlay (full-screen backdrop) -----
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay conflict-modal-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.55);
        backdrop-filter: blur(4px);
        -webkit-backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 16px;
        animation: conflictFadeIn 0.18s ease-out;
    `;
    
    // ----- Modal panel -----
    const panel = document.createElement('div');
    panel.className = 'conflict-modal-panel';
    panel.style.cssText = `
        background: var(--bg-secondary, #1a1a1a);
        color: var(--text-primary, #f0f0f0);
        border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.08));
        border-radius: 16px;
        max-width: 520px;
        width: 100%;
        max-height: 85vh;
        overflow-y: auto;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        animation: conflictSlideUp 0.22s cubic-bezier(0.16, 1, 0.3, 1);
    `;
    
    // ----- Header (warning icon + title) -----
    const conflictWord = conflicts.length === 1 ? 'conflict' : 'conflicts';
    const header = document.createElement('div');
    header.style.cssText = `
        padding: 24px 28px 16px;
        border-bottom: 1px solid var(--border-primary, rgba(255, 255, 255, 0.06));
    `;
    header.innerHTML = `
        <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 8px;">
            <div style="
                width: 44px;
                height: 44px;
                border-radius: 50%;
                background: rgba(255, 159, 64, 0.15);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 22px;
                flex-shrink: 0;
            ">⚠️</div>
            <div>
                <div style="font-size: 17px; font-weight: 600; line-height: 1.3;">
                    Schedule ${conflictWord} found
                </div>
                <div style="font-size: 13.5px; opacity: 0.7; margin-top: 2px;">
                    ${conflicts.length} existing event${conflicts.length === 1 ? '' : 's'} overlap${conflicts.length === 1 ? 's' : ''} with this time
                </div>
            </div>
        </div>
    `;
    
    // ----- Proposed event block -----
    const proposedBlock = document.createElement('div');
    proposedBlock.style.cssText = `
        padding: 18px 28px 14px;
        border-bottom: 1px solid var(--border-primary, rgba(255, 255, 255, 0.06));
    `;
    
    const proposedTimeDisplay = formatEventTimeDisplay(proposed.start, proposed.end);
    proposedBlock.innerHTML = `
        <div style="font-size: 11.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.55; margin-bottom: 8px;">
            You're trying to create
        </div>
        <div style="
            background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
            border-radius: 10px;
            padding: 12px 14px;
        ">
            <div style="font-size: 14.5px; font-weight: 600; margin-bottom: 4px;">
                ${escapeHtml(proposed.summary || '(untitled event)')}
            </div>
            <div style="font-size: 12.5px; opacity: 0.75;">
                🕐 ${escapeHtml(proposedTimeDisplay)}
            </div>
        </div>
    `;
    
    // ----- Conflicts list -----
    const conflictsBlock = document.createElement('div');
    conflictsBlock.style.cssText = `
        padding: 18px 28px;
    `;
    
    let conflictsHTML = `
        <div style="font-size: 11.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.55; margin-bottom: 10px;">
            Conflicts with
        </div>
    `;
    
    conflicts.forEach((c, idx) => {
        const overlapLabel = formatOverlapLabel(c.overlap_type);
        const linkHTML = c.html_link
            ? `<a href="${c.html_link}" target="_blank" rel="noopener" style="font-size: 12px; color: var(--accent-primary, #d97706); text-decoration: none; opacity: 0.85;">Open in Calendar →</a>`
            : '';
        const locationHTML = c.location
            ? `<div style="font-size: 12px; opacity: 0.65; margin-top: 4px;">📍 ${escapeHtml(c.location)}</div>`
            : '';
        
        conflictsHTML += `
            <div style="
                background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
                border-left: 3px solid rgba(239, 68, 68, 0.7);
                border-radius: 8px;
                padding: 12px 14px;
                margin-bottom: ${idx === conflicts.length - 1 ? '0' : '10px'};
            ">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 4px;">
                    <div style="font-size: 14px; font-weight: 600; line-height: 1.35; flex: 1;">
                        ${escapeHtml(c.summary || '(no title)')}
                    </div>
                    ${linkHTML}
                </div>
                <div style="font-size: 12.5px; opacity: 0.75;">
                    🕐 ${escapeHtml(c.display || `${c.start} → ${c.end}`)}
                </div>
                ${locationHTML}
                <div style="font-size: 11px; opacity: 0.55; margin-top: 6px; font-style: italic;">
                    ${overlapLabel}
                </div>
            </div>
        `;
    });
    
    conflictsBlock.innerHTML = conflictsHTML;
    
    // ----- Action buttons -----
    const actions = document.createElement('div');
    actions.style.cssText = `
        padding: 18px 28px 24px;
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        flex-wrap: wrap;
        border-top: 1px solid var(--border-primary, rgba(255, 255, 255, 0.06));
        background: var(--bg-tertiary, rgba(255, 255, 255, 0.02));
    `;
    
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'conflict-cancel-btn';
    cancelBtn.style.cssText = `
        background: transparent;
        color: var(--text-primary, #f0f0f0);
        border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.15));
        padding: 9px 18px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 500;
        font-family: inherit;
        cursor: pointer;
        transition: background 0.15s ease, border-color 0.15s ease;
    `;
    cancelBtn.onmouseenter = () => {
        cancelBtn.style.background = 'rgba(255, 255, 255, 0.06)';
    };
    cancelBtn.onmouseleave = () => {
        cancelBtn.style.background = 'transparent';
    };
    
    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = 'Create anyway';
    confirmBtn.className = 'conflict-confirm-btn';
    confirmBtn.style.cssText = `
        background: var(--accent-primary, #d97706);
        color: white;
        border: none;
        padding: 9px 18px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        font-family: inherit;
        cursor: pointer;
        transition: opacity 0.15s ease, transform 0.1s ease;
    `;
    confirmBtn.onmouseenter = () => {
        confirmBtn.style.opacity = '0.9';
    };
    confirmBtn.onmouseleave = () => {
        confirmBtn.style.opacity = '1';
    };
    
    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    
    // ----- Inject keyframe animations once -----
    if (!document.getElementById('conflictModalKeyframes')) {
        const styleTag = document.createElement('style');
        styleTag.id = 'conflictModalKeyframes';
        styleTag.textContent = `
            @keyframes conflictFadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes conflictSlideUp {
                from { opacity: 0; transform: translateY(12px); }
                to { opacity: 1; transform: translateY(0); }
            }
        `;
        document.head.appendChild(styleTag);
    }
    
    // ----- Assemble -----
    panel.appendChild(header);
    panel.appendChild(proposedBlock);
    panel.appendChild(conflictsBlock);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    
    // ----- Wire up dismiss handlers -----
    const dismiss = (action) => {
        overlay.remove();
        if (action === 'confirm' && onConfirm) onConfirm();
        else if (action === 'cancel' && onCancel) onCancel();
    };
    
    cancelBtn.onclick = () => dismiss('cancel');
    confirmBtn.onclick = () => dismiss('confirm');
    
    // Click on overlay (outside panel) → cancel
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) dismiss('cancel');
    });
    
    // Focus the cancel button by default — safer choice on Enter key
    setTimeout(() => cancelBtn.focus(), 50);
}

/**
 * Helper: turn an overlap_type code into a user-friendly label.
 */
function formatOverlapLabel(overlapType) {
    switch (overlapType) {
        case 'contains':       return 'Your new event would fully contain this one';
        case 'contained':      return 'Your new event sits entirely inside this one';
        case 'partial_start':  return 'Your new event overlaps the start of this one';
        case 'partial_end':    return 'Your new event overlaps the end of this one';
        case 'full':           return 'Same time as this event';
        default:               return 'Times overlap';
    }
}

/**
 * Helper: format a start/end ISO pair as "Fri, May 02 · 3:00 PM – 4:00 PM"
 */
function formatEventTimeDisplay(startStr, endStr) {
    if (!startStr) return '';
    try {
        const start = new Date(startStr);
        const end = endStr ? new Date(endStr) : null;
        const dateLabel = start.toLocaleDateString('en-IN', {
            weekday: 'short', month: 'short', day: 'numeric'
        });
        const startTime = start.toLocaleTimeString('en-IN', {
            hour: 'numeric', minute: '2-digit', hour12: true
        });
        if (end) {
            const endTime = end.toLocaleTimeString('en-IN', {
                hour: 'numeric', minute: '2-digit', hour12: true
            });
            return `${dateLabel} · ${startTime} – ${endTime}`;
        }
        return `${dateLabel} · ${startTime}`;
    } catch (e) {
        return startStr;
    }
}

// ============================================================================
// AI INTENT CLASSIFICATION — #33.5
// AI classifier with regex fallback. Handles natural language, Hindi, slang.
// ============================================================================

async function classifyIntent(message, mode) {
    try {
        const response = await authFetch('/api/v1/intent/classify', {
            method: 'POST',
            body: JSON.stringify({ message: message, mode: mode || 'normal' })
        });
        if (!response.ok) {
            console.log('[Intent] AI classifier returned non-200, will fall back to regex');
            return null;
        }
        const data = await response.json();
        if (data._error) {
            console.log('[Intent] AI classifier error:', data._error);
            return null;
        }
        console.log('[Intent] AI classified:', data);
        return data;
    } catch (e) {
        console.log('[Intent] AI classifier unavailable, will fall back to regex:', e.message);
        return null;
    }
}

async function routeByAIIntent(message, intent) {
    const domain = intent.domain;
    const action = intent.action;
    const params = intent.params || {};
    
    if (domain === 'gmail') {
        await handleGmailMessageWithIntent(message, action, params);
        return true;
    }
    
    if (domain === 'calendar') {
        await handleCalendarMessageWithIntent(message, action, params);
        return true;
    }
    
    if (domain === 'code') {
        return false;
    }
    
    return false;
}

async function handleCalendarMessageWithIntent(message, action, params) {
    if (!calendarConnected) {
        addAssistantMessage(`To use Calendar features, connect your Google Calendar first.\n\nClick the **📅 Connect Calendar** button below!`);
        return;
    }
    
    if (action === 'find_free_slots') {
        const range = params.range || 'week';
        const duration = params.duration_minutes || 30;
        addTypingIndicator(`🕐 Finding free ${duration}-min slots...`);
        try {
            const url = `/api/v1/calendar/free-slots?duration=${duration}&range=${range}&max_suggestions=10`;
            const response = await authFetch(url);
            removeTypingIndicator();
            if (response.ok) {
                const data = await response.json();
                displayFreeSlotCards(data);
            } else {
                addAssistantMessage('❌ Could not find free slots. Please try again.');
            }
        } catch (e) {
            removeTypingIndicator();
            addAssistantMessage('❌ Calendar error: ' + e.message);
        }
        return;
    }
    
    if (action === 'show_events') {
        const range = params.range || 'week';
        addTypingIndicator('📅 Loading your calendar...');
        try {
            const response = await authFetch(`/api/v1/calendar/events?range=${range}`);
            removeTypingIndicator();
            if (response.ok) {
                const data = await response.json();
                displayEventCards(data);
            } else {
                addAssistantMessage('❌ Could not load calendar events.');
            }
        } catch (e) {
            removeTypingIndicator();
            addAssistantMessage('❌ Calendar error: ' + e.message);
        }
        return;
    }
    
    // ====== #35 — create_event with conflict pre-check ======
    if (action === 'create_event') {
        // Pull params from the AI classifier; bail out gracefully if any
        // critical piece is missing (we don't want to silently create a
        // bad event).
        const summary = params.summary || params.title || 'New event';
        const start = params.start;
        const end = params.end;
        
        if (!start || !end) {
            addAssistantMessage(
                `I couldn't figure out the exact start/end time from your request. ` +
                `Try something like *"block 3pm to 4pm tomorrow for gym"* with a clear time range.`
            );
            return;
        }
        
        const eventPayload = {
            summary: summary,
            start: start,
            end: end,
            description: params.description || null,
            location: params.location || null,
            attendees: params.attendees || null,
            add_meet: params.add_meet === true,
            timezone: params.timezone || 'Asia/Kolkata'
        };
        
        addTypingIndicator('📅 Checking for conflicts...');
        
        await attemptCreateEventWithConflictCheck(eventPayload, {
            onSuccess: (ev) => {
                removeTypingIndicator();
                let confirmText = `✅ Created "${escapeHtml(summary)}"`;
                const timeDisplay = formatEventTimeDisplay(ev.start || start, ev.end || end);
                if (timeDisplay) confirmText += `<br/><span style="opacity:0.75; font-size:13px;">🕐 ${escapeHtml(timeDisplay)}</span>`;
                if (ev.html_link) {
                    confirmText += `<br/><a href="${ev.html_link}" target="_blank" class="event-cal-link">View in Calendar →</a>`;
                }
                if (ev.meet_link) {
                    confirmText += `<br/>📹 <a href="${ev.meet_link}" target="_blank" class="event-cal-link">${escapeHtml(ev.meet_link)}</a>`;
                }
                addAssistantMessage(confirmText, null, true);
            },
            onCancel: () => {
                removeTypingIndicator();
                // Cancel message is added inside attemptCreateEventWithConflictCheck
            },
            onError: (errMsg) => {
                removeTypingIndicator();
                addAssistantMessage('❌ Could not create event: ' + escapeHtml(errMsg));
            }
        });
        return;
    }
    
    // ====== #36 — ask_about_calendar (AI reasoning) ======
    // The classifier routes reasoning questions ("am I overbooked?",
    // "how's my week?", "kal busy hu kya?", "when can I do deep work?") here.
    // We hit /api/v1/calendar/analyze which runs the full reasoning pipeline:
    // fetch events → compute structural facts → Groq advisor → prose response.
    // The response is streamed into chat as a normal assistant message for a
    // conversational feel — no card UI, no structured table, just insight.
    if (action === 'ask_about_calendar') {
        const range = params.range || 'week';
        const question = params.raw_query || message;
        
        addTypingIndicator('🧠 Analyzing your schedule...');
        
        try {
            const response = await authFetch('/api/v1/calendar/analyze', {
                method: 'POST',
                body: JSON.stringify({
                    question: question,
                    range: range,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
                })
            });
            
            removeTypingIndicator();
            
            if (response.ok) {
                const data = await response.json();
                // Stream the advisor's prose into chat as a normal assistant message.
                // streamAssistantMessage gives us the typewriter effect — feels
                // conversational, exactly the vibe we want for AI reasoning.
                streamAssistantMessage(data.response || 'I could not analyze your schedule right now.');
            } else {
                let errMsg = 'Could not analyze your calendar.';
                try {
                    const errData = await response.json();
                    if (errData.detail) errMsg = errData.detail;
                } catch (e) { /* swallow JSON parse errors */ }
                addAssistantMessage('❌ ' + errMsg);
            }
        } catch (e) {
            removeTypingIndicator();
            addAssistantMessage('❌ Calendar analysis error: ' + e.message);
        }
        return;
    }
    
    // Anything else → fall back to regex handler
    await handleCalendarMessage(message);
}

async function handleGmailMessageWithIntent(message, action, params) {
    if (!gmailConnected) {
        addAssistantMessage(`To use Gmail features, connect your Gmail account first.\n\nClick the **📧 Connect Gmail** button below!`);
        return;
    }
    
    if (action === 'show_inbox') {
        await handleShowEmailsIntent(message);
        return;
    }
    
    if (action === 'show_unread') {
        await handleShowEmailsIntent('unread emails');
        return;
    }
    
    if (action === 'search_emails') {
        const query = params.query || message;
        addTypingIndicator('🔍 Searching your emails...');
        try {
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
        return;
    }
    
    if (action === 'send_email') {
        showComposeForm(message);
        return;
    }
    
    if (action === 'ask_about_emails') {
        await handleAskEmailIntent(message);
        return;
    }
    
    // Fallback to regex-based handler
    await handleGmailMessage(message);
}

// ============================================================================
// GMAIL INTEGRATION — #24 #25 #26 #27 #28
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
        /action item/i,
        /pending.*(action|task|item|email|reply)/i,
        /what.*urgent/i,
        /what.*pending/i,
        /who.*(haven'?t|have not|not).*(replied|responded)/i,
        /what.*replied/i,
        /follow.?up/i,
        /summarize.*(inbox|messages|this week|today)/i,
    ];
    return emailPatterns.some(p => p.test(message));
}

function detectSendIntent(message) {
    return /send.*email|compose.*email|write.*email|draft.*email/i.test(message);
}

function detectSearchIntent(message) {
    return /search.*email|find.*email|look.*email|email.*from|email.*about/i.test(message);
}

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
            body: JSON.stringify({ query: message, max_results: 20 })
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
    if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); openSettingsPanel(); }
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
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>,</kbd></span> <span>Open settings</span></div>
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
// SEND MESSAGE — AI Intent first (#33.5), regex fallback (#24-#28 #32 #33)
// ============================================================================

async function sendMessage() {
    if (isStreaming) return;
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message && attachedFiles.length === 0) return;

    // ============================================================
    // #33.5 — AI Intent Classification (with regex fallback)
    // ============================================================
    if (message) {
        const intent = await classifyIntent(message, currentMode);
        const CONFIDENCE_THRESHOLD = 0.7;
        
        if (intent && intent.confidence >= CONFIDENCE_THRESHOLD) {
            // AI is confident — route by AI intent
            input.value = '';
            input.style.height = 'auto';
            addUserMessage(message);
            const handled = await routeByAIIntent(message, intent);
            if (handled) return;
            // If routeByAIIntent returns false (e.g. code domain), fall through to default flow
        } else {
            // AI uncertain or unavailable — use regex fallback
            console.log('[Intent] Falling back to regex (AI confidence:', intent ? intent.confidence : 'N/A', ')');
            
            const shouldRouteToGmail = (currentMode === 'email') || detectGmailIntent(message);
            if (shouldRouteToGmail) {
                input.value = '';
                input.style.height = 'auto';
                addUserMessage(message);
                await handleGmailMessage(message);
                return;
            }

            const shouldRouteToCalendar = (currentMode === 'calendar') || detectCalendarIntent(message);
            if (shouldRouteToCalendar) {
                input.value = '';
                input.style.height = 'auto';
                addUserMessage(message);
                await handleCalendarMessage(message);
                return;
            }
        }
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
    
    if (message && !document.querySelector('.message.user[data-message-id]:last-child')) {
        // Only add user message if not already added by AI routing branch
        const allUserMessages = document.querySelectorAll('.message.user');
        const lastUserMsg = allUserMessages[allUserMessages.length - 1];
        const lastUserText = lastUserMsg ? lastUserMsg.querySelector('.message-content')?.textContent : '';
        if (lastUserText !== message) {
            addUserMessage(message);
        }
        input.value = '';
        input.style.height = 'auto';
    } else if (!uploadedFilesList) {
        return;
    }
    
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
            mode: currentMode
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
                    if (event.mode && event.mode !== currentMode) {
                        updateModePillUI(event.mode);
                    }
                    // #37 — Sync the badge state with the server's view on this turn
                    if (typeof event.custom_prompt_applied === 'boolean') {
                        customPromptActive = event.custom_prompt_applied;
                        updateCustomPromptBadge();
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
                    mode: currentMode
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

// ============================================================================
// #38 — PERSISTENT USER MEMORY (settings panel section)
// Renders the memory list inside the existing #37 settings panel, beneath the
// custom prompt section. Reads /api/v1/memories on panel open, supports
// edit/delete per-memory, "Forget everything" wipe, and pause-toggle.
// ============================================================================

const MEMORY_CATEGORY_LABELS = {
    identity: { label: 'Identity', icon: '👤' },
    preference: { label: 'Preferences', icon: '✨' },
    context: { label: 'Context', icon: '🎯' }
};

/**
 * Inject the memory section into an open settings panel.
 * Called from openSettingsPanel after the custom prompt section is built.
 */
async function renderMemorySection(panelBody) {
    if (!panelBody) return;
    
    // Container with placeholder so the section appears even before fetch completes
    const memorySection = document.createElement('div');
    memorySection.id = 'memorySection';
    memorySection.style.cssText = `
        margin-top: 28px;
        padding-top: 24px;
        border-top: 1px solid var(--border-primary, rgba(255, 255, 255, 0.08));
    `;
    memorySection.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; gap: 12px;">
            <div style="font-size: 14.5px; font-weight: 600; display: flex; align-items: center; gap: 8px;">
                <span>🧠 Memories</span>
                <span style="font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 4px; background: var(--accent-primary, #d97706); color: white; letter-spacing: 0.05em;">PRO</span>
            </div>
            <div id="memoryCountBadge" style="font-size: 12px; opacity: 0.7; font-variant-numeric: tabular-nums;">Loading…</div>
        </div>
        <div style="font-size: 12.5px; opacity: 0.7; line-height: 1.5; margin-bottom: 14px;">
            Durable facts OmniAI has learned about you. Used in every chat across all modes.
        </div>
        
        <div id="memoryPauseRow" style="
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 16px;
            font-size: 13px;
        ">
            <div>
                <div style="font-weight: 500;">Pause learning new memories</div>
                <div style="font-size: 11.5px; opacity: 0.6; margin-top: 2px;">Existing memories still apply. New facts won't be saved.</div>
            </div>
            <label style="position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0;">
                <input type="checkbox" id="memoryPauseToggle" style="opacity: 0; width: 0; height: 0;">
                <span id="memoryPauseSlider" style="
                    position: absolute;
                    cursor: pointer;
                    top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(255, 255, 255, 0.15);
                    border-radius: 22px;
                    transition: background 0.2s;
                "></span>
                <span id="memoryPauseSliderDot" style="
                    position: absolute;
                    height: 16px; width: 16px;
                    left: 3px; bottom: 3px;
                    background: white;
                    border-radius: 50%;
                    transition: transform 0.2s;
                    pointer-events: none;
                "></span>
            </label>
        </div>
        
        <div id="memoryList" style="
            min-height: 60px;
            max-height: 400px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 14px;
        ">
            <div style="opacity: 0.5; font-size: 13px; text-align: center; padding: 20px;">Loading memories…</div>
        </div>
        
        <div id="memoryWipeRow" style="margin-top: 18px; display: flex; justify-content: flex-end;">
            <button id="memoryWipeBtn" style="
                background: transparent;
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.4);
                padding: 8px 14px;
                border-radius: 8px;
                font-size: 12.5px;
                font-weight: 500;
                font-family: inherit;
                cursor: pointer;
                opacity: 0.85;
                transition: background 0.15s, opacity 0.15s;
                display: none;
            ">🗑️ Forget everything about me</button>
        </div>
    `;
    
    panelBody.appendChild(memorySection);
    
    // Wire up handlers, then load data
    wireMemorySectionHandlers();
    await loadMemories();
}


/**
 * Wire up the static buttons + toggle. Each is hooked to its respective
 * server endpoint via authFetch.
 */
function wireMemorySectionHandlers() {
    const pauseToggle = document.getElementById('memoryPauseToggle');
    const wipeBtn = document.getElementById('memoryWipeBtn');
    
    if (pauseToggle) {
        pauseToggle.addEventListener('change', async (e) => {
            const newPaused = e.target.checked;
            updatePauseSliderVisual(newPaused);
            try {
                const response = await authFetch('/api/v1/memories/settings', {
                    method: 'PUT',
                    body: JSON.stringify({ paused: newPaused })
                });
                if (!response.ok) {
                    // Revert on failure
                    pauseToggle.checked = !newPaused;
                    updatePauseSliderVisual(!newPaused);
                    showMemoryToast('Could not update pause state', 'error');
                }
            } catch (err) {
                pauseToggle.checked = !newPaused;
                updatePauseSliderVisual(!newPaused);
                showMemoryToast('Network error: ' + err.message, 'error');
            }
        });
    }
    
    if (wipeBtn) {
        wipeBtn.addEventListener('click', async () => {
            if (!confirm("Forget everything about you? This deletes all your memories. The AI will start fresh next chat. This cannot be undone.")) {
                return;
            }
            wipeBtn.disabled = true;
            wipeBtn.textContent = 'Wiping…';
            try {
                const response = await authFetch('/api/v1/memories', { method: 'DELETE' });
                if (response.ok) {
                    const data = await response.json();
                    showMemoryToast(`Forgot ${data.count || 0} memories`, 'success');
                    await loadMemories();
                } else {
                    showMemoryToast('Could not wipe memories', 'error');
                    wipeBtn.disabled = false;
                    wipeBtn.textContent = '🗑️ Forget everything about me';
                }
            } catch (err) {
                showMemoryToast('Network error: ' + err.message, 'error');
                wipeBtn.disabled = false;
                wipeBtn.textContent = '🗑️ Forget everything about me';
            }
        });
    }
}


/**
 * Visual update for the pause toggle slider — moves the dot, changes color.
 * Separate from the state because we may need to revert on server error.
 */
function updatePauseSliderVisual(isPaused) {
    const slider = document.getElementById('memoryPauseSlider');
    const dot = document.getElementById('memoryPauseSliderDot');
    if (slider) {
        slider.style.background = isPaused
            ? 'var(--accent-primary, #d97706)'
            : 'rgba(255, 255, 255, 0.15)';
    }
    if (dot) {
        dot.style.transform = isPaused ? 'translateX(18px)' : 'translateX(0)';
    }
}


/**
 * Fetch memories from server and render the list. Also updates the count
 * badge, pause toggle state, and wipe button visibility (hidden when 0).
 */
async function loadMemories() {
    const listEl = document.getElementById('memoryList');
    const countBadge = document.getElementById('memoryCountBadge');
    const pauseToggle = document.getElementById('memoryPauseToggle');
    const wipeBtn = document.getElementById('memoryWipeBtn');
    
    if (!listEl || !countBadge) return;
    
    listEl.innerHTML = '<div style="opacity: 0.5; font-size: 13px; text-align: center; padding: 20px;">Loading memories…</div>';
    
    try {
        const response = await authFetch('/api/v1/memories');
        if (!response.ok) {
            if (response.status === 401) {
                listEl.innerHTML = '<div style="opacity: 0.5; font-size: 13px; text-align: center; padding: 20px;">Please log in to use memory features.</div>';
                countBadge.textContent = '';
                return;
            }
            throw new Error('Server returned ' + response.status);
        }
        const data = await response.json();
        
        // Update count badge
        const used = data.active_count || 0;
        const cap = data.cap || 10;
        const isPro = !!data.is_pro;
        if (isPro) {
            countBadge.innerHTML = `<span style="opacity: 0.85;">${used} saved · unlimited</span>`;
        } else {
            // Color the badge red if at cap
            const atCap = used >= cap;
            const color = atCap ? '#ef4444' : 'inherit';
            countBadge.innerHTML = `<span style="color: ${color};">${used} of ${cap} used</span>`;
        }
        
        // Sync pause toggle (without firing the change event)
        if (pauseToggle) {
            pauseToggle.checked = !!data.paused;
            updatePauseSliderVisual(!!data.paused);
        }
        
        // Wipe button visible only if there's something to wipe
        if (wipeBtn) {
            wipeBtn.style.display = (data.memories && data.memories.length > 0) ? 'inline-block' : 'none';
            wipeBtn.disabled = false;
            wipeBtn.textContent = '🗑️ Forget everything about me';
        }
        
        renderMemoriesList(data.memories || []);
        
    } catch (err) {
        console.error('#38 loadMemories failed:', err);
        listEl.innerHTML = `<div style="opacity: 0.6; font-size: 13px; text-align: center; padding: 20px; color: #ef4444;">Could not load memories: ${escapeHtml(err.message)}</div>`;
        countBadge.textContent = '';
    }
}


/**
 * Render the memories list, grouped by category.
 * Empty state shows a helpful "no memories yet" message.
 */
function renderMemoriesList(memories) {
    const listEl = document.getElementById('memoryList');
    if (!listEl) return;
    
    if (!memories || memories.length === 0) {
        listEl.innerHTML = `
            <div style="
                opacity: 0.6;
                font-size: 13px;
                text-align: center;
                padding: 28px 16px;
                background: var(--bg-tertiary, rgba(255, 255, 255, 0.02));
                border-radius: 10px;
                line-height: 1.6;
            ">
                <div style="font-size: 22px; margin-bottom: 6px;">🧠</div>
                <div>No memories yet.</div>
                <div style="font-size: 11.5px; opacity: 0.7; margin-top: 6px;">
                    OmniAI will start learning durable facts about you as you chat.
                </div>
            </div>
        `;
        return;
    }
    
    // Group by category
    const grouped = { identity: [], preference: [], context: [] };
    memories.forEach(m => {
        const cat = (m.category || 'context').toLowerCase();
        if (grouped[cat]) grouped[cat].push(m);
    });
    
    const html = Object.keys(grouped)
        .filter(cat => grouped[cat].length > 0)
        .map(cat => {
            const meta = MEMORY_CATEGORY_LABELS[cat];
            const items = grouped[cat].map(m => renderSingleMemory(m)).join('');
            return `
                <div class="memory-category-group">
                    <div style="font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.55; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                        <span>${meta.icon}</span><span>${meta.label}</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 8px;">${items}</div>
                </div>
            `;
        })
        .join('');
    
    listEl.innerHTML = html;
    
    // Wire up the per-row buttons (delegated; one listener for each row)
    listEl.querySelectorAll('[data-memory-id]').forEach(row => {
        const id = row.dataset.memoryId;
        const editBtn = row.querySelector('.memory-edit-btn');
        const deleteBtn = row.querySelector('.memory-delete-btn');
        if (editBtn) editBtn.addEventListener('click', () => startEditMemory(id, row));
        if (deleteBtn) deleteBtn.addEventListener('click', () => deleteSingleMemory(id, row));
    });
}


function renderSingleMemory(memory) {
    const id = memory.id;
    const content = escapeHtml(memory.content || '');
    return `
        <div class="memory-row" data-memory-id="${id}" style="
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 10px;
            background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 13px;
            line-height: 1.45;
            transition: background 0.15s;
        ">
            <div class="memory-content-wrap" style="flex: 1; min-width: 0;">
                <div class="memory-content-display" style="word-wrap: break-word;">${content}</div>
            </div>
            <div class="memory-row-actions" style="display: flex; gap: 4px; flex-shrink: 0;">
                <button class="memory-edit-btn" title="Edit memory" style="
                    background: transparent;
                    border: none;
                    color: var(--text-primary, #f0f0f0);
                    font-size: 14px;
                    cursor: pointer;
                    padding: 4px 6px;
                    border-radius: 4px;
                    opacity: 0.55;
                    transition: opacity 0.15s, background 0.15s;
                " onmouseover="this.style.opacity='1';this.style.background='rgba(255,255,255,0.06)'" onmouseout="this.style.opacity='0.55';this.style.background='transparent'">✏️</button>
                <button class="memory-delete-btn" title="Delete memory" style="
                    background: transparent;
                    border: none;
                    color: #ef4444;
                    font-size: 14px;
                    cursor: pointer;
                    padding: 4px 6px;
                    border-radius: 4px;
                    opacity: 0.55;
                    transition: opacity 0.15s, background 0.15s;
                " onmouseover="this.style.opacity='1';this.style.background='rgba(239,68,68,0.1)'" onmouseout="this.style.opacity='0.55';this.style.background='transparent'">🗑️</button>
            </div>
        </div>
    `;
}


/**
 * Inline edit a single memory. Replaces the content with a textarea +
 * Save/Cancel buttons. On save, calls PUT /memories/{id} and reloads list.
 */
function startEditMemory(memoryId, rowEl) {
    const wrap = rowEl.querySelector('.memory-content-wrap');
    const display = rowEl.querySelector('.memory-content-display');
    const actions = rowEl.querySelector('.memory-row-actions');
    if (!wrap || !display || !actions) return;
    
    const originalContent = display.textContent;
    
    // Hide action buttons during edit
    actions.style.display = 'none';
    
    wrap.innerHTML = `
        <textarea class="memory-edit-textarea" style="
            width: 100%;
            background: var(--bg-secondary, #1a1a1a);
            color: var(--text-primary, #f0f0f0);
            border: 1px solid var(--accent-primary, #d97706);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 13px;
            font-family: inherit;
            line-height: 1.45;
            resize: vertical;
            min-height: 50px;
            box-sizing: border-box;
            outline: none;
        "></textarea>
        <div class="memory-edit-buttons" style="display: flex; gap: 6px; margin-top: 8px; justify-content: flex-end;">
            <button class="memory-edit-cancel" style="
                background: transparent;
                color: var(--text-primary, #f0f0f0);
                border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.15));
                padding: 5px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-family: inherit;
                cursor: pointer;
            ">Cancel</button>
            <button class="memory-edit-save" style="
                background: var(--accent-primary, #d97706);
                color: white;
                border: none;
                padding: 5px 14px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                font-family: inherit;
                cursor: pointer;
            ">Save</button>
        </div>
    `;
    
    const textarea = wrap.querySelector('textarea');
    const cancelBtn = wrap.querySelector('.memory-edit-cancel');
    const saveBtn = wrap.querySelector('.memory-edit-save');
    
    textarea.value = originalContent;
    setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }, 50);
    
    cancelBtn.addEventListener('click', () => {
        wrap.innerHTML = `<div class="memory-content-display" style="word-wrap: break-word;">${escapeHtml(originalContent)}</div>`;
        actions.style.display = 'flex';
    });
    
    saveBtn.addEventListener('click', async () => {
        const newContent = (textarea.value || '').trim();
        if (!newContent) {
            showMemoryToast('Memory cannot be empty', 'error');
            return;
        }
        if (newContent === originalContent) {
            cancelBtn.click();
            return;
        }
        if (newContent.length > 500) {
            showMemoryToast('Memory too long (max 500 chars)', 'error');
            return;
        }
        
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        try {
            const response = await authFetch(`/api/v1/memories/${memoryId}`, {
                method: 'PUT',
                body: JSON.stringify({ content: newContent })
            });
            if (response.ok) {
                showMemoryToast('Memory updated', 'success');
                await loadMemories();
            } else {
                let errMsg = 'Could not update memory';
                try {
                    const errData = await response.json();
                    if (errData.detail) errMsg = errData.detail;
                } catch (e) { /* swallow */ }
                showMemoryToast(errMsg, 'error');
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save';
            }
        } catch (err) {
            showMemoryToast('Network error: ' + err.message, 'error');
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
        }
    });
}


async function deleteSingleMemory(memoryId, rowEl) {
    if (!confirm('Delete this memory? OmniAI will no longer remember it.')) return;
    
    // Optimistic UI: fade the row immediately
    rowEl.style.opacity = '0.4';
    rowEl.style.pointerEvents = 'none';
    
    try {
        const response = await authFetch(`/api/v1/memories/${memoryId}`, { method: 'DELETE' });
        if (response.ok) {
            // Reload list (gives accurate count + handles empty state)
            await loadMemories();
        } else {
            // Revert on failure
            rowEl.style.opacity = '1';
            rowEl.style.pointerEvents = '';
            showMemoryToast('Could not delete memory', 'error');
        }
    } catch (err) {
        rowEl.style.opacity = '1';
        rowEl.style.pointerEvents = '';
        showMemoryToast('Network error: ' + err.message, 'error');
    }
}


/**
 * Tiny toast notification for memory operations. Floats top-center
 * of the settings panel, auto-dismisses after 2.5 seconds.
 */
function showMemoryToast(message, type) {
    // Remove any existing toast first so they don't stack
    const existing = document.getElementById('memoryToast');
    if (existing) existing.remove();
    
    const colors = {
        success: { bg: 'rgba(34, 197, 94, 0.15)', text: '#22c55e', border: 'rgba(34, 197, 94, 0.3)' },
        error: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', border: 'rgba(239, 68, 68, 0.3)' },
        info: { bg: 'rgba(255,255,255,0.06)', text: 'inherit', border: 'rgba(255,255,255,0.1)' }
    };
    const c = colors[type] || colors.info;
    
    const toast = document.createElement('div');
    toast.id = 'memoryToast';
    toast.style.cssText = `
        position: absolute;
        top: 12px;
        left: 50%;
        transform: translateX(-50%);
        background: ${c.bg};
        color: ${c.text};
        border: 1px solid ${c.border};
        padding: 8px 16px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        z-index: 10001;
        backdrop-filter: blur(8px);
        animation: settingsFadeIn 0.18s ease-out;
        pointer-events: none;
    `;
    toast.textContent = message;
    
    // Anchor inside the settings panel if it exists, otherwise body
    const panel = document.querySelector('.settings-panel');
    if (panel) {
        panel.style.position = 'relative';
        panel.appendChild(toast);
    } else {
        document.body.appendChild(toast);
    }
    
    setTimeout(() => {
        toast.style.transition = 'opacity 0.25s';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 280);
    }, 2500);
}
