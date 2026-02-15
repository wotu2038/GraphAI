"""
Mem0 客户端配置

用于对话记忆管理的持久化记忆层
"""
import logging
from typing import Optional
from mem0 import Memory
from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局 Mem0 实例
_mem0_instance: Optional[Memory] = None


def get_mem0_client() -> Memory:
    """
    获取 Mem0 客户端实例（单例模式）
    
    Returns:
        Memory: Mem0 客户端实例
    """
    global _mem0_instance
    
    if _mem0_instance is not None:
        return _mem0_instance
    
    try:
        import os
        # 步骤1：设置环境变量，让 Mem0 的 OpenAI provider 使用本地 LLM
        # Mem0 的 OpenAI provider 会自动从环境变量读取 OPENAI_API_KEY 和 OPENAI_BASE_URL
        # 确保 base_url 包含 /v1（OpenAI 兼容接口需要）
        local_base_url = settings.LOCAL_LLM_API_BASE_URL.rstrip('/')
        if not local_base_url.endswith("/v1"):
            if "/v1" not in local_base_url:
                local_base_url = f"{local_base_url}/v1"
        
        os.environ["OPENAI_API_KEY"] = settings.LOCAL_LLM_API_KEY or "not-needed"
        os.environ["OPENAI_BASE_URL"] = local_base_url
        
        # 步骤2：配置向量存储（使用远程 Milvus）
        # bge-large-zh-v1.5 的维度是 1024
        # 根据 Mem0 源码和 MilvusClient 文档：
        # - url 参数：完整的 URI，可以在 URI 中包含认证信息（格式：http://username:password@host:port）
        # - token 参数：用于 Zilliz Cloud 的 API key，对于本地 Milvus 使用用户名密码时，token 可以为空字符串
        milvus_url = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
        # 如果启用了认证，在 URL 中包含用户名和密码
        if settings.MILVUS_USERNAME and settings.MILVUS_PASSWORD:
            milvus_url = f"http://{settings.MILVUS_USERNAME}:{settings.MILVUS_PASSWORD}@{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
        
        vector_store_config = {
            "collection_name": "mem0_memories",  # Mem0 记忆集合名称
            "embedding_model_dims": 1024,  # bge-large-zh-v1.5 的维度
            "url": milvus_url,  # 远程 Milvus URL（包含认证信息）
            "token": "",  # 对于使用用户名密码的 Milvus，token 为空字符串
        }
        
        # 步骤3：配置 Mem0
        # LLM: 使用本地大模型（通过 OpenAI 兼容接口，base_url 通过环境变量传递）
        # Embedder: 使用远程 Ollama（独立的配置）
        # Vector Store: 使用远程 Milvus
        config = {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": settings.LOCAL_LLM_MODEL,
                    # base_url 和 api_key 通过环境变量 OPENAI_BASE_URL 和 OPENAI_API_KEY 传递
                }
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": settings.OLLAMA_EMBEDDING_MODEL,
                    "ollama_base_url": settings.OLLAMA_BASE_URL,
                }
            },
            "vector_store": {
                "provider": "milvus",
                "config": vector_store_config,
            },
        }
        
        # 步骤3：使用 from_config 方法创建 Memory 实例
        _mem0_instance = Memory.from_config(config)
        
        logger.info(f"Mem0 客户端初始化成功")
        logger.info(f"  - LLM: {settings.LOCAL_LLM_MODEL} (via {settings.LOCAL_LLM_API_BASE_URL})")
        logger.info(f"  - Embedder: {settings.OLLAMA_EMBEDDING_MODEL} (via {settings.OLLAMA_BASE_URL})")
        
        return _mem0_instance
        
    except Exception as e:
        logger.error(f"Mem0 客户端初始化失败: {e}")
        # 如果初始化失败，返回一个空实现以避免崩溃
        # 实际使用时需要处理这种情况
        raise


def clear_mem0_instance():
    """清除 Mem0 实例（用于测试）"""
    global _mem0_instance
    _mem0_instance = None

