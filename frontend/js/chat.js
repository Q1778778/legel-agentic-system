// Chat Interface Management
'use strict';

// Chat State
const ChatState = {
    currentSession: null,
    sessions: [],
    isTyping: false,
    uploadedFiles: [],
    streamingResponse: null,
    messageQueue: []
};

// Message Templates
const MessageTemplates = {
    welcome: {
        type: 'system',
        content: '欢迎使用法律智能助手！我可以帮助您进行：\n• 合同分析与风险评估\n• 法律案例检索\n• 法律文书生成\n• 合规性检查\n\n请问有什么可以帮助您的？'
    },
    analyzing: {
        type: 'system',
        content: '正在分析您的请求，请稍候...'
    },
    error: {
        type: 'system',
        content: '抱歉，处理您的请求时出现错误。请稍后重试或联系支持团队。'
    }
};

// Initialize Chat
document.addEventListener('DOMContentLoaded', () => {
    initializeChat();
    initializeChatSession();
});

// Initialize Chat
function initializeChat() {
    // Initialize markdown renderer
    if (window.marked) {
        window.marked.setOptions({
            highlight: function(code, lang) {
                if (window.hljs && lang && window.hljs.getLanguage(lang)) {
                    return window.hljs.highlight(code, { language: lang }).value;
                }
                return code;
            },
            breaks: true,
            gfm: true
        });
    }
    
    // Initialize voice input if available
    initializeVoiceInput();
    
    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();
}

// Initialize Chat Session
async function initializeChatSession() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/chat/session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                case_id: window.LegalAI?.AppState?.currentCase
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            ChatState.currentSession = data.session_id;
        }
    } catch (error) {
        console.error('Error initializing chat session:', error);
        // Generate local session ID as fallback
        ChatState.currentSession = generateSessionId();
    }
    
    // Show welcome message
    addSystemMessage(MessageTemplates.welcome.content);
}

// Generate Session ID
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// Initialize Voice Input
function initializeVoiceInput() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;
    
    // Add voice input button
    const chatInputWrapper = document.querySelector('.chat-input-wrapper');
    if (chatInputWrapper) {
        const voiceBtn = document.createElement('button');
        voiceBtn.className = 'btn-icon';
        voiceBtn.id = 'voiceInputBtn';
        voiceBtn.innerHTML = '<i class="ti ti-microphone"></i>';
        voiceBtn.title = '语音输入';
        
        chatInputWrapper.insertBefore(voiceBtn, chatInputWrapper.lastElementChild);
        
        voiceBtn.addEventListener('click', () => {
            if (ChatState.isListening) {
                recognition.stop();
            } else {
                recognition.start();
            }
        });
    }
    
    recognition.onstart = () => {
        ChatState.isListening = true;
        document.getElementById('voiceInputBtn')?.classList.add('listening');
        window.LegalAI.showToast('正在听取语音输入...', 'info');
    };
    
    recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
            .map(result => result[0].transcript)
            .join('');
        
        const chatInput = document.getElementById('chatInput');
        if (chatInput) {
            chatInput.value = transcript;
            window.LegalAI.autoResizeTextarea();
        }
    };
    
    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        window.LegalAI.showToast('语音识别失败', 'error');
    };
    
    recognition.onend = () => {
        ChatState.isListening = false;
        document.getElementById('voiceInputBtn')?.classList.remove('listening');
    };
    
    ChatState.recognition = recognition;
}

// Initialize Keyboard Shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + / for help
        if ((e.metaKey || e.ctrlKey) && e.key === '/') {
            e.preventDefault();
            showChatHelp();
        }
        
        // Cmd/Ctrl + L to clear chat
        if ((e.metaKey || e.ctrlKey) && e.key === 'l') {
            e.preventDefault();
            if (confirm('确定要清除聊天记录吗？')) {
                clearChatHistory();
            }
        }
        
        // Cmd/Ctrl + S to save chat
        if ((e.metaKey || e.ctrlKey) && e.key === 's') {
            e.preventDefault();
            exportChatHistory();
        }
    });
}

// Enhanced Send Message
async function sendEnhancedMessage(message, files = []) {
    if (!message && files.length === 0) return;
    
    // Add user message immediately
    const userMessageId = addUserMessage(message, files);
    
    // Show typing indicator
    const typingId = showEnhancedTypingIndicator();
    
    // Prepare request data
    const requestData = {
        message: message,
        files: files.map(f => ({
            name: f.name,
            type: f.type,
            size: f.size,
            data: f.data // Base64 encoded
        })),
        session_id: ChatState.currentSession,
        case_id: window.LegalAI?.AppState?.currentCase,
        context: getConversationContext()
    };
    
    try {
        // Check if streaming is supported
        if (supportsStreaming()) {
            await sendStreamingMessage(requestData, typingId);
        } else {
            await sendRegularMessage(requestData, typingId);
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator(typingId);
        addErrorMessage('发送消息时出现错误，请重试。');
    }
}

// Send Streaming Message
async function sendStreamingMessage(requestData, typingId) {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    });
    
    if (!response.ok) throw new Error('Stream request failed');
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    removeTypingIndicator(typingId);
    
    let assistantMessageId = null;
    let accumulatedContent = '';
    
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.slice(6));
                    
                    if (data.type === 'content') {
                        accumulatedContent += data.content;
                        
                        if (!assistantMessageId) {
                            assistantMessageId = addAssistantMessage('', true);
                        }
                        
                        updateStreamingMessage(assistantMessageId, accumulatedContent);
                    } else if (data.type === 'analysis') {
                        updateAnalysisPanel(data.analysis);
                    } else if (data.type === 'complete') {
                        finalizeStreamingMessage(assistantMessageId);
                    }
                } catch (e) {
                    console.error('Error parsing stream data:', e);
                }
            }
        }
    }
}

// Send Regular Message
async function sendRegularMessage(requestData, typingId) {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    });
    
    if (!response.ok) throw new Error('Request failed');
    
    const data = await response.json();
    
    removeTypingIndicator(typingId);
    
    // Add assistant response
    addAssistantMessage(data.response);
    
    // Update analysis if provided
    if (data.analysis) {
        updateAnalysisPanel(data.analysis);
    }
    
    // Handle additional actions
    if (data.actions) {
        handleResponseActions(data.actions);
    }
}

// Add User Message
function addUserMessage(content, files = []) {
    const messageId = 'msg_' + Date.now();
    const messageDiv = createMessageElement('user', content, files);
    messageDiv.id = messageId;
    
    appendMessage(messageDiv);
    
    // Store in state
    ChatState.messages.push({
        id: messageId,
        type: 'user',
        content: content,
        files: files,
        timestamp: new Date()
    });
    
    return messageId;
}

// Add Assistant Message
function addAssistantMessage(content, isStreaming = false) {
    const messageId = 'msg_' + Date.now();
    const messageDiv = createMessageElement('assistant', content);
    messageDiv.id = messageId;
    
    if (isStreaming) {
        messageDiv.classList.add('streaming');
    }
    
    appendMessage(messageDiv);
    
    // Store in state
    ChatState.messages.push({
        id: messageId,
        type: 'assistant',
        content: content,
        timestamp: new Date(),
        isStreaming: isStreaming
    });
    
    return messageId;
}

// Add System Message
function addSystemMessage(content) {
    const messageDiv = createMessageElement('system', content);
    appendMessage(messageDiv);
}

// Add Error Message
function addErrorMessage(content) {
    const messageDiv = createMessageElement('error', content);
    appendMessage(messageDiv);
}

// Create Message Element
function createMessageElement(type, content, files = []) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type} animate-slideInUp`;
    
    // Avatar
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    
    if (type === 'user') {
        avatarDiv.innerHTML = '<i class="ti ti-user"></i>';
    } else if (type === 'assistant') {
        avatarDiv.innerHTML = '<i class="ti ti-robot"></i>';
    } else if (type === 'system') {
        avatarDiv.innerHTML = '<i class="ti ti-info-circle"></i>';
    } else if (type === 'error') {
        avatarDiv.innerHTML = '<i class="ti ti-alert-triangle"></i>';
    }
    
    // Content
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'message-bubble';
    
    // Render content (support markdown)
    if (window.marked && type === 'assistant') {
        bubbleDiv.innerHTML = window.marked.parse(content);
    } else {
        bubbleDiv.textContent = content;
    }
    
    // Add files if present
    if (files && files.length > 0) {
        const filesDiv = document.createElement('div');
        filesDiv.className = 'message-files';
        filesDiv.innerHTML = files.map(file => `
            <div class="file-attachment">
                <i class="ti ti-file"></i>
                <span>${file.name}</span>
                <span class="file-size">(${formatFileSize(file.size)})</span>
            </div>
        `).join('');
        bubbleDiv.appendChild(filesDiv);
    }
    
    // Timestamp
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
    });
    
    contentDiv.appendChild(bubbleDiv);
    contentDiv.appendChild(timeDiv);
    
    // Actions for assistant messages
    if (type === 'assistant') {
        const actionsDiv = createMessageActions(content);
        contentDiv.appendChild(actionsDiv);
    }
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    return messageDiv;
}

// Create Message Actions
function createMessageActions(content) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';
    
    // Copy button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn-icon btn-sm';
    copyBtn.innerHTML = '<i class="ti ti-copy"></i>';
    copyBtn.title = '复制';
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(content);
        window.LegalAI.showToast('已复制到剪贴板', 'success');
    };
    
    // Regenerate button
    const regenerateBtn = document.createElement('button');
    regenerateBtn.className = 'btn-icon btn-sm';
    regenerateBtn.innerHTML = '<i class="ti ti-refresh"></i>';
    regenerateBtn.title = '重新生成';
    regenerateBtn.onclick = () => {
        regenerateResponse(content);
    };
    
    // Feedback buttons
    const likeBtn = document.createElement('button');
    likeBtn.className = 'btn-icon btn-sm';
    likeBtn.innerHTML = '<i class="ti ti-thumb-up"></i>';
    likeBtn.title = '有用';
    likeBtn.onclick = () => {
        sendFeedback('positive', content);
    };
    
    const dislikeBtn = document.createElement('button');
    dislikeBtn.className = 'btn-icon btn-sm';
    dislikeBtn.innerHTML = '<i class="ti ti-thumb-down"></i>';
    dislikeBtn.title = '无用';
    dislikeBtn.onclick = () => {
        sendFeedback('negative', content);
    };
    
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenerateBtn);
    actionsDiv.appendChild(likeBtn);
    actionsDiv.appendChild(dislikeBtn);
    
    return actionsDiv;
}

// Append Message to Chat
function appendMessage(messageElement) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;
    
    // Remove welcome message if exists
    const welcomeMessage = chatMessages.querySelector('.message-welcome');
    if (welcomeMessage) {
        welcomeMessage.classList.add('animate-fadeOut');
        setTimeout(() => welcomeMessage.remove(), 300);
    }
    
    chatMessages.appendChild(messageElement);
    
    // Smooth scroll to bottom
    setTimeout(() => {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }, 100);
}

// Update Streaming Message
function updateStreamingMessage(messageId, content) {
    const messageElement = document.getElementById(messageId);
    if (!messageElement) return;
    
    const bubbleDiv = messageElement.querySelector('.message-bubble');
    if (!bubbleDiv) return;
    
    // Render markdown content
    if (window.marked) {
        bubbleDiv.innerHTML = window.marked.parse(content) + '<span class="typing-cursor">|</span>';
    } else {
        bubbleDiv.textContent = content;
    }
    
    // Auto scroll
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop <= chatMessages.clientHeight + 100;
        if (isAtBottom) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
}

// Finalize Streaming Message
function finalizeStreamingMessage(messageId) {
    const messageElement = document.getElementById(messageId);
    if (!messageElement) return;
    
    messageElement.classList.remove('streaming');
    
    // Remove cursor
    const cursor = messageElement.querySelector('.typing-cursor');
    if (cursor) cursor.remove();
    
    // Update stored message
    const message = ChatState.messages.find(m => m.id === messageId);
    if (message) {
        message.isStreaming = false;
    }
}

// Show Enhanced Typing Indicator
function showEnhancedTypingIndicator() {
    const typingId = 'typing_' + Date.now();
    const indicator = document.createElement('div');
    indicator.id = typingId;
    indicator.className = 'message assistant typing-indicator animate-fadeIn';
    indicator.innerHTML = `
        <div class="message-avatar">
            <i class="ti ti-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-animation">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                <span class="typing-text">AI正在思考...</span>
            </div>
        </div>
    `;
    
    appendMessage(indicator);
    return typingId;
}

// Remove Typing Indicator
function removeTypingIndicator(typingId) {
    const indicator = document.getElementById(typingId);
    if (indicator) {
        indicator.classList.add('animate-fadeOut');
        setTimeout(() => indicator.remove(), 300);
    }
}

// Get Conversation Context
function getConversationContext(limit = 10) {
    return ChatState.messages
        .slice(-limit)
        .map(msg => ({
            role: msg.type === 'user' ? 'user' : 'assistant',
            content: msg.content
        }));
}

// Handle Response Actions
function handleResponseActions(actions) {
    actions.forEach(action => {
        switch (action.type) {
            case 'show_document':
                showDocument(action.document_id);
                break;
            case 'highlight_text':
                highlightText(action.text, action.color);
                break;
            case 'show_chart':
                showChart(action.chart_data);
                break;
            case 'suggest_questions':
                showSuggestedQuestions(action.questions);
                break;
        }
    });
}

// Show Suggested Questions
function showSuggestedQuestions(questions) {
    const suggestionsDiv = document.createElement('div');
    suggestionsDiv.className = 'suggested-questions animate-slideInUp';
    suggestionsDiv.innerHTML = `
        <p class="suggestions-title">您可能还想了解：</p>
        <div class="suggestions-list">
            ${questions.map(q => `
                <button class="suggestion-btn" onclick="askSuggestedQuestion('${q}')">
                    ${q}
                </button>
            `).join('')}
        </div>
    `;
    
    appendMessage(suggestionsDiv);
}

// Ask Suggested Question
window.askSuggestedQuestion = function(question) {
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.value = question;
        window.LegalAI.autoResizeTextarea();
        sendMessage();
    }
};

// Regenerate Response
async function regenerateResponse(originalContent) {
    window.LegalAI.showToast('正在重新生成回答...', 'info');
    
    // Find the last user message
    const lastUserMessage = ChatState.messages
        .filter(m => m.type === 'user')
        .pop();
    
    if (lastUserMessage) {
        await sendEnhancedMessage(lastUserMessage.content + '\n\n[请重新回答]');
    }
}

// Send Feedback
async function sendFeedback(type, content) {
    try {
        await fetch(`${API_BASE_URL}/api/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                type: type,
                content: content,
                session_id: ChatState.currentSession
            })
        });
        
        window.LegalAI.showToast('感谢您的反馈！', 'success');
    } catch (error) {
        console.error('Error sending feedback:', error);
    }
}

// Show Chat Help
function showChatHelp() {
    const helpContent = `
## 快捷键

- **Cmd/Ctrl + Enter**: 发送消息
- **Cmd/Ctrl + /**: 显示帮助
- **Cmd/Ctrl + L**: 清除聊天
- **Cmd/Ctrl + S**: 保存聊天记录
- **Cmd/Ctrl + K**: 打开案件面板

## 支持的命令

- **/help**: 显示帮助信息
- **/clear**: 清除聊天记录
- **/export**: 导出聊天记录
- **/case [name]**: 切换到指定案件
- **/analyze**: 开始分析模式

## 文件支持

支持上传以下格式的文件：
- PDF, DOC, DOCX (文档)
- XLS, XLSX (表格)
- TXT (纯文本)
- JPG, PNG (图片)

拖拽文件到聊天区域或点击附件按钮上传。
    `;
    
    addAssistantMessage(helpContent);
}

// Check Streaming Support
function supportsStreaming() {
    return 'ReadableStream' in window && 'TextDecoder' in window;
}

// Format File Size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Export chat functions
window.Chat = {
    sendMessage: sendEnhancedMessage,
    addSystemMessage,
    addErrorMessage,
    clearChat: clearChatHistory,
    exportChat: exportChatHistory
};