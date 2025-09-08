#!/bin/bash

echo "⚖️ Court Argument Simulator - 测试工具"
echo "========================================"
echo ""
echo "请选择测试方式："
echo "1) 命令行交互式测试"
echo "2) 退出"
echo ""
read -p "请输入选项 (1-2): " choice

case $choice in
    1)
        echo "启动命令行测试客户端..."
        python3 test_client.py
        ;;
    2)
        echo "再见！"
        exit 0
        ;;
    *)
        echo "无效选项"
        exit 1
        ;;
esac