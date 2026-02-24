// ============================================================================
// OmniAI - Core Chat Application (Steps 1-55)
// ============================================================================

const API_BASE = 'http://localhost:8000';
let conversationId = null;
let isStreaming = false;

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('messageInput');
    if (input) {
        input.focus();
    }
    loadConversations();
});

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

function useSuggestion(text) {
    document.getElementById('messageInput').value = text;
    sendMessage();
}

function hideWelcome() {
    const welcome = document.getElementById('welcome');
    if (welcome) {
        welcome.style.display = 'none';
    }
}

function showWelcome() {
    const welcome = document.getElementById('welcome');
    if (welcome) {
        welcome.style.display = 'block';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

// ============================================================================
// MESSAGE DISPLAY
// ============================================================================

function addUserMessage(text, messageId = null, scroll = true) {
    hideWelcome();
    
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    
    if (messageId) {
        messageDiv.dataset.messageId = messageId;
    }
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar user">👤</div>
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
    
    if (messageId) {
        messageDiv.dataset.messageId = messageId;
    }
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">🚀</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content">${isHtml ? text : escapeHtml(text)}</div>
        ${messageId ? `
        <div class="message-actions">
            <button class="regenerate-btn" onclick="regenerateResponse('${messageId}')">
                🔄 Regenerate
            </button>
            <button class="regenerate-btn" onclick="regenerateWithModel('${messageId}', 'llama3.2:3b')">
                🔄 Try 3B
            </button>
        </div>
        <div class="feedback-buttons">
            <button class="feedback-btn thumbs-up" onclick="submitFeedback('${messageId}', 1)" title="Good response">
                👍 Helpful
            </button>
            <button class="feedback-btn thumbs-down" onclick="submitFeedback('${messageId}', -1)" title="Bad response">
                👎 Not helpful
            </button>
        </div>
        ` : ''}
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
    
    // Add run buttons to code blocks
    setTimeout(addRunButtons, 100);
}

function addTypingIndicator() {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = 'typing-indicator';
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">🚀</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

function streamAssistantMessage(text, messageId = null) {
    removeTypingIndicator();
    
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    if (messageId) {
        messageDiv.dataset.messageId = messageId;
    }
    
    const contentId = 'content-' + Date.now();
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar assistant">🚀</div>
            <div class="sender-name">OmniAI</div>
        </div>
        <div class="message-content" id="${contentId}"></div>
        ${messageId ? `
        <div class="message-actions">
            <button class="regenerate-btn" onclick="regenerateResponse('${messageId}')">
                🔄 Regenerate
            </button>
        </div>
        <div class="feedback-buttons">
            <button class="feedback-btn thumbs-up" onclick="submitFeedback('${messageId}', 1)">
                👍 Helpful
            </button>
            <button class="feedback-btn thumbs-down" onclick="submitFeedback('${messageId}', -1)">
                👎 Not helpful
            </button>
        </div>
        ` : ''}
    `;
    
    container.appendChild(messageDiv);
    
    const contentDiv = document.getElementById(contentId);
    let index = 0;
    
    const cursor = document.createElement('span');
    cursor.className = 'streaming-cursor';
    contentDiv.appendChild(cursor);
    
    function typeNextChar() {
        if (index < text.length) {
            const char = text[index];
            const textNode = document.createTextNode(char);
            contentDiv.insertBefore(textNode, cursor);
            index++;
            scrollToBottom();
            
            let delay = 20;
            if (char === ' ') delay = 10;
            else if (['.', '!', '?', ','].includes(char)) delay = 100;
            
            setTimeout(typeNextChar, delay);
        } else {
            cursor.remove();
            isStreaming = false;
            // Add run buttons after streaming completes
            setTimeout(addRunButtons, 100);
        }
    }
    
    isStreaming = true;
    typeNextChar();
}

function streamTextIntoElement(text, element) {
    let index = 0;
    element.style.opacity = '1';
    
    function typeNextChar() {
        if (index < text.length) {
            element.textContent += text[index];
            index++;
            
            let delay = 15;
            if (text[index - 1] === ' ') delay = 5;
            else if (['.', '!', '?'].includes(text[index - 1])) delay = 80;
            
            setTimeout(typeNextChar, delay);
        }
    }
    
    typeNextChar();
}

function addFileMessage(files) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    
    const fileList = files.map(f => `📎 ${escapeHtml(f.filename)}`).join('<br>');
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <div class="avatar user">👤</div>
            <div class="sender-name">You</div>
        </div>
        <div class="message-content">${fileList}</div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

// ============================================================================
// CODE EXECUTION (STEP 50)
// ============================================================================

function detectCodeExecution(message) {
    const patterns = [
        /^run[:\s]/i,
        /^execute[:\s]/i,
        /run this code/i,
        /execute this code/i,
        /run the following/i,
        /please run/i,
        /can you run/i
    ];
    return patterns.some(pattern => pattern.test(message));
}

function extractCodeFromMessage(message) {
    const pythonBlock = message.match(/```python\s*([\s\S]*?)\s*```/);
    if (pythonBlock) return pythonBlock[1].trim();
    
    const codeBlock = message.match(/```\s*([\s\S]*?)\s*```/);
    if (codeBlock) return codeBlock[1].trim();
    
    const runMatch = message.match(/(?:run|execute)[:\s]+([\s\S]*)/i);
    if (runMatch) return runMatch[1].trim();
    
    return null;
}

async function executeCode(code) {
    try {
        const response = await fetch(`${API_BASE}/api/v1/code/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        html += `
            <div class="code-result-section">
                <div class="code-result-label">Output:</div>
                <pre class="code-result-output">${escapeHtml(result.output)}</pre>
            </div>
        `;
    }
    
    if (result.error) {
        html += `
            <div class="code-result-section">
                <div class="code-result-label">Error:</div>
                <pre class="code-result-error">${escapeHtml(result.error)}</pre>
            </div>
        `;
    }
    
    if (!result.output && !result.error && result.success) {
        html += `
            <div class="code-result-section">
                <div class="code-result-output empty">Code executed successfully (no output)</div>
            </div>
        `;
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
            code.includes('print(') || 
            code.includes('def ') || 
            code.includes('class ') ||
            code.includes('import ') || 
            code.includes('for ') || 
            code.includes('while ') || 
            code.includes('if ') ||
            code.includes(' = ') ||
            /^\s*\w+\s*=/.test(code);
        
        if (isPythonLike && code.trim().length > 0) {
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
            pre.appendChild(runBtn);
        }
    });
}

// ============================================================================
// STEP 51: EXPORT CONVERSATIONS
// ============================================================================

/**
 * Export a conversation in the specified format
 */
async function exportConversation(convId, format = 'md') {
    try {
        const response = await fetch(
            `${API_BASE}/api/v1/conversations/${convId}/export?format=${format}`
        );
        
        if (!response.ok) throw new Error('Export failed');
        
        // Get filename from header
        const disposition = response.headers.get('Content-Disposition');
        let filename = `conversation.${format}`;
        if (disposition) {
            const match = disposition.match(/filename="(.+)"/);
            if (match) filename = match[1];
        }
        
        // Trigger download
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

/**
 * Export all conversations as backup JSON
 */
async function exportAllConversations() {
    try {
        const response = await fetch(`${API_BASE}/api/v1/conversations/export/all`);
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

/**
 * Show export format picker menu
 */
function showExportMenu(convId, buttonElement) {
    // Remove any existing menu
    const existing = document.querySelector('.export-menu');
    if (existing) existing.remove();
    
    const menu = document.createElement('div');
    menu.className = 'export-menu';
    menu.innerHTML = `
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'md')">
            📝 Markdown (.md)
        </div>
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'txt')">
            📄 Plain Text (.txt)
        </div>
        <div class="export-menu-item" onclick="exportConversation('${convId}', 'json')">
            📦 JSON (.json)
        </div>
    `;
    
    const rect = buttonElement.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = `${rect.bottom + 5}px`;
    menu.style.left = `${rect.left}px`;
    menu.style.zIndex = '1000';
    
    document.body.appendChild(menu);
    
    // Close on outside click
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
// STEP 52: EDIT & DELETE MESSAGES
// ============================================================================

/**
 * Edit a user message inline
 */
function editMessage(buttonElement) {
    const messageDiv = buttonElement.closest('.message');
    const contentDiv = messageDiv.querySelector('.message-content');
    const messageId = messageDiv.dataset.messageId;
    const originalText = contentDiv.textContent;
    
    // Replace content with textarea
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

/**
 * Save edited message and re-generate AI response
 */
async function saveEdit(messageId, buttonElement) {
    const messageDiv = buttonElement.closest('.message');
    const textarea = messageDiv.querySelector('.edit-textarea');
    const newContent = textarea.value.trim();
    
    if (!newContent) return;
    
    const contentDiv = messageDiv.querySelector('.message-content');
    contentDiv.textContent = newContent;
    
    // If we have a message ID, update on server and delete messages after this one
    if (messageId && messageId !== 'null') {
        try {
            // Update the message
            await fetch(`${API_BASE}/api/v1/messages/${messageId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newContent })
            });
            
            // Delete all messages after this one (AI responses)
            await fetch(`${API_BASE}/api/v1/messages/${messageId}/and-after`, {
                method: 'DELETE'
            });
        } catch (error) {
            console.error('Edit save error:', error);
        }
    }
    
    // Remove all messages after the edited one in the UI
    let nextSibling = messageDiv.nextElementSibling;
    while (nextSibling) {
        const toRemove = nextSibling;
        nextSibling = nextSibling.nextElementSibling;
        toRemove.remove();
    }
    
    // Re-send the edited message to get a new AI response
    addTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: newContent,
                user_id: 'web-user-001',
                conversation_id: conversationId
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            streamAssistantMessage(data.response, data.message_id);
        } else {
            removeTypingIndicator();
            streamAssistantMessage(`⚠️ Error: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        removeTypingIndicator();
        streamAssistantMessage('⚠️ Could not connect to server.');
    }
}

/**
 * Cancel message edit
 */
function cancelEdit(buttonElement, originalText) {
    const contentDiv = buttonElement.closest('.message-content');
    contentDiv.textContent = originalText;
}

/**
 * Delete a single message
 */
async function deleteMessage(messageId, buttonElement) {
    if (!confirm('Delete this message?')) return;
    
    const messageDiv = buttonElement.closest('.message');
    
    if (messageId && messageId !== 'null') {
        try {
            await fetch(`${API_BASE}/api/v1/messages/${messageId}`, {
                method: 'DELETE'
            });
        } catch (error) {
            console.error('Delete error:', error);
        }
    }
    
    // Fade out and remove
    messageDiv.style.opacity = '0';
    messageDiv.style.transition = 'opacity 0.3s';
    setTimeout(() => messageDiv.remove(), 300);
}

// ============================================================================
// STEP 53: KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', (e) => {
    // Ctrl+N / Cmd+N → New conversation
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        startNewConversation();
    }
    
    // Ctrl+/ / Cmd+/ → Focus search
    if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        const search = document.getElementById('conversationSearch') || document.getElementById('searchInput');
        if (search) search.focus();
    }
    
    // Ctrl+Shift+D → Toggle dark mode
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        if (typeof toggleDarkMode === 'function') toggleDarkMode();
        if (typeof toggleTheme === 'function') toggleTheme();
    }
    
    // Ctrl+E → Export current conversation
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        if (conversationId) {
            exportConversation(conversationId, 'md');
        }
    }
    
    // Escape → Close any open menus/modals
    if (e.key === 'Escape') {
        const exportMenu = document.querySelector('.export-menu');
        if (exportMenu) exportMenu.remove();
        
        const modal = document.querySelector('.modal-overlay');
        if (modal) modal.remove();
        
        // Close mobile sidebar
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            toggleSidebar();
        }
    }
    
    // ? → Show shortcuts help (only when not typing in input)
    if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
        e.preventDefault();
        toggleShortcutsHelp();
    }
});

function toggleShortcutsHelp() {
    const existing = document.querySelector('.shortcuts-modal');
    if (existing) {
        existing.remove();
        return;
    }
    
    const modal = document.createElement('div');
    modal.className = 'shortcuts-modal modal-overlay';
    modal.innerHTML = `
        <div class="shortcuts-content">
            <h3>⌨️ Keyboard Shortcuts</h3>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>N</kbd></span> <span>New conversation</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>/</kbd></span> <span>Search conversations</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>E</kbd></span> <span>Export conversation</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd></span> <span>Toggle dark mode</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>Esc</kbd></span> <span>Close menus</span></div>
            <div class="shortcut-row"><span class="shortcut-keys"><kbd>?</kbd></span> <span>Show this help</span></div>
            <button class="shortcuts-close-btn" onclick="this.closest('.modal-overlay').remove()">Close</button>
        </div>
    `;
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
    document.body.appendChild(modal);
}

// ============================================================================
// STEP 54: FULL-TEXT SEARCH
// ============================================================================

let searchDebounceTimer = null;

/**
 * Search across all messages in all conversations
 */
async function searchAllMessages(query) {
    if (!query || query.trim().length < 2) {
        hideSearchResults();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/search?q=${encodeURIComponent(query)}&limit=10`);
        
        if (!response.ok) return;
        
        const data = await response.json();
        displaySearchResults(data.results, query);
        
    } catch (error) {
        console.error('Search error:', error);
    }
}

function displaySearchResults(results, query) {
    // Remove existing results
    hideSearchResults();
    
    if (results.length === 0) {
        return;
    }
    
    const dropdown = document.createElement('div');
    dropdown.className = 'search-results-dropdown';
    dropdown.id = 'searchResultsDropdown';
    
    results.forEach(result => {
        const item = document.createElement('div');
        item.className = 'search-result-item';
        
        // Highlight matching text
        const preview = result.content_preview;
        const highlighted = highlightSearchTerm(preview, query);
        
        item.innerHTML = `
            <div class="search-result-title">${escapeHtml(result.conversation_title || 'Untitled')}</div>
            <div class="search-result-preview">${highlighted}</div>
            <div class="search-result-meta">${result.role} · ${result.timestamp ? new Date(result.timestamp).toLocaleDateString() : ''}</div>
        `;
        
        item.onclick = () => {
            loadConversation(result.conversation_id);
            hideSearchResults();
        };
        
        dropdown.appendChild(item);
    });
    
    // Position below search input
    const searchInput = document.getElementById('conversationSearch') || document.getElementById('searchInput');
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
    const regex = new RegExp(`(${escaped})`, 'gi');
    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
}

/**
 * Debounced search handler - attach to your search input
 */
function handleSearchInput(event) {
    const query = event.target.value.trim();
    
    clearTimeout(searchDebounceTimer);
    
    if (query.length < 2) {
        hideSearchResults();
        return;
    }
    
    searchDebounceTimer = setTimeout(() => {
        searchAllMessages(query);
    }, 300);
}

// ============================================================================
// STEP 55: MOBILE SIDEBAR TOGGLE
// ============================================================================

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('show');
}

// Close sidebar when selecting a conversation on mobile
function closeSidebarOnMobile() {
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    }
}

// ============================================================================
// SEND MESSAGE
// ============================================================================

async function sendMessage() {
    if (isStreaming) return;
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message && attachedFiles.length === 0) return;
    
    // Handle file uploads first
    let uploadedFilesList = null;
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
    } else if (!uploadedFilesList) {
        return;
    }
    
    // Check for code execution request
    if (message && detectCodeExecution(message)) {
        const code = extractCodeFromMessage(message);
        
        if (code) {
            addTypingIndicator();
            const codeResult = await executeCode(code);
            removeTypingIndicator();
            
            const resultHtml = formatCodeResult(codeResult);
            const responseHtml = `I ran your code:\n\n<pre><code>${escapeHtml(code)}</code></pre>\n\n${resultHtml}`;
            addAssistantMessage(responseHtml, null, true);
            return;
        }
    }
    
    // Normal message flow
    addTypingIndicator();
    
    const sendButton = document.getElementById('sendButton');
    sendButton.disabled = true;
    
    try {
        const requestBody = {
            message: message || "I uploaded some files. Please analyze them.",
            user_id: 'web-user-001',
            conversation_id: conversationId
        };
        
        if (uploadedFilesList && uploadedFilesList.length > 0) {
            requestBody.file_ids = uploadedFilesList.map(f => f.file_id);
        }
        
        const response = await fetch(`${API_BASE}/api/v1/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            conversationId = data.conversation_id;
            streamAssistantMessage(data.response, data.message_id);
            loadConversations();
        } else {
            removeTypingIndicator();
            streamAssistantMessage(`⚠️ Error: ${data.detail || 'Unknown error'}`);
        }
        
    } catch (error) {
        console.error('Error:', error);
        removeTypingIndicator();
        streamAssistantMessage('⚠️ Could not connect to server.');
    } finally {
        sendButton.disabled = false;
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
        const response = await fetch(`${API_BASE}/api/v1/chat/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                message_id: messageId
            })
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

async function regenerateWithModel(messageId, model) {
    if (!conversationId || !messageId) return;
    
    const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
    if (!messageDiv) return;
    
    const contentDiv = messageDiv.querySelector('.message-content');
    const originalContent = contentDiv.innerHTML;
    contentDiv.style.opacity = '0.5';
    
    const buttons = messageDiv.querySelectorAll('.regenerate-btn');
    buttons.forEach(btn => btn.disabled = true);
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/chat/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                message_id: messageId,
                model: model
            })
        });
        
        if (!response.ok) throw new Error('Regeneration failed');
        
        const data = await response.json();
        contentDiv.innerHTML = '';
        streamTextIntoElement(data.response, contentDiv);
        
    } catch (error) {
        console.error('Error:', error);
        contentDiv.innerHTML = originalContent;
        contentDiv.style.opacity = '1';
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
        const response = await fetch(`${API_BASE}/api/v1/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message_id: messageId,
                conversation_id: conversationId,
                rating: rating
            })
        });
        
        if (!response.ok) throw new Error('Feedback failed');
        
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const thumbsUpBtn = messageDiv.querySelector('.thumbs-up');
            const thumbsDownBtn = messageDiv.querySelector('.thumbs-down');
            
            thumbsUpBtn.classList.remove('active');
            thumbsDownBtn.classList.remove('active');
            
            if (rating === 1) {
                thumbsUpBtn.classList.add('active');
            } else {
                thumbsDownBtn.classList.add('active');
            }
        }
        
    } catch (error) {
        console.error('Feedback error:', error);
    }
}

// ============================================================================
// NOTE: KEEP YOUR EXISTING FUNCTIONS BELOW THIS LINE
// ============================================================================
// The following functions should already exist in your app.js from previous
// steps. If they're in a separate section of your file, keep them as-is:
//
// - loadConversations()
// - loadConversation(id)
// - startNewConversation()
// - deleteConversation(id)
// - renameConversation(id)
// - toggleDarkMode() / toggleTheme()
// - attachedFiles, uploadFiles(), displayAttachedFiles()
//
// IMPORTANT: In your loadConversations() function, add the export button
// to each conversation item in the sidebar. Look for where you create
// conversation items and add:
//
//   <button class="conv-action-btn" onclick="event.stopPropagation(); showExportMenu('${conv.id}', this)" title="Export">📥</button>
//
// Also in loadConversation(), add closeSidebarOnMobile() call at the end
// so the sidebar closes when user picks a conversation on mobile.
// ============================================================================