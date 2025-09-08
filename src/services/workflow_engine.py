"""
Workflow Engine for managing legal debate workflows
"""
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
import asyncio
import uuid
from datetime import datetime
import logging

from .debate_orchestrator import DebateOrchestrator, DebateMode, DebateState

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Workflow status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(str, Enum):
    """Workflow step enumeration"""
    PARSE_INPUT = "parse_input"
    RETRIEVE_CONTEXT = "retrieve_context"
    INITIALIZE_AGENTS = "initialize_agents"
    CONDUCT_DEBATE = "conduct_debate"
    ANALYZE_OUTCOME = "analyze_outcome"
    GENERATE_FEEDBACK = "generate_feedback"


@dataclass
class WorkflowContext:
    """Context for a workflow execution"""
    workflow_id: str
    mode: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: Optional[WorkflowStep] = None
    steps_completed: List[WorkflowStep] = field(default_factory=list)
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """
    Manages legal debate workflows with step-by-step execution
    """
    
    def __init__(self):
        """Initialize the workflow engine"""
        self.workflows: Dict[str, WorkflowContext] = {}
        self.orchestrators: Dict[str, DebateOrchestrator] = {}
        self.update_callbacks: Dict[str, List[Callable]] = {}
        
    def create_workflow(
        self,
        mode: str,
        input_data: Dict[str, Any],
        workflow_id: Optional[str] = None
    ) -> WorkflowContext:
        """
        Create a new workflow
        
        Args:
            mode: Workflow mode (single or debate)
            input_data: Input data for the workflow
            workflow_id: Optional workflow ID (generated if not provided)
            
        Returns:
            Created workflow context
        """
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
        
        workflow = WorkflowContext(
            workflow_id=workflow_id,
            mode=mode,
            input_data=input_data,
            metadata={
                "max_turns": input_data.get("max_turns", 3),
                "model": input_data.get("model", "gpt-4o-mini")
            }
        )
        
        self.workflows[workflow_id] = workflow
        
        # Create orchestrator for this workflow
        debate_mode = DebateMode.SINGLE if mode == "single" else DebateMode.DEBATE
        self.orchestrators[workflow_id] = DebateOrchestrator(
            mode=debate_mode,
            max_turns=input_data.get("max_turns", 3),
            model=input_data.get("model", "gpt-4o-mini")
        )
        
        logger.info(f"Created workflow {workflow_id} with mode {mode}")
        return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowContext]:
        """
        Get a workflow by ID
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Workflow context if found
        """
        return self.workflows.get(workflow_id)
    
    def register_update_callback(self, workflow_id: str, callback: Callable):
        """
        Register a callback for workflow updates
        
        Args:
            workflow_id: Workflow ID
            callback: Callback function to call on updates
        """
        if workflow_id not in self.update_callbacks:
            self.update_callbacks[workflow_id] = []
        self.update_callbacks[workflow_id].append(callback)
    
    async def _notify_update(self, workflow_id: str, update_type: str, data: Any):
        """
        Notify registered callbacks of workflow updates
        
        Args:
            workflow_id: Workflow ID
            update_type: Type of update
            data: Update data
        """
        callbacks = self.update_callbacks.get(workflow_id, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update_type, data)
                else:
                    callback(update_type, data)
            except Exception as e:
                logger.error(f"Error in update callback: {e}")
    
    def _get_workflow_steps(self, mode: str) -> List[WorkflowStep]:
        """
        Get workflow steps based on mode
        
        Args:
            mode: Workflow mode
            
        Returns:
            List of workflow steps
        """
        if mode == "single":
            return [
                WorkflowStep.PARSE_INPUT,
                WorkflowStep.RETRIEVE_CONTEXT,
                WorkflowStep.INITIALIZE_AGENTS,
                WorkflowStep.ANALYZE_OUTCOME,
                WorkflowStep.GENERATE_FEEDBACK
            ]
        else:
            return [
                WorkflowStep.PARSE_INPUT,
                WorkflowStep.RETRIEVE_CONTEXT,
                WorkflowStep.INITIALIZE_AGENTS,
                WorkflowStep.CONDUCT_DEBATE,
                WorkflowStep.ANALYZE_OUTCOME,
                WorkflowStep.GENERATE_FEEDBACK
            ]
    
    async def execute_workflow(self, workflow_id: str) -> WorkflowContext:
        """
        Execute a workflow
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Completed workflow context
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if workflow.status != WorkflowStatus.PENDING:
            raise ValueError(f"Workflow {workflow_id} is not in pending state")
        
        orchestrator = self.orchestrators.get(workflow_id)
        if not orchestrator:
            raise ValueError(f"No orchestrator found for workflow {workflow_id}")
        
        try:
            # Update status
            workflow.status = WorkflowStatus.RUNNING
            workflow.updated_at = datetime.utcnow()
            
            # Get workflow steps
            steps = self._get_workflow_steps(workflow.mode)
            total_steps = len(steps)
            
            # Execute each step
            for i, step in enumerate(steps):
                workflow.current_step = step
                workflow.updated_at = datetime.utcnow()
                
                # Notify update
                await self._notify_update(workflow_id, "workflow_update", {
                    "status": workflow.status.value,
                    "currentStep": step.value,
                    "progress": (i + 1) / total_steps
                })
                
                # Execute step
                await self._execute_step(workflow, orchestrator, step)
                
                # Mark step as completed
                workflow.steps_completed.append(step)
                
                # Small delay between steps
                await asyncio.sleep(0.1)
            
            # Mark workflow as completed
            workflow.status = WorkflowStatus.COMPLETED
            workflow.current_step = None
            workflow.updated_at = datetime.utcnow()
            
            # Final notification
            await self._notify_update(workflow_id, "workflow_update", {
                "status": workflow.status.value,
                "currentStep": None,
                "progress": 1.0
            })
            
            logger.info(f"Workflow {workflow_id} completed successfully")
            return workflow
            
        except Exception as e:
            logger.error(f"Error executing workflow {workflow_id}: {e}")
            workflow.status = WorkflowStatus.FAILED
            workflow.error = str(e)
            workflow.updated_at = datetime.utcnow()
            
            # Error notification
            await self._notify_update(workflow_id, "workflow_error", {
                "error": str(e)
            })
            
            raise
    
    async def _execute_step(
        self,
        workflow: WorkflowContext,
        orchestrator: DebateOrchestrator,
        step: WorkflowStep
    ):
        """
        Execute a single workflow step
        
        Args:
            workflow: Workflow context
            orchestrator: Debate orchestrator
            step: Step to execute
        """
        logger.info(f"Executing step {step.value} for workflow {workflow.workflow_id}")
        
        if step == WorkflowStep.PARSE_INPUT:
            # Parse and validate input
            required_fields = ["case_id", "issue_text"]
            for field in required_fields:
                if field not in workflow.input_data:
                    raise ValueError(f"Missing required field: {field}")
            
            workflow.output_data["parsed_input"] = {
                "case_id": workflow.input_data["case_id"],
                "issue_text": workflow.input_data["issue_text"],
                "lawyer_id": workflow.input_data.get("lawyer_id"),
                "jurisdiction": workflow.input_data.get("jurisdiction")
            }
            
        elif step == WorkflowStep.RETRIEVE_CONTEXT:
            # Initialize debate with context retrieval
            context = await orchestrator.start_debate(
                case_id=workflow.input_data["case_id"],
                issue_text=workflow.input_data["issue_text"],
                lawyer_id=workflow.input_data.get("lawyer_id"),
                jurisdiction=workflow.input_data.get("jurisdiction")
            )
            workflow.output_data["context"] = {
                "bundles_retrieved": len(context.bundles),
                "case_id": context.case_id
            }
            
        elif step == WorkflowStep.INITIALIZE_AGENTS:
            # Agents are already initialized in orchestrator
            workflow.output_data["agents_initialized"] = True
            
        elif step == WorkflowStep.CONDUCT_DEBATE:
            # Stream debate messages
            messages = []
            async for message in orchestrator.stream_debate():
                messages.append(message)
                
                # Notify of each message
                await self._notify_update(workflow.workflow_id, "argument_generated", message)
                
            workflow.output_data["debate_messages"] = messages
            
        elif step == WorkflowStep.ANALYZE_OUTCOME:
            # Get debate summary
            summary = orchestrator.get_debate_summary()
            workflow.output_data["summary"] = summary
            
        elif step == WorkflowStep.GENERATE_FEEDBACK:
            # Extract feedback from messages
            messages = orchestrator.get_messages()
            feedback_messages = [m for m in messages if m.get("role") == "feedback"]
            
            if feedback_messages:
                feedback = feedback_messages[-1]
                workflow.output_data["feedback"] = {
                    "content": feedback.get("content"),
                    "timestamp": feedback.get("timestamp")
                }
                
                # Notify feedback ready
                await self._notify_update(workflow.workflow_id, "feedback_ready", {
                    "feedback": feedback.get("content")
                })
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel a running workflow
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            True if cancelled successfully
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        if workflow.status == WorkflowStatus.RUNNING:
            workflow.status = WorkflowStatus.CANCELLED
            workflow.updated_at = datetime.utcnow()
            
            # Notify cancellation
            await self._notify_update(workflow_id, "workflow_update", {
                "status": workflow.status.value,
                "currentStep": None,
                "progress": 0
            })
            
            logger.info(f"Workflow {workflow_id} cancelled")
            return True
        
        return False
    
    def cleanup_workflow(self, workflow_id: str):
        """
        Clean up workflow resources
        
        Args:
            workflow_id: Workflow ID
        """
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
        if workflow_id in self.orchestrators:
            del self.orchestrators[workflow_id]
        if workflow_id in self.update_callbacks:
            del self.update_callbacks[workflow_id]
        
        logger.info(f"Cleaned up workflow {workflow_id}")