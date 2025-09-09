#!/usr/bin/env python3
"""
Simplified Legal AI Assistant - All-in-One Interface
Integrates case extraction, legal consultation, and real-time legal data
"""

import streamlit as st
import requests
import json
from typing import Dict, Any, List, Optional
import time
from datetime import datetime
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure page
st.set_page_config(
    page_title="Legal AI Assistant",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE = "http://localhost:8000"
API_V1 = f"{API_BASE}/api/v1"
API_ROOT = API_BASE  # For endpoints without /api/v1 prefix

# Initialize OpenAI client
@st.cache_resource
def get_openai_client():
    """Get AI client with caching"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

# Initialize session state
if "current_case" not in st.session_state:
    st.session_state.current_case = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []

# Helper Functions
def api_call(endpoint: str, method: str = "GET", data: Dict = None, use_root: bool = False) -> Dict:
    """Make API call to backend"""
    try:
        # Use root path for MCP endpoints
        base_url = API_ROOT if use_root else API_V1
        url = f"{base_url}/{endpoint}"
        
        if method == "POST":
            response = requests.post(url, json=data)
        else:
            response = requests.get(url, params=data)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def extract_case_from_text(text: str) -> Dict:
    """Extract case information from text using AI"""
    client = get_openai_client()
    if not client:
        return {"error": "AI service not available"}
    
    try:
        # Create a prompt for GPT-4-mini to extract case information
        prompt = f"""Analyze the following legal case description and extract structured information.
        
Case Description:
{text}

Please extract and return the following information in JSON format:
1. title: A concise case title (if parties are mentioned, format as "Party1 v. Party2")
2. parties: List of parties involved (plaintiff, defendant, etc.)
3. type: Case type (Contract Dispute, Intellectual Property, Employment, Criminal, Civil, Other)
4. description: Brief summary of the case
5. issues: List of main legal issues (maximum 3)
6. facts: Key facts of the case
7. claims: Legal claims being made

Return ONLY valid JSON without any additional text or markdown formatting."""

        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": "You are a legal analyst expert at extracting structured information from case descriptions. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=10000
        )
        
        # Parse the response
        result_text = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        case_info = json.loads(result_text)
        case_info["extracted_at"] = datetime.now().isoformat()
        case_info["extraction_method"] = "AI"
        
        return case_info
        
    except json.JSONDecodeError as e:
        return {
            "error": "Failed to parse response",
            "title": "Legal Case",
            "description": text[:500],
            "issues": ["Unable to extract issues"],
            "type": "General"
        }
    except Exception as e:
        return {
            "error": "Service temporarily unavailable",
            "title": "Legal Case", 
            "description": text[:500],
            "issues": ["Error during extraction"],
            "type": "General"
        }

def search_similar_cases(query: str, limit: int = 10) -> List[Dict]:
    """Search for similar cases using GraphRAG"""
    result = api_call("retrieval/search", "POST", {
        "issue_text": query,
        "limit": limit,
        "use_graphrag": True
    })
    return result.get("bundles", [])

def get_legal_data(query: str, source: str = "all") -> Dict:
    """Get legal data from various APIs"""
    result = api_call("legal-data/search", "POST", {
        "query": query,
        "sources": [source] if source != "all" else [
            "courtlistener", "recap", "cap", "govinfo", "ecfr"
        ]
    })
    return result

def analyze_case(case_data: Dict) -> Dict:
    """Analyze case for legal strategy using AI"""
    client = get_openai_client()
    if not client:
        # Fallback to API if OpenAI not available
        bundle = {
            "case": {
                "id": "case_001",
                "caption": case_data.get("title", "Legal Case"),
                "court": "District Court",
                "date": "2024-01-01",
                "outcome": "pending"
            },
            "issue": {
                "id": "issue_001",
                "description": case_data.get("description", ""),
                "legal_area": case_data.get("type", "General")
            },
            "defense_arguments": [{
                "id": "arg_001",
                "text": case_data.get("description", ""),
                "type": "factual",
                "strength": 0.7
            }],
            "prosecution_arguments": [],
            "score": 0.8
        }
        
        result = api_call("analysis/analyze", "POST", {
            "bundles": [bundle],
            "context": case_data.get("description", ""),
            "include_prosecution": True,
            "include_judge": True,
            "max_length": 2000
        })
        
        if "error" not in result:
            return result
    
    try:
        # Use GPT-4-mini for analysis
        prompt = f"""Analyze the following legal case and provide strategic analysis.

Case Information:
Title: {case_data.get('title', 'N/A')}
Type: {case_data.get('type', 'N/A')}
Parties: {', '.join(case_data.get('parties', [])) if case_data.get('parties') else 'N/A'}
Description: {case_data.get('description', 'N/A')}
Issues: {'; '.join(case_data.get('issues', [])) if case_data.get('issues') else 'N/A'}

Please provide:
1. Strengths: Key strengths of the case (2-3 points)
2. Weaknesses: Potential weaknesses or challenges (2-3 points)
3. Strategy: Recommended legal strategy (3-4 key steps)
4. Precedents: Relevant case precedents or legal principles that may apply (2-3 examples)
5. Risk Assessment: Overall risk level (Low/Medium/High) with brief explanation

Format your response as JSON with keys: strengths, weaknesses, strategy, precedents, risk_assessment"""

        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": "You are an experienced legal strategist providing case analysis. Be specific and practical in your recommendations."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=15000
        )
        
        result_text = response.choices[0].message.content.strip()
        # Remove markdown if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        analysis = json.loads(result_text)
        analysis["analysis_method"] = "AI"
        
        return analysis
        
    except Exception as e:
        return {
            "strengths": f"Based on the {case_data.get('type', 'case')} type:\n• Clear identification of parties and dispute\n• Documented issues and claims",
            "weaknesses": "Areas needing attention:\n• Additional evidence may be required\n• Legal precedents should be thoroughly researched",
            "strategy": f"Recommended approach for {case_data.get('type', 'this case')}:\n1. Compile all relevant documentation\n2. Research similar cases and precedents\n3. Develop strong legal arguments\n4. Prepare for potential counterarguments",
            "precedents": ["Research similar cases in your jurisdiction", "Consider relevant statutory law", "Review appellate court decisions"],
            "risk_assessment": "Medium - Requires thorough preparation and research"
        }

# Main Interface
st.title("⚖️ Legal AI Assistant")
st.markdown("Simplified interface for case management, legal research, and AI consultation")

# Sidebar for workflow steps
with st.sidebar:
    st.header("📋 Workflow")
    workflow_step = st.radio(
        "Select Step:",
        ["1️⃣ Case Input", "2️⃣ Case Analysis", "3️⃣ Legal Research", "4️⃣ AI Consultation"],
        key="workflow"
    )
    
    st.divider()
    
    # Current case summary
    if st.session_state.current_case:
        st.success("✅ Case Loaded")
        st.json(st.session_state.current_case)
    else:
        st.info("📝 No case loaded yet")
    
    if st.button("🔄 Reset All", type="secondary"):
        st.session_state.current_case = None
        st.session_state.chat_history = []
        st.session_state.search_results = []
        st.rerun()

# Main content area
if workflow_step == "1️⃣ Case Input":
    st.header("Step 1: Input Your Case")
    
    input_method = st.radio(
        "Choose input method:",
        ["💬 Describe in Chat", "📄 Upload Document", "✍️ Manual Entry"]
    )
    
    if input_method == "💬 Describe in Chat":
        st.markdown("### Describe your case")
        case_description = st.text_area(
            "Case Description",
            placeholder="Describe your legal case in detail. Include parties involved, dispute details, and key issues...",
            height=200
        )
        
        if st.button("Extract Case Info", type="primary"):
            if case_description:
                with st.spinner("Extracting case information..."):
                    extracted = extract_case_from_text(case_description)
                    if "error" not in extracted:
                        st.session_state.current_case = extracted
                        st.success("✅ Case information extracted!")
                        st.json(extracted)
                    else:
                        st.error(f"Error: {extracted['error']}")
            else:
                st.warning("Please enter a case description")
    
    elif input_method == "📄 Upload Document":
        uploaded_file = st.file_uploader(
            "Upload case document",
            type=["pdf", "txt", "docx"]
        )
        
        if uploaded_file and st.button("Process Document", type="primary"):
            with st.spinner("Processing document..."):
                # Here you would process the file
                st.info("Document processing would extract case details")
                # Placeholder for document processing
                st.session_state.current_case = {
                    "title": uploaded_file.name,
                    "type": "document_upload",
                    "status": "extracted"
                }
    
    else:  # Manual Entry
        with st.form("manual_case_form"):
            st.markdown("### Enter Case Details")
            title = st.text_input("Case Title*")
            parties = st.text_input("Parties Involved*")
            case_type = st.selectbox(
                "Case Type*",
                ["Contract Dispute", "IP/Patent", "Employment", "Criminal", "Civil", "Other"]
            )
            description = st.text_area("Case Description*", height=100)
            key_issues = st.text_area("Key Legal Issues (one per line)", height=100)
            
            if st.form_submit_button("Create Case", type="primary"):
                if all([title, parties, case_type, description]):
                    st.session_state.current_case = {
                        "title": title,
                        "parties": parties,
                        "type": case_type,
                        "description": description,
                        "issues": [i.strip() for i in key_issues.split('\n') if i.strip()]
                    }
                    st.success("✅ Case created successfully!")
                else:
                    st.error("Please fill all required fields")

elif workflow_step == "2️⃣ Case Analysis":
    st.header("Step 2: Analyze Your Case")
    
    if not st.session_state.current_case:
        st.warning("⚠️ Please input a case first (Step 1)")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("### Case Analysis")
            
            if st.button("🔍 Analyze Case", type="primary"):
                with st.spinner("Analyzing case..."):
                    analysis = analyze_case(st.session_state.current_case)
                    
                    if "error" not in analysis:
                        # Display analysis results
                        st.markdown("#### 💪 Strengths")
                        st.write(analysis.get("strengths", "No strengths identified"))
                        
                        st.markdown("#### ⚠️ Weaknesses")
                        st.write(analysis.get("weaknesses", "No weaknesses identified"))
                        
                        st.markdown("#### 📋 Recommended Strategy")
                        st.write(analysis.get("strategy", "No strategy available"))
                        
                        st.markdown("#### 📚 Relevant Precedents")
                        precedents = analysis.get("precedents", [])
                        if precedents:
                            for p in precedents:
                                st.write(f"- {p}")
                        else:
                            st.write("No precedents found")
                    else:
                        st.error(f"Analysis failed: {analysis['error']}")
        
        with col2:
            st.markdown("### Quick Actions")
            if st.button("📊 Generate Report"):
                st.info("Report generation would create a PDF summary")
            
            if st.button("📧 Email Summary"):
                st.info("Email functionality would send case summary")

elif workflow_step == "3️⃣ Legal Research":
    st.header("Step 3: Legal Research")
    
    tab1, tab2, tab3 = st.tabs(["🔍 Similar Cases", "📚 Legal Databases", "📊 Analytics"])
    
    with tab1:
        st.markdown("### Search Similar Cases (GraphRAG)")
        
        search_query = st.text_input(
            "Search Query",
            value=st.session_state.current_case.get("description", "") if st.session_state.current_case else "",
            placeholder="Enter legal issue or case description..."
        )
        
        col1, col2 = st.columns([3, 1])
        with col1:
            search_button = st.button("🔎 Search Cases", type="primary")
        with col2:
            limit = st.number_input("Results", min_value=5, max_value=50, value=10)
        
        if search_button and search_query:
            with st.spinner("Searching with GraphRAG..."):
                results = search_similar_cases(search_query, limit)
                st.session_state.search_results = results
                
                if results:
                    st.success(f"Found {len(results)} similar cases")
                    
                    for i, case in enumerate(results, 1):
                        with st.expander(f"Case {i}: {case.get('caption', 'Unknown')}"):
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.write(f"**Court:** {case.get('court', 'N/A')}")
                                st.write(f"**Date:** {case.get('date', 'N/A')}")
                                st.write(f"**Outcome:** {case.get('outcome', 'N/A')}")
                            with col2:
                                st.metric("Relevance", f"{case.get('score', 0):.2%}")
                            
                            st.markdown("**Summary:**")
                            st.write(case.get('summary', 'No summary available'))
                else:
                    st.warning("No similar cases found")
    
    with tab2:
        st.markdown("### Search Legal Databases")
        
        db_query = st.text_input("Database Search Query", placeholder="Enter search terms...")
        
        data_source = st.selectbox(
            "Select Data Source",
            ["All Sources", "CourtListener", "RECAP", "CAP", "GovInfo", "eCFR"]
        )
        
        if st.button("📖 Search Databases", type="primary"):
            if db_query:
                with st.spinner(f"Searching {data_source}..."):
                    source_map = {
                        "All Sources": "all",
                        "CourtListener": "courtlistener",
                        "RECAP": "recap",
                        "CAP": "cap",
                        "GovInfo": "govinfo",
                        "eCFR": "ecfr"
                    }
                    
                    legal_data = get_legal_data(db_query, source_map[data_source])
                    
                    if "error" not in legal_data:
                        st.success(f"Found {legal_data.get('total_results', 0)} results")
                        
                        results = legal_data.get("results", [])
                        for result in results[:10]:  # Show first 10
                            with st.expander(result.get("title", "Untitled")):
                                st.write(f"**Source:** {result.get('source', 'Unknown')}")
                                st.write(f"**Date:** {result.get('date', 'N/A')}")
                                st.write(f"**URL:** {result.get('url', 'N/A')}")
                                st.write(result.get("snippet", "No preview available"))
                    else:
                        st.error(f"Search failed: {legal_data['error']}")
            else:
                st.warning("Please enter a search query")
    
    with tab3:
        st.markdown("### Case Analytics")
        
        if st.session_state.search_results:
            st.metric("Total Cases Found", len(st.session_state.search_results))
            
            # Simple analytics
            outcomes = {}
            for case in st.session_state.search_results:
                outcome = case.get("outcome", "Unknown")
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
            
            st.markdown("**Outcome Distribution:**")
            for outcome, count in outcomes.items():
                st.write(f"- {outcome}: {count} cases")
        else:
            st.info("No search results to analyze. Please perform a search first.")

elif workflow_step == "4️⃣ AI Consultation":
    st.header("Step 4: AI Legal Consultation")
    
    # Chat interface
    st.markdown("### 💬 Chat with Legal AI")
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    user_input = st.chat_input("Ask a legal question...")
    
    if user_input:
        # Add user message to history
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # Get AI response
        with st.spinner("Thinking..."):
            # Call the chat API
            response = api_call("chat/", "POST", {"message": user_input})
            
            if "error" not in response:
                ai_response = response.get("response", "I'm not sure how to respond to that.")
            else:
                ai_response = "Sorry, I encountered an error. Please try again."
        
        # Add AI response to history
        st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
        st.rerun()
    
    # Quick action buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🎯 Get Strategy Advice"):
            prompt = "Based on the current case, what legal strategy would you recommend?"
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.chat_history.append({"role": "assistant", "content": "I would recommend focusing on..."})
            st.rerun()
    
    with col2:
        if st.button("⚠️ Identify Risks"):
            prompt = "What are the main legal risks in this case?"
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.chat_history.append({"role": "assistant", "content": "The main risks include..."})
            st.rerun()
    
    with col3:
        if st.button("📝 Draft Arguments"):
            prompt = "Help me draft opening arguments for this case."
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.chat_history.append({"role": "assistant", "content": "Here's a draft of opening arguments..."})
            st.rerun()

# Footer
st.divider()
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Legal AI Assistant v1.0 | Powered by GraphRAG & Multiple Legal APIs
    </div>
    """,
    unsafe_allow_html=True
)