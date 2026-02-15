#!/bin/bash
set -e

echo "================================================"
echo "🚀 GraphAI Backend 启动流程"
echo "================================================"

# 1. 初始化 Neo4j 索引
echo ""
echo "📊 步骤1: 初始化 Neo4j 索引..."
python /app/scripts/init_neo4j_indexes.py
if [ $? -ne 0 ]; then
    echo "❌ Neo4j 索引初始化失败"
    exit 1
fi

# 2. 启动 Uvicorn 服务
echo ""
echo "🌐 步骤2: 启动 Uvicorn 服务..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --timeout-keep-alive 300
