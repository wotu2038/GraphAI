# GraphAI 前端应用

GraphAI 知识图谱应用的前端应用，基于 Vue 3 + Vite 构建，提供用户界面和交互功能。

## 📋 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [开发指南](#开发指南)
- [部署说明](#部署说明)
- [常见问题](#常见问题)

## ✨ 功能特性

### 核心功能

- **文档管理界面**
  - 文档上传和列表展示
  - 文档解析状态查看
  - 文档版本管理

- **知识图谱可视化**
  - 实体和关系图形化展示
  - 交互式图谱浏览
  - 节点和边的详细信息查看

- **语义搜索**
  - 智能搜索界面
  - 搜索结果展示
  - 多文档搜索支持

- **需求文档生成**
  - 需求文档生成界面
  - 生成进度跟踪
  - 文档预览和导出
  - 支持流式生成（实时显示生成内容）

- **智能问答**
  - 对话式问答界面
  - 知识图谱增强回答
  - 对话历史记录
  - 支持多个 LLM 提供商（千问、DeepSeek、Kimi）
  - 流式生成支持（打字机效果）
  - 对话模式和 Agent 模式

## 🛠 技术栈

- **框架**: Vue 3 + Vite
- **UI 组件**: Ant Design Vue 4.0
- **图表**: D3.js
- **状态管理**: Pinia
- **路由**: Vue Router 4
- **HTTP 客户端**: Axios

## 🚀 快速开始

### 前置要求

- Node.js 18+ 和 npm
- 或 Docker & Docker Compose（用于容器化部署）

### 安装步骤

1. **克隆项目**

```bash
git clone <repository-url>
cd GraphAI-frontend
```

2. **进入前端目录并安装依赖**

```bash
cd frontend
npm install
```

3. **配置后端 API 地址**

```bash
# 返回项目根目录
cd ..

# 复制环境变量示例文件
cp .env.example .env

# 编辑 .env 文件，配置后端 API 地址
vim .env
```

`.env` 文件内容：
```env
# 开发环境（后端运行在 localhost:8000）
VITE_API_BASE_URL=/api

# 或指定完整地址
# VITE_API_BASE_URL=http://localhost:8000/api
```

4. **启动开发服务器**

```bash
cd frontend
npm run dev
```

5. **访问应用**

- **前端应用**: http://localhost:3008

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VITE_API_BASE_URL` | 后端 API 基础地址 | `/api` |

### 配置方式

#### 本地开发

在项目根目录创建 `.env` 文件：

```env
VITE_API_BASE_URL=/api
```

Vite 开发服务器会自动将 `/api` 请求代理到后端。

#### Docker 构建

通过构建参数传递：

```bash
docker build --build-arg VITE_API_BASE_URL=/api -t graph-ai-frontend frontend/
```

#### GitLab CI/CD

在 GitLab CI/CD Variables 中设置 `VITE_API_BASE_URL`，CI 流程会自动使用。

### Nginx 配置

生产环境使用 Nginx 部署时，`frontend/nginx.conf` 已配置好 API 代理：

```nginx
location /api {
    # 修改为实际的后端地址
    proxy_pass http://your-backend-host:8000/api;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # 支持长时间运行的请求
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
}
```

**部署时需要修改 `proxy_pass` 为实际的后端地址。**

## 💻 开发指南

### 本地开发

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

### 代码结构

```
GraphAI-frontend/
├── frontend/                   # 前端源代码
│   ├── src/
│   │   ├── api/               # API 调用
│   │   │   └── index.js       # Axios 实例（使用 VITE_API_BASE_URL）
│   │   ├── components/        # Vue 组件
│   │   ├── views/             # 页面视图
│   │   ├── stores/            # Pinia 状态管理
│   │   ├── router/            # 路由配置
│   │   ├── utils/             # 工具函数
│   │   ├── App.vue            # 根组件
│   │   └── main.js            # 入口文件
│   ├── public/                # 静态资源
│   ├── Dockerfile             # 生产环境 Docker 构建
│   ├── Dockerfile.dev         # 开发环境 Docker 构建
│   ├── nginx.conf             # Nginx 配置
│   ├── vite.config.js         # Vite 配置
│   └── package.json
├── docker-compose.frontend.yml # Docker Compose 配置
├── .gitlab-ci.yml              # GitLab CI/CD 配置
├── .env.example                # 环境变量示例（提交到 Git）
├── .env                        # 实际配置（不提交到 Git）
└── README.md                   # 本文档
```

## 🚢 部署说明

### Docker 部署

1. **构建镜像**

```bash
# 在项目根目录执行
docker build \
  --build-arg VITE_API_BASE_URL=/api \
  -t graph-ai-frontend \
  frontend/
```

2. **使用 Docker Compose**

```bash
# 启动前端服务
docker-compose -f docker-compose.frontend.yml up -d

# 查看日志
docker-compose -f docker-compose.frontend.yml logs -f
```

### 前后端联合部署

如果前后端部署在同一台机器上：

1. 前端 nginx 配置使用 `proxy_pass http://host.docker.internal:8000/api`（Docker Desktop）
2. 或使用 Docker 网络连接后端容器

如果前后端分离部署：

1. 修改 `frontend/nginx.conf` 中的 `proxy_pass` 为后端实际地址
2. 或在构建时传入完整的后端 URL：`--build-arg VITE_API_BASE_URL=http://backend.example.com/api`

### GitLab CI/CD 自动化部署

项目已包含 `.gitlab-ci.yml` 配置文件，支持自动化构建和部署。

#### 配置步骤

1. **在 GitLab 中配置 CI/CD Variables**：
   - 进入项目：`Settings > CI/CD > Variables`
   - 添加以下变量：

   | 变量 | 说明 | 示例 |
   |------|------|------|
   | `VITE_API_BASE_URL` | 后端 API 地址 | `/api` |
   | `CI_REGISTRY_USER` | Docker Registry 用户名 | - |
   | `CI_REGISTRY_PASSWORD` | Docker Registry 密码 | - |
   | `SSH_PRIVATE_KEY` | 部署服务器 SSH 私钥 | - |
   | `DEPLOY_SERVER` | 生产环境服务器地址 | - |
   | `DEPLOY_USER` | 生产环境部署用户 | - |

2. **触发构建**：
   - 推送到 `main`/`master` 分支：自动构建，手动部署到生产环境
   - 推送到 `develop` 分支：自动构建，手动部署到开发环境

### 生产环境构建

```bash
cd frontend

# 构建生产版本
npm run build

# 构建产物在 dist/ 目录
# 可以使用 Nginx 或其他 Web 服务器部署
```

## ❓ 常见问题

### 1. API 请求失败

**问题**: 前端无法连接到后端 API

**解决方案**:
- 检查后端服务是否运行
- 检查 `.env` 中的 `VITE_API_BASE_URL` 配置
- 检查 `frontend/nginx.conf` 中的 `proxy_pass` 配置
- 检查浏览器控制台的网络请求错误

### 2. 构建失败

**问题**: `npm run build` 失败

**解决方案**:
- 检查 Node.js 版本（需要 18+）
- 清除缓存：`rm -rf node_modules package-lock.json && npm install`
- 检查依赖是否完整安装

### 3. 页面空白

**问题**: 页面加载后显示空白

**解决方案**:
- 打开浏览器开发者工具查看控制台错误
- 检查路由配置是否正确
- 检查 API 基础地址配置是否正确

### 4. 开发服务器代理不生效

**问题**: 开发环境 API 请求 404

**解决方案**:
- 确保 `.env` 文件在项目根目录
- 确保 `VITE_API_BASE_URL` 配置正确
- 检查 `vite.config.js` 中的 proxy 配置
- 重启开发服务器

### 5. Docker 构建后 API 地址错误

**问题**: Docker 部署后无法连接后端

**解决方案**:
- 构建时通过 `--build-arg VITE_API_BASE_URL=xxx` 传入正确地址
- 或修改 `frontend/nginx.conf` 中的 `proxy_pass`
- 确保后端服务可从前端容器访问

## 📝 许可证

[添加许可证信息]

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

[添加联系方式]

---

**注意**: 这是一个开发中的项目，生产环境使用前请仔细测试。
