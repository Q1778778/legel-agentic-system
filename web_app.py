#!/usr/bin/env python3
"""
Legal Analysis System - Streamlit Web Interface
"""

import streamlit as st
import requests
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

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
tab1, tab2, tab3 = st.tabs(["🔍 GraphRAG Retrieval", "🎭 Argument", "📊 System Status"])

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

# Tab 3: System Status
with tab3:
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