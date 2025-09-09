#!/usr/bin/env python3
"""
Legal Analysis System - Apple Style Web Interface
使用Apple设计风格的法律智能系统界面
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import os
from pathlib import Path
import asyncio
from typing import Dict, Any, List, Optional
import base64

# Page configuration
st.set_page_config(
    page_title="Legal AI - 法律智能系统",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Constants
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
FRONTEND_PATH = Path(__file__).parent / "frontend"

class AppleLegalAI:
    """Apple风格的法律AI界面"""
    
    def __init__(self):
        self.init_session_state()
        self.api_base_url = API_BASE_URL
        
    def init_session_state(self):
        """初始化会话状态"""
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        if 'current_case' not in st.session_state:
            st.session_state.current_case = None
        if 'theme' not in st.session_state:
            st.session_state.theme = 'light'
        if 'show_native' not in st.session_state:
            st.session_state.show_native = False
            
    def load_html_template(self):
        """加载HTML模板"""
        html_path = FRONTEND_PATH / "index.html"
        css_path = FRONTEND_PATH / "css" / "apple-style.css"
        animations_css_path = FRONTEND_PATH / "css" / "animations.css"
        main_js_path = FRONTEND_PATH / "js" / "main.js"
        case_js_path = FRONTEND_PATH / "js" / "case-panel.js"
        chat_js_path = FRONTEND_PATH / "js" / "chat.js"
        
        # Read HTML
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        # Read CSS files
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        with open(animations_css_path, 'r', encoding='utf-8') as f:
            animations_css = f.read()
            
        # Read JS files
        with open(main_js_path, 'r', encoding='utf-8') as f:
            main_js = f.read()
        with open(case_js_path, 'r', encoding='utf-8') as f:
            case_js = f.read()
        with open(chat_js_path, 'r', encoding='utf-8') as f:
            chat_js = f.read()
            
        # Inject CSS and JS into HTML
        html_content = html_content.replace(
            '<link rel="stylesheet" href="css/apple-style.css">',
            f'<style>{css_content}</style>'
        )
        html_content = html_content.replace(
            '<link rel="stylesheet" href="css/animations.css">',
            f'<style>{animations_css}</style>'
        )
        html_content = html_content.replace(
            '<script src="js/main.js"></script>',
            f'<script>{main_js}</script>'
        )
        html_content = html_content.replace(
            '<script src="js/case-panel.js"></script>',
            f'<script>{case_js}</script>'
        )
        html_content = html_content.replace(
            '<script src="js/chat.js"></script>',
            f'<script>{chat_js}</script>'
        )
        
        # Update API URL
        html_content = html_content.replace(
            "const API_BASE_URL = 'http://localhost:8000'",
            f"const API_BASE_URL = '{self.api_base_url}'"
        )
        
        return html_content
        
    def render_apple_interface(self):
        """渲染Apple风格界面"""
        html_content = self.load_html_template()
        
        # Create full-screen component
        components.html(
            html_content,
            height=1000,
            scrolling=True
        )
        
    def render_native_streamlit(self):
        """渲染原生Streamlit界面（备用）"""
        st.title("⚖️ Legal AI - 法律智能系统")
        
        # Sidebar
        with st.sidebar:
            st.header("案件管理")
            
            # Case selection
            cases = self.get_cases()
            if cases:
                selected_case = st.selectbox(
                    "选择案件",
                    options=[None] + cases,
                    format_func=lambda x: "选择案件..." if x is None else x.get('name', '')
                )
                if selected_case:
                    st.session_state.current_case = selected_case
                    
            # Create new case
            if st.button("➕ 新建案件"):
                self.show_new_case_form()
                
        # Main content area
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("智能对话")
            
            # Chat interface
            chat_container = st.container()
            with chat_container:
                # Display messages
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.write(message["content"])
                        
            # Input area
            with st.form("chat_form", clear_on_submit=True):
                col_input, col_send = st.columns([5, 1])
                with col_input:
                    user_input = st.text_area(
                        "输入您的法律问题...",
                        height=100,
                        key="user_input"
                    )
                with col_send:
                    st.write("")  # Spacer
                    st.write("")  # Spacer
                    send_button = st.form_submit_button("发送 ✈️", use_container_width=True)
                    
                # File upload
                uploaded_files = st.file_uploader(
                    "上传文件（可选）",
                    accept_multiple_files=True,
                    type=['pdf', 'txt', 'doc', 'docx']
                )
                
            if send_button and user_input:
                self.handle_message(user_input, uploaded_files)
                
        with col2:
            st.header("分析结果")
            
            # Analysis tabs
            tab1, tab2, tab3 = st.tabs(["📊 分析", "📚 案例", "📄 文档"])
            
            with tab1:
                if 'analysis' in st.session_state:
                    self.display_analysis(st.session_state.analysis)
                else:
                    st.info("分析结果将在这里显示")
                    
            with tab2:
                self.display_related_cases()
                
            with tab3:
                self.display_documents()
                
    def get_cases(self) -> List[Dict[str, Any]]:
        """获取案件列表"""
        try:
            response = requests.get(f"{self.api_base_url}/api/cases")
            if response.status_code == 200:
                return response.json().get('cases', [])
        except:
            pass
            
        # Return mock data if API fails
        return [
            {"id": "1", "name": "张某诉李某借贷纠纷案", "type": "civil"},
            {"id": "2", "name": "ABC公司商标侵权案", "type": "ip"},
            {"id": "3", "name": "房屋买卖合同纠纷", "type": "contract"}
        ]
        
    def show_new_case_form(self):
        """显示新建案件表单"""
        with st.expander("新建案件", expanded=True):
            case_name = st.text_input("案件名称")
            case_type = st.selectbox(
                "案件类型",
                ["合同纠纷", "刑事案件", "民事诉讼", "知识产权", "公司法务"]
            )
            case_description = st.text_area("案件描述")
            case_priority = st.radio("优先级", ["高", "中", "低"], horizontal=True)
            
            if st.button("创建案件"):
                self.create_case({
                    "name": case_name,
                    "type": case_type,
                    "description": case_description,
                    "priority": case_priority
                })
                
    def create_case(self, case_data: Dict[str, Any]):
        """创建新案件"""
        try:
            response = requests.post(
                f"{self.api_base_url}/api/cases",
                json=case_data
            )
            if response.status_code == 200:
                st.success("案件创建成功！")
                st.rerun()
            else:
                st.error("创建失败，请重试")
        except Exception as e:
            st.error(f"创建失败: {str(e)}")
            
    def handle_message(self, message: str, files: List = None):
        """处理用户消息"""
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": message
        })
        
        # Process files if any
        file_data = []
        if files:
            for file in files:
                file_data.append({
                    "name": file.name,
                    "type": file.type,
                    "size": file.size,
                    "content": base64.b64encode(file.read()).decode()
                })
                
        # Send to API
        try:
            response = requests.post(
                f"{self.api_base_url}/api/chat",
                json={
                    "message": message,
                    "files": file_data,
                    "case_id": st.session_state.current_case.get('id') if st.session_state.current_case else None
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Add assistant response
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data.get("response", "抱歉，我无法理解您的请求。")
                })
                
                # Store analysis
                if 'analysis' in data:
                    st.session_state.analysis = data['analysis']
                    
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "抱歉，处理您的请求时出现错误。"
                })
                
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"连接错误: {str(e)}"
            })
            
        st.rerun()
        
    def display_analysis(self, analysis: Dict[str, Any]):
        """显示分析结果"""
        if 'summary' in analysis:
            st.subheader("📝 摘要")
            st.write(analysis['summary'])
            
        if 'risks' in analysis:
            st.subheader("⚠️ 风险评估")
            for risk in analysis['risks']:
                risk_color = {
                    'high': '🔴',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(risk.get('level', 'low'), '⚪')
                st.write(f"{risk_color} {risk.get('description', '')}")
                
        if 'recommendations' in analysis:
            st.subheader("💡 建议")
            for rec in analysis['recommendations']:
                st.write(f"• {rec}")
                
    def display_related_cases(self):
        """显示相关案例"""
        # Mock data
        cases = [
            {
                "title": "类似借贷纠纷案",
                "similarity": 85,
                "summary": "原告诉被告民间借贷纠纷，法院判决被告返还借款本金及利息。"
            },
            {
                "title": "合同违约案",
                "similarity": 72,
                "summary": "因合同履行产生纠纷，法院认定被告违约并判决赔偿。"
            }
        ]
        
        for case in cases:
            with st.expander(f"{case['title']} (相似度: {case['similarity']}%)"):
                st.write(case['summary'])
                st.button("查看详情", key=f"case_{case['title']}")
                
    def display_documents(self):
        """显示文档列表"""
        st.info("暂无文档")
        
        if st.button("📤 上传文档"):
            st.file_uploader(
                "选择文档",
                accept_multiple_files=True,
                key="doc_uploader"
            )
            
    def run(self):
        """运行应用"""
        # Add toggle button for interface mode
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            interface_mode = st.radio(
                "界面模式",
                ["Apple风格界面", "原生Streamlit界面"],
                horizontal=True,
                label_visibility="collapsed"
            )
            
        if interface_mode == "Apple风格界面":
            # Check if frontend files exist
            if not FRONTEND_PATH.exists():
                st.error("前端文件未找到！请确保 frontend 文件夹存在。")
                st.info("切换到原生Streamlit界面...")
                self.render_native_streamlit()
            else:
                self.render_apple_interface()
        else:
            self.render_native_streamlit()

def main():
    """主函数"""
    # Hide Streamlit default elements for Apple interface
    st.markdown("""
        <style>
        /* Hide Streamlit elements when showing Apple interface */
        .stApp > header {
            background-color: transparent;
        }
        .stApp [data-testid="stToolbar"] {
            display: none;
        }
        </style>
    """, unsafe_allow_html=True)
    
    app = AppleLegalAI()
    app.run()

if __name__ == "__main__":
    main()