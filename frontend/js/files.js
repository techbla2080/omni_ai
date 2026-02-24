// ============================================================================
// OmniAI - File Management (Step 46 + Step 49 Search)
// ============================================================================

let uploadedFiles = [];
let attachedFiles = [];
let searchTimeout = null;

/**
 * Toggle files panel visibility
 */
function toggleFilesPanel() {
    const panel = document.getElementById('filesPanel');
    const sidebar = document.getElementById('sidebar');
    
    panel.classList.toggle('hidden');
    
    // Close sidebar if files panel is open (mobile)
    if (!panel.classList.contains('hidden') && window.innerWidth < 768) {
        sidebar.classList.add('collapsed');
    }
    
    // Load files when panel opens
    if (!panel.classList.contains('hidden')) {
        loadFiles();
    }
}

/**
 * Load all uploaded files from API
 */
async function loadFiles() {
    try {
        const response = await fetch(`${API_BASE}/api/v1/files`);
        if (!response.ok) throw new Error('Failed to load files');
        
        const data = await response.json();
        uploadedFiles = data.files || [];
        renderFiles();
        updateFilesStats();
    } catch (error) {
        console.error('Error loading files:', error);
        document.getElementById('filesList').innerHTML = 
            '<div class="empty-state">Failed to load files</div>';
    }
}

/**
 * Render files list in panel
 */
function renderFiles() {
    const container = document.getElementById('filesList');
    const filter = document.getElementById('fileTypeFilter').value;
    
    let filtered = uploadedFiles;
    
    // Apply filter
    if (filter) {
        filtered = uploadedFiles.filter(file => file.file_type === filter);
    }
    
    if (!filtered || filtered.length === 0) {
        container.innerHTML = '<div class="empty-state">No files uploaded yet.</div>';
        return;
    }
    
    container.innerHTML = filtered.map(file => `
        <div class="file-item" data-file-id="${file.file_id}">
            <div class="file-icon">${getFileIcon(file.original_filename || file.filename)}</div>
            <div class="file-info">
                <div class="file-name" title="${escapeHtml(file.original_filename || file.filename)}">${escapeHtml(truncateFilename(file.original_filename || file.filename, 25))}</div>
                <div class="file-meta">
                    <span class="file-size">${formatFileSize(file.file_size)}</span>
                    <span class="file-date">${formatDate(file.uploaded_at)}</span>
                </div>
            </div>
            <div class="file-actions">
                <button class="file-action-btn reference" onclick="referenceFile('${file.file_id}', '${escapeHtml(file.original_filename || file.filename)}')" title="Ask AI about this file">
                    💬
                </button>
                <button class="file-action-btn delete" onclick="deleteFile('${file.file_id}')" title="Delete file">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

/**
 * Filter files by type
 */
function filterFiles() {
    const searchInput = document.getElementById('fileSearchInput');
    if (searchInput && searchInput.value.trim()) {
        searchFiles();
    } else {
        renderFiles();
    }
}

/**
 * Get file category from mime type
 */
function getFileCategory(mimeType) {
    if (!mimeType) return 'other';
    
    if (mimeType.includes('pdf') || mimeType.includes('document') || mimeType.includes('msword')) {
        return 'document';
    }
    if (mimeType.includes('image')) {
        return 'image';
    }
    if (mimeType.includes('spreadsheet') || mimeType.includes('excel') || mimeType.includes('csv')) {
        return 'spreadsheet';
    }
    if (mimeType.includes('javascript') || mimeType.includes('python') || mimeType.includes('json') || mimeType.includes('text/plain')) {
        return 'code';
    }
    return 'other';
}

/**
 * Get icon for file type
 */
function getFileIcon(filename) {
    if (!filename) return '📁';
    const ext = filename.split('.').pop().toLowerCase();
    
    const icons = {
        'pdf': '📄',
        'doc': '📝',
        'docx': '📝',
        'xls': '📊',
        'xlsx': '📊',
        'csv': '📊',
        'png': '🖼️',
        'jpg': '🖼️',
        'jpeg': '🖼️',
        'gif': '🖼️',
        'webp': '🖼️',
        'py': '🐍',
        'js': '📜',
        'json': '📋',
        'txt': '📃',
        'md': '📃',
        'html': '🌐',
        'css': '🎨'
    };
    
    return icons[ext] || '📁';
}

/**
 * Format file size for display
 */
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

/**
 * Format date for display
 */
function formatDate(dateStr) {
    if (!dateStr) return '';
    
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 86400000 && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    if (diff < 172800000) {
        return 'Yesterday';
    }
    if (diff < 604800000) {
        return date.toLocaleDateString([], { weekday: 'short' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * Truncate filename if too long
 */
function truncateFilename(filename, maxLength) {
    if (!filename || filename.length <= maxLength) return filename || '';
    
    const ext = filename.split('.').pop();
    const name = filename.slice(0, -(ext.length + 1));
    const truncatedName = name.slice(0, maxLength - ext.length - 4) + '...';
    
    return truncatedName + '.' + ext;
}

/**
 * Update files statistics
 */
function updateFilesStats() {
    const statsContainer = document.getElementById('filesStats');
    
    if (!uploadedFiles || uploadedFiles.length === 0) {
        statsContainer.innerHTML = '';
        return;
    }
    
    const totalSize = uploadedFiles.reduce((sum, file) => sum + (file.file_size || 0), 0);
    
    statsContainer.innerHTML = `
        <div class="files-stats-grid">
            <div class="files-stat-item">
                <span class="files-stat-value">${uploadedFiles.length}</span>
                <span class="files-stat-label">Total Files</span>
            </div>
            <div class="files-stat-item">
                <span class="files-stat-value">${formatFileSize(totalSize)}</span>
                <span class="files-stat-label">Total Size</span>
            </div>
        </div>
    `;
}

/**
 * Delete a file
 */
async function deleteFile(fileId) {
    if (!confirm('Delete this file?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/files/${fileId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete file');
        
        await loadFiles();
    } catch (error) {
        console.error('Error deleting file:', error);
        alert('Failed to delete file');
    }
}

/**
 * Reference file in chat
 */
function referenceFile(fileId, filename) {
    const input = document.getElementById('messageInput');
    input.value = `Regarding the file "${filename}": `;
    input.focus();
    input.dataset.referencedFileId = fileId;
    toggleFilesPanel();
}

/**
 * Handle file selection for upload
 */
function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    
    files.forEach(file => {
        if (!attachedFiles.find(f => f.name === file.name)) {
            attachedFiles.push(file);
        }
    });
    
    displayAttachedFiles();
    event.target.value = '';
}

/**
 * Display attached files preview
 */
function displayAttachedFiles() {
    const container = document.getElementById('attachedFilesContainer');
    const filesDiv = document.getElementById('attachedFiles');
    
    if (!attachedFiles || attachedFiles.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'block';
    filesDiv.innerHTML = attachedFiles.map((file, index) => `
        <div class="file-item">
            <span class="file-icon">${getFileIcon(file.name)}</span>
            <div class="file-info">
                <div class="file-name">${escapeHtml(truncateFilename(file.name, 20))}</div>
                <div class="file-size">${formatFileSize(file.size)}</div>
            </div>
            <button class="file-remove" onclick="removeAttachedFile(${index})">×</button>
        </div>
    `).join('');
}

/**
 * Remove an attached file
 */
function removeAttachedFile(index) {
    attachedFiles.splice(index, 1);
    displayAttachedFiles();
}

/**
 * Upload attached files
 */
async function uploadFiles() {
    if (!attachedFiles || attachedFiles.length === 0) return [];
    
    const uploadedIds = [];
    
    for (const file of attachedFiles) {
        const formData = new FormData();
        formData.append('file', file);
        if (conversationId) {
            formData.append('conversation_id', conversationId);
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/v1/files/upload`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                uploadedIds.push({
                    file_id: result.file_id,
                    filename: result.original_filename
                });
            }
        } catch (error) {
            console.error('Error uploading file:', error);
        }
    }
    
    attachedFiles = [];
    displayAttachedFiles();
    
    if (!document.getElementById('filesPanel').classList.contains('hidden')) {
        loadFiles();
    }
    
    return uploadedIds;
}

/**
 * Trigger file input click
 */
function triggerFileUpload() {
    document.getElementById('fileInput').click();
}

// ============================================================================
// FILE SEARCH (STEP 49)
// ============================================================================

/**
 * Search files by content or filename
 */
function searchFiles() {
    const searchInput = document.getElementById('fileSearchInput');
    const query = searchInput.value.trim();
    
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }
    
    if (!query) {
        loadFiles();
        return;
    }
    
    // Debounce: wait 300ms after typing stops
    searchTimeout = setTimeout(async () => {
        await performFileSearch(query);
    }, 300);
}

/**
 * Perform the actual search API call
 */
async function performFileSearch(query) {
    const container = document.getElementById('filesList');
    const filter = document.getElementById('fileTypeFilter').value;
    
    container.innerHTML = '<div class="empty-state">🔍 Searching...</div>';
    
    try {
        let url = `${API_BASE}/api/v1/files/search?q=${encodeURIComponent(query)}`;
        if (filter) {
            url += `&file_type=${filter}`;
        }
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error('Search failed');
        }
        
        const data = await response.json();
        renderSearchResults(data.results, query);
        
    } catch (error) {
        console.error('Search error:', error);
        container.innerHTML = '<div class="empty-state">❌ Search failed</div>';
    }
}

/**
 * Render search results with highlighted snippets
 */
function renderSearchResults(results, query) {
    const container = document.getElementById('filesList');
    
    if (!results || results.length === 0) {
        container.innerHTML = `<div class="empty-state">No files found for "${escapeHtml(query)}"</div>`;
        return;
    }
    
    container.innerHTML = results.map(file => `
        <div class="file-item search-result" data-file-id="${file.file_id}">
            <div class="file-icon">${getFileIcon(file.filename)}</div>
            <div class="file-info">
                <div class="file-name" title="${escapeHtml(file.filename)}">${highlightMatch(escapeHtml(file.filename), query)}</div>
                <div class="file-snippet">${highlightMatch(escapeHtml(file.snippet), query)}</div>
                <div class="file-meta">
                    <span class="match-count">📍 ${file.match_count} match${file.match_count !== 1 ? 'es' : ''}</span>
                    <span class="file-type">${file.file_type}</span>
                </div>
            </div>
            <div class="file-actions">
                <button class="file-action-btn reference" onclick="referenceFile('${file.file_id}', '${escapeHtml(file.filename)}')" title="Ask AI about this file">
                    💬
                </button>
                <button class="file-action-btn delete" onclick="deleteFile('${file.file_id}')" title="Delete file">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
}

/**
 * Highlight matching text
 */
function highlightMatch(text, query) {
    if (!query || !text) return text;
    
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

/**
 * Escape regex special characters
 */
function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}