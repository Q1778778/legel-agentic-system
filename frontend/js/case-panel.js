// Case Panel Management
'use strict';

// Case Panel State
const CasePanelState = {
    isOpen: false,
    cases: [],
    filteredCases: [],
    selectedCase: null,
    searchQuery: ''
};

// Initialize Case Panel
document.addEventListener('DOMContentLoaded', () => {
    initializeCasePanel();
    loadCases();
});

// Initialize Case Panel
function initializeCasePanel() {
    // Get DOM elements
    const casePanel = document.getElementById('casePanel');
    const closeCasePanel = document.getElementById('closeCasePanel');
    const newCaseBtn = document.getElementById('newCaseBtn');
    const newCaseModal = document.getElementById('newCaseModal');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const cancelModalBtn = document.getElementById('cancelModalBtn');
    const createCaseBtn = document.getElementById('createCaseBtn');
    const searchInput = document.querySelector('.panel-search input');
    
    // Case panel toggle
    document.addEventListener('keydown', (e) => {
        // Press Cmd/Ctrl + K to toggle case panel
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleCasePanel();
        }
    });
    
    // Add case panel toggle button to nav
    const navActions = document.querySelector('.nav-actions');
    if (navActions) {
        const casePanelToggle = document.createElement('button');
        casePanelToggle.className = 'btn-icon';
        casePanelToggle.id = 'casePanelToggle';
        casePanelToggle.innerHTML = '<i class="ti ti-briefcase"></i>';
        casePanelToggle.title = '案件管理 (⌘K)';
        casePanelToggle.addEventListener('click', toggleCasePanel);
        navActions.insertBefore(casePanelToggle, navActions.firstChild);
    }
    
    // Close panel
    closeCasePanel?.addEventListener('click', () => {
        closeCasePanel();
    });
    
    // New case modal
    newCaseBtn?.addEventListener('click', () => {
        openNewCaseModal();
    });
    
    closeModalBtn?.addEventListener('click', closeNewCaseModal);
    cancelModalBtn?.addEventListener('click', closeNewCaseModal);
    createCaseBtn?.addEventListener('click', createNewCase);
    
    // Search functionality
    searchInput?.addEventListener('input', (e) => {
        CasePanelState.searchQuery = e.target.value;
        filterCases();
    });
    
    // Click outside to close modal
    newCaseModal?.addEventListener('click', (e) => {
        if (e.target === newCaseModal) {
            closeNewCaseModal();
        }
    });
}

// Toggle Case Panel
function toggleCasePanel() {
    const casePanel = document.getElementById('casePanel');
    CasePanelState.isOpen = !CasePanelState.isOpen;
    
    if (CasePanelState.isOpen) {
        casePanel.classList.add('open');
        document.body.style.paddingRight = '400px';
        loadCases();
    } else {
        casePanel.classList.remove('open');
        document.body.style.paddingRight = '0';
    }
}

// Close Case Panel
function closeCasePanel() {
    const casePanel = document.getElementById('casePanel');
    casePanel.classList.remove('open');
    document.body.style.paddingRight = '0';
    CasePanelState.isOpen = false;
}

// Open New Case Modal
function openNewCaseModal() {
    const modal = document.getElementById('newCaseModal');
    modal.classList.add('open');
    
    // Reset form
    document.getElementById('newCaseForm').reset();
    
    // Focus on first input
    setTimeout(() => {
        document.getElementById('caseName')?.focus();
    }, 100);
}

// Close New Case Modal
function closeNewCaseModal() {
    const modal = document.getElementById('newCaseModal');
    modal.classList.remove('open');
}

// Create New Case
async function createNewCase() {
    const form = document.getElementById('newCaseForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }
    
    const formData = {
        name: document.getElementById('caseName').value,
        type: document.getElementById('caseType').value,
        description: document.getElementById('caseDescription').value,
        priority: document.querySelector('input[name="priority"]:checked')?.value || 'medium',
        created_at: new Date().toISOString(),
        status: 'active'
    };
    
    window.LegalAI.showLoading('正在创建案件...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        if (!response.ok) throw new Error('Failed to create case');
        
        const newCase = await response.json();
        
        // Add to state
        CasePanelState.cases.unshift(newCase);
        
        // Update UI
        renderCases();
        
        // Close modal
        closeNewCaseModal();
        
        window.LegalAI.hideLoading();
        window.LegalAI.showToast('案件创建成功', 'success');
        
        // Select the new case
        selectCase(newCase);
        
    } catch (error) {
        console.error('Error creating case:', error);
        window.LegalAI.hideLoading();
        window.LegalAI.showToast('创建案件失败，请重试', 'error');
    }
}

// Load Cases
async function loadCases() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases`);
        
        if (!response.ok) {
            // Use mock data if API is not available
            CasePanelState.cases = getMockCases();
        } else {
            const data = await response.json();
            CasePanelState.cases = data.cases || [];
        }
        
        CasePanelState.filteredCases = [...CasePanelState.cases];
        renderCases();
        
    } catch (error) {
        console.error('Error loading cases:', error);
        // Use mock data as fallback
        CasePanelState.cases = getMockCases();
        CasePanelState.filteredCases = [...CasePanelState.cases];
        renderCases();
    }
}

// Filter Cases
function filterCases() {
    const query = CasePanelState.searchQuery.toLowerCase();
    
    if (!query) {
        CasePanelState.filteredCases = [...CasePanelState.cases];
    } else {
        CasePanelState.filteredCases = CasePanelState.cases.filter(case_ => 
            case_.name.toLowerCase().includes(query) ||
            case_.type.toLowerCase().includes(query) ||
            case_.description?.toLowerCase().includes(query)
        );
    }
    
    renderCases();
}

// Render Cases
function renderCases() {
    const caseList = document.getElementById('caseList');
    if (!caseList) return;
    
    if (CasePanelState.filteredCases.length === 0) {
        caseList.innerHTML = `
            <div class="empty-state">
                <i class="ti ti-briefcase-off"></i>
                <p>暂无案件</p>
                <button class="btn btn-primary btn-sm" onclick="openNewCaseModal()">
                    创建首个案件
                </button>
            </div>
        `;
        return;
    }
    
    caseList.innerHTML = CasePanelState.filteredCases.map(case_ => `
        <div class="case-item ${case_.id === CasePanelState.selectedCase?.id ? 'selected' : ''}" 
             data-case-id="${case_.id}"
             onclick="selectCase('${case_.id}')">
            <div class="case-item-header">
                <div class="case-item-title">${case_.name}</div>
                <span class="case-item-badge ${case_.priority}">${getPriorityLabel(case_.priority)}</span>
            </div>
            <div class="case-item-description">${case_.description || '暂无描述'}</div>
            <div class="case-item-meta">
                <span><i class="ti ti-folder"></i> ${getCaseTypeLabel(case_.type)}</span>
                <span><i class="ti ti-calendar"></i> ${formatDate(case_.created_at)}</span>
            </div>
            <div class="case-item-actions">
                <button class="btn-icon btn-sm" onclick="editCase('${case_.id}', event)">
                    <i class="ti ti-edit"></i>
                </button>
                <button class="btn-icon btn-sm" onclick="deleteCase('${case_.id}', event)">
                    <i class="ti ti-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Select Case
function selectCase(caseId) {
    const case_ = typeof caseId === 'string' 
        ? CasePanelState.cases.find(c => c.id === caseId)
        : caseId;
    
    if (!case_) return;
    
    CasePanelState.selectedCase = case_;
    window.LegalAI.AppState.currentCase = case_.id;
    
    // Update UI
    renderCases();
    
    // Update chat header
    const chatTitle = document.querySelector('.chat-title h3');
    if (chatTitle) {
        chatTitle.textContent = `法律智能助手 - ${case_.name}`;
    }
    
    // Add message to chat
    window.LegalAI.addMessage('system', `已切换到案件: ${case_.name}`);
    
    // Load case-specific data
    loadCaseData(case_.id);
}

// Edit Case
async function editCase(caseId, event) {
    event.stopPropagation();
    
    const case_ = CasePanelState.cases.find(c => c.id === caseId);
    if (!case_) return;
    
    // For now, just show a toast
    // In a real implementation, you would open an edit modal
    window.LegalAI.showToast('编辑功能即将推出', 'info');
}

// Delete Case
async function deleteCase(caseId, event) {
    event.stopPropagation();
    
    if (!confirm('确定要删除这个案件吗？此操作不可恢复。')) {
        return;
    }
    
    window.LegalAI.showLoading('正在删除案件...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases/${caseId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete case');
        
        // Remove from state
        CasePanelState.cases = CasePanelState.cases.filter(c => c.id !== caseId);
        CasePanelState.filteredCases = CasePanelState.filteredCases.filter(c => c.id !== caseId);
        
        // If this was the selected case, clear selection
        if (CasePanelState.selectedCase?.id === caseId) {
            CasePanelState.selectedCase = null;
            window.LegalAI.AppState.currentCase = null;
        }
        
        // Update UI
        renderCases();
        
        window.LegalAI.hideLoading();
        window.LegalAI.showToast('案件已删除', 'success');
        
    } catch (error) {
        console.error('Error deleting case:', error);
        window.LegalAI.hideLoading();
        window.LegalAI.showToast('删除失败，请重试', 'error');
    }
}

// Load Case Data
async function loadCaseData(caseId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases/${caseId}/data`);
        
        if (!response.ok) throw new Error('Failed to load case data');
        
        const data = await response.json();
        
        // Update related cases tab
        updateRelatedCases(data.related_cases);
        
        // Update documents tab
        updateCaseDocuments(data.documents);
        
    } catch (error) {
        console.error('Error loading case data:', error);
    }
}

// Update Related Cases
function updateRelatedCases(cases) {
    const casesTab = document.getElementById('casesTab');
    if (!casesTab) return;
    
    if (!cases || cases.length === 0) {
        casesTab.innerHTML = `
            <div class="empty-state">
                <i class="ti ti-folder-off"></i>
                <p>暂无相关案例</p>
            </div>
        `;
        return;
    }
    
    casesTab.innerHTML = `
        <div class="cases-list">
            ${cases.map(case_ => `
                <div class="related-case-item">
                    <h4>${case_.title}</h4>
                    <p>${case_.summary}</p>
                    <div class="case-meta">
                        <span>相似度: ${case_.similarity}%</span>
                        <span>${case_.date}</span>
                    </div>
                    <a href="#" class="case-link">查看详情 →</a>
                </div>
            `).join('')}
        </div>
    `;
}

// Update Case Documents
function updateCaseDocuments(documents) {
    const documentsTab = document.getElementById('documentsTab');
    if (!documentsTab) return;
    
    if (!documents || documents.length === 0) {
        documentsTab.innerHTML = `
            <div class="empty-state">
                <i class="ti ti-file-off"></i>
                <p>暂无文档</p>
                <button class="btn btn-primary btn-sm" onclick="uploadDocument()">
                    上传文档
                </button>
            </div>
        `;
        return;
    }
    
    documentsTab.innerHTML = `
        <div class="documents-list">
            ${documents.map(doc => `
                <div class="document-item">
                    <div class="doc-icon">
                        <i class="ti ti-file-${getFileIcon(doc.type)}"></i>
                    </div>
                    <div class="doc-info">
                        <h4>${doc.name}</h4>
                        <p>${doc.size} • ${doc.uploaded_at}</p>
                    </div>
                    <div class="doc-actions">
                        <button class="btn-icon btn-sm" onclick="viewDocument('${doc.id}')">
                            <i class="ti ti-eye"></i>
                        </button>
                        <button class="btn-icon btn-sm" onclick="downloadDocument('${doc.id}')">
                            <i class="ti ti-download"></i>
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Helper Functions
function getPriorityLabel(priority) {
    const labels = {
        high: '高',
        medium: '中',
        low: '低'
    };
    return labels[priority] || priority;
}

function getCaseTypeLabel(type) {
    const labels = {
        contract: '合同纠纷',
        criminal: '刑事案件',
        civil: '民事诉讼',
        ip: '知识产权',
        corporate: '公司法务'
    };
    return labels[type] || type;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function getFileIcon(fileType) {
    const icons = {
        pdf: 'pdf',
        doc: 'text',
        docx: 'text',
        xls: 'spreadsheet',
        xlsx: 'spreadsheet',
        ppt: 'presentation',
        pptx: 'presentation',
        txt: 'text',
        image: 'photo'
    };
    return icons[fileType] || 'text';
}

// Mock Data
function getMockCases() {
    return [
        {
            id: '1',
            name: '张某诉李某借贷纠纷案',
            type: 'civil',
            description: '民间借贷纠纷，涉及金额100万元',
            priority: 'high',
            created_at: '2024-01-15',
            status: 'active'
        },
        {
            id: '2',
            name: 'ABC公司商标侵权案',
            type: 'ip',
            description: '商标侵权及不正当竞争纠纷',
            priority: 'medium',
            created_at: '2024-01-10',
            status: 'active'
        },
        {
            id: '3',
            name: '房屋买卖合同纠纷',
            type: 'contract',
            description: '房屋买卖合同违约责任认定',
            priority: 'medium',
            created_at: '2024-01-08',
            status: 'active'
        },
        {
            id: '4',
            name: '劳动合同争议案',
            type: 'civil',
            description: '违法解除劳动合同赔偿',
            priority: 'low',
            created_at: '2024-01-05',
            status: 'closed'
        }
    ];
}

// Export functions for global use
window.CasePanel = {
    toggleCasePanel,
    openNewCaseModal,
    selectCase,
    loadCases
};