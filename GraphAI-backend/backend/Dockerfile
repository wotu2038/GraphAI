FROM python:3.10-slim

WORKDIR /app

# 配置apt-get使用阿里云镜像源（加速包下载）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 配置pip使用清华大学镜像源（加速Python包下载）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 分步安装依赖，解决 neo4j 版本冲突
# 步骤1: 先安装 neo4j==5.26.0（固定版本，必须在 cognee 之前）
RUN pip install --no-cache-dir neo4j==5.26.0

# 步骤2: 安装其他依赖（排除 cognee[neo4j]，避免版本冲突）
RUN grep -v "cognee\[neo4j\]" requirements.txt > /tmp/requirements_no_cognee.txt && \
    pip install --no-cache-dir -r /tmp/requirements_no_cognee.txt

# 步骤3: 处理版本冲突（cognee 要求的版本）
# 安装兼容版本的 pydantic 和 websockets（满足 cognee 要求）
RUN pip install --no-cache-dir 'pydantic>=2.10.5,<2.12.0' 'websockets>=15.0.1,<16.0.0'

# 步骤4: 安装 cognee[neo4j] 0.5.1（固定版本，避免 0.5.2 的 Instructor 问题），使用 --no-deps 避免升级 neo4j
# 注意：依赖已在步骤2中安装，这里只安装 cognee 本身
RUN pip install --no-cache-dir 'cognee[neo4j]==0.5.1' --no-deps

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

