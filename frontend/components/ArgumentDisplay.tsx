import React, { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { User, Bot, Brain } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

interface Argument {
  id: string
  agent: string
  content: string
  thinking: string
  timestamp: number
  isStreaming?: boolean
}

interface ArgumentDisplayProps {
  arguments: Argument[]
  className?: string
  userInput?: string
}

const ArgumentDisplay: React.FC<ArgumentDisplayProps> = ({ arguments: args, className, userInput }) => {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Auto-scroll to bottom when new arguments are added
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [args])

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  return (
    <Card className={cn("w-full h-full", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="w-5 h-5" />
          Legal Arguments
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[500px] pr-4" ref={scrollRef}>
          {/* Display user input first if provided */}
          {userInput && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 pb-4 border-b"
            >
              <div className="flex gap-3">
                <div className="flex-shrink-0">
                  <div className="w-12 h-12 rounded-full bg-blue-500/10 flex items-center justify-center">
                    <User className="w-6 h-6 text-blue-500" />
                  </div>
                </div>
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">User Input</span>
                    <Badge variant="outline" className="text-xs">
                      Initial Request
                    </Badge>
                  </div>
                  <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
                    <p className="text-sm whitespace-pre-wrap">{userInput}</p>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
          
          <AnimatePresence>
            {args.map((arg, index) => (
              <motion.div
                key={arg.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3 }}
                className="mb-4"
              >
                <div className="relative">
                  {/* Connector Line */}
                  {index > 0 && (
                    <div className="absolute left-6 -top-4 w-0.5 h-4 bg-border" />
                  )}

                  <div className="flex gap-3">
                    {/* Agent Avatar */}
                    <div className="flex-shrink-0">
                      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                        <User className="w-6 h-6 text-primary" />
                      </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 space-y-2">
                      {/* Header */}
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{arg.agent}</span>
                        <Badge variant="outline" className="text-xs">
                          {formatTimestamp(arg.timestamp)}
                        </Badge>
                        {arg.isStreaming && (
                          <Badge variant="secondary" className="text-xs animate-pulse">
                            Thinking...
                          </Badge>
                        )}
                      </div>

                      {/* Thinking Process */}
                      {arg.thinking && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          transition={{ duration: 0.3 }}
                          className="p-3 rounded-lg bg-muted/50 border border-muted"
                        >
                          <div className="flex items-start gap-2">
                            <Brain className="w-4 h-4 text-muted-foreground mt-1 flex-shrink-0" />
                            <div className="space-y-1">
                              <span className="text-xs font-medium text-muted-foreground">
                                Agent Reasoning
                              </span>
                              <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                                {arg.thinking}
                              </p>
                            </div>
                          </div>
                        </motion.div>
                      )}

                      {/* Main Argument */}
                      <div className="p-4 rounded-lg bg-card border">
                        <p className="text-sm whitespace-pre-wrap">
                          {arg.content}
                          {arg.isStreaming && (
                            <span className="inline-block w-2 h-4 ml-1 bg-primary animate-pulse" />
                          )}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {args.length === 0 && (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
              <Bot className="w-12 h-12 mb-4 opacity-50" />
              <p className="text-sm">No arguments generated yet</p>
              <p className="text-xs mt-1">Arguments will appear here as they are created</p>
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

export default ArgumentDisplay