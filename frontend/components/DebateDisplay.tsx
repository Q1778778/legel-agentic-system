import React, { useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Gavel, Shield, MessageSquare, Brain } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

interface DebateTurn {
  turn: number
  prosecutor: {
    argument: string
    thinking: string
  }
  defender: {
    response: string
    thinking: string
  }
  timestamp?: number
}

interface DebateDisplayProps {
  debateTurns: DebateTurn[]
  className?: string
}

const DebateDisplay: React.FC<DebateDisplayProps> = ({ debateTurns, className }) => {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Auto-scroll to bottom when new turns are added
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [debateTurns])

  const ParticipantCard = ({
    role,
    content,
    thinking,
    icon: Icon,
    color
  }: {
    role: string
    content: string
    thinking: string
    icon: React.ElementType
    color: string
  }) => (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className={cn("w-8 h-8 rounded-full flex items-center justify-center", color)}>
          <Icon className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold">{role}</span>
      </div>

      {/* Thinking Process */}
      {thinking && (
        <div className="ml-10 p-3 rounded-lg bg-muted/30 border border-muted">
          <div className="flex items-start gap-2">
            <Brain className="w-4 h-4 text-muted-foreground mt-1 flex-shrink-0" />
            <div className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">
                Strategic Thinking
              </span>
              <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                {thinking}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Argument Content */}
      <div className="ml-10 p-4 rounded-lg bg-card border">
        <p className="text-sm whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  )

  return (
    <Card className={cn("w-full h-full", className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5" />
            Legal Debate
          </CardTitle>
          {debateTurns.length > 0 && (
            <Badge variant="outline">
              Turn {debateTurns[debateTurns.length - 1].turn} of {debateTurns.length}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="timeline" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="timeline">Timeline View</TabsTrigger>
            <TabsTrigger value="sidebyside">Side-by-Side</TabsTrigger>
          </TabsList>

          <TabsContent value="timeline">
            <ScrollArea className="h-[500px] pr-4" ref={scrollRef}>
              <AnimatePresence>
                {debateTurns.map((turn, index) => (
                  <motion.div
                    key={turn.turn}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3, delay: index * 0.1 }}
                    className="mb-6"
                  >
                    {/* Turn Header */}
                    <div className="flex items-center gap-2 mb-4">
                      <Badge variant="secondary">Turn {turn.turn}</Badge>
                      {turn.timestamp && (
                        <span className="text-xs text-muted-foreground">
                          {new Date(turn.timestamp).toLocaleTimeString()}
                        </span>
                      )}
                    </div>

                    {/* Prosecutor Argument */}
                    <div className="mb-4">
                      <ParticipantCard
                        role="Prosecutor"
                        content={turn.prosecutor.argument}
                        thinking={turn.prosecutor.thinking}
                        icon={Gavel}
                        color="bg-red-500"
                      />
                    </div>

                    {/* Defender Response */}
                    <div>
                      <ParticipantCard
                        role="Defender"
                        content={turn.defender.response}
                        thinking={turn.defender.thinking}
                        icon={Shield}
                        color="bg-blue-500"
                      />
                    </div>

                    {/* Separator */}
                    {index < debateTurns.length - 1 && (
                      <div className="mt-6 border-b border-border" />
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {debateTurns.length === 0 && (
                <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                  <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
                  <p className="text-sm">No debate turns yet</p>
                  <p className="text-xs mt-1">The debate will appear here as it progresses</p>
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          <TabsContent value="sidebyside">
            <div className="grid grid-cols-2 gap-4">
              {/* Prosecutor Column */}
              <div>
                <div className="flex items-center gap-2 mb-4 pb-2 border-b">
                  <Gavel className="w-5 h-5 text-red-500" />
                  <span className="font-semibold">Prosecutor</span>
                </div>
                <ScrollArea className="h-[450px] pr-2">
                  {debateTurns.map((turn, index) => (
                    <motion.div
                      key={`prosecutor-${turn.turn}`}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: index * 0.1 }}
                      className="mb-4"
                    >
                      <Badge variant="outline" className="mb-2">
                        Turn {turn.turn}
                      </Badge>
                      <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
                        <p className="text-sm">{turn.prosecutor.argument}</p>
                      </div>
                    </motion.div>
                  ))}
                </ScrollArea>
              </div>

              {/* Defender Column */}
              <div>
                <div className="flex items-center gap-2 mb-4 pb-2 border-b">
                  <Shield className="w-5 h-5 text-blue-500" />
                  <span className="font-semibold">Defender</span>
                </div>
                <ScrollArea className="h-[450px] pr-2">
                  {debateTurns.map((turn, index) => (
                    <motion.div
                      key={`defender-${turn.turn}`}
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: index * 0.1 }}
                      className="mb-4"
                    >
                      <Badge variant="outline" className="mb-2">
                        Turn {turn.turn}
                      </Badge>
                      <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
                        <p className="text-sm">{turn.defender.response}</p>
                      </div>
                    </motion.div>
                  ))}
                </ScrollArea>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

export default DebateDisplay