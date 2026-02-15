"""
文档生成Agent实现
"""
import logging
from typing import Dict, Any, Optional, List
from .state import DocumentGenerationState, GenerationStage

logger = logging.getLogger(__name__)


class ContentRetriever:
    """内容检索Agent - 使用v4.0智能检索（两阶段检索）"""
    
    @staticmethod
    async def retrieve(state: DocumentGenerationState) -> DocumentGenerationState:
        """
        根据用户问题检索相关内容
        
        检索策略（v4.0）：
        1. 阶段1: DocumentChunk_text（文本片段）单路检索 + 分数阈值过滤 + Top K选择
        2. 阶段2: Graphiti（文档级业务结构化）+ Cognee（章节级语义实体）知识图谱扩展
        """
        user_query = state["user_query"]
        retrieval_limit = state.get("retrieval_limit", 20)
        group_id = state.get("group_id")
        group_ids = state.get("group_ids")
        all_documents = state.get("all_documents", False)
        top_k = state.get("top_k", retrieval_limit)  # v4.0参数
        min_score = state.get("min_score", 60.0)  # v4.0参数（0-100）
        enable_refine = state.get("enable_refine", True)  # v4.0参数
        
        logger.info(f"开始v4.0智能检索: query='{user_query}', top_k={top_k}, min_score={min_score}, enable_refine={enable_refine}")
        
        # 使用 v4.0 smartRetrieval
        from app.services.intelligent_chat_service import IntelligentChatService
        
        all_results = []
        retrieval_result = None  # 初始化，确保在try块外也可访问
        
        try:
            service = IntelligentChatService()
            
            # 确定检索范围
            target_group_ids = None
            if group_id:
                target_group_ids = [group_id]
            elif group_ids:
                target_group_ids = group_ids
            # all_documents 时 target_group_ids 为 None，表示检索全部文档
            
            # 执行v4.0智能检索
            retrieval_result = await service.smart_retrieval(
                query=user_query,
                top_k=top_k,
                min_score=min_score,
                group_ids=target_group_ids,
                enable_refine=enable_refine
            )
            
            # 转换v4.0格式为Agent需要的格式
            # v4.0返回格式: {
            #   "stage1": {"chunk_results": [...]},
            #   "stage2": {"graphiti": {"entities": [...]}, "cognee": {"entities": [...]}},
            #   "summary": {...}
            # }
            
            # 阶段1: DocumentChunk
            if retrieval_result.get("stage1") and retrieval_result["stage1"].get("chunk_results"):
                for chunk in retrieval_result["stage1"]["chunk_results"]:
                    agent_result = {
                        "type": "chunk",  # DocumentChunk
                        "name": chunk.get("chunk_name", ""),
                        "content": chunk.get("content", ""),
                        "score": chunk.get("score", 0.0) / 100.0,  # v4.0返回0-100，转换为0-1
                        "source": chunk.get("group_id", ""),
                        "raw_data": {
                            "chunk_id": chunk.get("chunk_id", ""),
                            "group_id": chunk.get("group_id", ""),
                            "doc_id": chunk.get("doc_id", ""),
                            "section_name": chunk.get("section_name", ""),
                            "document_name": chunk.get("document_name", ""),
                            "metadata": chunk.get("metadata", {})
                        }
                    }
                    all_results.append(agent_result)
            
            # 阶段2: Graphiti Entities
            if enable_refine and retrieval_result.get("stage2") and retrieval_result["stage2"].get("graphiti"):
                graphiti_entities = retrieval_result["stage2"]["graphiti"].get("entities", [])
                for entity in graphiti_entities:
                    # 参考对话模式的做法：从properties中提取内容
                    content_parts = []
                    
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "")
                    if entity_name:
                        content_parts.append(f"实体名称: {entity_name}")
                    if entity_type:
                        content_parts.append(f"类型: {entity_type}")
                    
                    # 从properties中提取关键字段
                    properties = entity.get("properties", {})
                    if isinstance(properties, dict):
                        if properties.get("description"):
                            content_parts.append(f"描述: {properties['description']}")
                        if properties.get("definition"):
                            content_parts.append(f"定义: {properties['definition']}")
                        if properties.get("specification"):
                            content_parts.append(f"规格: {properties['specification']}")
                    
                    # 如果没有properties中的字段，使用entity的description或definition
                    if not content_parts or len(content_parts) <= 2:  # 只有名称和类型
                        description = entity.get("description") or entity.get("definition", "")
                        if description:
                            content_parts.append(f"描述: {description}")
                    
                    # 组合content
                    entity_content = "\n".join(content_parts) if content_parts else entity_name or "实体信息"
                    
                    agent_result = {
                        "type": "graphiti_entity",  # Graphiti Entity
                        "name": entity_name,
                        "content": entity_content,
                        "score": entity.get("score", 0.0) / 100.0,  # v4.0返回0-100，转换为0-1
                        "source": entity.get("group_id", ""),
                        "raw_data": {
                            "uuid": entity.get("uuid", ""),
                            "type": entity_type,
                            "group_id": entity.get("group_id", ""),
                            "properties": properties,
                            "metadata": entity.get("metadata", {})
                        }
                    }
                    all_results.append(agent_result)
            
            # 阶段2: Cognee Entities
            if enable_refine and retrieval_result.get("stage2") and retrieval_result["stage2"].get("cognee"):
                cognee_entities = retrieval_result["stage2"]["cognee"].get("entities", [])
                for entity in cognee_entities:
                    # 参考对话模式的做法：从properties和related_chunks中提取内容
                    content_parts = []
                    
                    # 1. Entity名称和类型
                    entity_name = entity.get("name", "")
                    entity_type = entity.get("type", "")
                    if entity_name:
                        content_parts.append(f"实体名称: {entity_name}")
                    if entity_type:
                        content_parts.append(f"类型: {entity_type}")
                    
                    # 2. 从properties中提取关键字段（参考对话模式的formatEntityContent）
                    properties = entity.get("properties", {})
                    if isinstance(properties, dict):
                        if properties.get("description"):
                            content_parts.append(f"描述: {properties['description']}")
                        if properties.get("definition"):
                            content_parts.append(f"定义: {properties['definition']}")
                        if properties.get("specification"):
                            content_parts.append(f"规格: {properties['specification']}")
                        if properties.get("content") and isinstance(properties.get("content"), str):
                            content_text = properties["content"]
                            content_parts.append(f"内容: {content_text[:200]}{'...' if len(content_text) > 200 else ''}")
                    
                    # 3. 从related_chunks中提取关联章节信息
                    related_chunks = entity.get("related_chunks", [])
                    if related_chunks:
                        section_names = []
                        for chunk in related_chunks:
                            section_name = chunk.get("section_name") or chunk.get("content_preview", "")[:50]
                            if section_name:
                                section_names.append(section_name)
                        if section_names:
                            content_parts.append(f"关联章节: {', '.join(section_names[:3])}")  # 最多显示3个
                    
                    # 4. 组合content
                    entity_content = "\n".join(content_parts) if content_parts else entity_name or "实体信息"
                    
                    agent_result = {
                        "type": "cognee_entity",  # Cognee Entity
                        "name": entity_name,
                        "content": entity_content,
                        "score": entity.get("score", 0.0) / 100.0,  # v4.0返回0-100，转换为0-1
                        "source": entity.get("group_id", ""),
                        "raw_data": {
                            "id": entity.get("id", ""),
                            "type": entity_type,
                            "group_id": entity.get("group_id", ""),
                            "properties": properties,
                            "related_chunks": related_chunks
                        }
                    }
                    all_results.append(agent_result)
            
            logger.info(f"v4.0智能检索完成，返回 {len(all_results)} 个结果")
            
        except Exception as e:
            logger.error(f"v4.0智能检索失败: {e}", exc_info=True)
            # 如果检索失败，返回空结果，不影响后续流程
        
        # 按相关性分数排序
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # 限制数量
        retrieved_content = all_results[:retrieval_limit]
        
        # 统计各类型数量
        chunk_count = sum(1 for r in retrieved_content if r["type"] == "chunk")
        graphiti_count = sum(1 for r in retrieved_content if r["type"] == "graphiti_entity")
        cognee_count = sum(1 for r in retrieved_content if r["type"] == "cognee_entity")
        
        state["retrieved_content"] = retrieved_content
        # 保存原始检索结果（v4.0格式），用于前端显示
        if retrieval_result is not None:
            state["retrieval_result"] = retrieval_result
        state["current_stage"] = GenerationStage.RETRIEVING
        state["progress"] = 10
        state["current_step"] = f"已检索到 {len(retrieved_content)} 条相关内容（DocumentChunk: {chunk_count}, Graphiti: {graphiti_count}, Cognee: {cognee_count}）"
        
        logger.info(f"检索完成: 找到 {len(retrieved_content)} 条相关内容")
        
        return state


class DocumentGenerator:
    """文档生成Agent - 整合检索结果和相似需求生成文档"""
    
    @staticmethod
    async def generate(state: DocumentGenerationState, stream_callback=None) -> DocumentGenerationState:
        """
        生成初始文档（支持流式输出）
        
        Args:
            state: 文档生成状态
            stream_callback: 流式输出回调函数，接收(chunk: str, stage: str) -> None
        """
        from .prompts import build_generation_prompt
        from app.core.llm_client import get_llm_client
        
        # 构建生成Prompt（整合检索结果）
        retrieved_count = len(state["retrieved_content"])
        logger.info(f"DocumentGenerator: 准备生成文档，检索结果数量={retrieved_count}")
        if retrieved_count == 0:
            logger.warning("DocumentGenerator: ⚠️ 检索结果为空，将基于通用知识生成文档")
        
        prompt = build_generation_prompt(
            user_query=state["user_query"],
            retrieved_content=state["retrieved_content"],
            new_requirement=state.get("new_requirement"),
            similar_requirements=state["similar_requirements"]
        )
        
        # 调试：记录Prompt的前500字符
        logger.info(f"DocumentGenerator: Prompt前500字符: {prompt[:500]}...")
        
        # 调用LLM生成（支持流式输出）
        provider = state.get("provider", "qianwen")  # 从state读取provider，默认qianwen
        llm_client = get_llm_client(provider)
        use_thinking = state.get("use_thinking", False)
        temperature = state.get("temperature", 0.7)
        
        document = ""
        
        if stream_callback:
            # 流式生成
            async for chunk in llm_client.chat_stream(
                provider=provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                use_thinking=use_thinking
            ):
                document += chunk
                # 调用流式回调（异步）
                if stream_callback:
                    await stream_callback(chunk, "generating")
        else:
            # 非流式生成（兼容旧代码）
            document = await llm_client.generate(
                provider=provider,
                prompt=prompt,
                temperature=temperature,
                max_tokens=8000,
                use_thinking=use_thinking
            )
        
        state["current_document"] = document
        state["current_stage"] = GenerationStage.GENERATING
        state["progress"] = 40  # 生成阶段占40%（10%检索 + 30%生成）
        state["current_step"] = "文档生成完成"
        
        return state


class DocumentReviewer:
    """文档评审Agent - 评审文档质量"""
    
    @staticmethod
    async def review(state: DocumentGenerationState, stream_callback=None) -> DocumentGenerationState:
        """
        评审文档质量（支持流式输出）
        
        Args:
            state: 文档生成状态
            stream_callback: 流式输出回调函数，接收(chunk: str, stage: str) -> None
        """
        from .prompts import build_review_prompt
        from app.core.llm_client import get_llm_client
        import json
        import re
        
        # 构建评审Prompt
        prompt = build_review_prompt(state["current_document"])
        
        # 调用LLM评审（支持流式输出）
        provider = state.get("provider", "qianwen")  # 从state读取provider，默认qianwen
        llm_client = get_llm_client(provider)
        use_thinking = state.get("use_thinking", False)
        temperature = 0.3  # 评审需要更低的温度
        
        review_result = ""
        
        if stream_callback:
            # 流式生成
            async for chunk in llm_client.chat_stream(
                provider=provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                use_thinking=use_thinking
            ):
                review_result += chunk
                # 调用流式回调（异步）
                if stream_callback:
                    await stream_callback(chunk, "reviewing")
        else:
            # 非流式生成（兼容旧代码）
            review_result = await llm_client.generate(
                provider=provider,
                prompt=prompt,
                temperature=temperature,
                max_tokens=2000,
                use_thinking=use_thinking
            )
        
        # 解析评审结果（JSON格式）
        review_report = DocumentReviewer._parse_review_result(review_result)
        
        state["review_report"] = review_report
        state["quality_score"] = review_report.get("overall_score", 0.0)
        state["current_stage"] = GenerationStage.REVIEWING
        state["progress"] = 50 + (state["iteration_count"] * 10)  # 评审阶段进度
        state["current_step"] = f"文档评审完成，质量评分: {state['quality_score']:.1f}/100"
        
        return state
    
    @staticmethod
    def _parse_review_result(review_text: str) -> Dict[str, Any]:
        """解析评审结果JSON"""
        import json
        import re
        
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', review_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(review_text)
        except json.JSONDecodeError:
            logger.warning(f"评审结果解析失败，使用默认值: {review_text[:100]}")
            # 返回默认评审报告
            return {
                "overall_score": 70.0,
                "completeness_score": 70.0,
                "accuracy_score": 70.0,
                "consistency_score": 70.0,
                "readability_score": 70.0,
                "issues": ["评审结果解析失败"],
                "suggestions": []
            }


class DocumentOptimizer:
    """文档优化Agent - 根据评审结果优化文档"""
    
    @staticmethod
    async def optimize(state: DocumentGenerationState, stream_callback=None) -> DocumentGenerationState:
        """
        根据评审结果优化文档（支持流式输出）
        
        Args:
            state: 文档生成状态
            stream_callback: 流式输出回调函数，接收(chunk: str, stage: str) -> None
        """
        from .prompts import build_optimization_prompt
        from app.core.llm_client import get_llm_client
        
        # 构建优化Prompt
        prompt = build_optimization_prompt(
            state["current_document"],
            state["review_report"]
        )
        
        # 调用LLM优化（支持流式输出）
        provider = state.get("provider", "qianwen")  # 从state读取provider，默认qianwen
        llm_client = get_llm_client(provider)
        use_thinking = state.get("use_thinking", False)
        temperature = 0.5
        
        optimized_document = ""
        
        if stream_callback:
            # 流式生成
            async for chunk in llm_client.chat_stream(
                provider=provider,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                use_thinking=use_thinking
            ):
                optimized_document += chunk
                # 调用流式回调（异步）
                if stream_callback:
                    await stream_callback(chunk, "optimizing")
        else:
            # 非流式生成（兼容旧代码）
            optimized_document = await llm_client.generate(
                provider=provider,
                prompt=prompt,
                temperature=temperature,
                max_tokens=8000,
                use_thinking=use_thinking
            )
        
        state["current_document"] = optimized_document
        state["iteration_count"] += 1
        state["current_stage"] = GenerationStage.OPTIMIZING
        state["progress"] = 60 + (state["iteration_count"] * 5)  # 优化阶段进度
        state["current_step"] = f"文档优化完成（第{state['iteration_count']}次迭代）"
        
        return state


class Orchestrator:
    """协调Agent - 决定是否继续迭代"""
    
    @staticmethod
    async def decide(state: DocumentGenerationState) -> DocumentGenerationState:
        """决定是否继续迭代"""
        quality_score = state["quality_score"]
        iteration_count = state["iteration_count"]
        max_iterations = state["max_iterations"]
        quality_threshold = state["quality_threshold"]
        
        # 决策逻辑
        should_continue = (
            quality_score < quality_threshold and
            iteration_count < max_iterations
        )
        
        state["should_continue"] = should_continue
        state["is_final"] = not should_continue
        
        if not should_continue:
            state["current_stage"] = GenerationStage.COMPLETED
            state["progress"] = 100
            state["current_step"] = f"文档生成完成，最终质量评分: {quality_score:.1f}/100"
        else:
            state["current_step"] = f"需要继续优化（当前评分: {quality_score:.1f} < 阈值: {quality_threshold}）"
        
        return state
    
    @staticmethod
    def should_continue(state: DocumentGenerationState) -> str:
        """路由函数"""
        return "continue" if state["should_continue"] else "finish"

