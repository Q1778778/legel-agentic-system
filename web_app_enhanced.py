#!/usr/bin/env python3
"""
Enhanced Legal Analysis System - Streamlit Web Interface with Case Management
"""

import streamlit as st
import requests
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

# Page configuration
st.set_page_config(
    page_title="Legal Analysis System - Enhanced",
    page_icon="⚖️",
    layout="wide"
)

# API configuration
BASE_URL = "http://localhost:8000/api/v1"

# Custom CSS for better styling
st.markdown("""
<style>
.case-panel {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 10px;
    border: 1px solid #dee2e6;
}

.case-item {
    padding: 10px;
    border: 1px solid #dee2e6;
    border-radius: 5px;
    margin-bottom: 10px;
    background-color: white;
    transition: background-color 0.3s;
}

.case-item:hover {
    background-color: #e9ecef;
}

.case-item.active {
    border-color: #007bff;
    background-color: #e3f2fd;
}

.status-indicator {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 8px;
}

.status-draft { background-color: #ffc107; }
.status-active { background-color: #28a745; }
.status-closed { background-color: #dc3545; }
</style>
""", unsafe_allow_html=True)

# Case Management Functions
def get_cases() -> List[Dict[str, Any]]:
    """Get list of all cases"""
    try:
        response = requests.get(f"{BASE_URL}/cases/")
        if response.status_code == 200:
            return response.json().get("cases", [])
        return []
    except Exception as e:
        st.error(f"Error fetching cases: {e}")
        return []

def create_case(case_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create a new case"""
    try:
        response = requests.post(
            f"{BASE_URL}/cases/",
            json=case_data,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error creating case: {e}")
        return None

def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific case by ID"""
    try:
        response = requests.get(f"{BASE_URL}/cases/{case_id}")
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching case: {e}")
        return None

def check_health() -> Dict[str, Any]:
    """Check API health status"""
    try:
        response = requests.get(f"{BASE_URL}/health/")
        if response.status_code == 200:
            return response.json()
        return {"status": "unhealthy"}
    except:
        return {"status": "offline"}

def get_mcp_status() -> Dict[str, Any]:
    """Get MCP server status"""
    try:
        response = requests.get(f"{BASE_URL}/mcp/status")
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return result.get("data", {})
        return {}
    except Exception as e:
        return {"error": str(e)}

def start_mcp_chatbox_extraction() -> Optional[str]:
    """Start MCP chatbox extraction session"""
    try:
        response = requests.post(f"{BASE_URL}/mcp/case-extraction/chatbox/start")
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return result.get("data", {}).get("session_id")
        return None
    except Exception as e:
        st.error(f"Error starting chatbox extraction: {e}")
        return None

def send_chatbox_message(session_id: str, user_input: str) -> Optional[Dict[str, Any]]:
    """Send message to MCP chatbox extraction"""
    try:
        response = requests.post(
            f"{BASE_URL}/mcp/case-extraction/chatbox/respond",
            json={"session_id": session_id, "user_input": user_input}
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return result.get("data")
        return None
    except Exception as e:
        st.error(f"Error sending chatbox message: {e}")
        return None

# Initialize session state
if "cases" not in st.session_state:
    st.session_state.cases = []
if "active_case_id" not in st.session_state:
    st.session_state.active_case_id = None
if "show_create_case" not in st.session_state:
    st.session_state.show_create_case = False
if "extraction_session" not in st.session_state:
    st.session_state.extraction_session = None

# Main layout
st.title("⚖️ Legal Analysis System - Enhanced")
st.markdown("Legal analysis system with integrated case management and MCP servers")

# Create two columns: main content (70%) and case panel (30%)
main_col, case_col = st.columns([7, 3])

# Case Panel (Right side)
with case_col:
    st.markdown("### 📁 Case Management")
    
    # Case panel header
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("➕ New Case", key="new_case_btn", use_container_width=True):
            st.session_state.show_create_case = True
    
    with col2:
        if st.button("🔄", key="refresh_cases", help="Refresh"):
            st.session_state.cases = get_cases()
            st.rerun()
    
    # Load cases if not already loaded
    if not st.session_state.cases:
        st.session_state.cases = get_cases()
    
    # Display cases
    if st.session_state.cases:
        st.markdown("**Active Cases:**")
        for case in st.session_state.cases[:10]:
            case_id = case.get("id")
            title = case.get("title", "Untitled Case")
            status = case.get("status", "draft")
            
            # Status indicator
            status_emoji = {"draft": "🟡", "active": "🟢", "closed": "🔴"}.get(status, "⚪")
            
            if st.button(
                f"{status_emoji} {title[:25]}..." if len(title) > 25 else f"{status_emoji} {title}",
                key=f"case_{case_id}",
                help=f"Status: {status}",
                use_container_width=True
            ):
                st.session_state.active_case_id = case_id
                st.rerun()
    else:
        st.info("No cases found. Create your first case!")
    
    # Show active case details
    if st.session_state.active_case_id:
        active_case = get_case(st.session_state.active_case_id)
        if active_case:
            st.markdown("---")
            st.markdown("**Case Details:**")
            st.write(f"**Title:** {active_case.get('title')}")
            st.write(f"**Status:** {active_case.get('status')}")
            if active_case.get('description'):
                st.write(f"**Description:** {active_case.get('description')[:100]}...")
            
            # Case actions
            if st.button("💬 Chat with Lawyer", key="chat_lawyer", use_container_width=True):
                st.session_state.show_lawyer_chat = True
    
    # MCP Server Status
    st.markdown("---")
    st.markdown("**MCP Server Status:**")
    mcp_status = get_mcp_status()
    if "error" not in mcp_status and "servers" in mcp_status:
        for server, info in mcp_status["servers"].items():
            status_text = info.get("status", "unknown")
            if status_text == "running":
                st.success(f"✅ {info.get('name', server)}")
            elif status_text == "available":
                st.warning(f"⚠️ {info.get('name', server)}")
            else:
                st.error(f"❌ {info.get('name', server)}")
    else:
        st.error("❌ MCP services unavailable")

# Main Content (Left side)
with main_col:
    # Case creation dialog
    if st.session_state.show_create_case:
        st.markdown("## 📝 Create New Case")
        
        # Method selection
        method = st.radio(
            "Choose extraction method:",
            ["💬 Chat Extraction", "📁 File Upload", "✍️ Manual Entry"],
            key="extraction_method"
        )
        
        if method == "💬 Chat Extraction":
            st.markdown("### 💬 Chat-based Case Extraction")
            st.info("Chat with our AI to extract case information from your description.")
            
            # Start extraction session
            if not st.session_state.extraction_session:
                if st.button("🚀 Start Extraction Session", key="start_chat_extraction"):
                    session_id = start_mcp_chatbox_extraction()
                    if session_id:
                        st.session_state.extraction_session = {
                            "id": session_id,
                            "type": "chat",
                            "messages": [],
                            "extracted_info": {}
                        }
                        st.success("Extraction session started!")
                        st.rerun()
                    else:
                        st.error("Failed to start extraction session")
            else:
                # Show chat interface
                session = st.session_state.extraction_session
                
                # Display chat messages
                for msg in session["messages"]:
                    if msg["role"] == "user":
                        st.markdown(f"**You:** {msg['content']}")
                    else:
                        st.markdown(f"**AI:** {msg['content']}")
                
                # Chat input
                user_input = st.text_input("Your message:", key="chat_input")
                
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("Send", key="send_chat") and user_input:
                        # Add user message
                        session["messages"].append({"role": "user", "content": user_input})
                        
                        # Send to MCP (mock response for now)
                        # In reality, this would call send_chatbox_message
                        ai_response = f"I understand you mentioned: '{user_input}'. Let me extract the case information..."
                        session["messages"].append({"role": "assistant", "content": ai_response})
                        
                        # Mock completion after a few messages
                        if len(session["messages"]) >= 4:
                            session["extracted_info"] = {
                                "title": "Extracted Case from Chat",
                                "description": "Case extracted through chat interaction",
                                "parties": [{"name": "Party A", "role": "plaintiff"}],
                                "issues": ["contract_dispute"]
                            }
                            st.success("Case information extracted successfully!")
                            
                            if st.button("Create Case", key="create_from_chat"):
                                case_data = {
                                    "title": session["extracted_info"].get("title", "Case from Chat"),
                                    "description": session["extracted_info"].get("description"),
                                    "parties": session["extracted_info"].get("parties", []),
                                    "issues": session["extracted_info"].get("issues", []),
                                    "extraction_method": "chat",
                                    "extraction_session_id": session["id"]
                                }
                                
                                new_case = create_case(case_data)
                                if new_case:
                                    st.success(f"Case created: {new_case.get('title')}")
                                    st.session_state.cases = get_cases()
                                    st.session_state.active_case_id = new_case.get("id")
                                    st.session_state.show_create_case = False
                                    st.session_state.extraction_session = None
                                    st.rerun()
                        
                        st.rerun()
                
                with col2:
                    if st.button("Cancel", key="cancel_chat_extraction"):
                        st.session_state.extraction_session = None
                        st.session_state.show_create_case = False
                        st.rerun()
        
        elif method == "📁 File Upload":
            st.markdown("### 📁 File-based Case Extraction")
            st.info("Upload a legal document to extract case information automatically.")
            
            uploaded_file = st.file_uploader(
                "Choose a legal document",
                type=['txt', 'pdf', 'doc', 'docx'],
                key="case_file_upload"
            )
            
            if uploaded_file is not None:
                st.write(f"**File:** {uploaded_file.name}")
                st.write(f"**Size:** {uploaded_file.size} bytes")
                
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if st.button("🔍 Extract Information", key="extract_from_file"):
                        # Mock extraction (in reality, would use MCP service)
                        extracted_info = {
                            "title": f"Case from {uploaded_file.name}",
                            "description": "Case extracted from uploaded document",
                            "parties": [{"name": "Document Party", "role": "plaintiff"}],
                            "issues": ["document_analysis"]
                        }
                        
                        st.success("Information extracted successfully!")
                        st.json(extracted_info)
                        
                        if st.button("Create Case from File", key="create_from_file"):
                            case_data = {
                                "title": extracted_info.get("title", uploaded_file.name),
                                "description": extracted_info.get("description"),
                                "parties": extracted_info.get("parties", []),
                                "issues": extracted_info.get("issues", []),
                                "extraction_method": "file"
                            }
                            
                            new_case = create_case(case_data)
                            if new_case:
                                st.success(f"Case created: {new_case.get('title')}")
                                st.session_state.cases = get_cases()
                                st.session_state.active_case_id = new_case.get("id")
                                st.session_state.show_create_case = False
                                st.rerun()
                
                with col2:
                    if st.button("Cancel", key="cancel_file_extraction"):
                        st.session_state.show_create_case = False
                        st.rerun()
        
        else:  # Manual Entry
            st.markdown("### ✍️ Manual Case Entry")
            
            with st.form("manual_case_form"):
                title = st.text_input("Case Title*", placeholder="e.g., Contract Dispute - ABC Corp vs XYZ Inc")
                description = st.text_area("Case Description", placeholder="Brief description of the legal matter...")
                
                # Simple party entry
                party_name = st.text_input("Main Party Name")
                party_role = st.selectbox("Party Role", ["plaintiff", "defendant", "witness", "other"])
                
                # Simple issues entry
                issues_text = st.text_area("Legal Issues (one per line)", placeholder="contract_breach\ndamages")
                issues = [issue.strip() for issue in issues_text.split('\n') if issue.strip()]
                
                submitted = st.form_submit_button("Create Case")
                
                if submitted and title:
                    parties = [{"name": party_name, "role": party_role}] if party_name else []
                    
                    case_data = {
                        "title": title,
                        "description": description,
                        "parties": parties,
                        "issues": issues,
                        "extraction_method": "manual"
                    }
                    
                    new_case = create_case(case_data)
                    if new_case:
                        st.success(f"Case created: {new_case.get('title')}")
                        st.session_state.cases = get_cases()
                        st.session_state.active_case_id = new_case.get("id")
                        st.session_state.show_create_case = False
                        st.rerun()
                elif submitted and not title:
                    st.error("Please provide a case title")
        
        # Cancel button for case creation
        if st.button("❌ Cancel Case Creation", key="cancel_creation"):
            st.session_state.show_create_case = False
            st.rerun()
    
    else:
        # Main interface tabs when not creating case
        tab1, tab2, tab3 = st.tabs([
            "🔍 GraphRAG Retrieval", 
            "💬 Legal Chat",
            "📊 System Status"
        ])
        
        with tab1:
            st.header("GraphRAG Legal Case Retrieval")
            st.markdown("Search for relevant legal cases using hybrid Graph + Vector retrieval")
            
            issue_text = st.text_area(
                "Legal Issue Description",
                placeholder="Enter the legal issue or dispute description...",
                height=120
            )
            
            if st.button("🔍 Search Related Cases", type="primary"):
                if issue_text:
                    st.info("GraphRAG retrieval would be performed here with the existing system...")
                    # The original GraphRAG functionality would go here
                else:
                    st.warning("Please enter a legal issue description")
        
        with tab2:
            st.header("💬 Legal Chat Interface")
            
            if st.session_state.active_case_id:
                active_case = get_case(st.session_state.active_case_id)
                if active_case:
                    st.info(f"Chatting about case: {active_case.get('title')}")
                    
                    # Simple chat interface
                    if "chat_messages" not in st.session_state:
                        st.session_state.chat_messages = []
                    
                    # Display messages
                    for msg in st.session_state.chat_messages:
                        if msg["role"] == "user":
                            st.markdown(f"**You:** {msg['content']}")
                        else:
                            st.markdown(f"**Legal AI:** {msg['content']}")
                    
                    # Chat input
                    chat_input = st.text_input("Ask about this case:", key="legal_chat_input")
                    
                    if st.button("Send Message", key="send_legal_chat") and chat_input:
                        st.session_state.chat_messages.append({"role": "user", "content": chat_input})
                        # Mock AI response
                        ai_response = f"Regarding your case '{active_case.get('title')}', I can help analyze the legal implications of: {chat_input}"
                        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
                        st.rerun()
            else:
                st.info("Please select a case from the case panel to start legal consultation")
        
        with tab3:
            st.header("System Status & Monitoring")
            
            # Health check
            health = check_health()
            if health.get("status") == "healthy":
                st.success("✅ System is healthy")
            else:
                st.error("❌ System is not healthy")
            
            # MCP Status
            st.subheader("MCP Server Status")
            mcp_status = get_mcp_status()
            if mcp_status and "error" not in mcp_status:
                st.json(mcp_status)
            else:
                st.error("Failed to get MCP server status")
            
            # Cases summary
            st.subheader("Cases Summary")
            total_cases = len(st.session_state.cases)
            st.metric("Total Cases", total_cases)
            
            if st.session_state.cases:
                draft_count = len([c for c in st.session_state.cases if c.get("status") == "draft"])
                active_count = len([c for c in st.session_state.cases if c.get("status") == "active"])
                closed_count = len([c for c in st.session_state.cases if c.get("status") == "closed"])
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Draft", draft_count)
                with col2:
                    st.metric("Active", active_count)
                with col3:
                    st.metric("Closed", closed_count)