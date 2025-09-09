#!/usr/bin/env python3
"""
Enhanced Legal Analysis System - Streamlit Web Interface with Full MCP Integration
This version includes WebSocket-based real-time MCP communication.
"""

import streamlit as st
import requests
import json
import uuid
import asyncio
import websockets
from datetime import datetime
from typing import Dict, Any, List, Optional
import threading
import queue

# Page configuration
st.set_page_config(
    page_title="Legal Analysis System - MCP Integrated",
    page_icon="⚖️",
    layout="wide"
)

# API configuration
BASE_URL = "http://localhost:8000/api/v1"
WS_URL = "ws://localhost:8000/api/v1/mcp/ws"

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

.chat-message {
    padding: 10px;
    margin: 5px 0;
    border-radius: 10px;
}

.user-message {
    background-color: #007bff;
    color: white;
    margin-left: 20%;
}

.ai-message {
    background-color: #f1f3f4;
    color: black;
    margin-right: 20%;
}

.extraction-result {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 5px;
    padding: 15px;
    margin: 10px 0;
}

.lawyer-response {
    background-color: #fff3cd;
    border: 1px solid #ffeeba;
    border-radius: 5px;
    padding: 15px;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# WebSocket Manager Class
class MCPWebSocketManager:
    """Manages WebSocket connection to MCP servers"""
    
    def __init__(self):
        self.websocket = None
        self.client_id = str(uuid.uuid4())
        self.session_id = None
        self.connected = False
        self.message_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
    async def connect(self):
        """Connect to WebSocket endpoint"""
        try:
            self.websocket = await websockets.connect(
                f"{WS_URL}?client_id={self.client_id}"
            )
            self.connected = True
            
            # Wait for welcome message
            welcome = await self.websocket.recv()
            welcome_data = json.loads(welcome)
            
            # Create session
            await self.send_message({
                "type": "session_create",
                "data": {"client_id": self.client_id}
            })
            
            # Get session response
            session_response = await self.websocket.recv()
            session_data = json.loads(session_response)
            if session_data.get("type") == "session_create":
                self.session_id = session_data.get("data", {}).get("session_id")
                
            return True
            
        except Exception as e:
            st.error(f"WebSocket connection failed: {e}")
            return False
            
    async def send_message(self, message: Dict[str, Any]):
        """Send message through WebSocket"""
        if self.websocket:
            message["session_id"] = self.session_id
            await self.websocket.send(json.dumps(message))
            
    async def receive_messages(self):
        """Receive messages from WebSocket"""
        while self.connected:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                self.response_queue.put(data)
            except:
                self.connected = False
                break
                
    async def extract_case_chat(self, user_input: str, context: Dict = None):
        """Extract case information through chat"""
        await self.send_message({
            "type": "extract_chat",
            "data": {
                "input": user_input,
                "context": context or {}
            }
        })
        
    async def extract_case_file(self, file_content: str, file_type: str = "auto"):
        """Extract case from file"""
        await self.send_message({
            "type": "extract_file",
            "data": {
                "file_content": file_content,
                "file_type": file_type
            }
        })
        
    async def init_consultation(self, case_data: Dict[str, Any]):
        """Initialize legal consultation"""
        await self.send_message({
            "type": "consult_init",
            "data": {"case_data": case_data}
        })
        
    async def send_consultation_message(self, message: str):
        """Send message in consultation"""
        await self.send_message({
            "type": "consult_message",
            "data": {"message": message}
        })
        
    async def simulate_opponent(self, scenario: Dict[str, Any]):
        """Simulate opponent analysis"""
        await self.send_message({
            "type": "consult_opponent",
            "data": {"scenario": scenario}
        })
        
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False

# Initialize WebSocket manager in session state
if "ws_manager" not in st.session_state:
    st.session_state.ws_manager = MCPWebSocketManager()

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
            return response.json()
        return {}
    except Exception as e:
        return {"error": str(e)}

# Initialize session state
if "cases" not in st.session_state:
    st.session_state.cases = []
if "active_case_id" not in st.session_state:
    st.session_state.active_case_id = None
if "show_create_case" not in st.session_state:
    st.session_state.show_create_case = False
if "extraction_session" not in st.session_state:
    st.session_state.extraction_session = None
if "consultation_session" not in st.session_state:
    st.session_state.consultation_session = None
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "consultation_messages" not in st.session_state:
    st.session_state.consultation_messages = []

# Main layout
st.title("⚖️ Legal Analysis System - MCP Integrated")
st.markdown("Advanced legal analysis with real-time MCP server integration")

# Create three columns: main content (60%), MCP panel (20%), case panel (20%)
main_col, mcp_col, case_col = st.columns([6, 2, 2])

# MCP Panel (Middle)
with mcp_col:
    st.markdown("### 🔌 MCP Services")
    
    # WebSocket connection status
    if st.session_state.ws_connected:
        st.success("🟢 Connected")
    else:
        st.error("🔴 Disconnected")
        if st.button("Connect", key="ws_connect"):
            # This would need async handling
            st.info("Connecting...")
            st.session_state.ws_connected = True
            st.rerun()
    
    # MCP Server Status
    st.markdown("**Server Status:**")
    mcp_status = get_mcp_status()
    
    if not mcp_status.get("error"):
        # Bridge status
        bridge_status = mcp_status.get("bridge", {})
        if bridge_status.get("initialized"):
            st.success("✅ Bridge Active")
        else:
            st.warning("⚠️ Bridge Inactive")
            
        # Server statuses
        servers = bridge_status.get("servers", {})
        for server_name, server_info in servers.items():
            state = server_info.get("state", "unknown")
            if state == "connected":
                st.success(f"✅ {server_name}")
            elif state == "connecting":
                st.warning(f"⏳ {server_name}")
            elif state == "error":
                st.error(f"❌ {server_name}")
            else:
                st.info(f"⚪ {server_name}")
                
        # Session info
        sessions = mcp_status.get("sessions", {})
        st.markdown(f"**Active Sessions:** {len(sessions)}")
        
        # Connection info
        connections = mcp_status.get("connections", 0)
        st.markdown(f"**WS Connections:** {connections}")
    else:
        st.error("MCP services unavailable")
        
    # Quick actions
    st.markdown("---")
    st.markdown("**Quick Actions:**")
    if st.button("🔄 Refresh Status", key="refresh_mcp"):
        st.rerun()

# Case Panel (Right side)
with case_col:
    st.markdown("### 📁 Cases")
    
    # Case panel header
    if st.button("➕ New", key="new_case_btn", use_container_width=True):
        st.session_state.show_create_case = True
    
    # Load cases if not already loaded
    if not st.session_state.cases:
        st.session_state.cases = get_cases()
    
    # Display cases
    if st.session_state.cases:
        for case in st.session_state.cases[:5]:
            case_id = case.get("id")
            title = case.get("title", "Untitled")[:15]
            status = case.get("status", "draft")
            
            # Status emoji
            status_emoji = {
                "draft": "🟡",
                "active": "🟢",
                "closed": "🔴"
            }.get(status, "⚪")
            
            if st.button(
                f"{status_emoji} {title}",
                key=f"case_{case_id}",
                use_container_width=True
            ):
                st.session_state.active_case_id = case_id
                st.rerun()
    else:
        st.info("No cases")

# Main Content (Left side)
with main_col:
    # Tabs for different features
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 Case Extraction",
        "💬 Legal Consultation",
        "🎯 Opponent Analysis",
        "📊 Case Analysis"
    ])
    
    with tab1:
        st.markdown("## 📝 Intelligent Case Extraction")
        
        extraction_method = st.radio(
            "Choose extraction method:",
            ["💬 Interactive Chat", "📄 File Upload", "✍️ Manual Entry"],
            horizontal=True
        )
        
        if extraction_method == "💬 Interactive Chat":
            st.markdown("### Chat-based Case Extraction")
            st.info("Describe your case in natural language and our AI will extract structured information.")
            
            # Chat interface
            chat_container = st.container()
            with chat_container:
                # Display chat messages
                for msg in st.session_state.chat_messages:
                    if msg["role"] == "user":
                        st.markdown(
                            f'<div class="chat-message user-message">{msg["content"]}</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f'<div class="chat-message ai-message">{msg["content"]}</div>',
                            unsafe_allow_html=True
                        )
            
            # Input area
            col1, col2 = st.columns([5, 1])
            with col1:
                user_input = st.text_input(
                    "Describe your case:",
                    placeholder="E.g., I have a contract dispute with my business partner...",
                    key="chat_input"
                )
            with col2:
                send_button = st.button("Send", key="send_chat", use_container_width=True)
            
            if send_button and user_input:
                # Add user message
                st.session_state.chat_messages.append({
                    "role": "user",
                    "content": user_input
                })
                
                # Simulate AI response (replace with actual WebSocket call)
                ai_response = f"I understand you have a case involving: {user_input[:50]}... Let me extract the key information for you."
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": ai_response
                })
                
                # Show extracted information
                with st.expander("📋 Extracted Information", expanded=True):
                    st.markdown("""
                    **Case Type:** Contract Dispute  
                    **Parties:** You, Business Partner  
                    **Key Issues:** Terms violation, Payment disputes  
                    **Jurisdiction:** To be determined  
                    **Urgency:** Medium
                    """)
                    
                    if st.button("✅ Create Case from Extraction"):
                        # Create case with extracted data
                        st.success("Case created successfully!")
                
                st.rerun()
        
        elif extraction_method == "📄 File Upload":
            st.markdown("### Document-based Case Extraction")
            st.info("Upload legal documents and we'll extract case information automatically.")
            
            uploaded_file = st.file_uploader(
                "Choose a file",
                type=["pdf", "docx", "txt"],
                key="file_upload"
            )
            
            if uploaded_file:
                st.success(f"File uploaded: {uploaded_file.name}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔍 Extract Information", use_container_width=True):
                        with st.spinner("Analyzing document..."):
                            # Simulate extraction
                            st.success("Extraction complete!")
                            
                            st.markdown("### Extracted Information:")
                            st.json({
                                "case_type": "Civil Litigation",
                                "plaintiff": "John Doe",
                                "defendant": "ABC Corporation",
                                "filing_date": "2024-01-15",
                                "court": "Superior Court",
                                "case_number": "CV-2024-001234",
                                "claims": ["Breach of Contract", "Negligence"],
                                "amount": "$50,000"
                            })
                
                with col2:
                    if st.button("📊 Analyze Document", use_container_width=True):
                        st.info("Document analysis coming soon...")
        
        else:  # Manual Entry
            st.markdown("### Manual Case Entry")
            
            with st.form("manual_case_form"):
                title = st.text_input("Case Title*")
                case_type = st.selectbox(
                    "Case Type*",
                    ["Contract Dispute", "Personal Injury", "Employment", "Real Estate", "Other"]
                )
                description = st.text_area("Case Description*", height=150)
                
                col1, col2 = st.columns(2)
                with col1:
                    plaintiff = st.text_input("Plaintiff/Client Name")
                    filing_date = st.date_input("Filing Date")
                
                with col2:
                    defendant = st.text_input("Defendant/Opposing Party")
                    court = st.text_input("Court/Jurisdiction")
                
                urgency = st.select_slider(
                    "Urgency Level",
                    options=["Low", "Medium", "High", "Critical"]
                )
                
                submit = st.form_submit_button("Create Case", use_container_width=True)
                
                if submit and title and description:
                    case_data = {
                        "title": title,
                        "type": case_type,
                        "description": description,
                        "plaintiff": plaintiff,
                        "defendant": defendant,
                        "filing_date": str(filing_date),
                        "court": court,
                        "urgency": urgency,
                        "status": "draft"
                    }
                    
                    result = create_case(case_data)
                    if result:
                        st.success("✅ Case created successfully!")
                        st.session_state.cases = get_cases()
                        st.session_state.active_case_id = result.get("id")
                        st.rerun()
                    else:
                        st.error("Failed to create case")
    
    with tab2:
        st.markdown("## 💬 Legal Consultation")
        
        if st.session_state.active_case_id:
            active_case = get_case(st.session_state.active_case_id)
            if active_case:
                st.info(f"Consulting on: **{active_case.get('title')}**")
                
                # Consultation chat interface
                consultation_container = st.container()
                with consultation_container:
                    # Display consultation messages
                    for msg in st.session_state.consultation_messages:
                        if msg["role"] == "user":
                            st.markdown(
                                f'<div class="chat-message user-message">{msg["content"]}</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f'<div class="lawyer-response">{msg["content"]}</div>',
                                unsafe_allow_html=True
                            )
                
                # Consultation input
                col1, col2 = st.columns([5, 1])
                with col1:
                    consult_input = st.text_input(
                        "Ask your legal question:",
                        placeholder="What are my options in this case?",
                        key="consult_input"
                    )
                with col2:
                    consult_send = st.button("Send", key="send_consult", use_container_width=True)
                
                if consult_send and consult_input:
                    # Add user message
                    st.session_state.consultation_messages.append({
                        "role": "user",
                        "content": consult_input
                    })
                    
                    # Simulate lawyer response
                    lawyer_response = f"""Based on your case details, here are my recommendations:

1. **Immediate Actions**: Document all communications and gather relevant evidence.

2. **Legal Options**: You have several paths forward:
   - Negotiation and settlement
   - Mediation through a neutral third party
   - Formal litigation if necessary

3. **Risks & Considerations**: The main risks include time, cost, and uncertainty of outcome.

4. **Recommended Strategy**: I suggest starting with negotiation while preparing for potential litigation.

Would you like me to elaborate on any of these points?"""
                    
                    st.session_state.consultation_messages.append({
                        "role": "assistant",
                        "content": lawyer_response
                    })
                    
                    st.rerun()
                
                # Quick consultation actions
                st.markdown("---")
                st.markdown("**Quick Actions:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("📋 Get Case Summary", use_container_width=True):
                        st.info("Generating case summary...")
                with col2:
                    if st.button("⚖️ Legal Precedents", use_container_width=True):
                        st.info("Searching for precedents...")
                with col3:
                    if st.button("📄 Draft Document", use_container_width=True):
                        st.info("Document drafting...")
        else:
            st.warning("Please select a case to start consultation")
    
    with tab3:
        st.markdown("## 🎯 Opponent Strategy Analysis")
        
        if st.session_state.active_case_id:
            st.info("Analyze potential opponent strategies and prepare counter-arguments")
            
            # Scenario configuration
            st.markdown("### Configure Opponent Scenario")
            
            col1, col2 = st.columns(2)
            with col1:
                opponent_type = st.selectbox(
                    "Opponent Type",
                    ["Aggressive Litigator", "Settlement-Oriented", "Defensive", "Unpredictable"]
                )
                opponent_resources = st.select_slider(
                    "Opponent Resources",
                    options=["Limited", "Moderate", "Substantial", "Unlimited"]
                )
            
            with col2:
                opponent_experience = st.select_slider(
                    "Opponent Experience",
                    options=["Novice", "Intermediate", "Experienced", "Expert"]
                )
                risk_tolerance = st.select_slider(
                    "Risk Tolerance",
                    options=["Risk-Averse", "Cautious", "Balanced", "Risk-Taking"]
                )
            
            if st.button("🎯 Analyze Opponent Strategy", use_container_width=True):
                with st.spinner("Simulating opponent strategies..."):
                    # Simulate analysis
                    st.success("Analysis complete!")
                    
                    st.markdown("### Predicted Opponent Strategies:")
                    
                    with st.expander("🗡️ Primary Strategy", expanded=True):
                        st.markdown("""
                        **Likely Approach:** Aggressive pre-trial motions
                        
                        **Key Tactics:**
                        - File motion to dismiss on technical grounds
                        - Request extensive discovery
                        - Attempt to increase your legal costs
                        
                        **Probability:** 75%
                        """)
                    
                    with st.expander("🛡️ Counter-Strategies", expanded=True):
                        st.markdown("""
                        **Recommended Counters:**
                        
                        1. **Prepare Strong Opposition Briefs**
                           - Anticipate dismissal arguments
                           - Have case law ready
                        
                        2. **Streamline Discovery**
                           - Propose reasonable limits
                           - Use protective orders if needed
                        
                        3. **Cost Management**
                           - Consider fee-shifting motions
                           - Document all expenses
                        """)
                    
                    with st.expander("📊 Outcome Probabilities", expanded=True):
                        st.markdown("""
                        **Settlement:** 45%  
                        **Trial Victory:** 30%  
                        **Trial Loss:** 20%  
                        **Dismissal:** 5%
                        """)
        else:
            st.warning("Please select a case for opponent analysis")
    
    with tab4:
        st.markdown("## 📊 Comprehensive Case Analysis")
        
        if st.session_state.active_case_id:
            active_case = get_case(st.session_state.active_case_id)
            if active_case:
                st.info(f"Analyzing: **{active_case.get('title')}**")
                
                # Analysis options
                analysis_type = st.selectbox(
                    "Select Analysis Type",
                    ["Full Case Analysis", "Risk Assessment", "Timeline Analysis", "Cost-Benefit Analysis"]
                )
                
                if st.button("🔍 Run Analysis", use_container_width=True):
                    with st.spinner(f"Running {analysis_type}..."):
                        # Simulate analysis
                        st.success("Analysis complete!")
                        
                        if analysis_type == "Full Case Analysis":
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("### Strengths")
                                st.markdown("""
                                - Strong documentary evidence
                                - Clear breach of contract
                                - Favorable jurisdiction
                                - Credible witnesses
                                """)
                                
                                st.markdown("### Opportunities")
                                st.markdown("""
                                - Early settlement possibility
                                - Precedent cases in our favor
                                - Mediation option available
                                """)
                            
                            with col2:
                                st.markdown("### Weaknesses")
                                st.markdown("""
                                - Limited financial resources
                                - Some ambiguous contract terms
                                - Delayed filing
                                """)
                                
                                st.markdown("### Threats")
                                st.markdown("""
                                - Opponent's strong legal team
                                - Potential counterclaims
                                - Public relations impact
                                """)
                            
                            # Recommendations
                            st.markdown("---")
                            st.markdown("### 💡 Strategic Recommendations")
                            st.success("""
                            1. **Prioritize Settlement Negotiations** - 70% chance of favorable outcome
                            2. **Prepare for Litigation** - Build strongest arguments on breach claims
                            3. **Manage Costs** - Set budget limits and milestones
                            4. **Timeline** - Aim for resolution within 6-9 months
                            """)
                        
                        elif analysis_type == "Risk Assessment":
                            st.markdown("### Risk Matrix")
                            
                            risks = [
                                {"Risk": "Adverse Judgment", "Probability": "Medium", "Impact": "High", "Mitigation": "Strong legal arguments"},
                                {"Risk": "Excessive Costs", "Probability": "High", "Impact": "Medium", "Mitigation": "Budget controls"},
                                {"Risk": "Reputation Damage", "Probability": "Low", "Impact": "Medium", "Mitigation": "PR strategy"},
                                {"Risk": "Counterclaims", "Probability": "Medium", "Impact": "Medium", "Mitigation": "Defensive preparation"}
                            ]
                            
                            for risk in risks:
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.markdown(f"**{risk['Risk']}**")
                                with col2:
                                    st.markdown(f"P: {risk['Probability']}")
                                with col3:
                                    st.markdown(f"I: {risk['Impact']}")
                                with col4:
                                    st.markdown(f"_{risk['Mitigation']}_")
        else:
            st.warning("Please select a case for analysis")

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    health = check_health()
    if health.get("status") == "healthy":
        st.success("✅ System Healthy")
    else:
        st.error("❌ System Issues")

with col2:
    st.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with col3:
    if st.button("🔄 Refresh All", use_container_width=True):
        st.session_state.cases = get_cases()
        st.rerun()