import { useEffect, useState, useCallback, useRef } from 'react'

export interface WorkflowUpdate {
  type: 'workflow_update'
  status: 'pending' | 'running' | 'completed' | 'failed'
  currentStep: string
  progress: number
}

export interface ArgumentGenerated {
  type: 'argument_generated'
  agent: string
  content: string
  thinking: string
  timestamp: number
}

export interface DebateTurn {
  type: 'debate_turn'
  turn: number
  prosecutor: { argument: string; thinking: string }
  defender: { response: string; thinking: string }
}

export interface FeedbackReady {
  type: 'feedback_ready'
  recommendations: string[]
  strengths: string[]
  weaknesses: string[]
}

type WebSocketMessage = WorkflowUpdate | ArgumentGenerated | DebateTurn | FeedbackReady

export const useWebSocket = (workflowId?: string) => {
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<WebSocketMessage[]>([])
  const [workflowStatus, setWorkflowStatus] = useState<WorkflowUpdate | null>(null)
  const [wsArguments, setWsArguments] = useState<ArgumentGenerated[]>([])
  const [debateTurns, setDebateTurns] = useState<DebateTurn[]>([])
  const [feedback, setFeedback] = useState<FeedbackReady | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  const connect = useCallback(() => {
    if (!workflowId) return

    const ws = new WebSocket(`ws://localhost:8000/ws/${workflowId}`)

    ws.onopen = () => {
      console.log('WebSocket connected')
      setIsConnected(true)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setMessages(prev => [...prev, data])

        switch (data.type) {
          case 'workflow_update':
            setWorkflowStatus(data)
            break
          case 'argument_generated':
            setWsArguments(prev => [...prev, data])
            break
          case 'debate_turn':
            setDebateTurns(prev => [...prev, data])
            break
          case 'feedback_ready':
            setFeedback(data)
            break
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setIsConnected(false)
      setSocket(null)

      // Attempt to reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        console.log('Attempting to reconnect...')
        connect()
      }, 3000)
    }

    setSocket(ws)
  }, [workflowId])

  useEffect(() => {
    connect()

    return () => {
      if (socket) {
        socket.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [workflowId])

  const sendMessage = useCallback((message: any) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message))
    }
  }, [socket])

  return {
    socket,
    isConnected,
    messages,
    workflowStatus,
    arguments: wsArguments,
    debateTurns,
    feedback,
    sendMessage
  }
}