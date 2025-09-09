#!/usr/bin/env python3
"""
法律智能系统 - 完整启动指南
"""

import os
import sys
import subprocess
import time
from pathlib import Path
import webbrowser

def print_header(text):
    """打印标题"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def check_command(command):
    """检查命令是否存在"""
    try:
        subprocess.run(["which", command], capture_output=True, check=True)
        return True
    except:
        return False

def check_port(port):
    """检查端口是否被占用"""
    try:
        result = subprocess.run(
            f"lsof -i :{port}",
            shell=True,
            capture_output=True
        )
        return result.returncode != 0  # 返回0表示端口被占用
    except:
        return True  # 假设端口可用

def check_dependencies():
    """检查系统依赖"""
    print_header("检查系统依赖")
    
    dependencies = {
        "python3": "Python运行环境",
        "pip": "Python包管理器",
        "git": "版本控制",
    }
    
    missing = []
    for cmd, desc in dependencies.items():
        if check_command(cmd):
            print(f"✅ {desc} ({cmd})")
        else:
            print(f"❌ {desc} ({cmd}) - 需要安装")
            missing.append(cmd)
    
    return len(missing) == 0

def check_neo4j():
    """检查Neo4j状态"""
    print_header("检查Neo4j数据库")
    
    if check_command("neo4j"):
        print("✅ Neo4j已安装")
        
        # 检查是否运行中
        try:
            result = subprocess.run(
                ["neo4j", "status"],
                capture_output=True,
                text=True
            )
            if "is running" in result.stdout:
                print("✅ Neo4j正在运行")
                return True
            else:
                print("⚠️ Neo4j未运行")
                print("\n启动Neo4j:")
                print("  neo4j start")
                return False
        except:
            print("⚠️ 无法检查Neo4j状态")
            return False
    else:
        print("❌ Neo4j未安装")
        print("\n安装方法:")
        print("  macOS: brew install neo4j")
        print("  Ubuntu: sudo apt install neo4j")
        print("  下载: https://neo4j.com/download/")
        return False

def check_services():
    """检查运行中的服务"""
    print_header("当前运行的服务")
    
    services = {
        8501: "原始版Web界面",
        8502: "增强版案件管理",
        8503: "MCP集成版",
        8504: "Apple风格界面",
        8000: "FastAPI后端",
        7687: "Neo4j数据库",
    }
    
    running = []
    available = []
    
    for port, name in services.items():
        if not check_port(port):  # 端口被占用说明服务在运行
            print(f"✅ {name} (端口 {port})")
            running.append(port)
        else:
            print(f"⚠️ {name} (端口 {port}) - 未运行")
            available.append(port)
    
    return running, available

def setup_env():
    """设置环境变量"""
    print_header("配置环境变量")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️ .env文件不存在，创建默认配置...")
        with open(".env", "w") as f:
            f.write("""# API Keys
OPENAI_API_KEY=your_openai_key
GOVINFO_API_KEY=CFRckUTVkM839u72rl0HlZ4sgLhXggVSJeM78vCK

# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Vector Database
VECTOR_DB_TYPE=chroma
PINECONE_API_KEY=
PINECONE_ENVIRONMENT=

# GraphRAG
GRAPHRAG_API_ENDPOINT=http://localhost:8000
""")
        print("✅ 创建了.env文件，请编辑并添加API密钥")
    else:
        print("✅ .env文件已存在")
    
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ 环境变量已加载")

def start_services():
    """启动服务的命令"""
    print_header("启动服务指南")
    
    print("\n📋 启动顺序：\n")
    
    print("1️⃣ 启动Neo4j数据库:")
    print("   neo4j start")
    print("   访问: http://localhost:7474")
    print("   默认: neo4j/neo4j\n")
    
    print("2️⃣ 启动FastAPI后端:")
    print("   python -m src.main")
    print("   或: uvicorn src.main:app --reload")
    print("   访问: http://localhost:8000/docs\n")
    
    print("3️⃣ 启动Web界面 (选择一个):")
    print("   streamlit run web_app_enhanced.py --server.port 8502  # 推荐")
    print("   streamlit run web_app_mcp_integrated.py --server.port 8503")
    print("   streamlit run web_app_apple.py --server.port 8504\n")
    
    print("4️⃣ 启动MCP服务器 (可选):")
    print("   python mcp_case_extractor/server.py")
    print("   python mcp_lawyer_server/run_server.py")

def quick_start():
    """快速启动脚本"""
    print_header("快速启动")
    
    print("运行以下命令快速启动系统：\n")
    
    # 创建启动脚本
    script_content = """#!/bin/bash
# 法律智能系统快速启动脚本

echo "🚀 启动法律智能系统..."

# 1. 检查Neo4j
if command -v neo4j &> /dev/null; then
    echo "启动Neo4j..."
    neo4j start
    sleep 5
fi

# 2. 启动后端服务
echo "启动FastAPI后端..."
python -m src.main &
BACKEND_PID=$!
sleep 3

# 3. 启动Web界面
echo "启动Web界面..."
streamlit run web_app_enhanced.py --server.port 8502 &
WEB_PID=$!

echo ""
echo "✅ 系统启动完成！"
echo ""
echo "访问地址："
echo "  Web界面: http://localhost:8502"
echo "  API文档: http://localhost:8000/docs"
echo "  Neo4j: http://localhost:7474"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待用户中断
trap "kill $BACKEND_PID $WEB_PID; neo4j stop; exit" INT
wait
"""
    
    with open("quick_start.sh", "w") as f:
        f.write(script_content)
    
    subprocess.run(["chmod", "+x", "quick_start.sh"])
    print("✅ 创建了 quick_start.sh")
    print("   运行: ./quick_start.sh")

def show_urls():
    """显示访问地址"""
    print_header("系统访问地址")
    
    urls = {
        "增强版案件管理": "http://localhost:8502",
        "MCP集成版": "http://localhost:8503",
        "Apple风格界面": "http://localhost:8504",
        "API文档": "http://localhost:8000/docs",
        "Neo4j控制台": "http://localhost:7474",
    }
    
    print("\n🌐 Web界面:")
    for name, url in urls.items():
        print(f"  {name}: {url}")
    
    print("\n💡 推荐使用:")
    print("  http://localhost:8502 - 功能最完整的版本")

def main():
    print("\n" + "="*60)
    print("  🚀 法律智能系统 - 启动指南")
    print("="*60)
    
    # 1. 检查依赖
    deps_ok = check_dependencies()
    
    # 2. 检查Neo4j
    neo4j_ok = check_neo4j()
    
    # 3. 检查服务状态
    running, available = check_services()
    
    # 4. 设置环境变量
    setup_env()
    
    # 5. 显示启动指南
    start_services()
    
    # 6. 创建快速启动脚本
    quick_start()
    
    # 7. 显示访问地址
    show_urls()
    
    print_header("总结")
    
    if len(running) > 0:
        print(f"✅ 已有 {len(running)} 个服务在运行")
    
    if not neo4j_ok:
        print("⚠️ 建议安装并启动Neo4j以使用完整功能")
    
    print("\n📝 下一步:")
    if len(running) == 0:
        print("1. 运行 ./quick_start.sh 启动所有服务")
    else:
        print("1. 访问 http://localhost:8502 使用系统")
    
    print("2. 查看 README.md 了解详细功能")
    print("3. 运行测试: python test_govinfo_api.py")
    
    print("\n✨ 系统已准备就绪！")

if __name__ == "__main__":
    main()