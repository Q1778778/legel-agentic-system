'use client'

import React, { useState, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Scale, MessageSquare, FileText, Wifi, WifiOff } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import WorkflowCanvas from '@/components/WorkflowCanvas'
import ArgumentDisplay from '@/components/ArgumentDisplay'
import DebateDisplay from '@/components/DebateDisplay'
import { useWebSocket } from '@/hooks/useWebSocket'
import { cn } from '@/lib/utils'
import { getMockResponse } from '@/lib/mockData'

// Mock workflow ID for demonstration
const MOCK_WORKFLOW_ID = 'demo-workflow-123'

// Mock workflow steps
const WORKFLOW_STEPS = [
  { id: '1', name: 'Parse Legal Argument', status: 'pending' as const },
  { id: '2', name: 'Analyze Structure', status: 'pending' as const },
  { id: '3', name: 'Check Precedents', status: 'pending' as const },
  { id: '4', name: 'Generate Feedback', status: 'pending' as const },
]

const DEBATE_WORKFLOW_STEPS = [
  { id: '1', name: 'Parse Case Details', status: 'pending' as const },
  { id: '2', name: 'Retrieve Context', status: 'pending' as const },
  { id: '3', name: 'Initialize Agents', status: 'pending' as const },
  { id: '4', name: 'Conduct Debate', status: 'pending' as const },
  { id: '5', name: 'Analyze Outcome', status: 'pending' as const },
  { id: '6', name: 'Generate Feedback', status: 'pending' as const },
]

export default function Home() {
  const [mode, setMode] = useState<'single' | 'debate'>('single')
  const [workflowStarted, setWorkflowStarted] = useState(false)
  const [userInput, setUserInput] = useState('')
  const [caseContext, setCaseContext] = useState('')
  const [useMockData, setUseMockData] = useState(false)
  const [mockArguments, setMockArguments] = useState<any[]>([])
  const [mockDebateTurns, setMockDebateTurns] = useState<any[]>([])
  const [mockFeedback, setMockFeedback] = useState<any>(null)
  
  // Use WebSocket hook
  const {
    isConnected,
    workflowStatus,
    arguments: wsArguments,
    debateTurns,
    feedback
  } = useWebSocket(workflowStarted && !useMockData ? MOCK_WORKFLOW_ID : undefined)

  // Use mock or real data based on connection status
  const actualArguments = useMockData ? mockArguments : wsArguments
  const actualDebateTurns = useMockData ? mockDebateTurns : debateTurns
  const actualFeedback = useMockData ? mockFeedback : feedback
  
  // Transform arguments for display
  const displayArguments = actualArguments.map((arg, index) => ({
    id: `arg-${index}`,
    agent: arg.agent,
    content: arg.content,
    thinking: arg.thinking,
    timestamp: arg.timestamp,
    isStreaming: false
  }))

  const handleStartWorkflow = useCallback(async () => {
    // Validate input
    if (!userInput.trim()) {
      alert('Please enter a legal argument or case description')
      return
    }
    
    // Reset states
    setWorkflowStarted(true)
    setUseMockData(false)
    setMockArguments([])
    setMockDebateTurns([])
    setMockFeedback(null)
    
    // Call API to start workflow
    try {
      const response = await fetch('http://localhost:8000/api/workflows', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mode,
          case_id: `demo-${Date.now()}`,
          issue_text: userInput,
          max_turns: mode === 'debate' ? 3 : 1,
          model: "gpt-4o-mini"
        })
      })
      
      if (response.ok) {
        const data = await response.json()
        console.log('Workflow created:', data)
        
        // Execute the workflow after creation
        const executeResponse = await fetch(`http://localhost:8000/api/workflows/${data.workflow_id}/execute`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            async_execution: true
          })
        })
        
        if (executeResponse.ok) {
          const executeData = await executeResponse.json()
          console.log('Workflow execution started:', executeData)
        } else {
          console.error('Failed to execute workflow')
        }
      } else {
        throw new Error('Failed to create workflow')
      }
    } catch (error) {
      // Silently fall back to mock data without console errors
      // console.error('Error starting workflow, using mock data:', error)
      
      // Use mock data as fallback
      setUseMockData(true)
      const mockData = getMockResponse(mode, userInput)
      
      if (mode === 'single') {
        // Simulate streaming arguments
        mockData.arguments.forEach((arg, index) => {
          setTimeout(() => {
            setMockArguments(prev => [...prev, arg])
          }, 1000 * (index + 1))
        })
        
        // Show feedback after arguments
        setTimeout(() => {
          setMockFeedback(mockData.feedback)
        }, 1000 * (mockData.arguments.length + 1))
      } else {
        // Simulate streaming debate turns
        mockData.turns.forEach((turn, index) => {
          setTimeout(() => {
            setMockDebateTurns(prev => [...prev, turn])
          }, 2000 * (index + 1))
        })
        
        // Show feedback after debate
        setTimeout(() => {
          setMockFeedback(mockData.feedback)
        }, 2000 * (mockData.turns.length + 1))
      }
    }
  }, [mode, userInput])

  const currentStep = workflowStatus?.currentStep 
    ? (mode === 'single' ? WORKFLOW_STEPS : DEBATE_WORKFLOW_STEPS).findIndex(s => s.name === workflowStatus.currentStep)
    : 0

  const progress = workflowStatus?.progress || 0
  const status = workflowStatus?.status || 'pending'

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Scale className="w-8 h-8 text-primary" />
              <div>
                <h1 className="text-2xl font-bold">Legal Argumentation System</h1>
                <p className="text-sm text-muted-foreground">
                  AI-powered legal argument analysis and multi-party debate
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Badge 
                variant={(useMockData || isConnected) ? "default" : "secondary"} 
                className="flex items-center gap-1"
              >
                {(useMockData || isConnected) ? (
                  <>
                    <Wifi className="w-3 h-3" />
                    Connected
                  </>
                ) : (
                  <>
                    <WifiOff className="w-3 h-3" />
                    Disconnected
                  </>
                )}
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Workflow */}
          <div className="lg:col-span-1">
            <div className="space-y-4">
              {/* Mode Selection */}
              <Card>
                <CardHeader>
                  <CardTitle>Analysis Mode</CardTitle>
                  <CardDescription>
                    Choose between single lawyer analysis or multi-party debate
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setMode('single')}
                      className={cn(
                        "p-3 rounded-lg border-2 transition-all",
                        mode === 'single'
                          ? "border-primary bg-primary/10"
                          : "border-border hover:border-primary/50"
                      )}
                    >
                      <FileText className="w-6 h-6 mx-auto mb-2" />
                      <p className="text-sm font-medium">Single Analysis</p>
                    </button>
                    <button
                      onClick={() => setMode('debate')}
                      className={cn(
                        "p-3 rounded-lg border-2 transition-all",
                        mode === 'debate'
                          ? "border-primary bg-primary/10"
                          : "border-border hover:border-primary/50"
                      )}
                    >
                      <MessageSquare className="w-6 h-6 mx-auto mb-2" />
                      <p className="text-sm font-medium">Debate Mode</p>
                    </button>
                  </div>
                  
                  {!workflowStarted && (
                    <div className="mt-4 space-y-3">
                      <div>
                        <label htmlFor="userInput" className="block text-sm font-medium mb-2">
                          {mode === 'single' ? 'Legal Argument to Analyze' : 'Case Description'}
                        </label>
                        <textarea
                          id="userInput"
                          value={userInput}
                          onChange={(e) => setUserInput(e.target.value)}
                          placeholder={mode === 'single' 
                            ? "Enter your legal argument here (e.g., 'The defendant's actions constitute negligence under state law...')"
                            : "Enter the case facts and issues for debate (e.g., 'Criminal case involving fraud charges...')"}
                          className="w-full min-h-[100px] px-3 py-2 border rounded-lg bg-background text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                          rows={4}
                        />
                      </div>
                      
                      {mode === 'debate' && (
                        <div>
                          <label htmlFor="caseContext" className="block text-sm font-medium mb-2">
                            Additional Context (Optional)
                          </label>
                          <textarea
                            id="caseContext"
                            value={caseContext}
                            onChange={(e) => setCaseContext(e.target.value)}
                            placeholder="Any additional context or specific focus areas for the debate"
                            className="w-full min-h-[60px] px-3 py-2 border rounded-lg bg-background text-foreground resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                            rows={2}
                          />
                        </div>
                      )}
                      
                      <button
                        onClick={handleStartWorkflow}
                        className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={!userInput.trim()}
                      >
                        Start {mode === 'single' ? 'Analysis' : 'Debate'}
                      </button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Workflow Visualization */}
              <WorkflowCanvas
                steps={mode === 'single' ? WORKFLOW_STEPS : DEBATE_WORKFLOW_STEPS}
                currentStep={currentStep}
                progress={progress}
                status={status}
              />

              {/* Feedback Display */}
              {feedback && (
                <Card>
                  <CardHeader>
                    <CardTitle>Analysis Feedback</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {feedback.strengths.length > 0 && (
                      <div>
                        <h4 className="font-medium text-sm mb-2 text-green-600">Strengths</h4>
                        <ul className="list-disc list-inside space-y-1">
                          {feedback.strengths.map((strength, i) => (
                            <li key={i} className="text-sm text-muted-foreground">{strength}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {feedback.weaknesses.length > 0 && (
                      <div>
                        <h4 className="font-medium text-sm mb-2 text-red-600">Areas for Improvement</h4>
                        <ul className="list-disc list-inside space-y-1">
                          {feedback.weaknesses.map((weakness, i) => (
                            <li key={i} className="text-sm text-muted-foreground">{weakness}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {feedback.recommendations.length > 0 && (
                      <div>
                        <h4 className="font-medium text-sm mb-2 text-blue-600">Recommendations</h4>
                        <ul className="list-disc list-inside space-y-1">
                          {feedback.recommendations.map((rec, i) => (
                            <li key={i} className="text-sm text-muted-foreground">{rec}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {/* Right Column - Arguments/Debate */}
          <div className="lg:col-span-2">
            {mode === 'single' ? (
              <ArgumentDisplay 
                arguments={displayArguments}
                userInput={workflowStarted ? userInput : undefined}
              />
            ) : (
              <DebateDisplay 
                debateTurns={actualDebateTurns}
                userInput={workflowStarted ? userInput : undefined}
                caseContext={workflowStarted ? caseContext : undefined}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  )
}