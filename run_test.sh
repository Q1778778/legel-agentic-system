#!/bin/bash

echo "⚖️ Court Argument Simulator - 测试工具"
echo "========================================"
echo ""
echo "请选择测试方式："
echo "1) 命令行交互式测试"
echo "2) Web界面测试 (Streamlit)"
echo "3) 退出"
echo ""
read -p "请输入选项 (1-3): " choice

case $choice in
    1)
        echo "启动命令行测试客户端..."
        python3 test_client.py
        ;;
    2)
        echo "启动Web界面..."
        echo "正在安装Streamlit（如果需要）..."
        pip install -q streamlit 2>/dev/null
        echo ""
        echo "🌐 正在启动Web界面..."
        echo "📍 浏览器将自动打开，如未打开请访问: http://localhost:8501"
        echo "📍 按 Ctrl+C 停止服务"
        echo ""
        streamlit run web_app.py
        ;;
    3)
        echo "再见！"
        exit 0
        ;;
    *)
        echo "无效选项"
        exit 1
        ;;
esac