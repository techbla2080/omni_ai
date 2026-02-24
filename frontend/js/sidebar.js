// ============================================================================
// OmniAI - Sidebar & Conversations Management
// ============================================================================

let conversations = [];

/**
 * Toggle sidebar visibility
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('hidden');
}

/**
 * Load all conversations from API
 */
async function loadConversations() {
    try {
        const response = await fetch(`${API_BASE}/api/v1/chat/conversations?limit=50`);
        if (!response.ok) throw new Error('Failed to load conversations');
        
        const data = await response.json();
        conversations = data.conversations || [];
        renderConversations();
    } catch (error) {
        console.error('Error loading conversations:', error);
    }
}

/**
 * Render conversations list in sidebar
 */
function renderConversations() {
    const container = document.getElementById('conversationsList');
    
    if (!conversations || conversations.length === 0) {
        container.innerHTML = '<div class="empty-state">No conversations yet.<br>Start chatting to create one!</div>';
        return;
    }
    
    container.innerHTML = conversations.map(conv => `
        <div class="conversation-item ${conv.id === conversationId ? 'active' : ''}" 
             onclick="selectConversation('${conv.id}')"
             data-conv-id="${conv.id}">
            <div class="conversation-actions">
                <button class="edit-btn" onclick="editTitle(event, '${conv.id}')" title="Rename">✏️</button>
                <button class="delete-btn" onclick="deleteConversation(event, '${conv.id}')" title="Delete">×</button>
            </div>
            <div class="conversation-title" data-title="${escapeHtml(conv.title || 'New Conversation')}">${escapeHtml(conv.title || 'New Conversation')}</div>
            <div class="conversation-time">${formatTime(conv.updated_at)}</div>
        </div>
    `).join('');
}

/**
 * Select and load a conversation
 */
async function selectConversation(convId) {
    conversationId = convId;
    renderConversations();
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/chat/conversations/${convId}`);
        if (!response.ok) throw new Error('Failed to load messages');
        
        const data = await response.json();
        displayConversationMessages(data.messages || []);
        hideWelcome();
    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

/**
 * Display messages from a conversation
 */
function displayConversationMessages(messages) {
    const container = document.getElementById('messagesContainer');
    container.innerHTML = '';
    
    messages.forEach(msg => {
        if (msg.role === 'user') {
            addUserMessage(msg.content, false);
        } else if (msg.role === 'assistant') {
            addAssistantMessage(msg.content, msg.id);
        }
    });
    
    scrollToBottom();
}

/**
 * Create a new conversation
 */
function newChat() {
    conversationId = null;
    
    const container = document.getElementById('messagesContainer');
    container.innerHTML = `
        <div class="welcome" id="welcome">
            <h1>How can I help you today?</h1>
            <p>I'm OmniAI, your intelligent assistant with memory. I can help with emails, calendar, research, coding, and more.</p>
            
            <div class="suggestions">
                <div class="suggestion-card" onclick="useSuggestion('What can you do?')">
                    <div class="suggestion-title">💡 Discover capabilities</div>
                    <div class="suggestion-text">See all my features</div>
                </div>
                <div class="suggestion-card" onclick="useSuggestion('Help me write Python code')">
                    <div class="suggestion-title">💻 Code assistance</div>
                    <div class="suggestion-text">Generate and debug code</div>
                </div>
                <div class="suggestion-card" onclick="useSuggestion('Explain quantum computing')">
                    <div class="suggestion-title">🔍 Research & explain</div>
                    <div class="suggestion-text">Deep dive into topics</div>
                </div>
                <div class="suggestion-card" onclick="useSuggestion('Plan a trip to Paris')">
                    <div class="suggestion-title">✈️ Travel planning</div>
                    <div class="suggestion-text">Create itineraries</div>
                </div>
            </div>
        </div>
    `;
    
    renderConversations();
    
    const input = document.getElementById('messageInput');
    if (input) {
        input.value = '';
        input.style.height = 'auto';
        input.focus();
    }
}

/**
 * Delete a conversation
 */
async function deleteConversation(event, convId) {
    event.stopPropagation();
    
    if (!confirm('Delete this conversation?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/chat/conversations/${convId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete');
        
        if (convId === conversationId) {
            newChat();
        }
        
        await loadConversations();
    } catch (error) {
        console.error('Error deleting conversation:', error);
        alert('Failed to delete conversation');
    }
}

/**
 * Edit conversation title
 */
async function editTitle(event, convId) {
    event.stopPropagation();
    
    const item = document.querySelector(`[data-conv-id="${convId}"]`);
    if (!item) return;
    
    const titleDiv = item.querySelector('.conversation-title');
    const currentTitle = titleDiv.dataset.title;
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'title-input';
    input.value = currentTitle;
    
    titleDiv.replaceWith(input);
    input.focus();
    input.select();
    
    const saveTitle = async () => {
        const newTitle = input.value.trim() || currentTitle;
        
        try {
            await fetch(`${API_BASE}/api/v1/chat/conversations/${convId}/title`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });
            
            loadConversations();
        } catch (error) {
            console.error('Error updating title:', error);
            loadConversations();
        }
    };
    
    input.addEventListener('blur', saveTitle);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            input.blur();
        }
    });
}

/**
 * Search conversations
 */
function searchConversations() {
    const query = document.getElementById('searchBox').value.toLowerCase();
    
    if (!query) {
        renderConversations();
        return;
    }
    
    const filtered = conversations.filter(conv => 
        (conv.title || 'New Conversation').toLowerCase().includes(query)
    );
    
    const container = document.getElementById('conversationsList');
    
    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state">No matches found</div>';
        return;
    }
    
    container.innerHTML = filtered.map(conv => `
        <div class="conversation-item ${conv.id === conversationId ? 'active' : ''}" 
             onclick="selectConversation('${conv.id}')"
             data-conv-id="${conv.id}">
            <div class="conversation-actions">
                <button class="edit-btn" onclick="editTitle(event, '${conv.id}')" title="Rename">✏️</button>
                <button class="delete-btn" onclick="deleteConversation(event, '${conv.id}')" title="Delete">×</button>
            </div>
            <div class="conversation-title" data-title="${escapeHtml(conv.title || 'New Conversation')}">${escapeHtml(conv.title || 'New Conversation')}</div>
            <div class="conversation-time">${formatTime(conv.updated_at)}</div>
        </div>
    `).join('');
}

/**
 * Format timestamp for display
 */
function formatTime(timestamp) {
    if (!timestamp) return 'Just now';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days}d ago`;
    
    return date.toLocaleDateString();
}
