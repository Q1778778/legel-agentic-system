// Main JavaScript - Apple Design System
'use strict';

// Configuration
const API_BASE_URL = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';

// Application State
const AppState = {
    theme: localStorage.getItem('theme') || 'light',
    currentCase: null,
    currentChat: null,
    isLoading: false,
    messages: [],
    cases: [],
    websocket: null
};

// DOM Elements Cache
const DOM = {};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initializeDOM();
    initializeTheme();
    initializeEventListeners();
    initializeWebSocket();
    loadInitialData();
    initializeAnimations();
});

// Initialize DOM References
function initializeDOM() {
    DOM.themeToggle = document.getElementById('themeToggle');
    DOM.notificationBtn = document.getElementById('notificationBtn');
    DOM.profileBtn = document.getElementById('profileBtn');
    DOM.startAnalysis = document.getElementById('startAnalysis');
    DOM.viewDemo = document.getElementById('viewDemo');
    DOM.mainContent = document.getElementById('mainContent');
    DOM.chatMessages = document.getElementById('chatMessages');
    DOM.chatInput = document.getElementById('chatInput');
    DOM.sendBtn = document.getElementById('sendBtn');
    DOM.attachBtn = document.getElementById('attachBtn');
    DOM.clearChat = document.getElementById('clearChat');
    DOM.exportChat = document.getElementById('exportChat');
    DOM.fileUploadArea = document.getElementById('fileUploadArea');
    DOM.fileInput = document.getElementById('fileInput');
    DOM.casePanel = document.getElementById('casePanel');
    DOM.newCaseModal = document.getElementById('newCaseModal');
    DOM.loadingOverlay = document.getElementById('loadingOverlay');
    DOM.toastContainer = document.getElementById('toastContainer');
}

// Initialize Theme
function initializeTheme() {
    document.body.setAttribute('data-theme', AppState.theme);
    updateThemeIcon();
}

// Update Theme Icon
function updateThemeIcon() {
    const icon = DOM.themeToggle.querySelector('i');
    if (AppState.theme === 'dark') {
        icon.className = 'ti ti-moon';
    } else {
        icon.className = 'ti ti-sun';
    }
}

// Initialize Event Listeners
function initializeEventListeners() {
    // Theme Toggle
    DOM.themeToggle?.addEventListener('click', toggleTheme);
    
    // Navigation Actions
    DOM.notificationBtn?.addEventListener('click', showNotifications);
    DOM.profileBtn?.addEventListener('click', showProfile);
    
    // Hero Actions
    DOM.startAnalysis?.addEventListener('click', startAnalysisFlow);
    DOM.viewDemo?.addEventListener('click', playDemo);
    
    // Chat Actions
    DOM.sendBtn?.addEventListener('click', sendMessage);
    DOM.chatInput?.addEventListener('keydown', handleChatInput);
    DOM.attachBtn?.addEventListener('click', () => DOM.fileInput.click());
    DOM.clearChat?.addEventListener('click', clearChatHistory);
    DOM.exportChat?.addEventListener('click', exportChatHistory);
    
    // File Upload
    DOM.fileInput?.addEventListener('change', handleFileSelect);
    DOM.fileUploadArea?.addEventListener('click', () => DOM.fileInput.click());
    DOM.fileUploadArea?.addEventListener('dragover', handleDragOver);
    DOM.fileUploadArea?.addEventListener('drop', handleDrop);
    
    // Quick Actions
    document.querySelectorAll('.quick-action-btn').forEach(btn => {
        btn.addEventListener('click', handleQuickAction);
    });
    
    // Feature Cards
    document.querySelectorAll('.feature-card').forEach(card => {
        card.addEventListener('click', handleFeatureClick);
    });
    
    // Panel Tabs
    document.querySelectorAll('.tab-btn').forEach(tab => {
        tab.addEventListener('click', handleTabSwitch);
    });
    
    // Auto-resize textarea
    DOM.chatInput?.addEventListener('input', autoResizeTextarea);
}

// Theme Toggle
function toggleTheme() {
    AppState.theme = AppState.theme === 'light' ? 'dark' : 'light';
    document.body.setAttribute('data-theme', AppState.theme);
    localStorage.setItem('theme', AppState.theme);
    updateThemeIcon();
    
    // Smooth transition
    document.body.style.transition = 'background-color 0.3s ease, color 0.3s ease';
    setTimeout(() => {
        document.body.style.transition = '';
    }, 300);
}

// Show Notifications
function showNotifications() {
    showToast('您有3条新通知', 'info');
}

// Show Profile
function showProfile() {
    showToast('个人资料功能即将推出', 'info');
}

// Start Analysis Flow
function startAnalysisFlow() {
    // Hide hero, show main content
    document.querySelector('.hero').style.display = 'none';
    document.querySelector('.features').style.display = 'none';
    DOM.mainContent.style.display = 'block';
    
    // Animate entrance
    DOM.mainContent.classList.add('animate-fadeIn');
    
    // Focus on chat input
    setTimeout(() => {
        DOM.chatInput?.focus();
    }, 300);
}

// Play Demo
function playDemo() {
    showLoading('正在加载演示...');
    
    setTimeout(() => {
        hideLoading();
        startAnalysisFlow();
        
        // Auto-type demo message
        const demoMessage = '请帮我分析这份合同中的潜在风险点';
        typeMessage(demoMessage);
    }, 1500);
}

// Type Message Animation
function typeMessage(text) {
    let index = 0;
    DOM.chatInput.value = '';
    
    const typeInterval = setInterval(() => {
        if (index < text.length) {
            DOM.chatInput.value += text[index];
            index++;
            autoResizeTextarea();
        } else {
            clearInterval(typeInterval);
        }
    }, 50);
}

// Send Message
async function sendMessage() {
    const message = DOM.chatInput.value.trim();
    if (!message) return;
    
    // Add user message
    addMessage('user', message);
    
    // Clear input
    DOM.chatInput.value = '';
    autoResizeTextarea();
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        // Send to API
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                case_id: AppState.currentCase,
                session_id: AppState.currentChat
            })
        });
        
        if (!response.ok) throw new Error('Failed to send message');
        
        const data = await response.json();
        
        // Hide typing indicator
        hideTypingIndicator();
        
        // Add assistant response
        addMessage('assistant', data.response);
        
        // Update analysis panel if needed
        if (data.analysis) {
            updateAnalysisPanel(data.analysis);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        hideTypingIndicator();
        addMessage('assistant', '抱歉，发送消息时出现错误。请稍后重试。');
    }
}

// Handle Chat Input
function handleChatInput(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// Add Message to Chat
function addMessage(type, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type} animate-slideInUp`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.textContent = type === 'user' ? 'U' : 'AI';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';
    bubbleDiv.textContent = content;
    
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });
    
    contentDiv.appendChild(bubbleDiv);
    contentDiv.appendChild(timeDiv);
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    // Remove welcome message if exists
    const welcomeMessage = DOM.chatMessages.querySelector('.message-welcome');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
    
    DOM.chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
    
    // Store in state
    AppState.messages.push({ type, content, time: new Date() });
}

// Show Typing Indicator
function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant typing-indicator animate-fadeIn';
    indicator.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    DOM.chatMessages.appendChild(indicator);
    DOM.chatMessages.scrollTop = DOM.chatMessages.scrollHeight;
}

// Hide Typing Indicator
function hideTypingIndicator() {
    const indicator = DOM.chatMessages.querySelector('.typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

// Clear Chat History
function clearChatHistory() {
    if (confirm('确定要清除所有聊天记录吗？')) {
        DOM.chatMessages.innerHTML = `
            <div class="message-welcome">
                <div class="welcome-icon">
                    <i class="ti ti-scale"></i>
                </div>
                <h3>欢迎使用法律智能助手</h3>
                <p>我可以帮助您进行法律分析、案例检索、风险评估等任务。请告诉我您需要什么帮助？</p>
                <div class="quick-actions">
                    <button class="quick-action-btn" data-action="analyze-contract">
                        <i class="ti ti-file-text"></i>
                        分析合同
                    </button>
                    <button class="quick-action-btn" data-action="search-case">
                        <i class="ti ti-search"></i>
                        搜索案例
                    </button>
                    <button class="quick-action-btn" data-action="risk-assessment">
                        <i class="ti ti-alert-triangle"></i>
                        风险评估
                    </button>
                </div>
            </div>
        `;
        AppState.messages = [];
        showToast('聊天记录已清除', 'success');
        
        // Re-attach quick action listeners
        document.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', handleQuickAction);
        });
    }
}

// Export Chat History
function exportChatHistory() {
    if (AppState.messages.length === 0) {
        showToast('没有可导出的聊天记录', 'warning');
        return;
    }
    
    const chatData = {
        exportDate: new Date().toISOString(),
        messages: AppState.messages
    };
    
    const blob = new Blob([JSON.stringify(chatData, null, 2)], {
        type: 'application/json'
    });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat-export-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast('聊天记录已导出', 'success');
}

// Handle Quick Action
function handleQuickAction(e) {
    const action = e.currentTarget.dataset.action;
    let message = '';
    
    switch (action) {
        case 'analyze-contract':
            message = '我需要分析一份合同，请告诉我如何上传文件。';
            DOM.fileUploadArea.classList.add('active');
            break;
        case 'search-case':
            message = '我想搜索相关的法律案例。';
            break;
        case 'risk-assessment':
            message = '请帮我进行法律风险评估。';
            break;
    }
    
    if (message) {
        DOM.chatInput.value = message;
        autoResizeTextarea();
        sendMessage();
    }
}

// Handle Feature Click
function handleFeatureClick(e) {
    const feature = e.currentTarget.dataset.feature;
    startAnalysisFlow();
    
    setTimeout(() => {
        let message = '';
        switch (feature) {
            case 'smart-analysis':
                message = '我需要进行智能法律分析。';
                break;
            case 'case-search':
                message = '我想搜索相关法律案例。';
                break;
            case 'risk-assessment':
                message = '请帮我评估法律风险。';
                break;
            case 'document-generation':
                message = '我需要生成法律文书。';
                break;
        }
        
        if (message) {
            DOM.chatInput.value = message;
            autoResizeTextarea();
            sendMessage();
        }
    }, 500);
}

// Handle Tab Switch
function handleTabSwitch(e) {
    const targetTab = e.currentTarget.dataset.tab;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    e.currentTarget.classList.add('active');
    
    // Update tab panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    document.getElementById(`${targetTab}Tab`)?.classList.add('active');
}

// Auto-resize Textarea
function autoResizeTextarea() {
    DOM.chatInput.style.height = 'auto';
    DOM.chatInput.style.height = Math.min(DOM.chatInput.scrollHeight, 120) + 'px';
}

// File Handling
function handleFileSelect(e) {
    const files = e.target.files;
    handleFiles(files);
}

function handleDragOver(e) {
    e.preventDefault();
    DOM.fileUploadArea.classList.add('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    DOM.fileUploadArea.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    handleFiles(files);
}

async function handleFiles(files) {
    if (files.length === 0) return;
    
    showLoading('正在上传文件...');
    
    const formData = new FormData();
    for (let file of files) {
        formData.append('files', file);
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) throw new Error('Upload failed');
        
        const data = await response.json();
        hideLoading();
        
        showToast(`成功上传 ${files.length} 个文件`, 'success');
        
        // Add message about uploaded files
        addMessage('user', `我上传了 ${files.length} 个文件进行分析`);
        
        // Hide upload area
        DOM.fileUploadArea.classList.remove('active');
        
    } catch (error) {
        console.error('Error uploading files:', error);
        hideLoading();
        showToast('文件上传失败，请重试', 'error');
    }
}

// WebSocket Connection
function initializeWebSocket() {
    try {
        AppState.websocket = new WebSocket(WS_URL);
        
        AppState.websocket.onopen = () => {
            console.log('WebSocket connected');
        };
        
        AppState.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        };
        
        AppState.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        AppState.websocket.onclose = () => {
            console.log('WebSocket disconnected');
            // Attempt to reconnect after 5 seconds
            setTimeout(initializeWebSocket, 5000);
        };
        
    } catch (error) {
        console.error('Failed to initialize WebSocket:', error);
    }
}

// Handle WebSocket Messages
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'analysis_update':
            updateAnalysisPanel(data.analysis);
            break;
        case 'case_update':
            updateCaseList(data.cases);
            break;
        case 'notification':
            showToast(data.message, data.level || 'info');
            break;
    }
}

// Update Analysis Panel
function updateAnalysisPanel(analysis) {
    const analysisTab = document.getElementById('analysisTab');
    if (!analysisTab) return;
    
    analysisTab.innerHTML = `
        <div class="analysis-results animate-fadeIn">
            <h3>分析结果</h3>
            ${analysis.summary ? `
                <div class="analysis-section">
                    <h4>摘要</h4>
                    <p>${analysis.summary}</p>
                </div>
            ` : ''}
            ${analysis.risks ? `
                <div class="analysis-section">
                    <h4>风险评估</h4>
                    <ul>
                        ${analysis.risks.map(risk => `
                            <li class="risk-item ${risk.level}">
                                <span class="risk-level">${risk.level}</span>
                                <span>${risk.description}</span>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            ` : ''}
            ${analysis.recommendations ? `
                <div class="analysis-section">
                    <h4>建议</h4>
                    <ul>
                        ${analysis.recommendations.map(rec => `
                            <li>${rec}</li>
                        `).join('')}
                    </ul>
                </div>
            ` : ''}
        </div>
    `;
}

// Load Initial Data
async function loadInitialData() {
    try {
        // Load user preferences
        const preferences = localStorage.getItem('userPreferences');
        if (preferences) {
            Object.assign(AppState, JSON.parse(preferences));
        }
        
        // You can load more initial data here
        
    } catch (error) {
        console.error('Error loading initial data:', error);
    }
}

// Initialize Animations
function initializeAnimations() {
    // Intersection Observer for scroll animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-fadeIn');
            }
        });
    }, {
        threshold: 0.1
    });
    
    // Observe elements for animation
    document.querySelectorAll('.feature-card').forEach(card => {
        observer.observe(card);
    });
}

// Loading Overlay
function showLoading(message = '加载中...') {
    DOM.loadingOverlay.querySelector('p').textContent = message;
    DOM.loadingOverlay.classList.add('active');
}

function hideLoading() {
    DOM.loadingOverlay.classList.remove('active');
}

// Toast Notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type} animate-slideInRight`;
    
    const icon = {
        success: 'ti-check',
        error: 'ti-x',
        warning: 'ti-alert-triangle',
        info: 'ti-info-circle'
    }[type];
    
    toast.innerHTML = `
        <i class="ti ${icon}"></i>
        <span>${message}</span>
    `;
    
    DOM.toastContainer.appendChild(toast);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        toast.classList.add('animate-fadeOut');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Export for use in other modules
window.LegalAI = {
    AppState,
    showToast,
    showLoading,
    hideLoading,
    addMessage
};