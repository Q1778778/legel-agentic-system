const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface WorkflowCreateRequest {
  mode: 'single' | 'debate'
  input_data: {
    argument?: string
    context?: string
    prosecution_strategy?: string
    case_facts?: string
    desired_outcome?: string
  }
}

export interface WorkflowResponse {
  id: string
  mode: string
  status: string
  created_at: string
}

export interface ArgumentAnalysisRequest {
  content: string
  context: string
}

export interface DebateCreateRequest {
  prosecution_strategy: string
  case_facts: string
  desired_outcome: string
}

class ApiService {
  private baseUrl: string

  constructor() {
    this.baseUrl = API_BASE_URL
  }

  private async fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  // Workflow Management
  async createWorkflow(data: WorkflowCreateRequest): Promise<WorkflowResponse> {
    return this.fetchJson<WorkflowResponse>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getWorkflow(id: string): Promise<WorkflowResponse> {
    return this.fetchJson<WorkflowResponse>(`/api/workflows/${id}`)
  }

  async executeWorkflow(id: string): Promise<void> {
    await this.fetchJson(`/api/workflows/${id}/execute`, {
      method: 'POST',
    })
  }

  async cancelWorkflow(id: string): Promise<void> {
    await this.fetchJson(`/api/workflows/${id}`, {
      method: 'DELETE',
    })
  }

  // Argumentation
  async analyzeArgument(data: ArgumentAnalysisRequest): Promise<any> {
    return this.fetchJson('/api/arguments/analyze', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  // Debates
  async createDebate(data: DebateCreateRequest): Promise<any> {
    return this.fetchJson('/api/debates/create', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getDebateHistory(id: string): Promise<any> {
    return this.fetchJson(`/api/debates/${id}/history`)
  }

  // GraphRAG Integration
  async searchContext(query: string): Promise<any> {
    return this.fetchJson('/api/context/search', {
      method: 'POST',
      body: JSON.stringify({ query }),
    })
  }

  async getPrecedents(): Promise<any> {
    return this.fetchJson('/api/context/precedents')
  }
}

export const apiService = new ApiService()