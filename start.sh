#!/bin/bash
# 叙事引擎原型启动脚本

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
  echo "⚠️  未找到 .env 文件"
  echo "请创建 .env 文件并设置 ANTHROPIC_API_KEY："
  echo "  cp .env.example .env"
  echo "  然后编辑 .env 填入你的 API Key"
  exit 1
fi

echo "🎭 启动叙事引擎原型..."
PORT=${PORT:-5000}
echo "   访问地址：http://localhost:$PORT"
python3 app.py
