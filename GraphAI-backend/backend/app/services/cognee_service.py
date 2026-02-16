"""
Cognee 服务

使用 Cognee 为章节内容构建知识图谱
参考: https://github.com/topoteretes/cognee
"""
import logging
import asyncio
import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cognee 客户端（延迟导入）
_cognee = None


def get_cognee():
    """获取 Cognee 实例（单例）"""
    global _cognee
    if _cognee is None:
        try:
            logger.info("get_cognee() 开始执行，_cognee=None")
            # 关键：在导入 Cognee 之前设置环境变量
            # Cognee 在导入时会读取环境变量，所以必须先设置
            import os
            logger.info("开始设置环境变量...")
            # 优先使用本地大模型，如果没有则使用千问作为默认配置
            # 这样 Cognee 在初始化时就有正确的 LLM 配置，避免 add() 阶段出现 Instructor 错误
            has_local_llm = hasattr(settings, 'LOCAL_LLM_API_KEY') and settings.LOCAL_LLM_API_KEY
            has_qwen = (hasattr(settings, 'QWEN_API_KEY') and settings.QWEN_API_KEY) or (hasattr(settings, 'QIANWEN_API_KEY') and settings.QIANWEN_API_KEY)
            logger.info(f"LLM 配置检查: LOCAL_LLM={has_local_llm}, QWEN={has_qwen}")
            
            if has_local_llm:
                # 使用本地大模型配置
                os.environ["LLM_API_KEY"] = settings.LOCAL_LLM_API_KEY
                os.environ["OPENAI_API_KEY"] = settings.LOCAL_LLM_API_KEY
                os.environ["LLM_PROVIDER"] = "openai"
                
                # 设置 endpoint（先设置 endpoint，再设置 model，因为 model 设置依赖于 endpoint）
                if hasattr(settings, 'LOCAL_LLM_API_BASE_URL') and settings.LOCAL_LLM_API_BASE_URL:
                    local_base_url = settings.LOCAL_LLM_API_BASE_URL.rstrip('/')
                    if not local_base_url.endswith('/v1'):
                        if '/v1' not in local_base_url:
                            local_base_url = f"{local_base_url}/v1"
                    os.environ["OPENAI_BASE_URL"] = local_base_url
                    os.environ["LLM_ENDPOINT"] = local_base_url
                    # 对于 litellm，需要明确指定这是自定义 OpenAI 端点
                    # 使用 "openai/model_name" 格式，litellm 会使用 OPENAI_BASE_URL
                    # 注意：如果模型名称是完整路径（如 "/home/llm_deploy/Qwen3-32B"），需要保留完整路径
                    if hasattr(settings, 'LOCAL_LLM_MODEL') and settings.LOCAL_LLM_MODEL:
                        model_name = settings.LOCAL_LLM_MODEL
                        # 如果模型名称是完整路径，保留完整路径（服务器需要完整路径）
                        # 如果只是模型名，则直接使用
                        if model_name.startswith('/'):
                            # 完整路径，保留原样
                            os.environ["LLM_MODEL"] = f"openai/{model_name}"
                        else:
                            # 只是模型名，直接使用
                            os.environ["LLM_MODEL"] = f"openai/{model_name}"
                    else:
                        os.environ["LLM_MODEL"] = "openai/gpt-4"
                logger.info(f"环境变量设置完成（本地大模型）- LLM_MODEL={os.environ.get('LLM_MODEL')}, OPENAI_BASE_URL={os.environ.get('OPENAI_BASE_URL')}")
            elif has_qwen:
                # 使用千问作为默认配置（确保 Cognee 初始化时有 LLM 配置）
                api_key = settings.QWEN_API_KEY or settings.QIANWEN_API_KEY
                api_base = settings.QWEN_API_BASE or settings.QIANWEN_API_BASE or "https://dashscope.aliyuncs.com"
                model = settings.QWEN_MODEL or "qwen-turbo"
                
                base_url = api_base.rstrip('/')
                if "/compatible-mode/v1" not in base_url:
                    if "/compatible-mode" not in base_url:
                        base_url = f"{base_url}/compatible-mode/v1"
                    else:
                        if not base_url.endswith("/v1"):
                            base_url = f"{base_url}/v1"
                
                os.environ["LLM_API_KEY"] = api_key
                os.environ["OPENAI_API_KEY"] = api_key
                os.environ["LLM_PROVIDER"] = "openai"
                os.environ["OPENAI_BASE_URL"] = base_url
                os.environ["LLM_ENDPOINT"] = base_url
                os.environ["LLM_MODEL"] = f"openai/{model}"
                logger.info(f"环境变量设置完成（千问默认配置）- LLM_MODEL={os.environ.get('LLM_MODEL')}, OPENAI_BASE_URL={os.environ.get('OPENAI_BASE_URL')}")
            else:
                logger.warning("LOCAL_LLM_API_KEY 和 QWEN_API_KEY 均未设置，Cognee 可能无法正常工作")
            
            # 设置 Neo4j 图数据库环境变量（在导入 Cognee 之前）
            # 根据 Cognee 官方文档，这些环境变量必须在导入前设置
            # 注意：使用自托管 Neo4j 时，需要禁用多用户访问控制（ENABLE_BACKEND_ACCESS_CONTROL=false）
            # 因为 neo4j_aura_dev 需要 Neo4j Aura 云服务的认证信息
            os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
            os.environ["GRAPH_DATABASE_PROVIDER"] = "neo4j"
            os.environ["GRAPH_DATABASE_URL"] = settings.NEO4J_URI
            os.environ["GRAPH_DATABASE_NAME"] = "neo4j"
            os.environ["GRAPH_DATABASE_USERNAME"] = settings.NEO4J_USER
            os.environ["GRAPH_DATABASE_PASSWORD"] = settings.NEO4J_PASSWORD
            # 同时设置 NEO4J_* 环境变量（Cognee 可能也需要这些）
            os.environ["NEO4J_URI"] = settings.NEO4J_URI
            os.environ["NEO4J_USERNAME"] = settings.NEO4J_USER
            os.environ["NEO4J_PASSWORD"] = settings.NEO4J_PASSWORD
            # 设置 COGNEE_* 环境变量（Cognee 可能也需要这些）
            os.environ["COGNEE_GRAPH_DB_PROVIDER"] = "neo4j"
            os.environ["COGNEE_GRAPH_DB_NAME"] = "neo4j"
            
            # 设置 Cognee 数据库路径到可写目录（避免在只读的包目录中创建数据库）
            # Cognee 默认会在包目录中创建 .cognee_system，但 Docker 容器中包目录是只读的
            cognee_db_path = "/app/.cognee_system"
            os.environ["COGNEE_DATABASE_PATH"] = cognee_db_path
            # 确保目录存在
            import os
            os.makedirs(cognee_db_path, exist_ok=True)
            logger.info(f"Cognee 数据库路径已设置: {cognee_db_path}")
            
            logger.info(
                f"Neo4j 环境变量已设置: "
                f"GRAPH_DATABASE_PROVIDER={os.environ.get('GRAPH_DATABASE_PROVIDER')}, "
                f"GRAPH_DATABASE_URL={os.environ.get('GRAPH_DATABASE_URL')}, "
                f"NEO4J_USERNAME={os.environ.get('NEO4J_USERNAME')}"
            )
            
            # 设置 Embedding 环境变量（在导入 Cognee 之前）
            # 确保 embedding_endpoint 被正确设置，避免 None 值导致错误
            if hasattr(settings, 'OLLAMA_BASE_URL') and settings.OLLAMA_BASE_URL:
                ollama_base_url = settings.OLLAMA_BASE_URL.rstrip('/')
                if hasattr(settings, 'OLLAMA_EMBEDDING_MODEL') and settings.OLLAMA_EMBEDDING_MODEL:
                    embedding_model = settings.OLLAMA_EMBEDDING_MODEL
                    os.environ["EMBEDDING_PROVIDER"] = "ollama"
                    os.environ["EMBEDDING_MODEL"] = f"ollama/{embedding_model}"
                    os.environ["OLLAMA_BASE_URL"] = ollama_base_url
                    # 关键：设置 embedding_endpoint（OllamaEmbeddingEngine 需要这个）
                    embedding_endpoint = f"{ollama_base_url}/api/embeddings"
                    os.environ["EMBEDDING_ENDPOINT"] = embedding_endpoint
                    os.environ["EMBEDDING_DIMENSIONS"] = "1024"
                    
                    # 设置 tokeniser
                    tokeniser_model = embedding_model
                    if ':' in tokeniser_model:
                        tokeniser_model = tokeniser_model.split(':')[0]
                    if '/' in tokeniser_model:
                        tokeniser_model = tokeniser_model.split('/')[-1]
                    if 'bge' in tokeniser_model.lower():
                        os.environ["HUGGINGFACE_TOKENIZER"] = f"BAAI/{tokeniser_model}"
                    else:
                        os.environ["HUGGINGFACE_TOKENIZER"] = tokeniser_model
                    
                    logger.info(
                        f"Embedding 环境变量已设置: "
                        f"EMBEDDING_PROVIDER={os.environ.get('EMBEDDING_PROVIDER')}, "
                        f"EMBEDDING_ENDPOINT={embedding_endpoint}"
                    )
            
            # ========== 4. 配置向量数据库（Milvus）==========
            # 配置 Cognee 使用 Milvus 而不是默认的 LanceDB
            if hasattr(settings, 'ENABLE_MILVUS') and settings.ENABLE_MILVUS:
                if hasattr(settings, 'MILVUS_HOST') and settings.MILVUS_HOST:
                    # 设置 Milvus 环境变量（必须在导入 Cognee 之前！）
                    milvus_url = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
                    os.environ["VECTOR_DB_PROVIDER"] = "milvus"
                    os.environ["VECTOR_DB_URL"] = milvus_url
                    
                    # 构建认证信息（用户名:密码格式）
                    if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                        milvus_key = f"{settings.MILVUS_USERNAME}"
                        if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                            milvus_key = f"{settings.MILVUS_USERNAME}:{settings.MILVUS_PASSWORD}"
                        os.environ["VECTOR_DB_KEY"] = milvus_key
                    elif hasattr(settings, 'MILVUS_TOKEN') and settings.MILVUS_TOKEN:
                        os.environ["VECTOR_DB_KEY"] = settings.MILVUS_TOKEN
                    
                    logger.info(
                        f"Cognee Milvus 配置: "
                        f"VECTOR_DB_PROVIDER=milvus, "
                        f"VECTOR_DB_URL={milvus_url}, "
                        f"VECTOR_DB_KEY={'已设置' if os.environ.get('VECTOR_DB_KEY') else '未设置'}"
                    )
                else:
                    logger.warning("MILVUS_HOST 未设置，Cognee 将使用默认的 LanceDB")
            else:
                logger.info("ENABLE_MILVUS 未启用，Cognee 将使用默认的 LanceDB")
            
            # 导入并注册 Milvus 适配器（必须在导入 Cognee 之前）
            try:
                from community.adapters.vector.milvus import register  # noqa: F401
                logger.info("✅ Milvus 适配器已注册")
            except ImportError as e:
                logger.warning(f"⚠️ 无法导入 Milvus 适配器: {e}，Cognee 将使用默认向量数据库")
            
            # 现在导入 Cognee（此时所有环境变量已设置）
            logger.info("开始导入 cognee 模块...")
            import cognee
            logger.info("cognee 模块导入成功")
            
            # 可选：使用 config API 作为备用配置（确保 Cognee 使用 Milvus）
            if hasattr(settings, 'ENABLE_MILVUS') and settings.ENABLE_MILVUS:
                if hasattr(settings, 'MILVUS_HOST') and settings.MILVUS_HOST:
                    try:
                        milvus_url = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
                        milvus_key = ""
                        if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                            milvus_key = f"{settings.MILVUS_USERNAME}"
                            if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                                milvus_key = f"{settings.MILVUS_USERNAME}:{settings.MILVUS_PASSWORD}"
                        elif hasattr(settings, 'MILVUS_TOKEN') and settings.MILVUS_TOKEN:
                            milvus_key = settings.MILVUS_TOKEN
                        
                        cognee.config.set_vector_db_config({
                            "vector_db_provider": "milvus",
                            "vector_db_url": milvus_url,
                            "vector_db_key": milvus_key
                        })
                        logger.info("✅ 已通过 config API 设置 Cognee Milvus 配置")
                    except Exception as e:
                        logger.warning(f"⚠️ 通过 config API 设置 Milvus 配置失败: {e}")
            
            # ========== 应用 Monkey Patch 修复 Ollama 响应格式问题 ==========
            # Ollama API 返回格式: {'embedding': [...]}
            # Cognee 期望格式: {'embeddings': [...]} 或 {'data': [{'embedding': [...]}]}
            # 需要修复 OllamaEmbeddingEngine._get_embedding 方法
            try:
                from cognee.infrastructure.databases.vector.embeddings.OllamaEmbeddingEngine import OllamaEmbeddingEngine
                import types
                
                # 创建修复后的方法
                async def fixed_get_embedding(self, prompt: str):
                    """修复后的 _get_embedding 方法，支持 Ollama 标准响应格式"""
                    import aiohttp
                    import os
                    from cognee.shared.utils import create_secure_ssl_context
                    from cognee.shared.rate_limiting import embedding_rate_limiter_context_manager
                    
                    # 修复：从模型名称中移除 "ollama/" 前缀（Ollama API 不接受这个前缀）
                    model_name = self.model
                    if model_name.startswith("ollama/"):
                        model_name = model_name[7:]  # 移除 "ollama/" 前缀
                    
                    payload = {"model": model_name, "prompt": prompt, "input": prompt}
                    
                    headers = {}
                    api_key = os.getenv("LLM_API_KEY")
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    
                    ssl_context = create_secure_ssl_context()
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with embedding_rate_limiter_context_manager():
                            async with session.post(
                                self.endpoint, json=payload, headers=headers, timeout=60.0
                            ) as response:
                                data = await response.json()
                                
                                # 检查是否有错误
                                if "error" in data:
                                    raise ValueError(f"Ollama API error: {data['error']}")
                                
                                # 修复：支持 Ollama 的标准响应格式 {'embedding': [...]}
                                if "embedding" in data:
                                    return data["embedding"]
                                elif "embeddings" in data:
                                    return data["embeddings"][0]
                                elif "data" in data:
                                    return data["data"][0]["embedding"]
                                else:
                                    raise ValueError(f"Unexpected response format: {list(data.keys())}")
                
                # 应用 monkey patch
                OllamaEmbeddingEngine._get_embedding = fixed_get_embedding
                logger.info("✅ 已应用 OllamaEmbeddingEngine monkey patch（支持 Ollama 标准响应格式）")
            except Exception as e:
                logger.warning(f"⚠️  应用 OllamaEmbeddingEngine monkey patch 失败: {e}，将继续使用原始方法")
            
            _cognee = cognee
            logger.info("Cognee 客户端初始化成功")
        except ImportError as e:
            logger.error(f"Cognee 未安装，请运行: pip install cognee, 错误: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"get_cognee() 执行失败: {e}", exc_info=True)
            raise
    else:
        logger.info("get_cognee() 返回已存在的实例")
    return _cognee


class CogneeService:
    """
    Cognee 服务
    
    使用 Cognee 为章节内容构建知识图谱
    """
    
    def __init__(self):
        logger.info("CogneeService.__init__() 开始执行")
        try:
            logger.info("正在调用 get_cognee()...")
            self.cognee = get_cognee()
            logger.info(f"get_cognee() 成功，cognee 类型: {type(self.cognee)}")
            self._initialized = False
            logger.info("CogneeService.__init__() 完成")
        except Exception as e:
            logger.error(f"CogneeService.__init__() 失败: {e}", exc_info=True)
            raise
    
    async def _set_cognee_llm_env(self, provider: str = "qianwen"):
        """
        根据 provider 设置 Cognee LLM 环境变量和配置
        
        Args:
            provider: LLM提供商 (qianwen, deepseek, kimi, glm)
        """
        import os
        
        if provider == "qianwen":
            api_key = settings.QWEN_API_KEY or settings.QIANWEN_API_KEY
            api_base = settings.QWEN_API_BASE or settings.QIANWEN_API_BASE
            model = settings.QWEN_MODEL
            
            # 千问使用 OpenAI 兼容接口
            base_url = api_base.rstrip('/')
            if "/compatible-mode/v1" not in base_url:
                if "/compatible-mode" not in base_url:
                    base_url = f"{base_url}/compatible-mode/v1"
                else:
                    if not base_url.endswith("/v1"):
                        base_url = f"{base_url}/v1"
        elif provider == "deepseek":
            api_key = settings.DEEPSEEK_API_KEY
            api_base = settings.DEEPSEEK_API_BASE
            model = settings.DEEPSEEK_MODEL
            
            base_url = api_base.rstrip('/')
            if not base_url.endswith("/v1"):
                if "/v1" not in base_url:
                    base_url = f"{base_url}/v1"
        elif provider == "kimi":
            api_key = settings.KIMI_API_KEY
            api_base = settings.KIMI_API_BASE
            model = settings.KIMI_MODEL
            
            base_url = api_base.rstrip('/')
            if not base_url.endswith("/v1"):
                if "/v1" not in base_url:
                    base_url = f"{base_url}/v1"
        elif provider == "glm":
            api_key = settings.GLM_API_KEY
            api_base = settings.GLM_API_BASE
            model = settings.GLM_MODEL
            
            base_url = api_base.rstrip('/')
            if not base_url.endswith("/v1"):
                if "/v1" not in base_url:
                    base_url = f"{base_url}/v1"
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        if not api_key:
            raise ValueError(f"{provider} API key not configured")
        if not model:
            raise ValueError(f"{provider} model not configured")
        
        # 设置 Cognee LLM 环境变量
        os.environ["LLM_API_KEY"] = api_key
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ["LLM_ENDPOINT"] = base_url
        litellm_model = f"openai/{model}"
        os.environ["LLM_MODEL"] = litellm_model
        
        # 清空 Cognee 的配置缓存并重新设置配置
        try:
            from cognee.infrastructure.llm import get_llm_config
            from cognee.modules.settings.save_llm_config import save_llm_config, LLMConfig
            
            # 清空缓存（关键：Cognee 使用 @lru_cache）
            get_llm_config.cache_clear()
            logger.debug(f"✅ 已清除 get_llm_config 缓存 (provider={provider})")
            
            # 重新设置配置
            llm_config_obj = LLMConfig(
                provider="openai",
                model=litellm_model,
                api_key=api_key
            )
            await save_llm_config(llm_config_obj)
            
            # 手动设置 llm_endpoint（save_llm_config 不会设置）
            fresh_config = get_llm_config()
            fresh_config.llm_endpoint = base_url
            fresh_config.llm_api_key = api_key  # 确保设置
            fresh_config.llm_model = litellm_model  # 确保设置
            
            logger.debug(
                f"Cognee LLM 配置已设置 (provider={provider}): "
                f"llm_model={fresh_config.llm_model}, "
                f"llm_endpoint={fresh_config.llm_endpoint}, "
                f"llm_api_key={'SET' if fresh_config.llm_api_key else 'NOT SET'}"
            )
        except Exception as e:
            logger.warning(f"⚠️ 清空缓存或重新设置配置失败 (provider={provider}): {e}")
            # 继续使用环境变量，应该也能工作
            logger.debug(
                f"Cognee LLM 环境变量已设置 (provider={provider}): "
                f"LLM_API_KEY={'SET' if api_key else 'NOT SET'}, "
                f"OPENAI_BASE_URL={base_url}, "
                f"LLM_MODEL={litellm_model}"
            )
    
    async def initialize(self):
        """初始化 Cognee（配置 Neo4j，使用默认的 LanceDB 作为向量数据库）"""
        if self._initialized:
            return
        
        try:
            import os
            
            # ========== 1. 配置 LLM ==========
            # Cognee 需要的环境变量：
            # - LLM_API_KEY: LLM API key
            # - LLM_PROVIDER: LLM provider (如 "openai")
            # - LLM_MODEL: LLM model (格式: "openai/model_name")
            # - LLM_ENDPOINT: LLM endpoint (可选，如果使用自定义 endpoint)
            # - OPENAI_API_KEY: 如果使用 OpenAI provider，也需要这个
            # - OPENAI_BASE_URL: 如果使用自定义 endpoint，需要这个
            if hasattr(settings, 'LOCAL_LLM_API_KEY') and settings.LOCAL_LLM_API_KEY:
                # 强制设置，覆盖已存在的值（确保使用最新配置）
                os.environ["LLM_API_KEY"] = settings.LOCAL_LLM_API_KEY
                os.environ["OPENAI_API_KEY"] = settings.LOCAL_LLM_API_KEY
                
                # 设置 LLM provider（必须）
                os.environ["LLM_PROVIDER"] = "openai"
                
                # 注意：LLM_MODEL 会在 endpoint 设置时一起设置，这里不需要单独设置
                
                # 设置 LLM endpoint（如果使用自定义 endpoint）
                if hasattr(settings, 'LOCAL_LLM_API_BASE_URL') and settings.LOCAL_LLM_API_BASE_URL:
                    local_base_url = settings.LOCAL_LLM_API_BASE_URL.rstrip('/')
                    # 确保 URL 包含 /v1
                    if not local_base_url.endswith('/v1'):
                        if '/v1' not in local_base_url:
                            local_base_url = f"{local_base_url}/v1"
                    os.environ["OPENAI_BASE_URL"] = local_base_url
                    # Cognee 也可能需要 LLM_ENDPOINT
                    os.environ["LLM_ENDPOINT"] = local_base_url
            
            # ========== 2. 配置 Neo4j 图数据库 ==========
            # 根据 Cognee 官方文档配置 Neo4j
            # 参考: https://docs.cognee.ai/setup-configuration/graph-databases/neo4j
            
            # 注意：使用自托管 Neo4j 时，需要禁用多用户访问控制（ENABLE_BACKEND_ACCESS_CONTROL=false）
            # 因为 neo4j_aura_dev 需要 Neo4j Aura 云服务的认证信息
            if not os.environ.get("ENABLE_BACKEND_ACCESS_CONTROL"):
                os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
            
            # 图数据库提供商
            if not os.environ.get("GRAPH_DATABASE_PROVIDER"):
                os.environ["GRAPH_DATABASE_PROVIDER"] = "neo4j"
            
            # 图数据库 URL（格式：bolt://host:port）
            if not os.environ.get("GRAPH_DATABASE_URL"):
                neo4j_uri = settings.NEO4J_URI
                os.environ["GRAPH_DATABASE_URL"] = neo4j_uri
            
            # 图数据库名称（Neo4j 默认数据库名）
            if not os.environ.get("GRAPH_DATABASE_NAME"):
                os.environ["GRAPH_DATABASE_NAME"] = "neo4j"
            
            # 图数据库用户名
            if not os.environ.get("GRAPH_DATABASE_USERNAME"):
                os.environ["GRAPH_DATABASE_USERNAME"] = settings.NEO4J_USER
            
            # 图数据库密码
            if not os.environ.get("GRAPH_DATABASE_PASSWORD"):
                os.environ["GRAPH_DATABASE_PASSWORD"] = settings.NEO4J_PASSWORD
            
            logger.info(
                f"Neo4j 配置: "
                f"URL={os.environ.get('GRAPH_DATABASE_URL')}, "
                f"USERNAME={os.environ.get('GRAPH_DATABASE_USERNAME')}, "
                f"NAME={os.environ.get('GRAPH_DATABASE_NAME')}"
            )
            
            # ========== 3. 配置 Embedding 模型 ==========
            # Cognee 默认使用 openai/text-embedding-3-large，但我们的自定义端点没有这个模型
            # 配置使用 Ollama 的 embedding 模型
            if hasattr(settings, 'OLLAMA_BASE_URL') and settings.OLLAMA_BASE_URL:
                # 设置 Ollama embedding 配置
                # Cognee 使用 litellm，可以通过环境变量配置 embedding
                ollama_base_url = settings.OLLAMA_BASE_URL.rstrip('/')
                if hasattr(settings, 'OLLAMA_EMBEDDING_MODEL') and settings.OLLAMA_EMBEDDING_MODEL:
                    # 对于 Ollama，litellm 使用 "ollama/model_name" 格式
                    # 保留完整的模型名称（如 "quentinz/bge-large-zh-v1.5:latest"）
                    embedding_model = settings.OLLAMA_EMBEDDING_MODEL
                    
                    # 设置 embedding provider
                    os.environ["EMBEDDING_PROVIDER"] = "ollama"
                    
                    # 设置 embedding model（格式：ollama/model_name）
                    os.environ["EMBEDDING_MODEL"] = f"ollama/{embedding_model}"
                    
                    # 设置 Ollama base URL
                    os.environ["OLLAMA_BASE_URL"] = ollama_base_url
                    
                    # 设置 embedding endpoint（OllamaEmbeddingEngine 需要完整的 endpoint URL）
                    # 格式：http://host:port/api/embeddings
                    embedding_endpoint = f"{ollama_base_url}/api/embeddings"
                    os.environ["EMBEDDING_ENDPOINT"] = embedding_endpoint
                    
                    # 设置 embedding dimensions（bge-large-zh-v1.5 的维度是 1024）
                    # 这是必需的，否则 Cognee 无法正确初始化向量存储
                    os.environ["EMBEDDING_DIMENSIONS"] = "1024"
                    
                    # 设置 HuggingFace tokeniser（用于 token 计数）
                    # 对于 Ollama 模型，需要指定 tokeniser 以便正确计算 token 数量
                    # 使用模型名称（去掉 provider 前缀和版本标签）作为 tokeniser
                    tokeniser_model = embedding_model
                    if ':' in tokeniser_model:
                        tokeniser_model = tokeniser_model.split(':')[0]  # 去掉 :latest 等标签
                    if '/' in tokeniser_model:
                        tokeniser_model = tokeniser_model.split('/')[-1]  # 提取模型名
                    # 对于 bge-large-zh-v1.5，使用 BAAI/bge-large-zh-v1.5 作为 tokeniser
                    # 如果模型名包含 bge，使用 BAAI 前缀
                    if 'bge' in tokeniser_model.lower():
                        os.environ["HUGGINGFACE_TOKENIZER"] = f"BAAI/{tokeniser_model}"
                    else:
                        os.environ["HUGGINGFACE_TOKENIZER"] = tokeniser_model
                    
                    logger.info(
                        f"Cognee Embedding 配置: "
                        f"provider=ollama, model=ollama/{embedding_model}, "
                        f"endpoint={embedding_endpoint}, "
                        f"dimensions=1024, tokeniser={os.environ.get('HUGGINGFACE_TOKENIZER')}"
                    )
            
            # 向量数据库配置已在上面完成（在导入 Cognee 之前）
            # 如果配置了 Milvus，Cognee 将使用 Milvus；否则使用默认的 LanceDB
            
            self._initialized = True
            vector_db_info = "Milvus" if (hasattr(settings, 'ENABLE_MILVUS') and settings.ENABLE_MILVUS and hasattr(settings, 'MILVUS_HOST') and settings.MILVUS_HOST) else "LanceDB (默认)"
            logger.info(
                f"Cognee 初始化完成 - "
                f"图数据库: Neo4j ({settings.NEO4J_URI}), "
                f"向量数据库: {vector_db_info}"
            )
        except Exception as e:
            logger.error(f"Cognee 初始化失败: {e}")
            raise
    
    async def _generate_section_template(
        self,
        section_content: str,
        section_title: str,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        temperature: float = 0.3,
        provider: str = "qianwen"
    ) -> Dict[str, Any]:
        """
        为单个章节生成模板
        
        Args:
            section_content: 章节内容
            section_title: 章节标题
            system_prompt: 自定义 System Prompt（可选）
            user_prompt_template: 自定义 User Prompt 模板（可选，支持 {section_title} 和 {section_content} 占位符）
            temperature: LLM 温度参数
            
        Returns:
            模板配置（entity_types, edge_types, edge_type_map）
        """
        from app.services.template_generation_service import TemplateGenerationService
        from app.core.llm_client import get_llm_client
        import json
        import re
        
        logger.info(f"为章节 '{section_title}' 生成模板")
        
        # 使用自定义或默认 System Prompt
        default_system_prompt = "你是一个专业的知识图谱模板生成专家，擅长从章节内容中提取实体和关系结构，生成规范的模板配置。"
        final_system_prompt = system_prompt or default_system_prompt
        
        # 使用自定义或默认 User Prompt 模板
        default_user_prompt_template = """你是一个知识图谱模板生成专家。请分析以下章节内容，生成适合的实体和关系模板配置。

章节标题：{section_title}

章节内容：
{section_content}

请根据章节内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别章节中的核心实体
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么（例如："角色实体，代表系统中的各种角色和岗位"）
     * **fields**：字段定义（字段类型、是否必需、描述）
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么（例如："审批关系，表示一个实体对另一个实体的审批行为"）
     * **fields**：字段定义
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, source_node_uuid, target_node_uuid, name, fact, attributes

3. **关系映射（edge_type_map）**：
   - 定义哪些实体之间可以使用哪些关系
   - 格式：{{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}

返回标准JSON格式：
{{
  "entity_types": {{
    "EntityName": {{
      "description": "实体类型的描述",
      "fields": {{
        "field_name": {{
          "type": "str|Optional[str]|int|Optional[int]|bool|Optional[bool]",
          "required": true|false,
          "description": "字段描述"
        }}
      }}
    }}
  }},
  "edge_types": {{
    "EdgeName": {{
      "description": "关系类型的描述",
      "fields": {{
        "field_name": {{
          "type": "str|Optional[str]|int|Optional[int]|bool|Optional[bool]",
          "required": true|false,
          "description": "字段描述"
        }}
      }}
    }}
  }},
  "edge_type_map": {{
    "SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]
  }}
}}

只返回JSON，不要其他内容。"""
        
        final_user_prompt_template = user_prompt_template or default_user_prompt_template
        
        # 替换占位符
        user_prompt = final_user_prompt_template.replace("{section_title}", section_title)
        user_prompt = user_prompt.replace("{section_content}", section_content[:10000])  # 限制长度
        
        llm_client = get_llm_client()
        response = await llm_client.chat(
            provider,
            [
                {
                    "role": "system",
                    "content": final_system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=temperature,
            use_thinking=False
        )
        
        # 解析JSON响应
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                template_config = json.loads(json_match.group())
            else:
                template_config = json.loads(response)
            
            # 后处理：移除保留字段
            template_config = TemplateGenerationService._remove_reserved_fields(template_config)
            
            logger.info(f"章节 '{section_title}' 模板生成成功：{len(template_config.get('entity_types', {}))} 个实体类型，{len(template_config.get('edge_types', {}))} 个关系类型")
            return template_config
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM响应失败: {e}\n响应内容: {response[:500]}")
            # 返回空模板，让 Cognee 使用默认行为
            return {"entity_types": {}, "edge_types": {}, "edge_type_map": {}}
    
    def _template_to_custom_prompt(
        self,
        template_config: Dict[str, Any]
    ) -> str:
        """
        将模板配置转换为 Cognee 的 custom_prompt
        
        Args:
            template_config: 模板配置（entity_types, edge_types, edge_type_map）
            
        Returns:
            custom_prompt 字符串
        """
        entity_types = template_config.get("entity_types", {})
        edge_types = template_config.get("edge_types", {})
        edge_type_map = template_config.get("edge_type_map", {})
        
        # 构建实体类型描述
        entity_types_desc = []
        for entity_name, entity_def in entity_types.items():
            fields_desc = []
            entity_description = ""
            
            if isinstance(entity_def, dict):
                # 获取顶层 description
                entity_description = entity_def.get("description", "")
                
                # 获取字段描述
                if "fields" in entity_def:
                    for field_name, field_def in entity_def["fields"].items():
                        field_type = field_def.get("type", "str")
                        required = field_def.get("required", False)
                        description = field_def.get("description", "")
                        fields_desc.append(f"    - {field_name} ({field_type}, {'必需' if required else '可选'}): {description}")
            
            # 构建实体描述
            entity_desc = f"  - {entity_name}"
            if entity_description:
                entity_desc += f"：{entity_description}"
            if fields_desc:
                entity_desc += "\n" + "\n".join(fields_desc)
            entity_types_desc.append(entity_desc)
        
        # 构建关系类型描述
        edge_types_desc = []
        for edge_name, edge_def in edge_types.items():
            fields_desc = []
            edge_description = ""
            
            if isinstance(edge_def, dict):
                # 获取顶层 description
                edge_description = edge_def.get("description", "")
                
                # 获取字段描述
                if "fields" in edge_def:
                    for field_name, field_def in edge_def["fields"].items():
                        field_type = field_def.get("type", "str")
                        required = field_def.get("required", False)
                        description = field_def.get("description", "")
                        fields_desc.append(f"    - {field_name} ({field_type}, {'必需' if required else '可选'}): {description}")
            
            # 构建关系描述
            edge_desc = f"  - {edge_name}"
            if edge_description:
                edge_desc += f"：{edge_description}"
            if fields_desc:
                edge_desc += "\n" + "\n".join(fields_desc)
            edge_types_desc.append(edge_desc)
        
        # 构建关系映射描述
        edge_map_desc = []
        for key, values in edge_type_map.items():
            if isinstance(values, list):
                edge_map_desc.append(f"  - {key}: {', '.join(values)}")
            else:
                edge_map_desc.append(f"  - {key}: {values}")
        
        # 构建完整的 custom_prompt
        custom_prompt = f"""请根据以下实体和关系类型定义，从文本中提取知识图谱：

**实体类型定义**：
{chr(10).join(entity_types_desc) if entity_types_desc else "  （无预定义实体类型，请根据内容自由识别）"}

**关系类型定义**：
{chr(10).join(edge_types_desc) if edge_types_desc else "  （无预定义关系类型，请根据内容自由识别）"}

**关系映射规则**：
{chr(10).join(edge_map_desc) if edge_map_desc else "  （无预定义关系映射，请根据内容自由识别）"}

**提取要求**：
1. 严格按照上述实体类型和关系类型定义进行提取
2. 实体必须符合定义的实体类型
3. 关系必须符合定义的关系类型和关系映射规则
4. 如果文本中没有符合定义的实体或关系，不要强制提取
5. 确保提取的实体和关系准确反映文本内容

请开始提取知识图谱。"""
        
        return custom_prompt
    
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算文本的 token 数（中文通常 1 token ≈ 2 字符，英文 1 token ≈ 4 字符）"""
        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        other_chars = len(text) - chinese_chars
        return (chinese_chars // 2) + (other_chars // 4)
    
    @staticmethod
    def _get_max_tokens_per_batch(provider: str) -> int:
        """获取不同 provider 的每批最大 tokens"""
        if provider == "local":
            return 20000  # 保守估计，留出足够空间
        else:
            return 60000  # 其他模型通常有更大的上下文窗口
    
    def _group_sections_by_token_limit(
        self,
        section_texts: List[str],
        section_metadata: List[Dict[str, Any]],
        provider: str
    ) -> List[List[Dict[str, Any]]]:
        """
        将章节按token限制分组
        
        Args:
            section_texts: 章节内容列表
            section_metadata: 章节元数据列表
            provider: LLM提供商
            
        Returns:
            分组后的章节列表，每个元素是一个批次
        """
        max_tokens_per_batch = self._get_max_tokens_per_batch(provider)
        batches = []
        current_batch = []
        current_tokens = 0
        
        for i, (section_text, meta) in enumerate(zip(section_texts, section_metadata)):
            # 估算章节内容的token数（包括标题）
            section_content_with_title = f"## {meta['title']}\n{section_text}"
            section_tokens = self._estimate_tokens(section_content_with_title)
            
            # 如果当前批次加上新章节会超限，且当前批次不为空，开始新批次
            if current_tokens + section_tokens > max_tokens_per_batch and current_batch:
                batches.append(current_batch)
                current_batch = [{"index": i, "text": section_text, "meta": meta}]
                current_tokens = section_tokens
            else:
                current_batch.append({"index": i, "text": section_text, "meta": meta})
                current_tokens += section_tokens
        
        # 添加最后一个批次
        if current_batch:
            batches.append(current_batch)
        
        logger.info(f"章节分组完成：共 {len(section_texts)} 个章节，分为 {len(batches)} 个批次")
        for i, batch in enumerate(batches):
            batch_tokens = sum(self._estimate_tokens(f"## {item['meta']['title']}\n{item['text']}") for item in batch)
            logger.info(f"  批次 {i+1}：章节 {batch[0]['index']+1}～{batch[-1]['index']+1}（共 {len(batch)} 个章节，约 {batch_tokens} tokens）")
        
        return batches
    
    async def _process_batch_template(
        self,
        batch: List[Dict[str, Any]],
        batch_index: int,
        system_prompt: Optional[str],
        user_prompt_template: Optional[str],
        temperature: float,
        semaphore: asyncio.Semaphore,
        provider: str = "qianwen"
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个批次的模板生成
        
        Args:
            batch: 批次章节列表
            batch_index: 批次索引（从1开始）
            system_prompt: System Prompt
            user_prompt_template: User Prompt 模板
            temperature: 温度参数
            semaphore: 并发控制信号量
            
        Returns:
            模板配置，如果失败返回 None
        """
        # 先定义 batch_title，避免在 except 块中引用未定义的变量
        batch_title = f"批次{batch_index}"
        
        async with semaphore:
            try:
                # 构建批次标题和内容
                start_idx = batch[0]['index']
                end_idx = batch[-1]['index']
                batch_title = f"批次{batch_index}：章节{start_idx+1}～{end_idx+1}"
                
                batch_content = "\n\n".join([
                    f"## {item['meta']['title']}\n{item['text']}"
                    for item in batch
                ])
                
                logger.info(f"开始处理 {batch_title}（共 {len(batch)} 个章节）")
                
                # 生成模板
                template_config = await self._generate_section_template(
                    section_content=batch_content,
                    section_title=batch_title,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template,
                    temperature=temperature,
                    provider=provider
                )
                
                logger.info(f"✅ {batch_title} 处理成功：{len(template_config.get('entity_types', {}))} 个实体类型")
                return template_config
                
            except Exception as e:
                logger.warning(f"⚠️ {batch_title} 处理失败: {e}，跳过", exc_info=True)
                return None
    
    async def _merge_batch_templates(
        self,
        batch_results: List[Dict[str, Any]],
        provider: str
    ) -> Dict[str, Any]:
        """
        合并多个批次的模板结果
        
        Args:
            batch_results: 批次模板结果列表
            provider: LLM提供商
            
        Returns:
            合并后的统一模板配置
        """
        if not batch_results:
            raise ValueError("没有可合并的批次结果")
        
        # 1. 简单合并（去重，后出现的覆盖先出现的）
        all_entity_types = {}
        all_edge_types = {}
        all_edge_maps = {}
        
        for batch_result in batch_results:
            all_entity_types.update(batch_result.get('entity_types', {}))
            all_edge_types.update(batch_result.get('edge_types', {}))
            all_edge_maps.update(batch_result.get('edge_type_map', {}))
        
        logger.info(f"简单合并完成：{len(all_entity_types)} 个实体类型，{len(all_edge_types)} 个关系类型")
        
        # 2. LLM统一格式（参考 template_generation_service.py）
        from app.core.llm_client import get_llm_client
        import json
        import re
        
        final_prompt = f"""基于以下所有分析结果，生成统一的模板配置：

实体类型汇总：
{json.dumps(all_entity_types, ensure_ascii=False, indent=2)[:5000]}

关系类型汇总：
{json.dumps(all_edge_types, ensure_ascii=False, indent=2)[:5000]}

关系映射汇总：
{json.dumps(all_edge_maps, ensure_ascii=False, indent=2)[:5000]}

请合并、去重、统一，生成最终的模板配置。确保：
1. 实体类型定义完整（包含字段类型、是否必需、描述）
   - 格式：{{"EntityName": {{"description": "实体类型描述", "fields": {{"field_name": {{"type": "str", "required": true, "description": "..."}}}}}}}}
2. 关系类型定义完整
   - 格式：{{"EdgeName": {{"description": "关系类型描述", "fields": {{"field_name": {{"type": "str", "required": false, "description": "..."}}}}}}}}
3. 关系映射准确
   - ⚠️ **格式要求**：必须是字典，key格式为 "SourceEntity -> TargetEntity"（注意中间有空格和箭头）
   - 示例：{{"Product -> Order": ["HAS_ORDER"], "User -> Product": ["OWNS", "USES"]}}
   - ❌ 错误格式：{{"Product": ["HAS_ORDER"]}} 或单个实体名称作为key
4. 返回标准JSON格式
5. ⚠️ **严禁使用保留字段**：
   - 实体保留字段：uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 关系保留字段：uuid, source_node_uuid, target_node_uuid, name, fact, attributes
   - 请使用替代字段名，如：entity_name, title, description, status 等

返回JSON格式：
{{
  "entity_types": {{"EntityName": {{"description": "...", "fields": {{...}}}}}},
  "edge_types": {{"EdgeName": {{"description": "...", "fields": {{...}}}}}},
  "edge_type_map": {{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}
}}

只返回JSON，不要其他内容。"""
        
        llm_client = get_llm_client()
        response = await llm_client.chat(
            provider,
            [
                {
                    "role": "system",
                    "content": "你是一个专业的知识图谱模板生成专家，擅长合并和统一多个模板配置。"
                },
                {
                    "role": "user",
                    "content": final_prompt
                }
            ],
            temperature=0.3
        )
        
        # 解析JSON响应
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                final_template = json.loads(json_match.group())
            else:
                final_template = json.loads(response)
            
            logger.info(f"✅ LLM统一格式完成：{len(final_template.get('entity_types', {}))} 个实体类型，{len(final_template.get('edge_types', {}))} 个关系类型")
            return final_template
            
        except json.JSONDecodeError as e:
            logger.error(f"解析合并后的模板 JSON 失败: {e}, 响应内容: {response[:500]}")
            # 如果LLM合并失败，返回简单合并的结果
            logger.warning("⚠️ LLM合并失败，使用简单合并结果")
            return {
                "entity_types": all_entity_types,
                "edge_types": all_edge_types,
                "edge_type_map": all_edge_maps
            }
    
    async def _process_batch_rules(
        self,
        batch: List[Dict[str, Any]],
        batch_index: int,
        document_name: str,
        system_prompt: Optional[str],
        user_prompt_template: Optional[str],
        semaphore: asyncio.Semaphore,
        provider: str = "qianwen"
    ) -> Optional[List[str]]:
        """
        处理单个批次的规则生成
        
        Args:
            batch: 批次章节列表
            batch_index: 批次索引（从1开始）
            document_name: 文档名称
            system_prompt: System Prompt
            user_prompt_template: User Prompt 模板
            semaphore: 并发控制信号量
            
        Returns:
            规则列表，如果失败返回 None
        """
        # 先定义 batch_title，避免在 except 块中引用未定义的变量
        batch_title = f"批次{batch_index}"
        
        async with semaphore:
            try:
                from app.utils.patch_add_rule_associations import SimpleRuleSet
                from cognee.infrastructure.llm import LLMGateway
                
                # 构建批次标题和内容
                start_idx = batch[0]['index']
                end_idx = batch[-1]['index']
                batch_title = f"批次{batch_index}：章节{start_idx+1}～{end_idx+1}"
                
                batch_content = "\n\n".join([
                    f"## {item['meta']['title']}\n{item['text']}"
                    for item in batch
                ])
                
                logger.info(f"开始处理 {batch_title}（共 {len(batch)} 个章节）")
                
                # 准备提示词
                if not system_prompt:
                    system_prompt = "你是一个专业的规则提取专家，擅长从文档内容中提取编码规则和最佳实践。"
                
                if not user_prompt_template:
                    user_prompt_template = """分析以下文档内容，提取编码规则和最佳实践。

文档名称：{document_name}

文档内容：
{document_content}

请从文档内容中提取编码规则和最佳实践，每条规则应该：
1. 清晰明确，具有可操作性
2. 基于文档中的实际内容
3. 适用于编码实践

返回规则列表，每条规则一行。"""
                
                # 替换占位符
                user_prompt = user_prompt_template.replace("{document_name}", document_name)
                user_prompt = user_prompt.replace("{document_content}", batch_content)
                
                # 注意：LLM 环境变量已在 get_cognee() 初始化时设置，这里不需要动态设置
                # 规则生成将使用初始化时设置的默认 LLM（千问）
                
                # 使用 Cognee 的 LLMGateway.acreate_structured_output（只使用 Cognee）
                from app.utils.patch_add_rule_associations import SimpleRuleSet
                from cognee.infrastructure.llm import LLMGateway
                
                # 调用 LLM 生成规则列表（使用 Cognee 的 structured output）
                simple_rule_list = await LLMGateway.acreate_structured_output(
                    text_input=user_prompt,
                    system_prompt=system_prompt,
                    response_model=SimpleRuleSet
                )
                
                # 提取规则文本（现在 rules 直接是字符串列表）
                rules = simple_rule_list.rules
                logger.info(f"✅ {batch_title} 处理成功：{len(rules)} 条规则")
                return rules
                
            except Exception as e:
                logger.warning(f"⚠️ {batch_title} 处理失败: {e}，跳过", exc_info=True)
                return None
    
    async def _merge_batch_rules(
        self,
        batch_rules: List[List[str]],
        document_name: str,
        system_prompt: Optional[str],
        provider: str
    ) -> List[str]:
        """
        合并多个批次的规则结果，使用LLM统一格式
        
        Args:
            batch_rules: 批次规则结果列表
            document_name: 文档名称
            system_prompt: System Prompt
            provider: LLM提供商
            
        Returns:
            合并后的统一规则列表
        """
        if not batch_rules:
            return []
        
        # 1. 简单合并（去重，基于规则文本内容）
        all_rules = []
        seen_rules = set()
        
        for batch_rule_list in batch_rules:
            if batch_rule_list:
                for rule in batch_rule_list:
                    # 去重：忽略大小写和首尾空格
                    rule_normalized = rule.strip().lower()
                    if rule_normalized and rule_normalized not in seen_rules:
                        seen_rules.add(rule_normalized)
                        all_rules.append(rule.strip())
        
        logger.info(f"简单合并完成：{len(all_rules)} 条规则（去重后）")
        
        # 2. LLM统一格式（使用结构化输出，与批次处理阶段一致）
        try:
            from app.utils.patch_add_rule_associations import SimpleRuleSet
            from cognee.infrastructure.llm import LLMGateway
            
            if not system_prompt:
                system_prompt = "你是一个专业的规则提取专家，擅长从文档内容中提取编码规则和最佳实践。"
            
            # 构建规则列表文本
            rules_text = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(all_rules)])
            
            merge_prompt = f"""基于以下规则列表，进行统一格式、去重和规范化：

文档名称：{document_name}

规则列表：
{rules_text}

请对规则列表进行：
1. 去重：合并相同或相似的规则
2. 规范化：统一格式和表述
3. 优化：确保每条规则清晰明确，具有可操作性

返回优化后的规则列表，每条规则一行。"""
            
            # 使用结构化输出（与批次处理阶段一致）
            simple_rule_list = await LLMGateway.acreate_structured_output(
                text_input=merge_prompt,
                system_prompt=system_prompt,
                response_model=SimpleRuleSet
            )
            
            # 提取规则文本（现在 rules 直接是字符串列表）
            final_rules = simple_rule_list.rules
            
            logger.info(f"✅ LLM统一格式完成：{len(final_rules)} 条规则")
            return final_rules if final_rules else all_rules  # 如果LLM解析失败，返回简单合并的结果
            
        except Exception as e:
            logger.warning(f"⚠️ LLM统一格式失败: {e}，使用简单合并结果", exc_info=True)
            return all_rules
    
    async def _generate_memify_rules_batch(
        self,
        section_texts: List[str],
        section_metadata: List[Dict[str, Any]],
        document_name: str,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        provider: str = "local",
        max_concurrent: int = 3
    ) -> List[str]:
        """
        批次生成 Memify 规则列表（支持长文档）
        
        Args:
            section_texts: 章节内容列表
            section_metadata: 章节元数据列表
            document_name: 文档名称
            system_prompt: System Prompt（可选）
            user_prompt_template: User Prompt 模板（可选）
            provider: LLM提供商
            max_concurrent: 最大并发数
            
        Returns:
            规则列表
        """
        if not section_texts or not section_metadata:
            logger.warning("章节列表为空，无法生成规则列表")
            return []
        
        # 1. 将章节分组
        batches = self._group_sections_by_token_limit(
            section_texts=section_texts,
            section_metadata=section_metadata,
            provider=provider
        )
        
        if not batches:
            logger.warning("章节分组失败，无法生成规则列表")
            return []
        
        # 2. 并行处理批次
        semaphore = asyncio.Semaphore(max_concurrent)
        
        batch_tasks = [
            self._process_batch_rules(
                batch=batch,
                batch_index=i+1,
                document_name=document_name,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
                semaphore=semaphore,
                provider=provider
            )
            for i, batch in enumerate(batches)
        ]
        
        batch_results = await asyncio.gather(*batch_tasks)
        
        # 3. 过滤掉失败的结果
        successful_results = [r for r in batch_results if r is not None]
        failed_count = len(batch_results) - len(successful_results)
        
        if failed_count > 0:
            logger.warning(f"⚠️ {failed_count} 个批次处理失败，已跳过")
        
        if not successful_results:
            logger.error("❌ 所有批次处理失败，无法生成规则列表")
            return []
        
        # 4. 合并规则（使用LLM统一格式）
        final_rules = await self._merge_batch_rules(
            batch_rules=successful_results,
            document_name=document_name,
            system_prompt=system_prompt,
            provider=provider
        )
        
        logger.info(f"✅ 规则列表生成完成：共 {len(final_rules)} 条规则（来自 {len(successful_results)} 个批次）")
        return final_rules
    
    async def _save_cognee_template_to_db(
        self,
        template_config: Dict[str, Any],
        upload_id: int,
        document_name: str,
        section_count: int,
        template_type: str,
        provider: str = "local"
    ) -> Optional[int]:
        """
        保存 Cognee 生成的章节级别模板到数据库
        
        Args:
            template_config: 模板配置（entity_types, edge_types, edge_type_map）
            upload_id: 文档上传ID
            document_name: 文档名称
            section_count: 章节数量
            template_type: 模板类型（方案1-统一模板 或 方案2-章节级别）
            provider: LLM 提供商
            
        Returns:
            模板ID（如果保存成功），否则返回 None
        """
        try:
            from app.core.mysql_client import SessionLocal
            from app.models.template import EntityEdgeTemplate
            from app.services.template_service import TemplateService
            
            # 验证模板配置
            logger.info(f"开始验证 Cognee 模板: upload_id={upload_id}, document_name={document_name}")
            is_valid, errors, warnings = TemplateService.validate_template(
                template_config.get("entity_types", {}),
                template_config.get("edge_types", {}),
                template_config.get("edge_type_map", {})
            )
            
            if not is_valid:
                logger.warning(f"Cognee 模板验证失败，不保存到数据库: {', '.join(errors)}")
                return None
            
            logger.info(f"Cognee 模板验证通过: 实体类型数={len(template_config.get('entity_types', {}))}, 关系类型数={len(template_config.get('edge_types', {}))}")
            
            # 生成模板名称
            doc_name = document_name.rsplit('.', 1)[0] if '.' in document_name else document_name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            template_name = f"Cognee-章节级别-{doc_name}-{timestamp}"
            
            # 生成模板描述
            description = f"基于文档'{document_name}'的章节内容自动生成的Cognee模板（{template_type}，共{section_count}个章节）"
            
            # 创建模板记录
            db = SessionLocal()
            try:
                template = EntityEdgeTemplate(
                    name=template_name,
                    description=description,
                    category="custom",
                    entity_types=template_config.get("entity_types", {}),
                    edge_types=template_config.get("edge_types", {}),
                    edge_type_map=template_config.get("edge_type_map", {}),
                    is_default=False,
                    is_system=False,
                    is_llm_generated=True,
                    source_document_id=upload_id,
                    analysis_mode=f"cognee_section_{template_type.lower().replace('-', '_')}",
                    llm_provider=provider,
                    generated_at=datetime.now(),
                    usage_count=0
                )
                
                db.add(template)
                db.commit()
                db.refresh(template)
                
                logger.info(
                    f"Cognee 章节级别模板已保存到数据库: "
                    f"template_id={template.id}, "
                    f"name={template_name}, "
                    f"实体类型数={len(template_config.get('entity_types', {}))}, "
                    f"关系类型数={len(template_config.get('edge_types', {}))}"
                )
                
                return template.id
            except Exception as e:
                db.rollback()
                logger.error(f"保存 Cognee 模板到数据库失败: {e}", exc_info=True)
                return None
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"保存 Cognee 模板到数据库时发生异常: {e}", exc_info=True)
            return None
    
    async def _save_memify_template_to_db(
        self,
        memify_config: Dict[str, Any],
        upload_id: int,
        document_name: str,
        dataset_name: str,
        memify_template_mode: str,
        provider: str = "local"
    ) -> Optional[int]:
        """
        保存 Memify 阶段的配置到数据库
        
        Args:
            memify_config: Memify配置（extraction和enrichment配置）
            upload_id: 文档上传ID
            document_name: 文档名称
            dataset_name: Cognee dataset名称
            memify_template_mode: 模板模式（llm_generate 或 json_config）
            provider: LLM 提供商
            
        Returns:
            模板ID（如果保存成功），否则返回 None
        """
        try:
            from app.core.mysql_client import SessionLocal
            from app.models.template import EntityEdgeTemplate
            
            # 生成模板名称
            doc_name = document_name.rsplit('.', 1)[0] if '.' in document_name else document_name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            mode_label = "LLM自动生成" if memify_template_mode == "llm_generate" else "JSON手动配置"
            template_name = f"Memify-{mode_label}-{doc_name}-{timestamp}"
            
            # 生成模板描述
            description = f"基于文档'{document_name}'的Memify阶段配置（{mode_label}，dataset: {dataset_name}）"
            
            # 将Memify配置转换为模板格式（复用EntityEdgeTemplate表结构）
            # entity_types存储extraction配置，edge_types存储enrichment配置，edge_type_map存储其他元数据
            entity_types = {"extraction": memify_config.get("extraction", {})} if memify_config.get("extraction") else {}
            edge_types = {"enrichment": memify_config.get("enrichment", {})} if memify_config.get("enrichment") else {}
            edge_type_map = {
                "memify_config": memify_config,
                "dataset_name": dataset_name,
                "template_mode": memify_template_mode
            }
            
            # 创建模板记录
            db = SessionLocal()
            try:
                template = EntityEdgeTemplate(
                    name=template_name,
                    description=description,
                    category="custom",
                    entity_types=entity_types,  # 存储extraction配置
                    edge_types=edge_types,  # 存储enrichment配置
                    edge_type_map=edge_type_map,  # 存储完整配置和元数据
                    is_default=False,
                    is_system=False,
                    is_llm_generated=(memify_template_mode == "llm_generate"),
                    source_document_id=upload_id,
                    analysis_mode="cognee_memify",  # 使用analysis_mode区分Memify模板
                    llm_provider=provider,
                    generated_at=datetime.now(),
                    usage_count=0
                )
                
                db.add(template)
                db.commit()
                db.refresh(template)
                
                logger.info(
                    f"Memify 模板已保存到数据库: "
                    f"template_id={template.id}, "
                    f"name={template_name}, "
                    f"mode={memify_template_mode}"
                )
                
                return template.id
            except Exception as e:
                db.rollback()
                logger.error(f"保存 Memify 模板到数据库失败: {e}", exc_info=True)
                return None
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"保存 Memify 模板到数据库时发生异常: {e}", exc_info=True)
            return None
    
    async def build_section_knowledge_graph(
        self,
        sections: List[Dict[str, Any]],
        group_id: str,
        max_concurrent: int = 3,
        provider: str = "local",
        temperature: float = 0.7,
        upload_id: Optional[int] = None,
        document_name: Optional[str] = None,
        doc_id: Optional[str] = None,  # 文档ID（用于更新节点属性）
        version: Optional[str] = None,  # 版本号（用于更新节点属性）
        # 模板配置（cognify阶段）
        cognify_template_mode: str = "llm_generate",  # "llm_generate" 或 "json_config"
        cognify_template_config_json: Optional[Dict[str, Any]] = None,  # JSON配置
        cognify_system_prompt: Optional[str] = None,  # 自定义 System Prompt
        cognify_user_prompt_template: Optional[str] = None,  # 自定义 User Prompt 模板
        cognify_template_type: str = "default",  # 模版类型
        # 模板配置（memify阶段）
        memify_template_mode: str = "llm_generate",  # "llm_generate" 或 "json_config"
        memify_template_config_json: Optional[Dict[str, Any]] = None,  # JSON配置
        memify_system_prompt: Optional[str] = None,  # 自定义 System Prompt（LLM生成模式时使用，用于enrichment任务）
        memify_user_prompt_template: Optional[str] = None,  # 自定义 User Prompt 模板（LLM生成模式时使用，用于enrichment任务）
        memify_template_type: str = "default",  # 模版类型（暂时只有 default）
        memify_rules: Optional[List[str]] = None  # LLM生成模式下，前端已生成的规则列表（可选）
    ) -> Dict[str, Any]:
        """
        为所有章节构建知识图谱（与 Graphiti 联动）
        
        ### Cognee 三层结构（与 Graphiti Episode 联动）
        
        1. **数据一致性（跨层标识）**
           - doc_id, group_id, version 从 Graphiti Episode 继承
           - 确保 Cognee 节点可以回溯到 Graphiti Episode
           - 实现跨系统的数据关联和回溯能力
        
        2. **Cognee 三层结构**
           - **DataSet（逻辑容器）**: dataset_name = f"knowledge_base_{group_id}_{timestamp}"
             * 不是Neo4j节点，是Cognee内部概念
             * 通过 dataset_name 属性关联所有相关节点
           
           - **TextDocument/DataNode（章节级）**: 对应我们的每个预处理chunk
             * 一个文档有 N 个 TextDocument/DataNode（N = sections数量）
             * 存储章节级的完整内容（用于上下文补充）
             * 属性：doc_id, group_id, version, upload_id（继承自Episode）
           
           - **DocumentChunk（分块级）**: Cognee自动分块（向量检索单元）
             * 每个 TextDocument/DataNode 自动切分为多个 DocumentChunk
             * 这是真正的向量检索单元（存储到 Milvus）
             * 属性：doc_id, group_id, version, upload_id（继承）
        
        3. **引用关系（联动机制）**
           - (TextDocument)-[:RELATES_TO]->(Episode): 建立 Cognee 到 Graphiti 的关联
           - (DocumentChunk)-[:is_part_of]->(TextDocument): Cognee 内部关系
           - 用于前端展示联动状态和跨层检索
        
        4. **完整回溯链路**
           Milvus向量 → DocumentChunk → TextDocument/DataNode → Graphiti Episode
           通过 doc_id 实现跨层关联和回溯
        
        ### 参数说明
        
        Args:
            sections: 章节列表（对应我们的预处理chunks），每个包含 title, content, uuid 等
            group_id: 文档组 ID（从 Graphiti Episode 继承）
            max_concurrent: 最大并发数
            provider: LLM 提供商
            upload_id: 文档上传ID（用于保存模板到数据库和属性继承）
            document_name: 文档名称（用于保存模板到数据库）
            cognify_template_mode: Cognify阶段模板模式（"llm_generate" 或 "json_config"）
            cognify_template_config_json: Cognify阶段JSON配置（json_config模式时使用）
            memify_template_mode: Memify阶段模板模式（"llm_generate" 或 "json_config"）
            memify_template_config_json: Memify阶段JSON配置（json_config模式时使用）
            
        Returns:
            Dict[str, Any]: 构建结果统计，包含：
                - cognee_structure: Cognee三层结构统计
                - graphiti_linkage: 与Graphiti的联动状态
                - traceability: 回溯链路信息
        """
        if not sections:
            logger.warning("章节列表为空，跳过知识图谱构建")
            return {"success": False, "reason": "no_sections"}
        
        await self.initialize()
        
        # 再次确保环境变量已设置（在调用 Cognee API 之前）
        # Cognee 可能在内部重新读取配置，所以需要再次设置
        import os
        if hasattr(settings, 'LOCAL_LLM_API_KEY') and settings.LOCAL_LLM_API_KEY:
            # 强制设置所有必要的环境变量
            os.environ["LLM_API_KEY"] = settings.LOCAL_LLM_API_KEY
            os.environ["OPENAI_API_KEY"] = settings.LOCAL_LLM_API_KEY
            
            # 设置 LLM provider 和 model
            os.environ["LLM_PROVIDER"] = "openai"
            if hasattr(settings, 'LOCAL_LLM_MODEL') and settings.LOCAL_LLM_MODEL:
                model_name = settings.LOCAL_LLM_MODEL
                # 修复：如果模型路径是完整路径（以 / 开头），保留完整路径
                # 设置成 openai//home/llm_deploy/Qwen3-32B（双斜杠）
                # 这样 litellm 去掉 openai/ 前缀后会得到正确的 /home/llm_deploy/Qwen3-32B
                if model_name.startswith('/'):
                    # 完整路径，保留原样，设置成 openai//path（双斜杠）
                    os.environ["LLM_MODEL"] = f"openai/{model_name}"
                elif '/' in model_name and not model_name.startswith('openai/'):
                    # 非完整路径但包含斜杠，只取最后一部分（这是原来的逻辑）
                    model_name = model_name.split('/')[-1]
                    os.environ["LLM_MODEL"] = f"openai/{model_name}"
                elif not model_name.startswith('openai/'):
                    # 只是模型名，直接使用
                    os.environ["LLM_MODEL"] = f"openai/{model_name}"
                else:
                    # 已经是 openai/ 格式，直接使用
                    os.environ["LLM_MODEL"] = model_name
            else:
                os.environ["LLM_MODEL"] = "openai/gpt-4"
            
            # 设置 endpoint
            if hasattr(settings, 'LOCAL_LLM_API_BASE_URL') and settings.LOCAL_LLM_API_BASE_URL:
                local_base_url = settings.LOCAL_LLM_API_BASE_URL.rstrip('/')
                if not local_base_url.endswith('/v1'):
                    if '/v1' not in local_base_url:
                        local_base_url = f"{local_base_url}/v1"
                os.environ["OPENAI_BASE_URL"] = local_base_url
                os.environ["LLM_ENDPOINT"] = local_base_url
            
            logger.debug(
                f"Cognee LLM 环境变量已设置: "
                f"LLM_API_KEY={'SET' if os.environ.get('LLM_API_KEY') else 'NOT SET'}, "
                f"LLM_PROVIDER={os.environ.get('LLM_PROVIDER')}, "
                f"LLM_MODEL={os.environ.get('LLM_MODEL')}, "
                f"LLM_ENDPOINT={os.environ.get('LLM_ENDPOINT')}"
            )
        
        # 获取阈值配置
        threshold = getattr(settings, 'COGNEE_SECTION_TEMPLATE_THRESHOLD', 5)
        section_count = len(sections)
        
        logger.info(f"开始使用 Cognee 为 {section_count} 个章节构建知识图谱（阈值: {threshold}）")
        
        # 准备数据库配置
        # 注意：Cognee 的 config 参数格式可能与我们的预期不同，传递字典可能导致参数不匹配
        # 由于我们已经在 get_cognee() 中设置了所有必要的环境变量，这里传递 None 让 Cognee 使用环境变量
        # 这样可以避免参数不匹配的问题（如缺少 vector_db_name、graph_db_provider 格式错误等）
        graph_db_config = None
        vector_db_config = None
        
        # 记录配置状态（用于调试）
        if hasattr(settings, 'ENABLE_MILVUS') and settings.ENABLE_MILVUS:
            if hasattr(settings, 'MILVUS_HOST') and settings.MILVUS_HOST:
                logger.info(f"Milvus 已启用，Cognee 将使用环境变量中的 Milvus 配置（vector_db_config=None）")
            else:
                logger.warning("MILVUS_HOST 未设置，vector_db_config 为 None")
        else:
            logger.info("ENABLE_MILVUS 未启用，vector_db_config 为 None（将使用默认 LanceDB）")
        
        logger.info(f"Cognee 将使用环境变量中的 Neo4j 配置（graph_db_config=None）")
        
        # 统一 dataset_name 格式：固定格式，不包含时间戳
        # 这样同一份文档只有一个 dataset，如果已存在需要删除后重建
        dataset_name = f"knowledge_base_{group_id}"
        logger.info(f"使用固定的 dataset_name: {dataset_name} (group_id: {group_id})")
        
        # ========== 0. 检查是否已存在Cognee知识图谱 ==========
        # 注意：即使检测到已存在，也继续执行清理逻辑（方案A）
        # 清理逻辑会自动处理已存在的数据，确保可以重新执行
        kg_exists = await self.check_cognee_kg_exists(group_id)
        if kg_exists:
            logger.warning(
                f"⚠️ 检测到已存在Cognee知识图谱: group_id={group_id}, dataset_name={dataset_name}，"
                f"将自动清理后重新构建"
            )
        
        results = {
            "total": section_count,
            "success": 0,
            "failed": 0,
            "section_data": []
        }
        
        # 先批量添加所有章节内容
        # 根据确认的方案：智能分块产生的chunks对应DataNode，每个chunk的content来自chunks.json
        section_texts = []
        section_metadata = []
        
        logger.info(
            f"准备 {len(sections)} 个章节数据（来自智能分块的chunks.json），"
            f"每个章节将作为DataNode/TextDocument添加到Cognee"
        )
        
        for idx, section in enumerate(sections):
            section_title = section.get("title", f"章节_{idx+1}")
            section_content = section.get("content", "")
            section_uuid = section.get("uuid")
            
            if not section_content.strip():
                logger.warning(f"章节 '{section_title}' 内容为空，跳过")
                continue
            
            # 验证内容长度（DataNode受max_tokens_per_section限制，但这里已经分块完成）
            content_length = len(section_content)
            logger.debug(
                f"章节[{idx+1}] '{section_title}': "
                f"内容长度={content_length} 字符, uuid={section_uuid}"
            )
            
            section_texts.append(section_content)
            section_metadata.append({
                "title": section_title,
                "section_uuid": section_uuid,
                "group_id": group_id,
                "index": idx,
                "content_length": content_length
            })
        
        if not section_texts:
            logger.warning("没有有效的章节内容，跳过知识图谱构建")
            return {"success": False, "reason": "no_valid_sections"}
        
        try:
            # 注意：使用固定的 dataset_name（不包含时间戳），如果已存在需要先清理
            # 清理逻辑会在下面执行（步骤0.5），确保可以重新执行
            logger.info(f"开始处理 dataset '{dataset_name}' (group_id: {group_id})")
            
            # 0. 临时方案：修复 Cognee 内部 bug（get_all_user_permission_datasets 返回 None）
            try:
                # 方案1：确保至少存在一个有效的 Dataset
                from cognee.infrastructure.databases.relational import get_relational_engine
                from cognee.modules.data.models import Dataset
                from sqlalchemy import select
                from uuid import uuid4
                
                engine = get_relational_engine()
                async with engine.get_async_session() as session:
                    # 检查是否存在默认 Dataset
                    default_query = select(Dataset).filter(Dataset.name == "__default_dataset__")
                    default_datasets = (await session.execute(default_query)).scalars().all()
                    
                    if len(default_datasets) == 0:
                        logger.warning("⚠️ 检测到默认 Dataset 不存在，创建默认 Dataset 以避免 Cognee 内部 bug")
                        # 创建一个默认 Dataset（Dataset 模型只接受 id 和 name 参数）
                        default_dataset = Dataset(
                            id=uuid4(),
                            name="__default_dataset__"
                        )
                        session.add(default_dataset)
                        await session.commit()
                        logger.info("✅ 已创建默认 Dataset: __default_dataset__")
                    else:
                        logger.debug(f"✅ 默认 Dataset 已存在: __default_dataset__")
                
                # 方案2：使用 Monkey Patch 修复 get_all_user_permission_datasets 函数，过滤掉 None 值
                try:
                    import functools
                    # 直接导入模块文件，而不是通过 __init__.py
                    from cognee.modules.users.permissions.methods import get_all_user_permission_datasets
                    import cognee.modules.users.permissions.methods.get_all_user_permission_datasets as get_all_user_permission_datasets_module
                    
                    # 保存原始函数
                    original_get_all_user_permission_datasets = get_all_user_permission_datasets
                    
                    # 创建修复后的函数
                    @functools.wraps(original_get_all_user_permission_datasets)
                    async def patched_get_all_user_permission_datasets(user, permission_type="read", tenants=None):
                        """修复后的函数，过滤掉 None 值"""
                        result = await original_get_all_user_permission_datasets(user, permission_type, tenants)
                        # 过滤掉 None 值
                        if result and isinstance(result, list):
                            filtered_result = [ds for ds in result if ds is not None]
                            if len(filtered_result) != len(result):
                                logger.warning(f"⚠️ get_all_user_permission_datasets 返回了 {len(result) - len(filtered_result)} 个 None 值，已过滤")
                            return filtered_result
                        return result
                    
                    # 应用 Monkey Patch - 同时 patch 模块文件和 methods 模块
                    get_all_user_permission_datasets_module.get_all_user_permission_datasets = patched_get_all_user_permission_datasets
                    import cognee.modules.users.permissions.methods
                    cognee.modules.users.permissions.methods.get_all_user_permission_datasets = patched_get_all_user_permission_datasets
                    logger.info("✅ 已应用 Monkey Patch 修复 get_all_user_permission_datasets 函数")
                except Exception as patch_error:
                    logger.warning(f"⚠️ 应用 Monkey Patch 失败: {patch_error}，继续执行（可能不影响）", exc_info=True)
                    
            except Exception as e:
                logger.warning(f"⚠️ 临时方案执行失败: {e}，继续执行（可能不影响）", exc_info=True)
            
            # 0.5 清理已存在的 dataset（使用统一的清理逻辑）
            try:
                from cognee.infrastructure.databases.relational import get_relational_engine
                from cognee.modules.data.models import Dataset
                from cognee.modules.data.methods import delete_dataset
                from sqlalchemy import select
                from app.core.neo4j_client import neo4j_client
                
                engine = get_relational_engine()
                
                # 1. 使用官方 API 删除 SQLite 中的 dataset
                async with engine.get_async_session() as session:
                    query = select(Dataset).filter(Dataset.name == dataset_name)
                    result = await session.execute(query)
                    existing_datasets = result.scalars().all()
                    
                    if existing_datasets:
                        logger.warning(f"⚠️ 检测到已存在 {len(existing_datasets)} 个 dataset，开始清理...")
                        
                        # 先清理 PipelineRun 记录（必须！Cognee 会检查此表判断 dataset 是否存在）
                        try:
                            from cognee.modules.pipelines.models import PipelineRun
                            from sqlalchemy import delete as sql_delete
                            
                            for ds in existing_datasets:
                                # 删除该 dataset 的所有 PipelineRun 记录
                                delete_runs_query = sql_delete(PipelineRun).filter(PipelineRun.dataset_id == ds.id)
                                runs_result = await session.execute(delete_runs_query)
                                if runs_result.rowcount > 0:
                                    logger.info(f"  - 已删除 {runs_result.rowcount} 个 PipelineRun 记录（dataset_id: {ds.id}）")
                            
                            await session.commit()
                            logger.info("✅ PipelineRun 记录删除成功")
                        except Exception as runs_error:
                            logger.warning(f"⚠️ 删除 PipelineRun 记录失败: {runs_error}，继续执行", exc_info=True)
                        
                        # 使用官方 API 删除 dataset（自动处理 SQLite，可能处理部分 Neo4j）
                        for ds in existing_datasets:
                            # delete_dataset() 只接受一个参数（dataset对象），不需要 session
                            await delete_dataset(ds)
                            logger.info(f"  - 已删除 dataset: {ds.name} (id: {ds.id})")
                        
                        logger.info("✅ Dataset 删除成功（使用官方 API）")
                    else:
                        logger.info("✅ 不存在同名 dataset，无需删除")
                
                # 2. 手动清理 Neo4j 节点（确保清理干净，只清理与当前 group_id 相关的节点）
                try:
                    # 先统计节点数量
                    stats_query = """
                    MATCH (n)
                    WHERE '__Node__' IN labels(n)
                       AND ('Entity' IN labels(n)
                       OR 'DocumentChunk' IN labels(n)
                       OR 'TextDocument' IN labels(n)
                       OR 'EntityType' IN labels(n)
                       OR 'TextSummary' IN labels(n)
                       OR 'DataNode' IN labels(n))
                       AND (
                           n.group_id = $group_id
                           OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                       )
                    RETURN count(n) as node_count
                    """
                    stats_result = neo4j_client.execute_query(stats_query, {"group_id": group_id})
                    node_count = stats_result[0].get("node_count", 0) if stats_result else 0
                    
                    if node_count > 0:
                        logger.warning(f"⚠️ 检测到 Neo4j 中有 {node_count} 个 Cognee 节点残留，强制删除...")
                        
                        # 先删除关系
                        delete_rels_query = """
                        MATCH (a)-[r]->(b)
                        WHERE '__Node__' IN labels(a) OR '__Node__' IN labels(b)
                           AND (
                               a.group_id = $group_id OR b.group_id = $group_id
                               OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id)
                               OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id)
                           )
                        DELETE r
                        RETURN count(r) as deleted_count
                        """
                        rel_result = neo4j_client.execute_query(delete_rels_query, {"group_id": group_id})
                        rel_count = rel_result[0].get("deleted_count", 0) if rel_result else 0
                        logger.info(f"  - Neo4j: 删除了 {rel_count} 个关系")
                        
                        # 删除节点
                        delete_nodes_query = """
                        MATCH (n)
                        WHERE '__Node__' IN labels(n)
                           AND ('Entity' IN labels(n)
                           OR 'DocumentChunk' IN labels(n)
                           OR 'TextDocument' IN labels(n)
                           OR 'EntityType' IN labels(n)
                           OR 'TextSummary' IN labels(n)
                           OR 'DataNode' IN labels(n))
                           AND (
                               n.group_id = $group_id
                               OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                           )
                        DETACH DELETE n
                        RETURN count(n) as deleted_count
                        """
                        node_result = neo4j_client.execute_query(delete_nodes_query, {"group_id": group_id})
                        deleted_count = node_result[0].get("deleted_count", 0) if node_result else 0
                        logger.info(f"  - Neo4j: 删除了 {deleted_count} 个节点")
                        
                        logger.info("✅ Neo4j 中残留的 Cognee 节点删除成功")
                    else:
                        logger.info("✅ Neo4j 中不存在 Cognee 节点残留，无需删除")
                except Exception as neo4j_error:
                    logger.warning(f"⚠️ 删除 Neo4j 节点失败: {neo4j_error}，继续执行（可能导致 add() 失败）", exc_info=True)
                
                # 3. 手动清理 Milvus collection（必须！delete_dataset() 不处理）
                try:
                    from app.services.milvus_service import get_milvus_service
                    from pymilvus import utility, Collection, connections
                    # settings 已在函数开头导入，不需要重复导入
                    
                    milvus_service = get_milvus_service()
                    if milvus_service.is_available():
                        alias = "cognee_milvus"
                        
                        # 确保连接已建立（参考 MilvusAdapter 的实现）
                        try:
                            # 检查连接是否已存在
                            if connections.has_connection(alias):
                                logger.debug(f"Milvus 连接已存在: {alias}")
                            else:
                                # 连接不存在，建立连接
                                connection_params = {
                                    "host": settings.MILVUS_HOST,
                                    "port": settings.MILVUS_PORT
                                }
                                if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                                    connection_params["user"] = settings.MILVUS_USERNAME
                                if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                                    connection_params["password"] = settings.MILVUS_PASSWORD
                                
                                connections.connect(alias=alias, **connection_params)
                                logger.info(f"✅ 已建立 Milvus 连接: {alias}")
                        except Exception as conn_error:
                            # 如果检查连接失败，尝试直接建立连接
                            logger.warning(f"检查 Milvus 连接失败: {conn_error}，尝试建立新连接")
                            try:
                                connection_params = {
                                    "host": settings.MILVUS_HOST,
                                    "port": settings.MILVUS_PORT
                                }
                                if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                                    connection_params["user"] = settings.MILVUS_USERNAME
                                if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                                    connection_params["password"] = settings.MILVUS_PASSWORD
                                
                                connections.connect(alias=alias, **connection_params)
                                logger.info(f"✅ 已建立 Milvus 连接: {alias}")
                            except Exception as connect_error:
                                logger.error(f"建立 Milvus 连接失败: {connect_error}")
                                raise
                        
                        all_collections = utility.list_collections(using=alias)
                        logger.info(f"📋 Milvus 中所有 collection 列表: {all_collections[:10]}... (共 {len(all_collections)} 个)")
                        
                        # 查找所有与 dataset_name 或 group_id 相关的 collection
                        # collection 命名格式可能是：
                        # - {dataset_name}_{timestamp}_{suffix}
                        # - {dataset_name}_text
                        # - 或其他包含 dataset_name 或 group_id 的格式
                        related_collections = [
                            col for col in all_collections 
                            if (dataset_name in col or group_id in col)
                        ]
                        
                        if related_collections:
                            logger.warning(f"⚠️ 找到 {len(related_collections)} 个相关 collection: {related_collections}")
                        else:
                            logger.info(f"ℹ️ 未找到相关 collection（dataset_name: {dataset_name}, group_id: {group_id}）")
                        
                        deleted_collections_count = 0
                        for collection_name in related_collections:
                            try:
                                collection = Collection(collection_name, using=alias)
                                entity_count = collection.num_entities
                                utility.drop_collection(collection_name, using=alias)
                                deleted_collections_count += 1
                                logger.info(f"  - Milvus: 删除了 collection {collection_name} ({entity_count} 个向量)")
                            except Exception as e:
                                logger.warning(f"删除 Milvus collection {collection_name} 失败: {e}")
                        
                        if deleted_collections_count > 0:
                            logger.info(f"✅ Milvus collection 删除成功（删除了 {deleted_collections_count} 个）")
                        else:
                            logger.info("✅ Milvus 中不存在相关 collection，无需删除")
                    else:
                        logger.info("✅ Milvus 不可用，跳过 collection 删除")
                except Exception as milvus_error:
                    logger.warning(f"⚠️ 删除 Milvus collection 失败: {milvus_error}，继续执行（可能导致 add() 失败）", exc_info=True)
                
                # 4. 清理 .data_storage 缓存（必须！Cognee 会检查此缓存判断 dataset 是否存在）
                try:
                    import os
                    import shutil
                    import cognee
                    
                    # 找到 Cognee 的安装路径
                    cognee_path = os.path.dirname(os.path.abspath(cognee.__file__))
                    data_storage_path = os.path.join(cognee_path, ".data_storage")
                    
                    if os.path.exists(data_storage_path):
                        # 查找并删除所有与 dataset_name 或 group_id 相关的文件/目录
                        related_files = []
                        for filename in os.listdir(data_storage_path):
                            file_path = os.path.join(data_storage_path, filename)
                            # 检查文件名是否包含 dataset_name 或 group_id
                            if dataset_name in filename or group_id in filename:
                                related_files.append(file_path)
                        
                        if related_files:
                            logger.warning(f"⚠️ .data_storage 中发现 {len(related_files)} 个相关缓存文件/目录，开始删除...")
                            deleted_count = 0
                            for file_path in related_files:
                                try:
                                    if os.path.isdir(file_path):
                                        shutil.rmtree(file_path)
                                        logger.info(f"  - 已删除目录: {os.path.basename(file_path)}")
                                    else:
                                        os.remove(file_path)
                                        logger.info(f"  - 已删除文件: {os.path.basename(file_path)}")
                                    deleted_count += 1
                                except Exception as e:
                                    logger.warning(f"删除 {os.path.basename(file_path)} 失败: {e}")
                            
                            logger.info(f"✅ .data_storage 清理成功（删除了 {deleted_count} 个文件/目录）")
                        else:
                            logger.info("✅ .data_storage 中不存在相关缓存文件，无需删除")
                    else:
                        logger.info("✅ .data_storage 目录不存在，无需删除")
                except Exception as storage_error:
                    logger.warning(f"⚠️ 清理 .data_storage 失败: {storage_error}，继续执行（可能导致 add() 失败）", exc_info=True)
                    
            except Exception as e:
                logger.warning(f"⚠️ 清理已存在数据失败: {e}，继续执行（可能导致 add() 失败）", exc_info=True)
            
            # 1. 批量添加章节内容到 Cognee
            # 注意：LLM 环境变量已在 get_cognee() 初始化时设置，这里不需要动态设置
            # 根据确认的方案：智能分块产生的chunks对应DataNode，Cognee会自动创建DocumentChunk
            logger.info(
                f"添加 {len(section_texts)} 个章节到 Cognee dataset: {dataset_name} "
                f"(每个章节对应一个DataNode/TextDocument，Cognee会自动创建DocumentChunk)"
            )
            # 不传递 vector_db_config 和 graph_db_config，让 Cognee 使用环境变量
            # 添加重试机制处理 SQLite 数据库锁定问题
            max_retries = 3
            retry_delay = 2  # 秒
            add_result = None
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    add_result = await self.cognee.add(
                        section_texts,
                        dataset_name=dataset_name
                    )
                    logger.info(f"✅ add() 执行完成，返回值: {add_result}")
                    
                    # 检查是否返回了 PipelineRunAlreadyCompleted
                    # add_result 可能是 PipelineRunResult 对象，status 可能是 'PipelineRunCompleted'
                    # 但 data_ingestion_info 中的 run_info 可能是 PipelineRunAlreadyCompleted
                    has_already_completed = False
                    if add_result:
                        # 检查 status
                        if hasattr(add_result, 'status') and add_result.status == 'PipelineRunCompleted':
                            # 检查 data_ingestion_info 中是否有 PipelineRunAlreadyCompleted
                            if hasattr(add_result, 'data_ingestion_info') and add_result.data_ingestion_info:
                                for info in add_result.data_ingestion_info:
                                    if hasattr(info, 'run_info') and hasattr(info.run_info, 'status'):
                                        if info.run_info.status == 'PipelineRunAlreadyCompleted':
                                            has_already_completed = True
                                            break
                                    elif isinstance(info, dict) and info.get('run_info'):
                                        run_info = info.get('run_info')
                                        if hasattr(run_info, 'status') and run_info.status == 'PipelineRunAlreadyCompleted':
                                            has_already_completed = True
                                            break
                    
                    if has_already_completed:
                        # Dataset已存在，使用带时间戳的 dataset_name 重新尝试（绕过 Cognee 的检查机制）
                        import datetime
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        fallback_dataset_name = f"{dataset_name}_{timestamp}"
                        logger.warning(
                            f"⚠️ add() 返回 PipelineRunAlreadyCompleted，说明 dataset '{dataset_name}' 已经存在。"
                            f"使用带时间戳的 dataset_name 重新尝试: {fallback_dataset_name}"
                        )
                        # 使用新的 dataset_name 重新调用 add()
                        add_result = await self.cognee.add(
                            section_texts,
                            dataset_name=fallback_dataset_name
                        )
                        logger.info(f"✅ add() 执行完成（使用 fallback dataset_name），返回值: {add_result}")
                        # 更新 dataset_name 为实际使用的名称
                        dataset_name = fallback_dataset_name
                    
                    break  # 成功，退出重试循环
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    
                    # 检查是否是 SQLite 数据库锁定错误
                    if "database is locked" in error_str.lower() or "sqlite3.operationalerror" in error_str.lower():
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)  # 递增等待时间
                            logger.warning(
                                f"⚠️ SQLite 数据库锁定错误（尝试 {attempt + 1}/{max_retries}），"
                                f"等待 {wait_time} 秒后重试..."
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(
                                f"❌ SQLite 数据库锁定错误，已重试 {max_retries} 次仍失败: {e}",
                                exc_info=True
                            )
                            raise
                    else:
                        # 其他错误，直接抛出
                        logger.error(f"❌ add() 执行失败（非锁定错误）: {e}", exc_info=True)
                        raise
            
            if add_result is None and last_error:
                raise last_error
                
                # 验证层级关系：TextDocument -> DataNode -> DocumentChunk
                from app.core.neo4j_client import neo4j_client
                
                # 检查 add() 是否在 Neo4j 中创建了节点
                check_add_nodes_query = """
                MATCH (n)
                WHERE '__Node__' IN labels(n)
                   OR 'DataNode' IN labels(n)
                   OR 'TextDocument' IN labels(n)
                   OR 'DocumentChunk' IN labels(n)
                   OR 'Chunk' IN labels(n)
                   OR 'Entity' IN labels(n)
                   OR 'EntityType' IN labels(n)
                   OR 'TextSummary' IN labels(n)
                RETURN count(n) as node_count
                """
                check_add_result = neo4j_client.execute_query(check_add_nodes_query)
                add_node_count = check_add_result[0]["node_count"] if check_add_result else 0
                logger.info(f"✅ add() 后在 Neo4j 中创建了 {add_node_count} 个节点")
                
                # 验证层级关系：TextDocument/DataNode -> DocumentChunk
                hierarchy_check_query = """
                MATCH (td)
                WHERE ('TextDocument' IN labels(td) OR 'DataNode' IN labels(td))
                  AND (td.dataset_name = $dataset_name OR td.dataset_id = $dataset_name)
                WITH td
                OPTIONAL MATCH (td)<-[:is_part_of]-(dc)
                WHERE 'DocumentChunk' IN labels(dc) OR 'Chunk' IN labels(dc)
                RETURN 
                    count(DISTINCT td) as text_document_count,
                    count(DISTINCT dc) as document_chunk_count
                """
                hierarchy_result = neo4j_client.execute_query(hierarchy_check_query, {
                    "dataset_name": dataset_name
                })
                
                if hierarchy_result:
                    td_count = hierarchy_result[0].get("text_document_count", 0)
                    dc_count = hierarchy_result[0].get("document_chunk_count", 0)
                    logger.info(
                        f"✅ 层级关系验证: TextDocument/DataNode={td_count} 个, "
                        f"DocumentChunk={dc_count} 个 "
                        f"(预期: TextDocument/DataNode={len(section_texts)} 个, DocumentChunk由Cognee自动创建)"
                    )
                    
                    # 验证：每个TextDocument/DataNode应该对应多个DocumentChunk（Cognee自动分块）
                    if td_count > 0 and dc_count == 0:
                        logger.warning(
                            f"⚠️ 检测到 {td_count} 个 TextDocument/DataNode，但没有 DocumentChunk。"
                            f"这可能表示Cognee尚未完成分块，或者配置有问题。"
                        )
                    elif td_count == 0:
                        logger.warning(
                            f"⚠️ 未检测到 TextDocument/DataNode 节点。"
                            f"这可能表示Cognee尚未创建节点，或者dataset_name不匹配。"
                        )
                else:
                    logger.warning("⚠️ 层级关系验证查询返回空结果")
                
                if add_node_count == 0:
                    logger.warning(f"⚠️ add() 执行完成，但 Neo4j 中没有创建任何节点！这可能是配置问题。")
            
            # 2. 根据配置模式选择模板生成方案
            custom_prompt = None
            
            # 检查是否使用JSON配置（包括已生成的 JSON）
            # 如果传入了 cognify_template_config_json，优先使用（无论是 json_config 还是 llm_generate 模式）
            if cognify_template_config_json:
                logger.info(f"使用已提供的JSON配置生成模板（模式: {cognify_template_mode}）")
                # 直接使用JSON配置转换为 custom_prompt
                custom_prompt = self._template_to_custom_prompt(cognify_template_config_json)
                logger.info(f"✅ 已使用JSON配置生成模板，包含 {len(cognify_template_config_json.get('entity_types', {}))} 个实体类型")
                
                # 保存模板到数据库（如果提供了upload_id）
                if upload_id and document_name:
                    template_id = await self._save_cognee_template_to_db(
                        template_config=cognify_template_config_json,
                        upload_id=upload_id,
                        document_name=document_name,
                        section_count=section_count,
                        template_type="JSON配置",
                        provider=provider
                    )
                    if template_id:
                        logger.info(f"✅ Cognee 模板保存成功，template_id={template_id}")
            else:
                # 新方案：批次处理 - 将章节按token限制分组，并行处理，然后合并
                logger.info(f"使用批次处理方案：将 {section_count} 个章节按token限制分组处理")
                
                # 1. 将章节分组
                batches = self._group_sections_by_token_limit(
                    section_texts=section_texts,
                    section_metadata=section_metadata,
                    provider=provider
                )
                
                # 2. 并行处理批次（最大并发数=3）
                max_concurrent = 3
                semaphore = asyncio.Semaphore(max_concurrent)
                
                batch_tasks = [
                    self._process_batch_template(
                        batch=batch,
                        batch_index=i+1,
                        system_prompt=cognify_system_prompt,
                        user_prompt_template=cognify_user_prompt_template,
                        temperature=temperature,
                        semaphore=semaphore
                    )
                    for i, batch in enumerate(batches)
                ]
                
                batch_results = await asyncio.gather(*batch_tasks)
                
                # 3. 过滤掉失败的结果
                successful_results = [r for r in batch_results if r is not None]
                failed_count = len(batch_results) - len(successful_results)
                
                if failed_count > 0:
                    logger.warning(f"⚠️ {failed_count} 个批次处理失败，继续使用成功的结果")
                
                if not successful_results:
                    raise ValueError("所有批次处理失败，无法生成模板")
                
                # 4. 合并批次结果
                logger.info(f"开始合并 {len(successful_results)} 个批次的模板结果")
                template_config = await self._merge_batch_templates(
                    batch_results=successful_results,
                    provider=provider
                )
                
                # 转换为 custom_prompt
                custom_prompt = self._template_to_custom_prompt(template_config)
                logger.info(f"✅ 批次处理完成：已生成统一模板，包含 {len(template_config.get('entity_types', {}))} 个实体类型")
                
                # 保存模板到数据库
                logger.info(f"准备保存 Cognee 模板到数据库: upload_id={upload_id}, document_name={document_name}, section_count={section_count}")
                if upload_id and document_name:
                    template_id = await self._save_cognee_template_to_db(
                        template_config=template_config,
                        upload_id=upload_id,
                        document_name=document_name,
                        section_count=section_count,
                        template_type=f"批次处理-{len(batches)}批次",
                        provider=provider
                    )
                    if template_id:
                        logger.info(f"✅ Cognee 模板保存成功，template_id={template_id}")
                    else:
                        logger.warning(f"⚠️ Cognee 模板保存失败（返回 None）")
                else:
                    logger.warning(f"⚠️ 跳过 Cognee 模板保存: upload_id={upload_id}, document_name={document_name}")
            
            # 3. Cognify: 为整个 dataset 生成知识图谱（使用 custom_prompt）
            logger.info(f"开始为 dataset '{dataset_name}' 构建知识图谱（使用自定义模板）")
            # 不传递 vector_db_config 和 graph_db_config，让 Cognee 使用环境变量
            # 注意：LLM 环境变量已在 get_cognee() 初始化时设置，这里不需要动态设置
            try:
                await self.cognee.cognify(
                    datasets=dataset_name,
                    custom_prompt=custom_prompt  # 传递自定义模板
                )
            except Exception as cognify_error:
                # 检查是否是 Milvus 向量为 nil 的错误
                error_str = str(cognify_error)
                if "nil" in error_str.lower() or "vector" in error_str.lower() and "illegal" in error_str.lower():
                    logger.warning(f"⚠️ cognify() 遇到向量为 nil 的错误（可能是某些数据点没有有效文本）: {cognify_error}")
                    logger.warning(f"⚠️ 这通常不影响知识图谱的核心功能（Neo4j 节点和关系可能已创建）")
                    # 继续执行，不中断流程
                else:
                    # 其他错误，重新抛出
                    raise
            
            # 检查 cognify() 是否成功创建了节点
            # Cognee 实际创建的节点类型：Entity, DocumentChunk, TextDocument, EntityType, TextSummary（都有 __Node__ 标签）
            from app.core.neo4j_client import neo4j_client
            check_nodes_query = """
            MATCH (n)
            WHERE '__Node__' IN labels(n)
               AND ('Entity' IN labels(n) 
               OR 'DocumentChunk' IN labels(n)
               OR 'TextDocument' IN labels(n)
               OR 'EntityType' IN labels(n)
               OR 'TextSummary' IN labels(n)
               OR 'KnowledgeNode' IN labels(n))
            RETURN count(n) as node_count
            """
            check_result = neo4j_client.execute_query(check_nodes_query)
            node_count = check_result[0]["node_count"] if check_result else 0
            
            if node_count == 0:
                logger.warning(
                    f"⚠️ cognify() 完成后，Neo4j 中仍然没有节点。"
                    f"这可能是因为 Cognee 认为 dataset '{dataset_name}' 已经处理过，跳过了知识提取。"
                    f"尝试清除 Cognee 的 pipeline runs 并重试..."
                )
                
                # 尝试清除 Cognee 的 pipeline runs 并重试
                try:
                    from cognee.infrastructure.databases.relational import get_relational_engine
                    from cognee.modules.pipelines.models import PipelineRun
                    from cognee.modules.data.models import Dataset
                    from sqlalchemy import select, delete
                    
                    engine = get_relational_engine()
                    deleted_count = 0
                    
                    # 通过 dataset_name 查找 dataset_id
                    async with engine.get_async_session() as session:
                        query = select(Dataset).filter(Dataset.name == dataset_name)
                        datasets = (await session.execute(query)).scalars().all()
                        
                        if datasets:
                            for dataset in datasets:
                                dataset_id = dataset.id
                                logger.info(f"找到 dataset ID: {dataset_id}，清除其 pipeline runs...")
                                
                                # 删除所有相关的 pipeline runs
                                delete_query = delete(PipelineRun).filter(PipelineRun.dataset_id == dataset_id)
                                result = await session.execute(delete_query)
                                await session.commit()
                                
                                deleted_count = result.rowcount
                                logger.info(f"✅ 清除了 {deleted_count} 个 pipeline runs")
                        else:
                            logger.warning(f"未找到 dataset: {dataset_name}，无法清除 pipeline runs")
                    
                    # 如果成功清除了 pipeline runs，重试 cognify()
                    if deleted_count > 0:
                        logger.info(f"重试 cognify()...")
                        await self.cognee.cognify(
                            datasets=dataset_name,
                            custom_prompt=custom_prompt
                        )
                        
                        # 再次检查节点数量
                        check_result = neo4j_client.execute_query(check_nodes_query)
                        node_count = check_result[0]["node_count"] if check_result else 0
                        
                        if node_count > 0:
                            logger.info(f"✅ 重试成功！cognify() 创建了 {node_count} 个节点")
                        else:
                            logger.warning(f"⚠️ 重试后仍然没有创建节点")
                            
                except Exception as e:
                    logger.error(f"清除 pipeline runs 并重试失败: {e}", exc_info=True)
            else:
                logger.info(f"✅ cognify() 成功创建了 {node_count} 个节点")
            
            # ========== 3.5 统计当前dataset的节点和关系数量 ==========
            # 使用时间窗口过滤：在cognify()执行前记录时间戳，执行后查询这个时间窗口内的节点
            import time
            before_timestamp = time.time() - 300  # 向前5分钟（确保包含所有新创建的节点）
            after_timestamp = time.time() + 60     # 向后1分钟（容错）
            
            # 统计Entity节点（通过group_id过滤，因为节点已更新group_id属性）
            entity_count_query = """
            MATCH (n:Entity)
            WHERE '__Node__' IN labels(n)
               AND n.group_id = $group_id
            RETURN count(n) as entity_count
            """
            entity_result = neo4j_client.execute_query(entity_count_query, {"group_id": group_id})
            entity_count = entity_result[0].get("entity_count", 0) if entity_result else 0
            
            # 统计关系（通过group_id过滤）
            edge_count_query = """
            MATCH (a)-[r]->(b)
            WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
               AND (
                   (a.group_id = $group_id AND b.group_id = $group_id)
                   OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id)
                   OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id)
               )
            RETURN count(DISTINCT r) as edge_count
            """
            edge_result = neo4j_client.execute_query(edge_count_query, {"group_id": group_id})
            edge_count = edge_result[0].get("edge_count", 0) if edge_result else 0
            
            # 统计实体类型分布
            entity_type_query = """
            MATCH (n:Entity)
            WHERE '__Node__' IN labels(n)
               AND n.group_id = $group_id
            UNWIND labels(n) as label
            WITH label
            WHERE label <> 'Entity' AND label <> '__Node__'
            RETURN label, count(*) as count
            ORDER BY count DESC
            """
            entity_type_result = neo4j_client.execute_query(entity_type_query, {"group_id": group_id})
            entity_type_counts = {row.get("label"): row.get("count", 0) for row in entity_type_result} if entity_type_result else {}
            
            # 统计关系类型分布
            edge_type_query = """
            MATCH (a)-[r]->(b)
            WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
               AND (
                   (a.group_id = $group_id AND b.group_id = $group_id)
                   OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id)
                   OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id)
               )
            RETURN type(r) as edge_type, count(*) as count
            ORDER BY count DESC
            """
            edge_type_result = neo4j_client.execute_query(edge_type_query, {"group_id": group_id})
            edge_type_counts = {row.get("edge_type"): row.get("count", 0) for row in edge_type_result} if edge_type_result else {}
            
            logger.info(
                f"✅ Cognify统计完成: "
                f"Entity={entity_count}个, "
                f"关系={edge_count}个, "
                f"实体类型={len(entity_type_counts)}种, "
                f"关系类型={len(edge_type_counts)}种"
            )
            
            # 构建cognify_result
            cognify_result = {
                "entity_count": entity_count,
                "edge_count": edge_count,
                "entity_type_counts": entity_type_counts,
                "edge_type_counts": edge_type_counts
            }
            
            # 4. Memify: 添加记忆算法到图谱
            # ========== 关键修复：解决 @lru_cache + Pipeline 多进程配置传递问题 ==========
            # 问题本质：get_llm_config() 使用 @lru_cache，在 Pipeline Task 多进程执行时，
            # 子进程第一次调用会缓存"空配置"，导致后续配置无法传递
            # 
            # 解决方案（采用 GPT 建议的方案三 + 方案二组合）：
            # 1. 方案三：环境变量兜底（最稳定，子进程一定能拿到）
            # 2. 方案二：显式清空缓存 + 重新设置配置
            
            if hasattr(settings, 'LOCAL_LLM_API_KEY') and settings.LOCAL_LLM_API_KEY:
                import os
                import litellm
                
                # ========== 关键修复：禁用 litellm 的 aiohttp 传输，改用 httpx ==========
                # 问题：litellm 使用 aiohttp 时出现 "Server disconnected" 错误
                # 原因：LLM 服务对 aiohttp 的异步连接处理有问题
                # 解决：禁用 aiohttp，改用 httpx（更稳定）
                try:
                    # 关键1：删除已缓存的 aiohttp handler
                    if hasattr(litellm, 'base_llm_aiohttp_handler'):
                        litellm.base_llm_aiohttp_handler = None
                        logger.info("✅ 已删除 litellm.base_llm_aiohttp_handler")
                    
                    # 关键2：设置配置标志
                    litellm.disable_aiohttp_transport = True
                    litellm.use_aiohttp_transport = False
                    logger.info("✅ 已禁用 litellm 的 aiohttp 传输，改用 httpx")
                except Exception as e:
                    logger.warning(f"⚠️ 无法禁用 aiohttp 传输: {e}")
                
                # ========== 步骤1：设置环境变量（方案三：环境变量兜底）==========
                # 这是最稳定的方案，因为子进程一定能拿到环境变量
                os.environ["LLM_API_KEY"] = settings.LOCAL_LLM_API_KEY
                os.environ["OPENAI_API_KEY"] = settings.LOCAL_LLM_API_KEY
                os.environ["LLM_PROVIDER"] = "openai"
                
                # 设置 LLM 请求超时时间
                timeout_seconds = getattr(settings, 'COGNEE_LLM_REQUEST_TIMEOUT', 600.0)
                os.environ["LITELLM_REQUEST_TIMEOUT"] = str(timeout_seconds)
                
                if hasattr(settings, 'LOCAL_LLM_API_BASE_URL') and settings.LOCAL_LLM_API_BASE_URL:
                    local_base_url = settings.LOCAL_LLM_API_BASE_URL.rstrip('/')
                    if not local_base_url.endswith('/v1'):
                        if '/v1' not in local_base_url:
                            local_base_url = f"{local_base_url}/v1"
                    os.environ["OPENAI_BASE_URL"] = local_base_url
                    os.environ["LLM_ENDPOINT"] = local_base_url
                    
                    if hasattr(settings, 'LOCAL_LLM_MODEL') and settings.LOCAL_LLM_MODEL:
                        model_name = settings.LOCAL_LLM_MODEL
                        if model_name.startswith('/'):
                            litellm_model = f"openai/{model_name}"
                        else:
                            litellm_model = f"openai/{model_name}"
                    else:
                        litellm_model = "openai/gpt-4"
                    
                    os.environ["LLM_MODEL"] = litellm_model
                    os.environ["LITELLM_MODEL"] = litellm_model  # LiteLLM 也认这个变量
                    
                    logger.info(f"✅ 环境变量已设置（方案三：环境变量兜底）: LLM_MODEL={litellm_model}, OPENAI_BASE_URL={local_base_url}, LITELLM_REQUEST_TIMEOUT={timeout_seconds}")
                    
                    # ========== 步骤2：清空缓存 + 重新设置配置（方案二）==========
                    # 关键：必须在设置环境变量后，再清空缓存，然后重新设置配置
                    try:
                        from cognee.infrastructure.llm import get_llm_config
                        from cognee.modules.settings.save_llm_config import save_llm_config, LLMConfig
                        
                        # 清空缓存（方案二：显式清空缓存）
                        get_llm_config.cache_clear()
                        logger.info("✅ 已清除 get_llm_config 缓存（方案二：显式清空缓存）")
                        
                        # 重新设置配置（此时环境变量已设置，get_llm_config() 会读取到正确的值）
                        llm_config_obj = LLMConfig(
                            provider="openai",
                            model=litellm_model,
                            api_key=settings.LOCAL_LLM_API_KEY
                        )
                        await save_llm_config(llm_config_obj)
                        
                        # 手动设置 llm_endpoint（save_llm_config 不会设置）
                        fresh_config = get_llm_config()
                        fresh_config.llm_endpoint = local_base_url
                        fresh_config.llm_api_key = settings.LOCAL_LLM_API_KEY  # 确保设置
                        fresh_config.llm_model = litellm_model  # 确保设置
                        
                        logger.info(f"✅ 配置已重新设置: llm_model={fresh_config.llm_model}, llm_endpoint={fresh_config.llm_endpoint}, llm_api_key={'已设置' if fresh_config.llm_api_key else '未设置'}")
                    except Exception as e:
                        logger.warning(f"⚠️ 清空缓存或重新设置配置失败: {e}")
                        logger.warning("⚠️ 将继续使用环境变量（方案三），这应该足够稳定")
                        import traceback
                        logger.debug(f"配置设置错误详情: {traceback.format_exc()}")
                
                logger.info(f"memify() 调用前配置检查完成 - 环境变量已设置，缓存已清除，配置已更新")
            
            logger.info(f"为 dataset '{dataset_name}' 添加记忆算法")
            
            # ========== 统计memify()执行前的节点和关系数量 ==========
            memify_before_stats = {
                "text_summary_count": 0,
                "total_nodes": 0,
                "total_edges": 0
            }
            
            # 初始化memify统计变量
            extraction_count = 0
            enrichment_count = 0
            
            try:
                # 统计TextSummary节点（extraction可能创建的）
                # 通过group_id直接匹配，或通过made_from关系链匹配（备用方案）
                text_summary_before_query = """
                MATCH (ts:TextSummary)
                WHERE '__Node__' IN labels(ts)
                   AND (
                       ts.group_id = $group_id
                       OR (ts.dataset_name IS NOT NULL AND ts.dataset_name CONTAINS $group_id)
                       OR EXISTS {
                           (ts)-[:made_from]->(dc:DocumentChunk)
                           WHERE dc.group_id = $group_id
                       }
                   )
                RETURN count(ts) as count
                """
                text_summary_before_result = neo4j_client.execute_query(text_summary_before_query, {"group_id": group_id})
                memify_before_stats["text_summary_count"] = text_summary_before_result[0].get("count", 0) if text_summary_before_result else 0
                
                # 统计所有节点和关系（用于计算差值）
                # 包括通过关系链匹配的TextSummary节点
                total_nodes_before_query = """
                MATCH (n)
                WHERE '__Node__' IN labels(n)
                   AND (
                       n.group_id = $group_id
                       OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                       OR (
                           'TextSummary' IN labels(n)
                           AND EXISTS {
                               (n)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                   )
                RETURN count(n) as count
                """
                total_nodes_before_result = neo4j_client.execute_query(total_nodes_before_query, {"group_id": group_id})
                memify_before_stats["total_nodes"] = total_nodes_before_result[0].get("count", 0) if total_nodes_before_result else 0
                
                total_edges_before_query = """
                MATCH (a)-[r]->(b)
                WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
                   AND (
                       (a.group_id = $group_id AND b.group_id = $group_id)
                       OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id)
                       OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id)
                       OR (
                           'TextSummary' IN labels(a)
                           AND EXISTS {
                               (a)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                       OR (
                           'TextSummary' IN labels(b)
                           AND EXISTS {
                               (b)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                   )
                RETURN count(DISTINCT r) as count
                """
                total_edges_before_result = neo4j_client.execute_query(total_edges_before_query, {"group_id": group_id})
                memify_before_stats["total_edges"] = total_edges_before_result[0].get("count", 0) if total_edges_before_result else 0
                
                logger.info(
                    f"memify() 执行前统计: "
                    f"TextSummary={memify_before_stats['text_summary_count']}, "
                    f"总节点={memify_before_stats['total_nodes']}, "
                    f"总关系={memify_before_stats['total_edges']}"
                )
            except Exception as stats_error:
                logger.warning(f"⚠️ 统计memify()执行前的节点和关系失败: {stats_error}")
            
            try:
                # 检查是否使用JSON配置
                if memify_template_mode == "json_config" and memify_template_config_json:
                    logger.info(f"使用JSON配置模式执行 memify()")
                    # 解析JSON配置
                    extraction_config = memify_template_config_json.get("extraction", {})
                    enrichment_config = memify_template_config_json.get("enrichment", {})
                    
                    extraction_enabled = extraction_config.get("enabled", True)
                    enrichment_enabled = enrichment_config.get("enabled", True)
                    
                    extraction_tasks_list = []
                    enrichment_tasks_list = []
                    
                    # 构建 extraction_tasks
                    if extraction_enabled:
                        try:
                            from cognee.modules.pipelines.tasks.task import Task
                            from cognee.tasks.memify.extract_subgraph_chunks import extract_subgraph_chunks
                            
                            extraction_task = Task(extract_subgraph_chunks)
                            extraction_tasks_list.append(extraction_task)
                            logger.info(f"✅ extraction_task 创建成功（JSON配置）")
                        except ImportError as e:
                            logger.warning(f"⚠️ 无法导入 extraction 相关函数: {e}")
                    
                    # 构建 enrichment_tasks
                    if enrichment_enabled:
                        try:
                            from cognee.modules.pipelines.tasks.task import Task
                            from app.utils.cognee_task_wrapper import wrap_add_rule_associations
                            
                            # 获取配置参数
                            # 如果前端未提供rules_nodeset_name，则使用基于group_id的独立名称
                            config_rules_nodeset_name = enrichment_config.get("rules_nodeset_name")
                            if config_rules_nodeset_name:
                                rules_nodeset_name = config_rules_nodeset_name
                            else:
                                # 每个文档使用独立的规则集（基于group_id）
                                rules_nodeset_name = f"rules_{group_id}"
                            
                            manual_rules = enrichment_config.get("rules")  # 手动配置的规则列表
                            enrichment_mode = enrichment_config.get("mode", "llm_extract")  # "manual" 或 "llm_extract"
                            
                            # 如果提供了手动配置的规则且mode为"manual"，直接使用规则列表建立关联边
                            if manual_rules and isinstance(manual_rules, list) and enrichment_mode == "manual":
                                logger.info(f"使用手动配置的规则（rules_nodeset_name={rules_nodeset_name}, 规则数量={len(manual_rules)}）")
                            
                                # 创建enrichment任务：保存规则并建立关联边
                                async def save_rules_and_create_edges_task(*args, **kwargs):
                                    """保存规则并建立关联边的任务"""
                                    from cognee.modules.engine.models import NodeSet
                                    from cognee.tasks.codingagents.coding_rule_associations import Rule, get_origin_edges
                                    from cognee.tasks.storage import add_data_points, index_graph_edges
                                    from cognee.infrastructure.databases.graph import get_graph_engine
                                    from uuid import NAMESPACE_OID, uuid5
                                    
                                    # 创建NodeSet
                                    rules_nodeset = NodeSet(
                                        id=uuid5(NAMESPACE_OID, name=rules_nodeset_name),
                                        name=rules_nodeset_name
                                    )
                                    
                                    # 将规则文本转换为Rule对象
                                    cognee_rules = []
                                    for rule_text in manual_rules:
                                        if rule_text and rule_text.strip():
                                            cognee_rule = Rule(
                                                text=rule_text.strip(),
                                                belongs_to_set=rules_nodeset
                                            )
                                            cognee_rules.append(cognee_rule)
                                    
                                    # 保存规则到Neo4j
                                    if cognee_rules:
                                        await add_data_points(data_points=cognee_rules)
                                        logger.info(f"✅ 已保存 {len(cognee_rules)} 条规则到 {rules_nodeset_name}")
                                    
                                    # 为每个文档块建立关联边
                                    graph_engine = await get_graph_engine()
                                    total_edges = 0
                                    
                                    # 从args中获取subgraphs（memify()传递的数据）
                                    if args and len(args) > 0:
                                        subgraphs = args[0] if isinstance(args[0], list) else [args[0]]
                                        
                                        for subgraph in subgraphs:
                                            # 提取DocumentChunk文本
                                            if hasattr(subgraph, 'nodes'):
                                                for node in subgraph.nodes.values():
                                                    if hasattr(node, 'attributes') and node.attributes.get("type") == "DocumentChunk":
                                                        chunk_text = node.attributes.get("text", "")
                                                        if chunk_text:
                                                            # 调用get_origin_edges建立关联边
                                                            edges_to_save = await get_origin_edges(data=chunk_text, rules=cognee_rules)
                                                            if edges_to_save:
                                                                await graph_engine.add_edges(edges_to_save)
                                                                await index_graph_edges(edges_to_save)
                                                                total_edges += len(edges_to_save)
                                    
                                    logger.info(f"✅ 已建立 {total_edges} 条关联边")
                                    return {"rules_saved": len(cognee_rules), "edges_created": total_edges}
                                
                                enrichment_task = Task(save_rules_and_create_edges_task)
                                enrichment_tasks_list.append(enrichment_task)
                                logger.info(f"✅ 已添加规则关联任务（直接使用规则列表建立关联边）")
                            else:
                                # 如果没有手动配置的规则，跳过enrichment任务
                                logger.warning(f"⚠️ 未提供手动配置的规则，跳过enrichment任务（mode={enrichment_mode}）")
                        except ImportError as e:
                            logger.warning(f"⚠️ 无法导入 enrichment 相关函数: {e}")
                    
                    # 执行 memify()
                    if extraction_tasks_list or enrichment_tasks_list:
                        await self.cognee.memify(
                            dataset=dataset_name,
                            extraction_tasks=extraction_tasks_list if extraction_tasks_list else None,
                            enrichment_tasks=enrichment_tasks_list if enrichment_tasks_list else None,
                        )
                        logger.info(f"✅ memify() 执行完成（JSON配置: extraction={extraction_enabled}, enrichment={enrichment_enabled}）")
                        
                        # 保存Memify模板到数据库（JSON配置）
                        if upload_id and document_name:
                            template_id = await self._save_memify_template_to_db(
                                memify_config=memify_template_config_json,
                                upload_id=upload_id,
                                document_name=document_name,
                                dataset_name=dataset_name,
                                memify_template_mode=memify_template_mode,
                                provider=provider
                            )
                            if template_id:
                                logger.info(f"✅ Memify 模板保存成功，template_id={template_id}")
                    else:
                        logger.warning("⚠️ extraction 和 enrichment 都被禁用，跳过 memify()")
                else:
                    # 使用LLM自动生成配置：直接使用规则列表建立关联边（不调用add_rule_associations）
                    logger.info(f"使用LLM自动生成配置执行 memify()")
                    try:
                        from cognee.modules.pipelines.tasks.task import Task
                        from cognee.tasks.memify.extract_subgraph_chunks import extract_subgraph_chunks
                        logger.info(f"✅ 成功导入 Task 和相关函数")
                        
                        extraction_task = Task(extract_subgraph_chunks)
                        logger.info(f"✅ extraction_task 创建成功")
                        
                        # 步骤1: 获取规则列表
                        rules_list = memify_rules  # 前端已生成的规则列表
                        
                        # 如果前端未传递规则列表，使用批次处理生成规则列表
                        if not rules_list or len(rules_list) == 0:
                            logger.info(f"前端未传递规则列表，使用批次处理生成规则列表")
                            try:
                                # 使用批次处理方法（与预览API一致）
                                rules_list = await self._generate_memify_rules_batch(
                                    section_texts=section_texts,
                                    section_metadata=section_metadata,
                                    document_name=document_name or "文档",
                                    system_prompt=memify_system_prompt,
                                    user_prompt_template=memify_user_prompt_template,
                                    provider=provider,
                                    max_concurrent=3
                                )
                                logger.info(f"✅ 规则列表生成成功，共 {len(rules_list)} 条规则")
                            except Exception as gen_error:
                                logger.error(f"❌ 生成规则列表失败: {gen_error}", exc_info=True)
                                rules_list = []
                        
                        # 步骤2: 创建enrichment任务，直接使用规则列表建立关联边
                        if rules_list and len(rules_list) > 0:
                            logger.info(f"使用规则列表建立关联边（规则数量: {len(rules_list)}）")
                            
                            # 创建enrichment任务：保存规则并建立关联边
                            async def save_rules_and_create_edges_task(*args, **kwargs):
                                """保存规则并建立关联边的任务"""
                                from cognee.modules.engine.models import NodeSet
                                from cognee.tasks.codingagents.coding_rule_associations import Rule, get_origin_edges
                                from cognee.tasks.storage import add_data_points, index_graph_edges
                                from cognee.infrastructure.databases.graph import get_graph_engine
                                from uuid import NAMESPACE_OID, uuid5
                                
                                # 每个文档使用独立的规则集（基于group_id）
                                rules_nodeset_name = f"rules_{group_id}"
                                
                                # 创建NodeSet
                                rules_nodeset = NodeSet(
                                    id=uuid5(NAMESPACE_OID, name=rules_nodeset_name),
                                    name=rules_nodeset_name
                                )
                                
                                # 将规则文本转换为Rule对象
                                cognee_rules = []
                                for rule_text in rules_list:
                                    if rule_text and rule_text.strip():
                                        cognee_rule = Rule(
                                            text=rule_text.strip(),
                                            belongs_to_set=rules_nodeset
                                        )
                                        cognee_rules.append(cognee_rule)
                                
                                # 保存规则到Neo4j
                                if cognee_rules:
                                    await add_data_points(data_points=cognee_rules)
                                    logger.info(f"✅ 已保存 {len(cognee_rules)} 条规则到 {rules_nodeset_name}")
                                
                                # 为每个文档块建立关联边
                                # memify()会传递subgraphs，我们需要从中提取DocumentChunk文本
                                graph_engine = await get_graph_engine()
                                total_edges = 0
                                
                                # 从args中获取subgraphs（memify()传递的数据）
                                if args and len(args) > 0:
                                    subgraphs = args[0] if isinstance(args[0], list) else [args[0]]
                                    
                                    for subgraph in subgraphs:
                                        # 提取DocumentChunk文本
                                        if hasattr(subgraph, 'nodes'):
                                            for node in subgraph.nodes.values():
                                                if hasattr(node, 'attributes') and node.attributes.get("type") == "DocumentChunk":
                                                    chunk_text = node.attributes.get("text", "")
                                                    if chunk_text:
                                                        # 调用get_origin_edges建立关联边
                                                        edges_to_save = await get_origin_edges(data=chunk_text, rules=cognee_rules)
                                                        if edges_to_save:
                                                            await graph_engine.add_edges(edges_to_save)
                                                            await index_graph_edges(edges_to_save)
                                                            total_edges += len(edges_to_save)
                                
                                logger.info(f"✅ 已建立 {total_edges} 条关联边")
                                return {"rules_saved": len(cognee_rules), "edges_created": total_edges}
                            
                            enrichment_task = Task(save_rules_and_create_edges_task)
                            logger.info(f"✅ enrichment_task 创建成功（直接使用规则列表）")
                        else:
                            logger.warning(f"⚠️ 规则列表为空，跳过enrichment任务")
                            enrichment_task = None
                        
                        # 执行memify()
                        enrichment_tasks = [enrichment_task] if enrichment_task else None
                        await self.cognee.memify(
                            dataset=dataset_name,
                            extraction_tasks=[extraction_task],
                            enrichment_tasks=enrichment_tasks,
                        )
                        logger.info(f"✅ memify() 执行完成（使用LLM自动生成配置）")
                        
                        # 保存Memify模板到数据库
                        if upload_id and document_name:
                            memify_config = {
                                "extraction": {
                                    "enabled": True,
                                    "task": "extract_subgraph_chunks"
                                },
                                "enrichment": {
                                    "enabled": True,
                                    "task": "add_rule_associations",
                                    "rules_nodeset_name": "default_rules"
                                }
                            }
                            template_id = await self._save_memify_template_to_db(
                                memify_config=memify_config,
                                upload_id=upload_id,
                                document_name=document_name,
                                dataset_name=dataset_name,
                                memify_template_mode=memify_template_mode,
                                provider=provider
                            )
                            if template_id:
                                logger.info(f"✅ Memify 模板保存成功，template_id={template_id}")
                    except ImportError as import_error:
                        logger.warning(f"⚠️ 无法导入 Task 或相关函数，使用默认 memify() 调用: {import_error}")
                        await self.cognee.memify()
                        logger.info(f"✅ memify() 执行完成（使用LLM自动生成配置）")
                        
                        # 保存Memify模板到数据库（默认配置）
                        if upload_id and document_name:
                            memify_config = {
                                "extraction": {
                                    "enabled": True,
                                    "task": "extract_subgraph_chunks"
                                },
                                "enrichment": {
                                    "enabled": True,
                                    "task": "add_rule_associations",
                                    "rules_nodeset_name": "default_rules"
                                }
                            }
                            template_id = await self._save_memify_template_to_db(
                                memify_config=memify_config,
                                upload_id=upload_id,
                                document_name=document_name,
                                dataset_name=dataset_name,
                                memify_template_mode=memify_template_mode,
                                provider=provider
                            )
                            if template_id:
                                logger.info(f"✅ Memify 模板保存成功，template_id={template_id}")
                    except Exception as task_error:
                        logger.warning(f"⚠️ Task 创建失败，使用默认 memify() 调用: {task_error}")
                        await self.cognee.memify()
                        logger.info(f"✅ memify() 执行完成（使用LLM自动生成配置）")
                        
                        # 保存Memify模板到数据库（默认配置）
                        if upload_id and document_name:
                            memify_config = {
                                "extraction": {
                                    "enabled": True,
                                    "task": "extract_subgraph_chunks"
                                },
                                "enrichment": {
                                    "enabled": True,
                                    "task": "add_rule_associations",
                                    "rules_nodeset_name": "default_rules"
                            }
                            }
                            template_id = await self._save_memify_template_to_db(
                                memify_config=memify_config,
                                upload_id=upload_id,
                                document_name=document_name,
                                dataset_name=dataset_name,
                                memify_template_mode=memify_template_mode,
                                provider=provider
                            )
                            if template_id:
                                logger.info(f"✅ Memify 模板保存成功，template_id={template_id}")
            except Exception as memify_error:
                # memify() 失败不影响整体流程，记录错误但继续执行
                error_str = str(memify_error)
                if "Connection error" in error_str or "Connection" in error_str:
                    logger.warning(f"⚠️ memify() 执行失败（LLM 连接错误）: {memify_error}")
                    logger.warning(f"⚠️ 这通常不影响知识图谱的核心功能（Entity 和关系已由 cognify() 创建）")
                    logger.warning(f"⚠️ LLM 连接问题可能是临时的，可以稍后重试")
                else:
                    logger.warning(f"⚠️ memify() 执行失败（可能是 add_rule_associations 任务失败）: {memify_error}")
                    logger.warning(f"⚠️ 这通常不影响知识图谱的核心功能（Entity 和关系已由 cognify() 创建）")
            
            # ========== 更新DocumentChunk和TextSummary节点的group_id（在memify()执行后，统计前） ==========
            # 这些统计数据将返回给调用方（用于前端展示）
            updated_chunk_count = 0
            updated_text_summary_count = 0
            
            try:
                # 等待一下，确保memify()创建的节点已提交到Neo4j
                await asyncio.sleep(2)
                
                from app.core.neo4j_client import neo4j_client
                
                # 步骤1: 先更新DocumentChunk节点的group_id（如果doc_id和version已提供）
                # 添加详细的参数检查日志
                logger.info(f"🔍 DocumentChunk更新参数检查: doc_id={doc_id} (type={type(doc_id).__name__}), version={version} (type={type(version).__name__}), upload_id={upload_id} (type={type(upload_id).__name__})")
                logger.info(f"🔍 条件检查结果: doc_id and version and upload_id = {bool(doc_id and version and upload_id)}")
                
                if doc_id and version and upload_id:
                    logger.info(f"🔍 准备更新DocumentChunk节点: doc_id={doc_id}, version={version}, upload_id={upload_id}, group_id={group_id}")
                    update_document_chunk_query = """
                    MATCH (dc:DocumentChunk)
                    WHERE '__Node__' IN labels(dc)
                      AND ('DocumentChunk' IN labels(dc) OR 'Chunk' IN labels(dc))
                      AND (dc.doc_id IS NULL OR dc.group_id IS NULL)
                    WITH dc
                    ORDER BY dc.created_at DESC
                    LIMIT 200
                    SET dc.doc_id = $doc_id,
                        dc.group_id = $group_id,
                        dc.version = $version,
                        dc.upload_id = $upload_id
                    RETURN count(dc) as updated_count
                    """
                    chunk_update_result = neo4j_client.execute_query(update_document_chunk_query, {
                        "doc_id": doc_id,
                        "group_id": group_id,
                        "version": version,
                        "upload_id": upload_id
                    })
                    updated_chunk_count = chunk_update_result[0].get("updated_count", 0) if chunk_update_result else 0
                    if updated_chunk_count > 0:
                        logger.info(f"✅ 更新了 {updated_chunk_count} 个DocumentChunk节点的group_id（memify()执行后）")
                    else:
                        # 检查为什么更新返回 0
                        check_query = """
                        MATCH (dc:DocumentChunk)
                        WHERE '__Node__' IN labels(dc)
                          AND ('DocumentChunk' IN labels(dc) OR 'Chunk' IN labels(dc))
                          AND (dc.doc_id IS NULL OR dc.group_id IS NULL)
                        RETURN count(dc) as count
                        """
                        check_result = neo4j_client.execute_query(check_query)
                        available_count = check_result[0].get("count", 0) if check_result else 0
                        logger.warning(f"⚠️ DocumentChunk节点更新返回0（满足条件的节点数={available_count}，可能原因：节点已存在这些属性或查询条件不匹配）")
                else:
                    logger.warning(f"⚠️ DocumentChunk节点更新跳过（参数检查失败: doc_id={doc_id}, version={version}, upload_id={upload_id}）")
                
                # 步骤2: 更新TextSummary节点的group_id（通过made_from关系找到DocumentChunk，复制group_id）
                # 先检查TextSummary节点和made_from关系
                check_ts_query = """
                MATCH (ts:TextSummary)
                WHERE '__Node__' IN labels(ts)
                RETURN count(ts) as total_count
                """
                check_ts_result = neo4j_client.execute_query(check_ts_query)
                ts_total_count = check_ts_result[0].get("total_count", 0) if check_ts_result else 0
                
                check_relation_query = """
                MATCH (ts:TextSummary)-[r:made_from]->(dc:DocumentChunk)
                WHERE '__Node__' IN labels(ts) AND '__Node__' IN labels(dc)
                   AND dc.group_id = $group_id
                RETURN count(r) as relation_count
                """
                check_relation_result = neo4j_client.execute_query(check_relation_query, {"group_id": group_id})
                relation_count = check_relation_result[0].get("relation_count", 0) if check_relation_result else 0
                logger.info(f"🔍 检查TextSummary节点更新条件: TextSummary总数={ts_total_count}, made_from关系数={relation_count}, group_id={group_id}")
                
                update_text_summary_query = """
                MATCH (ts:TextSummary)-[:made_from]->(dc:DocumentChunk)
                WHERE '__Node__' IN labels(ts) AND '__Node__' IN labels(dc)
                   AND ts.group_id IS NULL
                   AND dc.group_id = $group_id
                WITH ts, dc
                SET ts.group_id = dc.group_id,
                    ts.doc_id = dc.doc_id,
                    ts.version = dc.version,
                    ts.upload_id = dc.upload_id
                RETURN count(ts) as updated_count
                """
                update_text_summary_result = neo4j_client.execute_query(update_text_summary_query, {"group_id": group_id})
                updated_text_summary_count = update_text_summary_result[0].get("updated_count", 0) if update_text_summary_result else 0
                
                if updated_text_summary_count > 0:
                    logger.info(f"✅ 更新了 {updated_text_summary_count} 个TextSummary节点的group_id（memify()执行后）")
                else:
                    logger.warning(f"⚠️ TextSummary节点更新返回0（TextSummary总数={ts_total_count}，made_from关系数={relation_count}，可能原因：关系不存在或DocumentChunk未设置group_id）")
            except Exception as update_error:
                logger.warning(f"⚠️ 更新DocumentChunk/TextSummary节点group_id失败: {update_error}")
            
            # ========== 统计memify()执行后的节点和关系数量 ==========
            memify_after_stats = {
                "text_summary_count": 0,
                "total_nodes": 0,
                "total_edges": 0
            }
            
            try:
                
                # 统计TextSummary节点（extraction创建的）
                # 通过group_id直接匹配，或通过made_from关系链匹配（备用方案）
                text_summary_after_query = """
                MATCH (ts:TextSummary)
                WHERE '__Node__' IN labels(ts)
                   AND (
                       ts.group_id = $group_id
                       OR (ts.dataset_name IS NOT NULL AND ts.dataset_name CONTAINS $group_id)
                       OR EXISTS {
                           (ts)-[:made_from]->(dc:DocumentChunk)
                           WHERE dc.group_id = $group_id
                       }
                   )
                RETURN count(ts) as count
                """
                text_summary_after_result = neo4j_client.execute_query(text_summary_after_query, {"group_id": group_id})
                memify_after_stats["text_summary_count"] = text_summary_after_result[0].get("count", 0) if text_summary_after_result else 0
                
                # 统计所有节点和关系（用于计算差值）
                # 包括通过关系链匹配的TextSummary节点
                total_nodes_after_query = """
                MATCH (n)
                WHERE '__Node__' IN labels(n)
                   AND (
                       n.group_id = $group_id
                       OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                       OR (
                           'TextSummary' IN labels(n)
                           AND EXISTS {
                               (n)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                   )
                RETURN count(n) as count
                """
                total_nodes_after_result = neo4j_client.execute_query(total_nodes_after_query, {"group_id": group_id})
                memify_after_stats["total_nodes"] = total_nodes_after_result[0].get("count", 0) if total_nodes_after_result else 0
                
                total_edges_after_query = """
                MATCH (a)-[r]->(b)
                WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
                   AND (
                       (a.group_id = $group_id AND b.group_id = $group_id)
                       OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id)
                       OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id)
                       OR (
                           'TextSummary' IN labels(a)
                           AND EXISTS {
                               (a)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                       OR (
                           'TextSummary' IN labels(b)
                           AND EXISTS {
                               (b)-[:made_from]->(dc:DocumentChunk)
                               WHERE dc.group_id = $group_id
                           }
                       )
                   )
                RETURN count(DISTINCT r) as count
                """
                total_edges_after_result = neo4j_client.execute_query(total_edges_after_query, {"group_id": group_id})
                memify_after_stats["total_edges"] = total_edges_after_result[0].get("count", 0) if total_edges_after_result else 0
                
                # 计算差值
                extraction_count = max(0, memify_after_stats["text_summary_count"] - memify_before_stats["text_summary_count"])
                enrichment_count = max(0, (memify_after_stats["total_edges"] - memify_before_stats["total_edges"]))
                
                logger.info(
                    f"memify() 执行后统计: "
                    f"TextSummary={memify_after_stats['text_summary_count']} (新增={extraction_count}), "
                    f"总节点={memify_after_stats['total_nodes']} (新增={memify_after_stats['total_nodes'] - memify_before_stats['total_nodes']}), "
                    f"总关系={memify_after_stats['total_edges']} (新增={enrichment_count})"
                )
            except Exception as stats_error:
                logger.warning(f"⚠️ 统计memify()执行后的节点和关系失败: {stats_error}")
                extraction_count = 0
                enrichment_count = 0
            


            
            results["success"] = len(section_texts)
            results["section_data"] = [
                {
                    "section_uuid": meta.get("section_uuid"),
                    "title": meta.get("title"),
                    "index": meta.get("index")
                }
                for meta in section_metadata
            ]
            
            logger.info(
                f"Cognee 章节知识图谱构建完成: "
                f"总数={results['total']}, "
                f"成功={results['success']}, "
                f"失败={results['failed']}, "
                f"dataset={dataset_name}, "
                f"使用模板={'是' if custom_prompt else '否'}"
            )
            
            return {
                "success": True,
                "results": results,
                "dataset_name": dataset_name,
                "template_used": custom_prompt is not None,
                "cognify_result": cognify_result,
                "memify_result": {
                    "enabled": memify_template_mode != "default",
                    "extraction_count": extraction_count,
                    "enrichment_count": enrichment_count
                },
                "updated_nodes": {
                    "document_chunk_count": updated_chunk_count,
                    "text_summary_count": updated_text_summary_count
                }
            }
            
        except Exception as e:
            logger.error(f"Cognee 章节知识图谱构建失败: {e}", exc_info=True)
            results["failed"] = len(section_texts)
            return {
                "success": False,
                "results": results,
                "error": str(e),
                "dataset_name": None,
                "template_used": False,
                "cognify_result": {
                    "entity_count": 0,
                    "edge_count": 0,
                    "entity_types": {},
                    "edge_types": {}
                },
                "memify_result": {
                    "enabled": False,
                    "extraction_count": 0,
                    "enrichment_count": 0
                },
                "updated_nodes": {
                    "document_chunk_count": 0,
                    "text_summary_count": 0
                }
            }
    
    async def check_cognee_kg_exists(self, group_id: str) -> bool:
        """
        检查 Cognee 知识图谱是否存在
        
        Args:
            group_id: 文档组ID
            
        Returns:
            True 如果知识图谱存在，False 否则
        """
        from app.core.neo4j_client import neo4j_client
        
        try:
            # 使用 group_id 查询所有相关的节点（因为 dataset_name 每次都是唯一的）
            # Cognee 创建的节点可能有 group_id 属性，或者 dataset_name 包含 group_id
            query = """
            MATCH (n)
            WHERE '__Node__' IN labels(n)
               AND ('Entity' IN labels(n)
               OR 'DocumentChunk' IN labels(n)
               OR 'TextDocument' IN labels(n)
               OR 'EntityType' IN labels(n)
               OR 'TextSummary' IN labels(n)
               OR 'KnowledgeNode' IN labels(n))
               AND (
                   n.group_id = $group_id
                   OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                   OR (n.dataset_id IS NOT NULL AND n.dataset_id CONTAINS $group_id)
               )
            RETURN count(n) as count
            LIMIT 1
            """
            
            result = neo4j_client.execute_query(query, {
                "group_id": group_id
            })
            
            if result and len(result) > 0:
                count = result[0].get("count", 0)
                exists = count > 0
                logger.debug(f"检查 Cognee 知识图谱: group_id={group_id}, 节点数={count}, 存在={exists}")
                return exists
            
            # 方法2：检查 Cognee 内部的 dataset 记录（最可靠的方法）
            # 如果 dataset 存在，说明已经处理过，即使 Neo4j 中没有节点也应该返回 True
            try:
                from cognee.infrastructure.databases.relational import get_relational_engine
                from cognee.modules.data.models import Dataset
                from sqlalchemy import select
                
                engine = get_relational_engine()
                dataset_name = f"knowledge_base_{group_id}"
                
                async with engine.get_async_session() as session:
                    # 精确匹配
                    exact_query = select(Dataset).filter(Dataset.name == dataset_name)
                    exact_datasets = (await session.execute(exact_query)).scalars().all()
                    
                    # 模糊匹配（旧格式可能包含时间戳）
                    prefix = f"{dataset_name}_"
                    fuzzy_query = select(Dataset).filter(Dataset.name.startswith(prefix))
                    fuzzy_datasets = (await session.execute(fuzzy_query)).scalars().all()
                    
                    # 合并结果
                    all_datasets = list(exact_datasets) + list(fuzzy_datasets)
                    datasets = list({ds.id: ds for ds in all_datasets}.values())
                    
                    if datasets:
                        logger.debug(
                            f"检查 Cognee dataset: dataset_name={dataset_name}, "
                            f"找到 {len(datasets)} 个dataset记录"
                        )
                        return True
            except Exception as e:
                logger.warning(f"检查 Cognee dataset 失败: {e}，继续检查其他方法")
            
            # 方法3：检查 Milvus 中是否有对应的 collection（更可靠的方法）
            # Cognee 使用 Milvus 时，会创建名为 {dataset_name}_text 的 collection
            try:
                from app.services.milvus_service import get_milvus_service
                milvus_service = get_milvus_service()
                
                if milvus_service.is_available():
                    # 使用固定的dataset_name格式检查
                    dataset_name = f"knowledge_base_{group_id}"
                    # 检查 Milvus collection 是否存在
                    collection_name = f"{dataset_name}_text"
                    from pymilvus import utility
                    from app.core.config import settings
                    
                    # 获取 Milvus 连接别名
                    alias = "cognee_milvus"
                    
                    # 检查 collection 是否存在
                    collections = utility.list_collections(using=alias)
                    exists = collection_name in collections
                    
                    logger.debug(
                        f"检查 Milvus collection: collection_name={collection_name}, "
                        f"exists={exists}, all_collections={collections[:5]}..."
                    )
                    return exists
            except Exception as e:
                logger.warning(f"检查 Milvus collection 失败: {e}，回退到 Neo4j 检查结果")
            
            return False
            
        except Exception as e:
            logger.error(f"检查 Cognee 知识图谱是否存在时出错: {e}", exc_info=True)
            return False
    
    async def delete_cognee_kg(self, group_id: str) -> Dict[str, Any]:
        """
        删除Cognee知识图谱
        
        删除包括：
        1. Neo4j中的Cognee节点（TextDocument、DataNode、DocumentChunk、Entity、EntityType、TextSummary等）
        2. Milvus中的向量数据（相关collection）
        3. Cognee内部的dataset记录（通过Cognee API）
        
        Args:
            group_id: 文档组ID
            
        Returns:
            包含删除结果的字典
        """
        from app.core.neo4j_client import neo4j_client
        
        deletion_results = {
            "cognee_dataset": {"success": False, "message": ""},
            "neo4j": {"success": False, "deleted_count": 0},
            "milvus": {"success": False, "deleted_collections": []},
            "data_storage": {"success": False, "message": "暂不执行"}
        }
        
        try:
            # 1. 删除Cognee内部的dataset记录（使用官方 API）
            try:
                from cognee.infrastructure.databases.relational import get_relational_engine
                from cognee.modules.data.models import Dataset
                from cognee.modules.data.methods import delete_dataset
                from sqlalchemy import select
                
                engine = get_relational_engine()
                dataset_name = f"knowledge_base_{group_id}"
                
                # 查找所有匹配的dataset（精确匹配 + 模糊匹配旧格式）
                async with engine.get_async_session() as session:
                    # 先查找精确匹配
                    exact_query = select(Dataset).filter(Dataset.name == dataset_name)
                    exact_datasets = (await session.execute(exact_query)).scalars().all()
                    
                    # 再查找模糊匹配（旧格式可能包含时间戳）
                    prefix = f"{dataset_name}_"
                    fuzzy_query = select(Dataset).filter(Dataset.name.startswith(prefix))
                    fuzzy_datasets = (await session.execute(fuzzy_query)).scalars().all()
                    
                    # 合并结果并去重
                    all_datasets = list(exact_datasets) + list(fuzzy_datasets)
                    datasets = list({ds.id: ds for ds in all_datasets}.values())
                    
                    deleted_datasets = 0
                    
                    if datasets:
                        logger.info(f"找到 {len(datasets)} 个匹配的 dataset，使用官方 API 删除...")
                        
                        # 先清理 PipelineRun 记录（必须！Cognee 会检查此表判断 dataset 是否存在）
                        try:
                            from cognee.modules.pipelines.models import PipelineRun
                            from sqlalchemy import delete as sql_delete
                            
                            total_runs_deleted = 0
                            for ds in datasets:
                                # 删除该 dataset 的所有 PipelineRun 记录
                                delete_runs_query = sql_delete(PipelineRun).filter(PipelineRun.dataset_id == ds.id)
                                runs_result = await session.execute(delete_runs_query)
                                if runs_result.rowcount > 0:
                                    total_runs_deleted += runs_result.rowcount
                                    logger.info(f"  - 已删除 {runs_result.rowcount} 个 PipelineRun 记录（dataset_id: {ds.id}）")
                            
                            if total_runs_deleted > 0:
                                await session.commit()
                                logger.info(f"✅ PipelineRun 记录删除成功（共删除 {total_runs_deleted} 个）")
                        except Exception as runs_error:
                            logger.warning(f"⚠️ 删除 PipelineRun 记录失败: {runs_error}，继续执行", exc_info=True)
                        
                        # 使用官方 API 删除每个 dataset
                        # delete_dataset() 只接受一个参数（dataset对象），不需要 session
                        for ds in datasets:
                            await delete_dataset(ds)
                            deleted_datasets += 1
                            logger.info(f"  - 已删除 dataset: {ds.name} (id: {ds.id})")
                        
                        deletion_results["cognee_dataset"] = {
                            "success": True,
                            "deleted_datasets": deleted_datasets,
                            "message": f"使用官方 API 删除了 {deleted_datasets} 个 dataset"
                        }
                        logger.info(f"✅ 已删除Cognee dataset记录: {deleted_datasets} 个dataset（使用官方 API）")
                    else:
                        logger.info("未找到匹配的 dataset，无需删除")
                        deletion_results["cognee_dataset"] = {
                            "success": True,
                            "deleted_datasets": 0,
                            "message": "未找到匹配的 dataset"
                        }
            except Exception as e:
                logger.warning(f"删除Cognee dataset记录失败: {e}", exc_info=True)
                deletion_results["cognee_dataset"] = {
                    "success": False,
                    "message": str(e)
                }
            
            # 2. 删除Neo4j中的Cognee节点
            logger.info(f"开始删除Neo4j中的Cognee节点: group_id={group_id}")
            
            # 2.1 统计要删除的节点
            stats_query = """
            MATCH (n)
            WHERE '__Node__' IN labels(n)
               AND ('Entity' IN labels(n)
               OR 'DocumentChunk' IN labels(n)
               OR 'TextDocument' IN labels(n)
               OR 'EntityType' IN labels(n)
               OR 'TextSummary' IN labels(n)
               OR 'KnowledgeNode' IN labels(n)
               OR 'DataNode' IN labels(n))
               AND (
                   n.group_id = $group_id
                   OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                   OR (n.dataset_id IS NOT NULL AND n.dataset_id CONTAINS $group_id)
               )
            RETURN count(n) as node_count
            """
            stats_result = neo4j_client.execute_query(stats_query, {"group_id": group_id})
            node_count = stats_result[0].get("node_count", 0) if stats_result else 0
            
            # 2.2 删除所有相关的关系（先删除关系，避免约束问题）
            delete_relationships_query = """
            MATCH (a)-[r]->(b)
            WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
               AND (
                   (a.group_id = $group_id OR (a.dataset_name IS NOT NULL AND a.dataset_name CONTAINS $group_id))
                   OR (b.group_id = $group_id OR (b.dataset_name IS NOT NULL AND b.dataset_name CONTAINS $group_id))
               )
            DELETE r
            RETURN count(r) as deleted_count
            """
            rel_result = neo4j_client.execute_query(delete_relationships_query, {"group_id": group_id})
            rel_count = rel_result[0].get("deleted_count", 0) if rel_result else 0
            logger.info(f"已删除 {rel_count} 个关系")
            
            # 2.3 删除所有相关的节点（包括Rule节点）
            delete_nodes_query = """
            MATCH (n)
            WHERE '__Node__' IN labels(n)
               AND ('Entity' IN labels(n)
               OR 'DocumentChunk' IN labels(n)
               OR 'TextDocument' IN labels(n)
               OR 'EntityType' IN labels(n)
               OR 'TextSummary' IN labels(n)
               OR 'KnowledgeNode' IN labels(n)
               OR 'DataNode' IN labels(n))
               AND (
                   n.group_id = $group_id
                   OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                   OR (n.dataset_id IS NOT NULL AND n.dataset_id CONTAINS $group_id)
               )
            DETACH DELETE n
            RETURN count(n) as deleted_count
            """
            node_result = neo4j_client.execute_query(delete_nodes_query, {"group_id": group_id})
            deleted_count = node_result[0].get("deleted_count", 0) if node_result else 0
            
            # 2.4 删除Rule节点和NodeSet节点（通过NodeSet名称匹配）
            # Rule节点可能没有group_id属性，但通过belongs_to_set关联到NodeSet
            # NodeSet的名称是 rules_{group_id}
            rules_nodeset_name = f"rules_{group_id}"
            
            # 先查找NodeSet节点，获取其ID
            find_nodeset_query = """
            MATCH (ns:NodeSet)
            WHERE ns.name = $rules_nodeset_name
            RETURN ns.id as nodeset_id, id(ns) as nodeset_neo4j_id
            LIMIT 1
            """
            nodeset_info = neo4j_client.execute_query(find_nodeset_query, {"rules_nodeset_name": rules_nodeset_name})
            
            deleted_rules_count = 0
            deleted_nodeset_count = 0
            
            if nodeset_info and len(nodeset_info) > 0:
                nodeset_id = nodeset_info[0].get("nodeset_id")
                nodeset_neo4j_id = nodeset_info[0].get("nodeset_neo4j_id")
                
                # 删除Rule节点（通过belongs_to_set属性或关系边）
                delete_rules_query = """
                MATCH (r:Rule)
                WHERE (
                    // 通过belongs_to_set属性匹配
                    r.belongs_to_set = $nodeset_id 
                    OR r.belongs_to_set_id = $nodeset_id
                    OR (r.belongs_to_set IS NOT NULL AND toString(r.belongs_to_set) = toString($nodeset_id))
                    // 通过关系边匹配
                    OR EXISTS {
                        (r)-[:BELONGS_TO|belongs_to|HAS_MEMBER|has_member]->(ns:NodeSet)
                        WHERE ns.name = $rules_nodeset_name
                    }
                )
                DETACH DELETE r
                RETURN count(r) as deleted_count
                """
                rules_result = neo4j_client.execute_query(delete_rules_query, {
                    "nodeset_id": nodeset_id,
                    "rules_nodeset_name": rules_nodeset_name
                })
                deleted_rules_count = rules_result[0].get("deleted_count", 0) if rules_result else 0
                
                # 删除NodeSet节点
                delete_nodeset_query = """
                MATCH (ns:NodeSet)
                WHERE ns.name = $rules_nodeset_name
                DETACH DELETE ns
                RETURN count(ns) as deleted_count
                """
                nodeset_result = neo4j_client.execute_query(delete_nodeset_query, {"rules_nodeset_name": rules_nodeset_name})
                deleted_nodeset_count = nodeset_result[0].get("deleted_count", 0) if nodeset_result else 0
            
            if deleted_rules_count > 0:
                logger.info(f"✅ 已删除 {deleted_rules_count} 个Rule节点（通过NodeSet: {rules_nodeset_name}）")
            if deleted_nodeset_count > 0:
                logger.info(f"✅ 已删除 {deleted_nodeset_count} 个NodeSet节点（{rules_nodeset_name}）")
            
            # 更新删除计数
            deleted_count += deleted_rules_count + deleted_nodeset_count
            
            deletion_results["neo4j"] = {
                "success": True,
                "deleted_count": deleted_count,
                "relationship_count": rel_count
            }
            logger.info(f"✅ 已删除Neo4j中的 {deleted_count} 个Cognee节点")
            
            # 3. 删除Milvus中的向量数据
            try:
                from app.services.milvus_service import get_milvus_service
                from pymilvus import utility, Collection, connections
                # settings 已在文件开头导入，不需要重复导入
                
                milvus_service = get_milvus_service()
                if milvus_service.is_available():
                    alias = "cognee_milvus"
                    
                    # 确保连接已建立（参考 MilvusAdapter 的实现）
                    try:
                        # 检查连接是否已存在
                        if connections.has_connection(alias):
                            logger.debug(f"Milvus 连接已存在: {alias}")
                        else:
                            # 连接不存在，建立连接
                            connection_params = {
                                "host": settings.MILVUS_HOST,
                                "port": settings.MILVUS_PORT
                            }
                            if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                                connection_params["user"] = settings.MILVUS_USERNAME
                            if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                                connection_params["password"] = settings.MILVUS_PASSWORD
                            
                            connections.connect(alias=alias, **connection_params)
                            logger.info(f"✅ 已建立 Milvus 连接: {alias}")
                    except Exception as conn_error:
                        # 如果检查连接失败，尝试直接建立连接
                        logger.warning(f"检查 Milvus 连接失败: {conn_error}，尝试建立新连接")
                        try:
                            connection_params = {
                                "host": settings.MILVUS_HOST,
                                "port": settings.MILVUS_PORT
                            }
                            if hasattr(settings, 'MILVUS_USERNAME') and settings.MILVUS_USERNAME:
                                connection_params["user"] = settings.MILVUS_USERNAME
                            if hasattr(settings, 'MILVUS_PASSWORD') and settings.MILVUS_PASSWORD:
                                connection_params["password"] = settings.MILVUS_PASSWORD
                            
                            connections.connect(alias=alias, **connection_params)
                            logger.info(f"✅ 已建立 Milvus 连接: {alias}")
                        except Exception as connect_error:
                            logger.error(f"建立 Milvus 连接失败: {connect_error}")
                            raise
                    
                    all_collections = utility.list_collections(using=alias)
                    logger.info(f"📋 Milvus 中所有 collection 列表: {all_collections[:10]}... (共 {len(all_collections)} 个)")
                    
                    # 查找所有与group_id相关的collection
                    # Cognee创建的collection格式：{dataset_name}_{timestamp}_{suffix}, {dataset_name}_text等
                    dataset_name = f"knowledge_base_{group_id}"
                    related_collections = [
                        col for col in all_collections 
                        if (dataset_name in col or group_id in col)
                    ]
                    
                    if related_collections:
                        logger.warning(f"⚠️ 找到 {len(related_collections)} 个相关 collection: {related_collections}")
                    else:
                        logger.info(f"ℹ️ 未找到相关 collection（dataset_name: {dataset_name}, group_id: {group_id}）")
                    
                    deleted_collections = []
                    for collection_name in related_collections:
                        try:
                            collection = Collection(collection_name, using=alias)
                            entity_count = collection.num_entities
                            
                            # 删除collection
                            utility.drop_collection(collection_name, using=alias)
                            deleted_collections.append({
                                "name": collection_name,
                                "entity_count": entity_count
                            })
                            logger.info(f"✅ 已删除Milvus collection: {collection_name} ({entity_count} 个向量)")
                        except Exception as e:
                            logger.warning(f"删除Milvus collection {collection_name} 失败: {e}")
                    
                    deletion_results["milvus"] = {
                        "success": True,
                        "deleted_collections": deleted_collections
                    }
                else:
                    logger.warning("Milvus 不可用，跳过向量数据删除")
                    deletion_results["milvus"] = {
                        "success": False,
                        "message": "Milvus不可用"
                    }
            except Exception as e:
                logger.error(f"删除Milvus向量数据失败: {e}", exc_info=True)
                deletion_results["milvus"] = {
                    "success": False,
                    "message": str(e)
                }
            
            # 4. 清理 .data_storage 缓存（必须！Cognee 会检查此缓存判断 dataset 是否存在）
            try:
                import os
                import shutil
                import cognee
                
                # 找到 Cognee 的安装路径
                cognee_path = os.path.dirname(os.path.abspath(cognee.__file__))
                data_storage_path = os.path.join(cognee_path, ".data_storage")
                
                deleted_files = []
                if os.path.exists(data_storage_path):
                    # 查找并删除所有与 dataset_name 或 group_id 相关的文件/目录
                    for filename in os.listdir(data_storage_path):
                        file_path = os.path.join(data_storage_path, filename)
                        # 检查文件名是否包含 dataset_name 或 group_id
                        if dataset_name in filename or group_id in filename:
                            try:
                                if os.path.isdir(file_path):
                                    shutil.rmtree(file_path)
                                    logger.info(f"  - 已删除目录: {filename}")
                                else:
                                    os.remove(file_path)
                                    logger.info(f"  - 已删除文件: {filename}")
                                deleted_files.append(filename)
                            except Exception as e:
                                logger.warning(f"删除 {filename} 失败: {e}")
                    
                    if deleted_files:
                        logger.info(f"✅ .data_storage 清理成功（删除了 {len(deleted_files)} 个文件/目录）")
                        deletion_results["data_storage"] = {
                            "success": True,
                            "deleted_files": deleted_files,
                            "message": f"删除了 {len(deleted_files)} 个文件/目录"
                        }
                    else:
                        logger.debug("✅ .data_storage 中不存在相关缓存文件，无需删除")
                        deletion_results["data_storage"] = {
                            "success": True,
                            "deleted_files": [],
                            "message": "未找到相关缓存文件"
                        }
                else:
                    logger.debug("✅ .data_storage 目录不存在，无需删除")
                    deletion_results["data_storage"] = {
                        "success": True,
                        "deleted_files": [],
                        "message": ".data_storage 目录不存在"
                    }
            except Exception as storage_error:
                logger.warning(f"⚠️ 清理 .data_storage 失败: {storage_error}", exc_info=True)
                deletion_results["data_storage"] = {
                    "success": False,
                    "message": str(storage_error)
                }
            
            return {
                "success": True,
                "group_id": group_id,
                "results": deletion_results
            }
            
        except Exception as e:
            logger.error(f"删除Cognee知识图谱失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": deletion_results
            }
    
    async def ensure_cognee_kg(
        self,
        group_id: str,
        upload_id: int = None,
        provider: str = "local"
    ) -> Dict[str, Any]:
        """
        确保 Cognee 知识图谱存在，不存在则创建（按需创建）
        
        这是两阶段检索策略的核心：
        - 第一次查询慢（需要构建知识图谱）
        - 之后查询快（复用已有知识图谱）
        
        Args:
            group_id: 文档组ID
            upload_id: 文档上传ID（可选，如果提供则从数据库读取章节数据）
            provider: LLM 提供商
            
        Returns:
            包含创建状态和统计信息的字典
        """
        import time
        from app.models.document_upload import DocumentUpload
        from app.core.mysql_client import SessionLocal
        
        start_time = time.time()
        dataset_name = f"knowledge_base_{group_id}"
        
        # 检查知识图谱是否已存在
        if await self.check_cognee_kg_exists(group_id):
            elapsed_time = time.time() - start_time
            logger.info(
                f"✅ Cognee 知识图谱已存在: dataset_name={dataset_name}, "
                f"检查耗时={elapsed_time:.2f}秒"
            )
            return {
                "exists": True,
                "created": False,
                "dataset_name": dataset_name,
                "check_time": elapsed_time,
                "build_time": 0
            }
        
        # 知识图谱不存在，需要创建
        logger.info(
            f"🔨 Cognee 知识图谱不存在，开始按需创建: "
            f"dataset_name={dataset_name}, group_id={group_id}"
        )
        
        build_start_time = time.time()
        
        # 如果没有提供 upload_id，尝试从 group_id 中提取
        if upload_id is None:
            # 尝试从 group_id 中提取 upload_id（格式：doc_123 或 upload_123）
            try:
                if group_id.startswith("doc_"):
                    upload_id = int(group_id.replace("doc_", ""))
                elif group_id.startswith("upload_"):
                    upload_id = int(group_id.replace("upload_", ""))
                else:
                    # 尝试从 group_id 末尾提取数字
                    import re
                    match = re.search(r'(\d+)$', group_id)
                    if match:
                        upload_id = int(match.group(1))
                    else:
                        raise ValueError(f"无法从 group_id 中提取 upload_id: {group_id}")
            except (ValueError, AttributeError) as e:
                logger.error(f"无法从 group_id 提取 upload_id: {e}")
            return {
                "exists": False,
                "created": False,
                "error": f"无法提取 upload_id: {e}",
                "group_id": group_id
            }
        
        # 从数据库读取文档和章节数据
        db = SessionLocal()
        try:
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 检查是否有分块数据
            if not document.chunks_path or not os.path.exists(document.chunks_path):
                raise ValueError(f"文档尚未分块，无法创建知识图谱: upload_id={upload_id}")
            
            # 读取章节数据
            import json
            with open(document.chunks_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
            
            chunks = chunks_data.get("chunks", [])
            if not chunks:
                raise ValueError(f"文档没有有效的章节数据: upload_id={upload_id}")
            
            logger.info(f"读取到 {len(chunks)} 个章节，开始构建知识图谱")
            
            # 准备章节数据
            sections = []
            for idx, chunk in enumerate(chunks):
                sections.append({
                    "title": chunk.get("title", f"章节_{idx+1}"),
                    "content": chunk.get("content", ""),
                    "uuid": chunk.get("uuid", f"{group_id}_chunk_{idx+1}")
                })
            
            # 确保 Cognee 已初始化
            await self.initialize()
            
            # 构建知识图谱
            build_result = await self.build_section_knowledge_graph(
                sections=sections,
                group_id=group_id,
                provider=provider
            )
            
            build_time = time.time() - build_start_time
            total_time = time.time() - start_time
            
            logger.info(
                f"✅ Cognee 知识图谱创建完成: group_id={group_id}, "
                f"章节数={len(sections)}, 构建耗时={build_time:.2f}秒, "
                f"总耗时={total_time:.2f}秒"
            )
            
            return {
                "exists": False,
                "created": True,
                "group_id": group_id,
                "section_count": len(sections),
                "check_time": build_start_time - start_time,
                "build_time": build_time,
                "total_time": total_time,
                "build_result": build_result
            }
            
        except Exception as e:
            build_time = time.time() - build_start_time
            logger.error(
                f"❌ Cognee 知识图谱创建失败: group_id={group_id}, "
                f"错误={e}, 耗时={build_time:.2f}秒",
                exc_info=True
            )
            return {
                "exists": False,
                "created": False,
                "error": str(e),
                "group_id": group_id,
                "build_time": build_time
            }
        finally:
            db.close()
    
    async def search_sections(
        self,
        query: str,
        group_id: Optional[str] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索章节内容
        
        Args:
            query: 查询文本
            group_id: 文档组 ID（可选，用于过滤）
            top_k: 返回数量
            
        Returns:
            搜索结果列表
        """
        await self.initialize()
        
        try:
            # 如果指定了 group_id，搜索对应的 dataset
            datasets = None
            if group_id:
                # 🔥 临时方案：模糊匹配 dataset_name（兼容旧格式）
                # 旧格式：knowledge_base_{group_id}_{timestamp}_{unique_id}
                # 新格式：knowledge_base_{group_id}
                # 策略：查询所有以 "knowledge_base_{group_id}" 开头的 dataset
                try:
                    from cognee.modules.users.methods import get_default_user
                    from cognee.modules.data.methods import get_datasets
                    
                    # 获取默认用户（Cognee v0.5.x 多用户模式）
                    default_user = await get_default_user()
                    user_id = default_user.id if default_user else None
                    
                    if not user_id:
                        logger.warning("⚠️ 无法获取默认用户，回退到精确匹配")
                        datasets = f"knowledge_base_{group_id}"
                    else:
                        # 获取所有 dataset
                        all_datasets = await get_datasets(user_id)
                        
                        # 模糊匹配：找到所有以 knowledge_base_{group_id} 开头的 dataset
                        prefix = f"knowledge_base_{group_id}"
                        matched_datasets = [
                            ds for ds in all_datasets 
                            if hasattr(ds, 'name') and ds.name.startswith(prefix)
                        ]
                        
                        if not matched_datasets:
                            logger.warning(f"⚠️ 未找到匹配的 dataset，prefix={prefix}，使用精确匹配")
                            datasets = prefix
                        else:
                            # 优先使用最新的 dataset（按名称排序，最后创建的在最后）
                            matched_datasets.sort(key=lambda ds: ds.name, reverse=True)
                            datasets = matched_datasets[0].name
                            
                            logger.info(
                                f"✅ 模糊匹配成功: prefix={prefix}, "
                                f"找到 {len(matched_datasets)} 个匹配的 dataset, "
                                f"使用最新的: {datasets}"
                            )
                except Exception as match_error:
                    logger.warning(f"⚠️ 模糊匹配 dataset 失败，回退到精确匹配: {match_error}")
                datasets = f"knowledge_base_{group_id}"
            
            # 使用 Cognee 搜索
            results = await self.cognee.search(
                query_text=query,
                datasets=datasets,
                top_k=top_k
            )
            
            # 转换结果格式
            formatted_results = []
            for result in results:
                if hasattr(result, 'content'):
                    formatted_results.append({
                        "content": result.content,
                        "metadata": getattr(result, 'metadata', {}),
                        "score": getattr(result, 'score', 0.0)
                    })
                elif isinstance(result, dict):
                    formatted_results.append(result)
                else:
                    formatted_results.append({"content": str(result)})
            
            return formatted_results[:top_k]
            
        except Exception as e:
            logger.error(f"Cognee 搜索失败: {e}", exc_info=True)
            return []

