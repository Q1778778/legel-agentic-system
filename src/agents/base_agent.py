"""Base agent class for OpenAI Agents SDK integration."""

from typing import Dict, Any, List, Optional, Callable
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
import structlog
from openai import AsyncOpenAI
from datetime import datetime
import json

logger = structlog.get_logger()


class AgentMessage(BaseModel):
    """Message format for agent communication."""
    role: str  # prosecutor, defender, feedback, judge
    content: str
    citations: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    def to_openai_format(self) -> Dict[str, str]:
        """Convert to OpenAI message format."""
        return {
            "role": "assistant",
            "content": self.content
        }


class AgentContext(BaseModel):
    """Context passed between agents in the debate."""
    case_id: str
    issue_text: str
    bundles: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[AgentMessage] = Field(default_factory=list)
    current_turn: int = Field(default=0)
    max_turns: int = Field(default=3)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_message(self, message: AgentMessage):
        """Add a message to the context."""
        self.messages.append(message)
        
    def get_last_message(self) -> Optional[AgentMessage]:
        """Get the last message in the context."""
        return self.messages[-1] if self.messages else None
    
    def get_messages_by_role(self, role: str) -> List[AgentMessage]:
        """Get all messages from a specific role."""
        return [msg for msg in self.messages if msg.role == role]


class BaseAgent(ABC):
    """Base class for all legal argumentation agents."""
    
    def __init__(
        self,
        name: str,
        role: str,
        model: str = "gpt-4-turbo-preview",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        api_key: Optional[str] = None
    ):
        """Initialize base agent.
        
        Args:
            name: Agent name
            role: Agent role (prosecutor, defender, feedback)
            model: OpenAI model to use
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            api_key: OpenAI API key
        """
        self.name = name
        self.role = role
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.tools = self._register_tools()
        
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        pass
    
    @abstractmethod
    async def process(self, context: AgentContext) -> AgentMessage:
        """Process the context and generate a response.
        
        Args:
            context: Current debate context
            
        Returns:
            Generated message from this agent
        """
        pass
    
    def _register_tools(self) -> List[Dict[str, Any]]:
        """Register tools available to this agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "cite_precedent",
                    "description": "Cite a legal precedent or case",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "case_name": {"type": "string"},
                            "citation": {"type": "string"},
                            "relevance": {"type": "string"}
                        },
                        "required": ["case_name", "citation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_argument",
                    "description": "Analyze the strength of an argument",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "argument": {"type": "string"},
                            "strengths": {"type": "array", "items": {"type": "string"}},
                            "weaknesses": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["argument", "confidence"]
                    }
                }
            }
        ]
    
    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Call the OpenAI API with the given messages.
        
        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools to use
            
        Returns:
            Generated response content
        """
        if not self.client:
            logger.warning(f"{self.name}: No OpenAI client configured, using mock response")
            return self._generate_mock_response(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tools=tools if tools else None
            )
            
            # Handle tool calls if present
            if response.choices[0].message.tool_calls:
                tool_results = await self._execute_tools(
                    response.choices[0].message.tool_calls
                )
                # Add tool results to messages and call again
                messages.append(response.choices[0].message.model_dump())
                for result in tool_results:
                    messages.append(result)
                    
                # Make another call with tool results
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"{self.name}: Error calling OpenAI API: {e}")
            return self._generate_mock_response(messages)
    
    async def _execute_tools(self, tool_calls) -> List[Dict[str, Any]]:
        """Execute tool calls and return results.
        
        Args:
            tool_calls: List of tool calls from OpenAI
            
        Returns:
            List of tool results
        """
        results = []
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            # Execute the tool based on its name
            if function_name == "cite_precedent":
                result = {
                    "status": "success",
                    "citation_added": arguments["citation"]
                }
            elif function_name == "analyze_argument":
                result = {
                    "status": "success",
                    "confidence": arguments["confidence"]
                }
            else:
                result = {"status": "error", "message": "Unknown tool"}
            
            results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
        
        return results
    
    def _generate_mock_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate a mock response for testing without API.
        
        Args:
            messages: List of messages
            
        Returns:
            Mock response content
        """
        return f"Mock {self.role} response based on {len(messages)} messages"
    
    def _extract_citations(self, content: str) -> List[str]:
        """Extract legal citations from content.
        
        Args:
            content: Text content
            
        Returns:
            List of extracted citations
        """
        import re
        
        # Pattern for common legal citations
        patterns = [
            r'\d+\s+U\.S\.\s+\d+',  # US Reports
            r'\d+\s+F\.\d+d\s+\d+',  # Federal Reporter
            r'\d+\s+S\.Ct\.\s+\d+',  # Supreme Court Reporter
            r'§\s*\d+',  # Section references
        ]
        
        citations = []
        for pattern in patterns:
            matches = re.findall(pattern, content)
            citations.extend(matches)
        
        return list(set(citations))  # Remove duplicates
    
    def _calculate_confidence(self, content: str, citations: List[str]) -> float:
        """Calculate confidence score for the response.
        
        Args:
            content: Response content
            citations: List of citations used
            
        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence
        confidence = 0.5
        
        # Boost for citations
        if citations:
            confidence += min(len(citations) * 0.1, 0.3)
        
        # Boost for length and structure
        if len(content) > 500:
            confidence += 0.1
        
        # Boost for legal terminology
        legal_terms = ["precedent", "statute", "jurisdiction", "liability", "defendant", "plaintiff"]
        term_count = sum(1 for term in legal_terms if term.lower() in content.lower())
        confidence += min(term_count * 0.05, 0.2)
        
        return min(confidence, 1.0)