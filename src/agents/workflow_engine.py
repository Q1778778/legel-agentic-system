"""Workflow engine for managing debate execution steps."""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import structlog

logger = structlog.get_logger()


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(str, Enum):
    """Types of workflow steps."""
    RETRIEVAL = "retrieval"
    AGENT_TURN = "agent_turn"
    FEEDBACK = "feedback"
    VALIDATION = "validation"
    NOTIFICATION = "notification"


@dataclass
class WorkflowStep:
    """Individual workflow step."""
    id: str
    name: str
    type: StepType
    handler: Callable
    dependencies: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    timeout: int = 30  # seconds
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_execute(self, completed_steps: List[str]) -> bool:
        """Check if this step can be executed.
        
        Args:
            completed_steps: List of completed step IDs
            
        Returns:
            True if all dependencies are met
        """
        return all(dep in completed_steps for dep in self.dependencies)
    
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute the step.
        
        Args:
            context: Execution context
            
        Returns:
            Step result
        """
        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.utcnow()
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self.handler(context),
                timeout=self.timeout
            )
            
            self.result = result
            self.status = WorkflowStatus.COMPLETED
            self.completed_at = datetime.utcnow()
            
            return result
            
        except asyncio.TimeoutError:
            self.error = f"Step timed out after {self.timeout} seconds"
            self.status = WorkflowStatus.FAILED
            self.completed_at = datetime.utcnow()
            raise
            
        except Exception as e:
            self.error = str(e)
            self.status = WorkflowStatus.FAILED
            self.completed_at = datetime.utcnow()
            
            # Check if we should retry
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                logger.warning(f"Step {self.id} failed, retrying ({self.retry_count}/{self.max_retries})")
                self.status = WorkflowStatus.PENDING
                return await self.execute(context)
            
            raise


@dataclass
class WorkflowDefinition:
    """Definition of a workflow."""
    id: str
    name: str
    description: str
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> bool:
        """Validate the workflow definition.
        
        Returns:
            True if valid
        """
        # Check for circular dependencies
        step_ids = {step.id for step in self.steps}
        
        for step in self.steps:
            # Check all dependencies exist
            for dep in step.dependencies:
                if dep not in step_ids:
                    logger.error(f"Step {step.id} has invalid dependency: {dep}")
                    return False
        
        # TODO: Check for circular dependencies using topological sort
        
        return True
    
    def get_execution_order(self) -> List[WorkflowStep]:
        """Get steps in execution order using topological sort.
        
        Returns:
            Ordered list of steps
        """
        # Build dependency graph
        graph = {step.id: step.dependencies for step in self.steps}
        step_map = {step.id: step for step in self.steps}
        
        # Kahn's algorithm for topological sort
        in_degree = {step_id: 0 for step_id in graph}
        for deps in graph.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
        ordered = []
        
        while queue:
            current = queue.pop(0)
            ordered.append(step_map[current])
            
            # Reduce in-degree for dependent steps
            for step_id, deps in graph.items():
                if current in deps:
                    in_degree[step_id] -= 1
                    if in_degree[step_id] == 0:
                        queue.append(step_id)
        
        return ordered


class WorkflowEngine:
    """Engine for executing workflows."""
    
    def __init__(self):
        """Initialize the workflow engine."""
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.executions: Dict[str, Dict[str, Any]] = {}
        self._execution_counter = 0
        
    def register_workflow(self, workflow: WorkflowDefinition):
        """Register a workflow definition.
        
        Args:
            workflow: Workflow to register
        """
        if not workflow.validate():
            raise ValueError(f"Invalid workflow: {workflow.id}")
        
        self.workflows[workflow.id] = workflow
        logger.info(f"Registered workflow: {workflow.id}")
    
    def create_debate_workflow(
        self,
        max_turns: int = 3,
        enable_feedback: bool = True
    ) -> WorkflowDefinition:
        """Create a standard debate workflow.
        
        Args:
            max_turns: Maximum debate turns
            enable_feedback: Whether to include feedback
            
        Returns:
            Workflow definition for debates
        """
        steps = []
        
        # Step 1: Retrieval
        steps.append(WorkflowStep(
            id="retrieval",
            name="Retrieve Past Cases",
            type=StepType.RETRIEVAL,
            handler=self._retrieval_handler,
            timeout=30
        ))
        
        # Step 2-N: Agent turns
        for turn in range(max_turns):
            # Prosecutor turn
            steps.append(WorkflowStep(
                id=f"prosecutor_turn_{turn}",
                name=f"Prosecutor Turn {turn + 1}",
                type=StepType.AGENT_TURN,
                handler=self._create_agent_handler("prosecutor"),
                dependencies=["retrieval"] if turn == 0 else [f"defender_turn_{turn - 1}"],
                timeout=60
            ))
            
            # Defender turn
            steps.append(WorkflowStep(
                id=f"defender_turn_{turn}",
                name=f"Defender Turn {turn + 1}",
                type=StepType.AGENT_TURN,
                handler=self._create_agent_handler("defender"),
                dependencies=[f"prosecutor_turn_{turn}"],
                timeout=60
            ))
        
        # Final feedback step
        if enable_feedback:
            steps.append(WorkflowStep(
                id="feedback",
                name="Generate Feedback",
                type=StepType.FEEDBACK,
                handler=self._feedback_handler,
                dependencies=[f"defender_turn_{max_turns - 1}"],
                timeout=90
            ))
        
        # Notification step
        steps.append(WorkflowStep(
            id="notification",
            name="Send Completion Notification",
            type=StepType.NOTIFICATION,
            handler=self._notification_handler,
            dependencies=["feedback"] if enable_feedback else [f"defender_turn_{max_turns - 1}"],
            timeout=10
        ))
        
        return WorkflowDefinition(
            id="debate_workflow",
            name="Legal Debate Workflow",
            description="Standard workflow for legal debates",
            steps=steps,
            metadata={
                "max_turns": max_turns,
                "enable_feedback": enable_feedback
            }
        )
    
    async def execute_workflow(
        self,
        workflow_id: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a workflow.
        
        Args:
            workflow_id: ID of workflow to execute
            context: Execution context
            
        Returns:
            Execution results
        """
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        workflow = self.workflows[workflow_id]
        
        # Create execution record
        execution_id = f"exec_{self._execution_counter}"
        self._execution_counter += 1
        
        execution = {
            "id": execution_id,
            "workflow_id": workflow_id,
            "status": WorkflowStatus.RUNNING,
            "context": context,
            "steps": {},
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "error": None
        }
        
        self.executions[execution_id] = execution
        
        try:
            # Get execution order
            ordered_steps = workflow.get_execution_order()
            completed_steps = []
            
            # Execute steps in order
            for step in ordered_steps:
                # Check if step can execute
                if not step.can_execute(completed_steps):
                    logger.warning(f"Skipping step {step.id} - dependencies not met")
                    continue
                
                logger.info(f"Executing step: {step.id}")
                
                # Execute step
                try:
                    result = await step.execute(context)
                    execution["steps"][step.id] = {
                        "status": step.status,
                        "result": result,
                        "started_at": step.started_at,
                        "completed_at": step.completed_at
                    }
                    completed_steps.append(step.id)
                    
                    # Update context with result
                    context[f"{step.id}_result"] = result
                    
                except Exception as e:
                    logger.error(f"Step {step.id} failed: {e}")
                    execution["steps"][step.id] = {
                        "status": WorkflowStatus.FAILED,
                        "error": str(e)
                    }
                    
                    # Decide whether to continue or fail workflow
                    if step.type in [StepType.NOTIFICATION]:
                        # Non-critical steps - continue
                        continue
                    else:
                        # Critical step - fail workflow
                        raise
            
            execution["status"] = WorkflowStatus.COMPLETED
            execution["completed_at"] = datetime.utcnow()
            
            return execution
            
        except Exception as e:
            execution["status"] = WorkflowStatus.FAILED
            execution["error"] = str(e)
            execution["completed_at"] = datetime.utcnow()
            raise
    
    async def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """Get the status of a workflow execution.
        
        Args:
            execution_id: Execution ID
            
        Returns:
            Execution status
        """
        if execution_id not in self.executions:
            raise ValueError(f"Execution not found: {execution_id}")
        
        execution = self.executions[execution_id]
        
        return {
            "id": execution_id,
            "workflow_id": execution["workflow_id"],
            "status": execution["status"],
            "started_at": execution["started_at"],
            "completed_at": execution["completed_at"],
            "steps": {
                step_id: {
                    "status": step_data.get("status"),
                    "started_at": step_data.get("started_at"),
                    "completed_at": step_data.get("completed_at"),
                    "error": step_data.get("error")
                }
                for step_id, step_data in execution["steps"].items()
            }
        }
    
    # Handler methods
    async def _retrieval_handler(self, context: Dict[str, Any]) -> Any:
        """Handler for retrieval steps."""
        # This would call the GraphRAG retrieval service
        logger.info("Executing retrieval step")
        await asyncio.sleep(1)  # Simulate work
        return {"bundles": [], "time_ms": 1000}
    
    def _create_agent_handler(self, agent_type: str) -> Callable:
        """Create a handler for agent turns."""
        async def handler(context: Dict[str, Any]) -> Any:
            logger.info(f"Executing {agent_type} turn")
            await asyncio.sleep(1)  # Simulate work
            return {
                "agent": agent_type,
                "message": f"{agent_type} argument",
                "confidence": 0.8
            }
        return handler
    
    async def _feedback_handler(self, context: Dict[str, Any]) -> Any:
        """Handler for feedback generation."""
        logger.info("Generating feedback")
        await asyncio.sleep(1)  # Simulate work
        return {
            "feedback": "Analysis of debate",
            "winner": "prosecution",
            "confidence": 0.85
        }
    
    async def _notification_handler(self, context: Dict[str, Any]) -> Any:
        """Handler for sending notifications."""
        logger.info("Sending notification")
        # This would send WebSocket notification
        return {"notified": True}