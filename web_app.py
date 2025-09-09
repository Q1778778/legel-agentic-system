#!/usr/bin/env python3
"""
Legal Analysis System - Streamlit Web Interface
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import subprocess
import os

# Page configuration
st.set_page_config(
    page_title="Legal Analysis System",
    page_icon="⚖️",
    layout="wide"
)

# API configuration
BASE_URL = "http://localhost:8000/api/v1"

def check_health() -> Dict[str, Any]:
    """Check API health status"""
    try:
        response = requests.get(f"{BASE_URL}/health/")
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy"}
    except:
        return {"status": "offline"}

def search_past_defenses(issue_text: str, limit: int = 10, 
                        lawyer_id: Optional[str] = None,
                        current_issue_id: Optional[str] = None) -> Dict[str, Any]:
    """Search for related cases using GraphRAG"""
    # Ensure at least issue_text is provided
    request_data = {
        "issue_text": issue_text if issue_text else None,
        "tenant": "default",
        "limit": limit,
        "since": None,
        "current_issue_id": current_issue_id if current_issue_id else None,
        "lawyer_id": lawyer_id if lawyer_id else None,
        "judge_id": None,
        "jurisdiction": None,
        "stage": None
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/retrieval/past-defenses",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Status {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def analyze_arguments(bundles: List[Dict], context: str, 
                      include_prosecution: bool = True,
                      include_judge: bool = True,
                      max_length: int = 1000) -> Dict[str, Any]:
    """Generate arguments using multi-agent analysis"""
    request_data = {
        "bundles": bundles,
        "context": context,
        "include_prosecution": include_prosecution,
        "include_judge": include_judge,
        "max_length": max_length
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/analysis/analyze",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json()
        return {"error": f"Status {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

# Title and description
st.title("⚖️ Legal Analysis System - GraphRAG Demo")
st.markdown("Legal analysis system powered by Graph + Vector RAG hybrid technology")

# Sidebar configuration
with st.sidebar:
    st.header("System Configuration")
    
    # Check system health
    health = check_health()
    if health.get("status") == "healthy":
        st.success("✅ System Online")
    else:
        st.error("❌ System Offline")
    
    st.header("Retrieval Parameters")
    retrieval_limit = st.slider("Max Results", min_value=1, max_value=20, value=5)
    
    st.header("Options")
    include_prosecution = st.checkbox("Include Prosecution", value=True)
    include_judge = st.checkbox("Include Judge", value=True)
    max_length = st.slider("Max Argument Length", min_value=100, max_value=2000, value=1000)
    
    st.markdown("---")
    st.markdown("### About")
    st.markdown("""
    This system implements the Court Argument 
    as specified in the GraphRAG technical documentation.
    
    **Technologies:**
    - Vector DB: Qdrant
    - Graph DB: Neo4j
    - Embeddings: OpenAI
    - Multi-Agent: GPT-4
    """)

# Main interface tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 GraphRAG Retrieval", 
    "🎭 Argument", 
    "💬 NLWeb Chat",
    "🔌 MCP Context",
    "📊 System Status"
])

# Tab 1: GraphRAG Retrieval
with tab1:
    st.header("GraphRAG Legal Case Retrieval")
    st.markdown("Search for relevant legal cases using hybrid Graph + Vector retrieval")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        issue_text = st.text_area(
            "Legal Issue Description",
            placeholder="Enter the legal issue or dispute description...\nExample: Contract breach involving late delivery, intellectual property infringement, employment discrimination...",
            height=120
        )
    
    with col2:
        st.markdown("**Optional Filters**")
        lawyer_id = st.text_input("Lawyer ID", placeholder="e.g., lawyer_001")
        issue_id = st.text_input("Issue ID", placeholder="e.g., issue_001")
    
    if st.button("🔍 Search Related Cases", type="primary", key="search"):
        if not issue_text:
            st.warning("Please enter a legal issue description")
        else:
            with st.spinner("Performing GraphRAG retrieval..."):
                result = search_past_defenses(
                    issue_text=issue_text,
                    limit=retrieval_limit,
                    lawyer_id=lawyer_id if lawyer_id else None,
                    current_issue_id=issue_id if issue_id else None
                )
                
                if "error" in result:
                    st.error(f"Retrieval failed: {result['error']}")
                else:
                    bundles = result.get("bundles", [])
                    query_time = result.get("query_time_ms", 0)
                    
                    st.success(f"✅ Found {len(bundles)} relevant cases in {query_time}ms")
                    
                    # Store in session state for analysis
                    st.session_state["retrieved_bundles"] = bundles
                    
                    # Display Core Metrics if available
                    if result.get("metrics"):
                        st.markdown("### 📊 Core Metrics")
                        metrics = result["metrics"]
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            win_rate = metrics.get("win_rate", {})
                            st.metric(
                                "Win Rate",
                                f"{win_rate.get('overall_win_rate', 0):.1%}",
                                f"{win_rate.get('total_cases', 0)} cases"
                            )
                        
                        with col2:
                            if "judge_alignment" in metrics:
                                alignment = metrics["judge_alignment"]
                                st.metric(
                                    "Judge Alignment",
                                    f"{alignment.get('overall_alignment_rate', 0):.1%}",
                                    f"{alignment.get('total_appearances', 0)} appearances"
                                )
                        
                        with col3:
                            diversity = metrics.get("argument_diversity", {})
                            st.metric(
                                "Argument Diversity",
                                diversity.get("total_unique_arguments", 0),
                                "unique strategies"
                            )
                    
                    # Display results
                    for i, bundle in enumerate(bundles, 1):
                        with st.expander(f"Case {i}: {bundle.get('case', {}).get('caption', 'Unknown')}"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.markdown("**Case Details**")
                                case = bundle.get("case", {})
                                st.write(f"Court: {case.get('court', 'N/A')}")
                                st.write(f"Jurisdiction: {case.get('jurisdiction', 'N/A')}")
                                st.write(f"Filed: {case.get('filed_date', 'N/A')[:10] if case.get('filed_date') else 'N/A'}")
                            
                            with col2:
                                st.markdown("**Issue Classification**")
                                issue = bundle.get("issue", {})
                                st.write(f"Title: {issue.get('title', 'N/A')}")
                                path = issue.get("taxonomy_path", [])
                                st.write(f"Category: {' > '.join(path) if path else 'N/A'}")
                            
                            with col3:
                                st.markdown("**Match Metrics**")
                                conf = bundle.get("confidence", {})
                                if isinstance(conf, dict):
                                    st.metric("Confidence", f"{conf.get('value', 0):.2%}")
                                else:
                                    st.metric("Confidence", f"{conf:.2%}")
                                
                                metadata = bundle.get("metadata", {})
                                if metadata.get("outcome"):
                                    st.write(f"Outcome: {metadata['outcome']}")
                            
                            # Show argument segments
                            segments = bundle.get("segments", [])
                            if segments:
                                st.markdown("**Argument Excerpts**")
                                for seg in segments[:2]:  # Show first 2 segments
                                    role = seg.get("role", "unknown")
                                    text = seg.get("text", "")
                                    st.info(f"[{role.upper()}] {text[:200]}...")

# Tab 2: Argument Analysis  
with tab2:
    st.header("Multi-Agent Argument")
    st.markdown("""
    Generate court arguments using AI agents based on retrieved cases:
    - **Defense Agent**: Constructs defense arguments from precedents
    - **Prosecution Agent**: Builds opposing arguments
    - **Judge Agent**: Provides judicial perspective
    """)
    
    # Case context input
    context = st.text_area(
        "Case Context & Background",
        placeholder="Describe the specific facts, parties involved, and key dispute points...\nExample: Company A failed to deliver equipment on time causing Company B to lose revenue...",
        height=150
    )
    
    # Check if we have retrieved bundles
    has_bundles = "retrieved_bundles" in st.session_state and st.session_state["retrieved_bundles"]
    
    col1, col2 = st.columns(2)
    with col1:
        if has_bundles:
            st.info(f"📚 Using {len(st.session_state['retrieved_bundles'])} retrieved cases")
        else:
            st.warning("⚠️ No cases retrieved. Please search first or use mock data.")
    
    with col2:
        use_mock = st.checkbox("Use mock data for testing", value=not has_bundles)
    
    if st.button("🎭 Generate Arguments", type="primary", key="begin"):
        if not context:
            st.warning("Please provide case context")
        else:
            # Prepare bundles
            if use_mock:
                # Create minimal mock bundle
                bundles = [{
                    "argument_id": "mock_001",
                    "confidence": {"value": 0.85},
                    "case": {
                        "id": "mock_case_001",
                        "caption": "Mock Case v. Test Case",
                        "court": "Supreme Court",
                        "jurisdiction": "US",
                        "filed_date": datetime.now().isoformat()
                    },
                    "issue": {
                        "id": "mock_issue_001",
                        "title": "Contract Dispute",
                        "taxonomy_path": ["Civil", "Contract", "Breach"]
                    },
                    "segments": [{
                        "segment_id": "mock_seg_001",
                        "argument_id": "mock_001",
                        "text": "The defendant breached the contract by failing to deliver.",
                        "role": "opening",
                        "seq": 0,
                        "citations": []
                    }]
                }]
            else:
                bundles = st.session_state.get("retrieved_bundles", [])[:3]  # Use top 3
            
            # Check if bundles is empty
            if not bundles:
                st.error("❌ No argument bundles available. Please either:")
                st.info("1. Check 'Use mock data for testing' option, OR")
                st.info("2. First retrieve some cases from the 'GraphRAG Retrieval' tab")
                st.stop()
            
            with st.spinner("AI agents are generating arguments..."):
                result = analyze_arguments(
                    bundles=bundles,
                    context=context,
                    include_prosecution=include_prosecution,
                    include_judge=include_judge,
                    max_length=max_length
                )
                
                if "error" in result:
                    st.error(f" failed: {result['error']}")
                else:
                    st.success("✅ Arguments generated successfully!")
                    
                    # Display arguments
                    cols = st.columns(2 if include_prosecution else 1)
                    
                    # Defense arguments
                    with cols[0]:
                        st.markdown("### ⚖️ Defense Arguments")
                        defense = result.get("defense", {})
                        st.write(defense.get("text", "No defense arguments generated"))
                        if defense.get("generation_time_ms"):
                            st.caption(f"Generated in {defense['generation_time_ms']}ms")
                    
                    # Prosecution arguments
                    if include_prosecution and len(cols) > 1:
                        with cols[1]:
                            st.markdown("### 👨‍⚖️ Prosecution Arguments")
                            prosecution = result.get("prosecution", {})
                            st.write(prosecution.get("text", "No prosecution arguments generated"))
                            if prosecution.get("generation_time_ms"):
                                st.caption(f"Generated in {prosecution['generation_time_ms']}ms")
                    
                    # Judge perspective
                    if include_judge and "judge" in result:
                        st.markdown("### 👩‍⚖️ Judge's Perspective")
                        judge = result.get("judge", {})
                        st.write(judge.get("text", "No judicial perspective generated"))
                        if judge.get("generation_time_ms"):
                            st.caption(f"Generated in {judge['generation_time_ms']}ms")

# Tab 3: NLWeb Chat Interface
with tab3:
    st.header("💬 NLWeb Chat Interface")
    st.markdown("Use natural language to interact with the legal analysis system")
    
    # Check if NLWeb server is running (on port 8080)
    nlweb_status = "unknown"
    try:
        nlweb_response = requests.get("http://localhost:8080/health", timeout=2)
        if nlweb_response.status_code == 200:
            nlweb_status = "online"
            st.success("✅ NLWeb service online")
        else:
            nlweb_status = "offline"
            st.warning("⚠️ NLWeb service not responding")
    except:
        nlweb_status = "offline"
        st.error("❌ NLWeb service offline")
        
        # Provide instructions to start NLWeb
        with st.expander("How to start NLWeb service"):
            st.markdown("""
            Please run the following commands in terminal to start NLWeb service:
            
            ```bash
            cd NLWeb/code
            ./python/startup_aiohttp.sh
            ```
            
            Or run Python command directly:
            
            ```bash
            cd NLWeb/code/python
            python -m webserver.aiohttp_server
            ```
            """)
    
    # If NLWeb is online, embed the interface
    if nlweb_status == "online":
        # Create two columns for layout
        col1, col2 = st.columns([4, 1])
        
        with col1:
            # Real NLWeb chat interface
            st.markdown("### Legal Analysis Chat")
            
            # Initialize chat session if not exists
            if "conversation_id" not in st.session_state:
                st.session_state.conversation_id = None
            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []
            
            # Start conversation button
            if st.session_state.conversation_id is None:
                if st.button("🚀 Start New Legal Analysis Session", type="primary"):
                    try:
                        # Create a new conversation with NLWeb
                        create_response = requests.post("http://localhost:8080/chat/create", 
                            json={
                                "title": "Legal Analysis Chat",
                                "enable_ai": True,
                                "anonymous_user_id": f"user_{uuid.uuid4().hex[:8]}"
                            }, 
                            timeout=10
                        )
                        
                        if create_response.status_code == 201:
                            conv_data = create_response.json()
                            st.session_state.conversation_id = conv_data["conversation_id"]
                            st.session_state.chat_messages = []
                            st.success("✅ Legal analysis session started!")
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to create conversation: {create_response.text}")
                    except Exception as e:
                        st.error(f"❌ Error connecting to NLWeb: {str(e)}")
            
            else:
                # Show chat interface
                st.success(f"📝 Chat Session: {st.session_state.conversation_id[:8]}...")
                
                # Display chat messages
                chat_container = st.container()
                with chat_container:
                    for msg in st.session_state.chat_messages:
                        if msg["role"] == "user":
                            st.markdown(f"**You:** {msg['content']}")
                        else:
                            st.markdown(f"**Legal AI:** {msg['content']}")
                
                # Chat input
                user_input = st.text_input("💬 Ask your legal question:", 
                    placeholder="e.g., What are the key precedents for contract breach cases?",
                    key="chat_input"
                )
                
                col_send, col_clear = st.columns([1, 1])
                
                with col_send:
                    if st.button("📤 Send Message", type="primary") and user_input:
                        # Add user message to chat
                        st.session_state.chat_messages.append({
                            "role": "user", 
                            "content": user_input
                        })
                        
                        # Send message to NLWeb
                        try:
                            # Use the conversation management API
                            message_data = {
                                "message": user_input,
                                "user_id": f"user_{uuid.uuid4().hex[:8]}",
                                "participant_name": "User"
                            }
                            
                            # Join the conversation first
                            join_response = requests.post(
                                f"http://localhost:8080/chat/{st.session_state.conversation_id}/join",
                                json=message_data,
                                timeout=30
                            )
                            
                            if join_response.status_code == 200:
                                response_data = join_response.json()
                                # Extract AI response from the conversation
                                if "response" in response_data:
                                    ai_response = response_data["response"]
                                    st.session_state.chat_messages.append({
                                        "role": "assistant",
                                        "content": ai_response
                                    })
                                else:
                                    st.session_state.chat_messages.append({
                                        "role": "assistant",
                                        "content": "I received your legal question and I'm analyzing relevant cases and precedents. Please allow me a moment to provide a comprehensive response."
                                    })
                            else:
                                st.error(f"❌ Error sending message: {join_response.text}")
                                
                        except Exception as e:
                            st.error(f"❌ Error communicating with NLWeb: {str(e)}")
                            st.session_state.chat_messages.append({
                                "role": "assistant",
                                "content": f"I'm experiencing technical difficulties: {str(e)}. Please try again."
                            })
                        
                        st.rerun()
                
                with col_clear:
                    if st.button("🗑️ Clear Chat"):
                        st.session_state.conversation_id = None
                        st.session_state.chat_messages = []
                        st.rerun()
                
                # External links section
                with st.expander("🔗 Alternative Access Options"):
                    st.markdown("**Direct NLWeb Access:**")
                    st.markdown("🌐 [Full NLWeb Interface](http://localhost:8080)")
                    st.markdown("📱 [Multi-Chat Interface](http://localhost:8080/static/multi-chat.html)")
                    st.markdown("🔧 [API Health Check](http://localhost:8080/health)")
                    
                    if st.button("🚀 Open NLWeb in New Tab", key="open_nlweb"):
                        st.javascript("window.open('http://localhost:8080', '_blank');")
                        st.info("Opening NLWeb in new tab...")
        
        with col2:
            st.markdown("### Quick Guide")
            st.info("""
            **Usage Tips:**
            
            1. Enter legal questions directly
            2. System will automatically search relevant cases
            3. Provides intelligent legal advice
            
            **Example Questions:**
            - Contract breach compensation standards
            - Intellectual property infringement determination
            - Labor dispute resolution process
            """)
            
            st.markdown("### Conversation Settings")
            conversation_mode = st.selectbox(
                "Conversation Mode",
                ["Standard Mode", "Professional Mode", "Quick Mode"]
            )
            
            max_context = st.slider(
                "Context Length",
                min_value=1,
                max_value=10,
                value=5,
                help="Number of historical conversation rounds to retain"
            )

# Tab 4: MCP Context Visualization
with tab4:
    st.header("🔌 MCP Agent Context")
    st.markdown("Real-time display of MCP (Model Context Protocol) agent tool usage and context status")
    
    # Check MCP server status
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("MCP Server Status")
        
        # Define MCP servers
        mcp_servers = {
            "lawyer_server": {"name": "Lawyer Agent", "path": "mcp_lawyer_server"},
            "case_extractor": {"name": "Case Extractor", "path": "mcp_case_extractor"},
            "opponent_simulator": {"name": "Opponent Simulator", "path": "mcp_opponent_simulator"}
        }
        
        # Check MCP server availability (based on directory existence)
        server_statuses = {}
        for server_id, server_info in mcp_servers.items():
            # MCP servers use stdio protocol, not HTTP
            # Check if server directory exists
            if os.path.exists(server_info['path']):
                server_statuses[server_id] = "configured"
                st.success(f"✅ {server_info['name']}: Configured (stdio mode)")
            else:
                server_statuses[server_id] = "not_available"
                st.info(f"ℹ️ {server_info['name']}: Not Available")
        
        # Instructions for using MCP servers
        if any(status == "not_available" for status in server_statuses.values()):
            with st.expander("How to start MCP servers"):
                st.markdown("""
                Please run the following commands in terminal to start MCP servers:
                
                ```bash
                # Start Lawyer Agent Server
                cd mcp_lawyer_server
                python server.py
                
                # Start Case Extractor Server
                cd mcp_case_extractor
                python server.py
                
                # Start Opponent Simulator Server
                cd mcp_opponent_simulator
                python server.py
                ```
                """)
    
    with col2:
        st.subheader("Active Tools")
        
        # Display active MCP tools
        active_tools = []
        if server_statuses.get("lawyer_server") == "configured":
            active_tools.extend(["legal_search", "case_analyzer", "argument_generator"])
        if server_statuses.get("case_extractor") == "configured":
            active_tools.extend(["extract_facts", "identify_issues", "find_precedents"])
        if server_statuses.get("opponent_simulator") == "configured":
            active_tools.extend(["predict_opposition", "counter_argument", "weakness_analysis"])
        
        if active_tools:
            for tool in active_tools:
                st.write(f"🔧 {tool}")
        else:
            st.warning("No active tools")
    
    # MCP Context Visualization
    st.markdown("---")
    st.subheader("Current Session Context")
    
    # Create tabs for different context views
    context_tab1, context_tab2, context_tab3 = st.tabs(["Conversation Flow", "Tool Calls", "Resource Status"])
    
    with context_tab1:
        st.markdown("### Conversation Flow Chart")
        
        # Display conversation flow (mock data for now)
        if st.button("Refresh Conversation Flow", key="refresh_flow"):
            flow_data = {
                "session_id": "session_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
                "participants": ["User", "Lawyer Agent", "Case Extractor"],
                "current_step": "Waiting for user input",
                "completed_steps": [
                    "Initialize session",
                    "Load agent configuration",
                    "Connect to database"
                ],
                "pending_steps": [
                    "Receive user query",
                    "Analyze legal issue",
                    "Retrieve relevant cases",
                    "Generate legal advice"
                ]
            }
            
            st.json(flow_data)
    
    with context_tab2:
        st.markdown("### Tool Call History")
        
        # Display tool call history (mock data)
        tool_calls = [
            {
                "timestamp": "2024-01-20 10:30:15",
                "tool": "legal_search",
                "input": "Contract breach compensation",
                "output": "Found 15 relevant cases",
                "duration": "250ms"
            },
            {
                "timestamp": "2024-01-20 10:30:16",
                "tool": "case_analyzer",
                "input": "Case ID: case_001",
                "output": "Extract key arguments",
                "duration": "180ms"
            }
        ]
        
        for call in tool_calls:
            with st.expander(f"{call['timestamp']} - {call['tool']}"):
                st.write(f"**Input:** {call['input']}")
                st.write(f"**Output:** {call['output']}")
                st.write(f"**Duration:** {call['duration']}")
    
    with context_tab3:
        st.markdown("### Resource Status")
        
        # Display resource status
        resources = {
            "case_database": {
                "name": "Case Database",
                "status": "Available",
                "records": "10,234",
                "last_update": "2024-01-19"
            },
            "legal_precedents": {
                "name": "Legal Precedents",
                "status": "Available",
                "records": "5,678",
                "last_update": "2024-01-18"
            },
            "judge_profiles": {
                "name": "Judge Profiles",
                "status": "Under Maintenance",
                "records": "234",
                "last_update": "2024-01-15"
            }
        }
        
        for resource_id, resource_info in resources.items():
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**{resource_info['name']}**")
            with col2:
                if resource_info['status'] == "Available":
                    st.success(resource_info['status'])
                else:
                    st.warning(resource_info['status'])
            with col3:
                st.write(f"Records: {resource_info['records']}")

# Tab 5: System Status (原来的 Tab 3)
with tab5:
    st.header("System Status & Monitoring")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Refresh Status", key="refresh"):
            health = check_health()
            
            if health.get("status") == "healthy":
                st.success("System is healthy")
                
                # Display metrics
                metrics = st.columns(4)
                with metrics[0]:
                    st.metric("Status", health.get("status", "unknown"))
                with metrics[1]:
                    st.metric("Version", health.get("version", "unknown"))
                with metrics[2]:
                    st.metric("Uptime", health.get("uptime", "unknown"))
                with metrics[3]:
                    st.metric("Environment", health.get("environment", "unknown"))
                
                # Component status
                st.markdown("### Component Status")
                components = health.get("components", {})
                
                comp_cols = st.columns(3)
                with comp_cols[0]:
                    qdrant_status = "✅ Online" if components.get("qdrant") else "❌ Offline"
                    st.write(f"**Qdrant**: {qdrant_status}")
                
                with comp_cols[1]:
                    neo4j_status = "✅ Online" if components.get("neo4j") else "❌ Offline"
                    st.write(f"**Neo4j**: {neo4j_status}")
                
                with comp_cols[2]:
                    redis_status = "✅ Online" if components.get("redis") else "❌ Offline"
                    st.write(f"**Redis**: {redis_status}")
            else:
                st.error("System is not healthy")
    
    with col2:
        st.markdown("### Quick Test")
        if st.button("🧪 Run System Test", key="test"):
            with st.spinner("Running tests..."):
                # Test retrieval
                test_result = search_past_defenses("test query", limit=1)
                if "error" not in test_result:
                    st.success("✅ Retrieval system working")
                else:
                    st.error("❌ Retrieval system error")
                
                # Test analysis with mock data
                mock_bundle = [{
                    "argument_id": "test",
                    "confidence": {"value": 0.5},
                    "case": {"id": "test", "caption": "Test", "court": "Test", 
                            "jurisdiction": "US", "filed_date": datetime.now().isoformat()},
                    "issue": {"id": "test", "title": "Test", "taxonomy_path": ["Test"]},
                    "segments": [{"segment_id": "test", "argument_id": "test",
                                "text": "Test", "role": "opening", "seq": 0, "citations": []}]
                }]
                
                sim_result = analyze_arguments(mock_bundle, "test", False, False, 100)
                if "error" not in sim_result:
                    st.success("✅ system working")
                else:
                    st.error("❌ system error")
    
    # Usage instructions
    st.markdown("---")
    st.markdown("""
    ### Usage Instructions
    
    1. **Start with Retrieval**: Go to the GraphRAG Retrieval tab and search for relevant cases
    2. **Review Results**: Examine the retrieved cases and their confidence scores
    3. **Generate Arguments**: Switch to Argument Analysis tab and provide case context
    4. **Analyze Output**: Review the multi-agent generated arguments from different perspectives
    
    ### GraphRAG Technology
    
    This system implements a hybrid retrieval approach:
    - **Vector Search**: Semantic similarity using Qdrant embeddings
    - **Graph Traversal**: Relationship-based expansion using Neo4j
    - **Scoring Formula**: α·vector + β·judge + γ·citation + δ·outcome - ε·hops
    
    For more details, refer to the technical specification documents.
    """)