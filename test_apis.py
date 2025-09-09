#!/usr/bin/env python3
"""
API Test Script for Legal Argumentation System
Tests all endpoints defined in LEGAL_SYSTEM.md
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional
import aiohttp
import websockets
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# API Configuration
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# Test data
SINGLE_ANALYSIS_DATA = {
    "argument": """
    The defendant's actions constitute negligence under state law because:
    1. They owed a duty of care to the plaintiff as a property owner
    2. They breached this duty by failing to maintain safe conditions
    3. This breach directly caused the plaintiff's injuries
    4. The plaintiff suffered quantifiable damages as a result
    """,
    "context": "Personal injury case involving slip and fall at commercial property"
}

DEBATE_DATA = {
    "case_description": """
    Criminal fraud case: The defendant is accused of wire fraud involving 
    cryptocurrency investments. They allegedly misrepresented the nature 
    and risks of investments to multiple victims, resulting in losses 
    exceeding $2 million.
    """,
    "prosecution_strategy": """
    Focus on pattern of deception, multiple victims, and documentary evidence 
    showing intentional misrepresentation. Emphasize the sophisticated nature 
    of the scheme and the defendant's expertise in cryptocurrency.
    """,
    "defense_strategy": """
    Argue that investments inherently carry risk, all disclosures were provided,
    and losses were due to market conditions beyond defendant's control.
    """
}

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}{text}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

def print_success(text: str):
    """Print success message"""
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")

def print_error(text: str):
    """Print error message"""
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")

def print_info(text: str):
    """Print info message"""
    print(f"{Fore.YELLOW}ℹ {text}{Style.RESET_ALL}")

def print_json(data: Dict[str, Any], indent: int = 2):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=indent, default=str))

async def test_health_check():
    """Test health check endpoint"""
    print_header("Testing Health Check")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print_success(f"Health check passed: {data}")
                else:
                    print_error(f"Health check failed: Status {response.status}")
        except Exception as e:
            print_error(f"Health check error: {e}")

async def test_create_workflow(mode: str, input_data: Dict[str, Any]) -> Optional[str]:
    """Test workflow creation"""
    print_header(f"Testing Workflow Creation - {mode.upper()} Mode")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Prepare request data based on mode
            if mode == "single":
                request_data = {
                    "mode": "single",
                    "case_id": f"test-single-{int(time.time())}",
                    "issue_text": input_data["argument"],
                    "max_turns": 1,
                    "model": "gpt-4o-mini"
                }
            else:  # debate mode
                request_data = {
                    "mode": "debate",
                    "case_id": f"test-debate-{int(time.time())}",
                    "issue_text": input_data["case_description"],
                    "max_turns": 3,
                    "model": "gpt-4o-mini"
                }
            
            print_info(f"Creating {mode} workflow...")
            print_json(request_data)
            
            async with session.post(
                f"{BASE_URL}/api/workflows",
                json=request_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    workflow_id = data["workflow_id"]
                    print_success(f"Workflow created: {workflow_id}")
                    print_json(data)
                    return workflow_id
                else:
                    error_text = await response.text()
                    print_error(f"Failed to create workflow: {response.status}")
                    print_error(f"Error: {error_text}")
                    return None
                    
        except Exception as e:
            print_error(f"Workflow creation error: {e}")
            return None

async def test_execute_workflow(workflow_id: str):
    """Test workflow execution"""
    print_header(f"Testing Workflow Execution: {workflow_id}")
    
    async with aiohttp.ClientSession() as session:
        try:
            print_info("Executing workflow...")
            
            async with session.post(
                f"{BASE_URL}/api/workflows/{workflow_id}/execute",
                json={"async_execution": True}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print_success("Workflow execution started")
                    print_json(data)
                    return True
                else:
                    error_text = await response.text()
                    print_error(f"Failed to execute workflow: {response.status}")
                    print_error(f"Error: {error_text}")
                    return False
                    
        except Exception as e:
            print_error(f"Workflow execution error: {e}")
            return False

async def test_get_workflow_status(workflow_id: str):
    """Test getting workflow status"""
    print_header(f"Testing Workflow Status: {workflow_id}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/api/workflows/{workflow_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    print_success(f"Workflow status: {data['status']}")
                    print_json(data)
                    return data
                else:
                    print_error(f"Failed to get workflow status: {response.status}")
                    return None
                    
        except Exception as e:
            print_error(f"Get workflow status error: {e}")
            return None

async def test_websocket_connection(workflow_id: str, duration: int = 10):
    """Test WebSocket connection and receive updates"""
    print_header(f"Testing WebSocket Connection: {workflow_id}")
    
    try:
        uri = f"{WS_URL}/ws/{workflow_id}"
        print_info(f"Connecting to WebSocket: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print_success("WebSocket connected")
            
            start_time = time.time()
            message_count = 0
            
            while time.time() - start_time < duration:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    message_count += 1
                    
                    print_info(f"Message {message_count} - Type: {data.get('type', 'unknown')}")
                    
                    if data.get('type') == 'workflow_update':
                        print(f"  Status: {data.get('status')}")
                        print(f"  Step: {data.get('currentStep')}")
                        print(f"  Progress: {data.get('progress')}%")
                    elif data.get('type') == 'argument_generated':
                        print(f"  Agent: {data.get('agent')}")
                        print(f"  Content: {data.get('content')[:100]}...")
                    elif data.get('type') == 'debate_turn':
                        print(f"  Turn: {data.get('turn')}")
                    elif data.get('type') == 'feedback_ready':
                        print(f"  Strengths: {len(data.get('strengths', []))} items")
                        print(f"  Weaknesses: {len(data.get('weaknesses', []))} items")
                        
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print_info("WebSocket connection closed")
                    break
                    
            print_success(f"Received {message_count} messages in {duration} seconds")
            
    except Exception as e:
        print_error(f"WebSocket error: {e}")

async def test_simple_analysis():
    """Test simple analysis endpoint"""
    print_header("Testing Simple Analysis Endpoint")
    
    async with aiohttp.ClientSession() as session:
        try:
            request_data = {
                "text": SINGLE_ANALYSIS_DATA["argument"],
                "analysis_type": "legal_argument"
            }
            
            print_info("Sending analysis request...")
            
            async with session.post(
                f"{BASE_URL}/api/analyze",
                json=request_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print_success("Analysis completed")
                    print_json(data)
                else:
                    print_error(f"Analysis failed: {response.status}")
                    
        except Exception as e:
            print_error(f"Simple analysis error: {e}")

async def test_smart_analysis():
    """Test smart analysis with GraphRAG"""
    print_header("Testing Smart Analysis with GraphRAG")
    
    async with aiohttp.ClientSession() as session:
        try:
            request_data = {
                "text": SINGLE_ANALYSIS_DATA["argument"],
                "use_graphrag": True,
                "retrieve_precedents": True,
                "max_precedents": 3
            }
            
            print_info("Sending smart analysis request...")
            
            async with session.post(
                f"{BASE_URL}/api/smart-analyze",
                json=request_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print_success("Smart analysis completed")
                    print_json(data)
                else:
                    print_error(f"Smart analysis failed: {response.status}")
                    
        except Exception as e:
            print_error(f"Smart analysis error: {e}")

async def test_debate_creation():
    """Test debate creation and monitoring"""
    print_header("Testing Debate Creation")
    
    async with aiohttp.ClientSession() as session:
        try:
            request_data = {
                "case_id": f"debate-test-{int(time.time())}",
                "prosecution_strategy": DEBATE_DATA["prosecution_strategy"],
                "case_facts": DEBATE_DATA["case_description"],
                "max_turns": 3
            }
            
            print_info("Creating debate...")
            
            async with session.post(
                f"{BASE_URL}/api/workflows/debates/create",
                json=request_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    debate_id = data["debate_id"]
                    print_success(f"Debate created: {debate_id}")
                    print_json(data)
                    
                    # Wait a bit for debate to progress
                    await asyncio.sleep(5)
                    
                    # Get debate history
                    async with session.get(
                        f"{BASE_URL}/api/workflows/debates/{debate_id}/history"
                    ) as hist_response:
                        if hist_response.status == 200:
                            history = await hist_response.json()
                            print_success("Debate history retrieved")
                            print_json(history)
                        else:
                            print_error("Failed to get debate history")
                            
                else:
                    print_error(f"Debate creation failed: {response.status}")
                    
        except Exception as e:
            print_error(f"Debate creation error: {e}")

async def test_complete_workflow_single():
    """Test complete single analysis workflow"""
    print_header("COMPLETE SINGLE ANALYSIS WORKFLOW TEST")
    
    # Create workflow
    workflow_id = await test_create_workflow("single", SINGLE_ANALYSIS_DATA)
    if not workflow_id:
        print_error("Failed to create workflow")
        return
    
    # Execute workflow
    success = await test_execute_workflow(workflow_id)
    if not success:
        print_error("Failed to execute workflow")
        return
    
    # Monitor via WebSocket (run concurrently with status checks)
    ws_task = asyncio.create_task(test_websocket_connection(workflow_id, 15))
    
    # Poll status
    for i in range(5):
        await asyncio.sleep(3)
        status = await test_get_workflow_status(workflow_id)
        if status and status["status"] == "completed":
            print_success("Workflow completed successfully!")
            break
    
    await ws_task

async def test_complete_workflow_debate():
    """Test complete debate workflow"""
    print_header("COMPLETE DEBATE WORKFLOW TEST")
    
    # Create workflow
    workflow_id = await test_create_workflow("debate", DEBATE_DATA)
    if not workflow_id:
        print_error("Failed to create workflow")
        return
    
    # Execute workflow
    success = await test_execute_workflow(workflow_id)
    if not success:
        print_error("Failed to execute workflow")
        return
    
    # Monitor via WebSocket (run concurrently with status checks)
    ws_task = asyncio.create_task(test_websocket_connection(workflow_id, 30))
    
    # Poll status
    for i in range(10):
        await asyncio.sleep(3)
        status = await test_get_workflow_status(workflow_id)
        if status and status["status"] == "completed":
            print_success("Debate workflow completed successfully!")
            break
    
    await ws_task

async def main():
    """Run all tests"""
    print(f"{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}    LEGAL ARGUMENTATION SYSTEM - API TEST SUITE")
    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
    
    # Basic connectivity tests
    await test_health_check()
    
    # Simple endpoint tests
    await test_simple_analysis()
    await test_smart_analysis()
    
    # Complete workflow tests
    await test_complete_workflow_single()
    await test_complete_workflow_debate()
    
    # Debate specific test
    await test_debate_creation()
    
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print(f"{Fore.MAGENTA}    ALL TESTS COMPLETED")
    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")

if __name__ == "__main__":
    asyncio.run(main())