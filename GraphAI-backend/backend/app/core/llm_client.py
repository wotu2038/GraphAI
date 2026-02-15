from typing import Literal, Optional, AsyncGenerator
from openai import OpenAI
import httpx
import json
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

LLMProvider = Literal["qianwen", "deepseek", "kimi", "glm"]


class LLMClient:
    def __init__(self):
        self.qianwen_client = None
        self.deepseek_client = None
        self.kimi_client = None
        self.glm_client = None
        self._init_clients()
    
    def _init_clients(self):
        """初始化LLM客户端"""
        # 千问使用OpenAI兼容接口（支持QWEN和QIANWEN两种命名）
        self.qianwen_api_key = settings.QWEN_API_KEY or settings.QIANWEN_API_KEY
        self.qianwen_api_base = settings.QWEN_API_BASE or settings.QIANWEN_API_BASE
        self.qianwen_model = settings.QWEN_MODEL
        
        # 千问客户端（使用OpenAI兼容接口）
        if self.qianwen_api_key:
            try:
                qianwen_base_url = self.qianwen_api_base.rstrip('/')
                if "/compatible-mode/v1" not in qianwen_base_url:
                    if "/compatible-mode" not in qianwen_base_url:
                        qianwen_base_url = f"{qianwen_base_url}/compatible-mode/v1"
                    else:
                        # 如果已经有 compatible-mode，确保有 /v1
                        if not qianwen_base_url.endswith("/v1"):
                            qianwen_base_url = f"{qianwen_base_url}/v1"
                self.qianwen_client = OpenAI(
                    api_key=self.qianwen_api_key,
                    base_url=qianwen_base_url
                )
            except Exception as e:
                logger.warning(f"千问客户端初始化失败: {e}")
                self.qianwen_client = None
        
        # DeepSeek客户端（使用OpenAI兼容接口）
        if settings.DEEPSEEK_API_KEY:
            try:
                deepseek_base_url = settings.DEEPSEEK_API_BASE.rstrip('/')
                if not deepseek_base_url.endswith("/v1"):
                    if "/v1" not in deepseek_base_url:
                        deepseek_base_url = f"{deepseek_base_url}/v1"
                self.deepseek_client = OpenAI(
                    api_key=settings.DEEPSEEK_API_KEY,
                    base_url=deepseek_base_url
                )
            except Exception as e:
                logger.warning(f"DeepSeek客户端初始化失败: {e}")
                self.deepseek_client = None
        
        # Kimi客户端（使用OpenAI兼容接口）
        if settings.KIMI_API_KEY:
            try:
                kimi_base_url = settings.KIMI_API_BASE.rstrip('/')
                if not kimi_base_url.endswith("/v1"):
                    if "/v1" not in kimi_base_url:
                        kimi_base_url = f"{kimi_base_url}/v1"
                self.kimi_client = OpenAI(
                    api_key=settings.KIMI_API_KEY,
                    base_url=kimi_base_url
                )
            except Exception as e:
                logger.warning(f"Kimi客户端初始化失败: {e}")
                self.kimi_client = None
        
        # GLM客户端（使用OpenAI兼容接口）
        if settings.GLM_API_KEY:
            try:
                glm_base_url = settings.GLM_API_BASE.rstrip('/')
                if not glm_base_url.endswith("/v1"):
                    if "/v1" not in glm_base_url:
                        glm_base_url = f"{glm_base_url}/v1"
                self.glm_client = OpenAI(
                    api_key=settings.GLM_API_KEY,
                    base_url=glm_base_url
                )
            except Exception as e:
                logger.warning(f"GLM客户端初始化失败: {e}")
                self.glm_client = None
    
    async def chat(
        self,
        provider: LLMProvider,
        messages: list,
        model: Optional[str] = None,
        temperature: float = 0.7,
        use_thinking: bool = False
    ) -> str:
        """调用LLM进行对话"""
        if provider == "qianwen":
            return await self._chat_qianwen(messages, model, temperature)
        elif provider == "deepseek":
            return await self._chat_deepseek(messages, model, temperature)
        elif provider == "kimi":
            return await self._chat_kimi(messages, model, temperature)
        elif provider == "glm":
            return await self._chat_glm(messages, model, temperature)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def _chat_qianwen(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> str:
        """千问对话（OpenAI兼容接口）"""
        if not self.qianwen_client:
            raise ValueError("千问 API 未配置")
        
        model = model or self.qianwen_model
        if not model:
            raise ValueError("千问 model 未配置")
        
        # 获取 base_url
        qianwen_base_url = self.qianwen_api_base.rstrip('/')
        if "/compatible-mode/v1" not in qianwen_base_url:
            if "/compatible-mode" not in qianwen_base_url:
                qianwen_base_url = f"{qianwen_base_url}/compatible-mode/v1"
            else:
                if not qianwen_base_url.endswith("/v1"):
                    qianwen_base_url = f"{qianwen_base_url}/v1"
        
        logger.info(f"🟢 调用千问 API: model={model}, base_url={qianwen_base_url}, temperature={temperature}")
        
        # 使用异步方式调用
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.qianwen_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
            )
            logger.info(f"✅ 千问 API 调用成功: model={model}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ 千问 API 调用失败: {e}")
            raise
    
    async def _chat_deepseek(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> str:
        """DeepSeek对话（OpenAI兼容接口）"""
        if not self.deepseek_client:
            raise ValueError("DeepSeek API 未配置")
        
        model = model or settings.DEEPSEEK_MODEL
        if not model:
            raise ValueError("DeepSeek model 未配置")
        
        logger.info(f"🔵 调用 DeepSeek API: model={model}, base_url={settings.DEEPSEEK_API_BASE}, temperature={temperature}")
        
        # 使用异步方式调用
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.deepseek_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
            )
            logger.info(f"✅ DeepSeek API 调用成功: model={model}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ DeepSeek API 调用失败: {e}")
            raise
    
    async def _chat_kimi(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> str:
        """Kimi对话（OpenAI兼容接口）"""
        if not self.kimi_client:
            raise ValueError("Kimi API 未配置")
        
        model = model or settings.KIMI_MODEL
        if not model:
            raise ValueError("Kimi model 未配置")
        
        logger.info(f"🟣 调用 Kimi API: model={model}, base_url={settings.KIMI_API_BASE}, temperature={temperature}")
        
        # 使用异步方式调用
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.kimi_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
            )
            logger.info(f"✅ Kimi API 调用成功: model={model}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Kimi API 调用失败: {e}")
            raise
    
    async def _chat_glm(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> str:
        """GLM对话（OpenAI兼容接口）"""
        if not self.glm_client:
            raise ValueError("GLM API 未配置")
        
        model = model or settings.GLM_MODEL
        if not model:
            raise ValueError("GLM model 未配置")
        
        logger.info(f"🟢 调用 GLM API: model={model}, base_url={settings.GLM_API_BASE}, temperature={temperature}")
        
        # 使用异步方式调用
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.glm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
            )
            logger.info(f"✅ GLM API 调用成功: model={model}")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ GLM API 调用失败: {e}")
            raise
    
    async def _chat_local(
        self,
        messages: list,
        model: Optional[str],
        temperature: float,
        use_thinking: bool = False
    ) -> str:
        """本地大模型对话（OpenAI兼容接口）"""
        if not self.local_client:
            raise ValueError("本地大模型 API 未配置")
        
        model = model or settings.LOCAL_LLM_MODEL
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }
        
        # 如果启用Thinking模式，添加extra_body参数
        if use_thinking:
            request_params["extra_body"] = {"thinking": True}
            logger.info(f"启用Thinking模式: extra_body={request_params['extra_body']}")
        else:
            logger.info(f"未启用Thinking模式 (use_thinking={use_thinking})")
        
        # 使用异步方式调用
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.local_client.chat.completions.create(**request_params)
        )
        return response.choices[0].message.content
    
    async def chat_stream(
        self,
        provider: LLMProvider,
        messages: list,
        model: Optional[str] = None,
        temperature: float = 0.7,
        use_thinking: bool = False
    ) -> AsyncGenerator[str, None]:
        """流式调用LLM进行对话（支持 OpenAI 兼容接口的模型）"""
        if provider == "qianwen":
            async for chunk in self._chat_qianwen_stream(messages, model, temperature):
                yield chunk
        elif provider == "deepseek":
            async for chunk in self._chat_deepseek_stream(messages, model, temperature):
                yield chunk
        elif provider == "kimi":
            async for chunk in self._chat_kimi_stream(messages, model, temperature):
                yield chunk
        else:
            raise ValueError(f"流式输出不支持 provider: {provider}，支持的 provider: qianwen, deepseek, kimi")
    
    async def _chat_qianwen_stream(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> AsyncGenerator[str, None]:
        """千问流式对话（OpenAI兼容接口）"""
        if not self.qianwen_client:
            raise ValueError("千问 API 未配置")
        
        model = model or self.qianwen_model
        if not model:
            raise ValueError("千问 model 未配置")
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True  # 启用流式输出
        }
        
        logger.info(f"🟢 调用千问流式 API: model={model}, temperature={temperature}")
        
        # 使用异步方式调用流式接口
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 创建流式响应（同步调用，但返回的是流对象）
        def create_stream():
            return self.qianwen_client.chat.completions.create(**request_params)
        
        stream = await loop.run_in_executor(None, create_stream)
        
        # 异步迭代流式响应
        # 注意：OpenAI的流式响应是同步迭代器，需要在executor中迭代
        import queue
        q = queue.Queue()
        exception_holder = [None]
        finished = False
        
        def sync_iterate():
            nonlocal finished
            try:
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            q.put(delta.content)
                finished = True
                q.put(None)  # 结束标记
            except Exception as e:
                exception_holder[0] = e
                finished = True
                q.put(None)
        
        # 在后台线程中迭代
        loop.run_in_executor(None, sync_iterate)
        
        # 异步从队列中获取内容
        while not finished or not q.empty():
            try:
                # 使用超时避免无限等待
                content = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=0.5)
                )
                if content is None:
                    if exception_holder[0]:
                        raise exception_holder[0]
                    break
                yield content
            except queue.Empty:
                # 超时，继续等待（但检查是否已完成）
                if finished and q.empty():
                    break
                await asyncio.sleep(0.05)
                continue
    
    async def _chat_deepseek_stream(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> AsyncGenerator[str, None]:
        """DeepSeek流式对话（OpenAI兼容接口）"""
        if not self.deepseek_client:
            raise ValueError("DeepSeek API 未配置")
        
        model = model or settings.DEEPSEEK_MODEL
        if not model:
            raise ValueError("DeepSeek model 未配置")
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True  # 启用流式输出
        }
        
        logger.info(f"🔵 调用 DeepSeek 流式 API: model={model}, temperature={temperature}")
        
        # 使用异步方式调用流式接口
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 创建流式响应（同步调用，但返回的是流对象）
        def create_stream():
            return self.deepseek_client.chat.completions.create(**request_params)
        
        stream = await loop.run_in_executor(None, create_stream)
        
        # 异步迭代流式响应
        import queue
        q = queue.Queue()
        exception_holder = [None]
        finished = False
        
        def sync_iterate():
            nonlocal finished
            try:
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            q.put(delta.content)
                finished = True
                q.put(None)  # 结束标记
            except Exception as e:
                exception_holder[0] = e
                finished = True
                q.put(None)
        
        # 在后台线程中迭代
        loop.run_in_executor(None, sync_iterate)
        
        # 异步从队列中获取内容
        while not finished or not q.empty():
            try:
                content = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=0.5)
                )
                if content is None:
                    if exception_holder[0]:
                        raise exception_holder[0]
                    break
                yield content
            except queue.Empty:
                if finished and q.empty():
                    break
                await asyncio.sleep(0.05)
                continue
    
    async def _chat_kimi_stream(
        self,
        messages: list,
        model: Optional[str],
        temperature: float
    ) -> AsyncGenerator[str, None]:
        """Kimi流式对话（OpenAI兼容接口）"""
        if not self.kimi_client:
            raise ValueError("Kimi API 未配置")
        
        model = model or settings.KIMI_MODEL
        if not model:
            raise ValueError("Kimi model 未配置")
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True  # 启用流式输出
        }
        
        logger.info(f"🟣 调用 Kimi 流式 API: model={model}, temperature={temperature}")
        
        # 使用异步方式调用流式接口
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 创建流式响应（同步调用，但返回的是流对象）
        def create_stream():
            return self.kimi_client.chat.completions.create(**request_params)
        
        stream = await loop.run_in_executor(None, create_stream)
        
        # 异步迭代流式响应
        import queue
        q = queue.Queue()
        exception_holder = [None]
        finished = False
        
        def sync_iterate():
            nonlocal finished
            try:
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            q.put(delta.content)
                finished = True
                q.put(None)  # 结束标记
            except Exception as e:
                exception_holder[0] = e
                finished = True
                q.put(None)
        
        # 在后台线程中迭代
        loop.run_in_executor(None, sync_iterate)
        
        # 异步从队列中获取内容
        while not finished or not q.empty():
            try:
                content = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=0.5)
                )
                if content is None:
                    if exception_holder[0]:
                        raise exception_holder[0]
                    break
                yield content
            except queue.Empty:
                if finished and q.empty():
                    break
                await asyncio.sleep(0.05)
                continue
    
    async def extract_entities(
        self,
        provider: LLMProvider,
        text: str
    ) -> dict:
        """从文本中提取实体和关系"""
        prompt = f"""请从以下文本中提取实体和关系，返回JSON格式：
{{
  "entities": [
    {{"name": "实体名称", "type": "实体类型", "properties": {{"key": "value"}}}}
  ],
  "relationships": [
    {{"source": "源实体", "target": "目标实体", "type": "关系类型", "properties": {{}}}}
  ]
}}

文本内容：
{text}

只返回JSON，不要其他内容。"""
        
        messages = [
            {"role": "system", "content": "你是一个知识图谱实体抽取专家，擅长从文本中提取结构化信息。"},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.chat(provider, messages, temperature=0.3, use_thinking=False)
        
        # 解析JSON响应
        try:
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {response}")
            return {"entities": [], "relationships": []}
    
    async def generate(
        self,
        provider: LLMProvider,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        use_thinking: bool = False
    ) -> str:
        """生成文本（基于prompt）"""
        messages = [
            {"role": "user", "content": prompt}
        ]
        return await self.chat(provider, messages, temperature=temperature, use_thinking=use_thinking)


llm_client = LLMClient()


def get_llm_client(provider: Optional[LLMProvider] = None) -> LLMClient:
    """获取LLM客户端实例"""
    return llm_client

