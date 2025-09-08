import React from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, Circle, Loader2, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface WorkflowStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
}

interface WorkflowCanvasProps {
  steps: WorkflowStep[]
  currentStep: number
  progress: number
  status: 'pending' | 'running' | 'completed' | 'failed'
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  steps,
  currentStep,
  progress,
  status
}) => {
  const getStepIcon = (step: WorkflowStep, index: number) => {
    if (index < currentStep) {
      return <CheckCircle className="w-6 h-6 text-green-500" />
    } else if (index === currentStep && status === 'running') {
      return <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
    } else if (step.status === 'failed') {
      return <XCircle className="w-6 h-6 text-red-500" />
    } else {
      return <Circle className="w-6 h-6 text-gray-400" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500'
      case 'running':
        return 'bg-blue-500'
      case 'failed':
        return 'bg-red-500'
      default:
        return 'bg-gray-400'
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Workflow Progress</CardTitle>
          <Badge variant={status === 'completed' ? 'default' : status === 'failed' ? 'destructive' : 'secondary'}>
            {status.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Progress Bar */}
          <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
            <motion.div
              className="bg-blue-600 h-2.5 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${progress * 100}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>

          {/* Steps */}
          <div className="relative">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center mb-4 last:mb-0">
                {/* Connector Line */}
                {index > 0 && (
                  <div
                    className={cn(
                      "absolute left-3 -top-4 w-0.5 h-8",
                      index <= currentStep ? "bg-blue-500" : "bg-gray-300"
                    )}
                    style={{ top: `${index * 60 - 28}px` }}
                  />
                )}

                {/* Step Icon */}
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: index * 0.1 }}
                  className="flex-shrink-0 mr-4"
                >
                  {getStepIcon(step, index)}
                </motion.div>

                {/* Step Content */}
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className={cn(
                    "flex-1 p-3 rounded-lg border",
                    index === currentStep && status === 'running' 
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                      : index < currentStep
                      ? "border-green-500 bg-green-50 dark:bg-green-950"
                      : "border-gray-300 bg-gray-50 dark:bg-gray-900"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className={cn(
                      "font-medium",
                      index <= currentStep ? "text-foreground" : "text-muted-foreground"
                    )}>
                      {step.name}
                    </span>
                    {index === currentStep && status === 'running' && (
                      <Badge variant="outline" className="ml-2">
                        Processing...
                      </Badge>
                    )}
                  </div>
                </motion.div>
              </div>
            ))}
          </div>

          {/* Progress Text */}
          <div className="text-center text-sm text-muted-foreground">
            Step {currentStep + 1} of {steps.length} • {Math.round(progress * 100)}% Complete
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default WorkflowCanvas