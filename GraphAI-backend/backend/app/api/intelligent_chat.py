"""
智能对话API

提供文档入库流程和检索生成流程的分步执行API
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.core.mysql_client import SessionLocal, get_db
from sqlalchemy.orm import Session
from app.models.document_upload import DocumentUpload
from app.models.user import User
from app.core.auth import get_current_user_optional
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligent-chat", tags=["智能对话"])


# ==================== 请求模型 ====================

class PreviewTemplateRequest(BaseModel):
    """预览LLM生成的实体关系模板请求"""
    upload_id: int
    provider: str = "qianwen"
    temperature: float = 0.7
    system_prompt: Optional[str] = None  # 自定义System Prompt（可选，不传则使用默认）
    user_prompt_template: Optional[str] = None  # 自定义User Prompt模板（可选，不传则使用默认）
    parse_mode: str = "summary_parse"  # 解析模式："summary_parse"（摘要解析）或 "full_parse"（全文解析）


class Step1GraphitiEpisodeRequest(BaseModel):
    upload_id: int
    provider: str = "qianwen"
    temperature: float = 0.7
    # 模板配置（必选）
    template_mode: str  # "llm_generate" 或 "json_config"（必选，无默认值）
    template_config_json: Optional[Dict[str, Any]] = None  # JSON配置（json_config 模式时必填）
    episode_body: Optional[str] = None  # 用户自定义的 Episode body（可选）
    parse_mode: str = "summary_parse"  # 解析模式："summary_parse"（摘要解析）或 "full_parse"（全文解析）
    system_prompt: Optional[str] = None  # 自定义System Prompt（LLM生成模式）
    user_prompt_template: Optional[str] = None  # 自定义User Prompt模板（LLM生成模式）


class CognifyTemplatePreviewRequest(BaseModel):
    """Cognify 模板预览生成请求"""
    upload_id: int
    system_prompt: Optional[str] = None  # 自定义 System Prompt（可选）
    user_prompt_template: Optional[str] = None  # 自定义 User Prompt 模板（可选）
    template_type: str = "default"  # 模版类型（暂时只有 default）
    provider: str = "qianwen"  # LLM提供商：qianwen, deepseek, kimi, glm


class MemifyPromptPreviewRequest(BaseModel):
    """Memify提示词预览请求"""
    upload_id: int
    system_prompt: Optional[str] = None  # 自定义 System Prompt（可选）
    user_prompt_template: Optional[str] = None  # 自定义 User Prompt 模板（可选，支持占位符：{document_name}, {chat}, {rules}等）
    template_type: str = "default"  # 模版类型（暂时只有 default）


class MemifyRulesPreviewRequest(BaseModel):
    """Memify规则列表预览生成请求"""
    upload_id: int
    system_prompt: Optional[str] = None  # 自定义 System Prompt（可选）
    user_prompt_template: Optional[str] = None  # 自定义 User Prompt 模板（可选，支持占位符：{document_name}, {section_title}, {section_content}等）
    template_type: str = "default"  # 模版类型（暂时只有 default）
    provider: str = "qianwen"  # LLM提供商：qianwen, deepseek, kimi, glm


class Step2CogneeBuildRequest(BaseModel):
    upload_id: int
    group_id: Optional[str] = None  # 可选，如果没有则自动生成
    provider: str = "local"
    temperature: Optional[float] = 0.7  # LLM 温度参数
    # 模板配置（cognify阶段）
    cognify_template_mode: str = "llm_generate"  # "llm_generate" 或 "json_config"
    cognify_template_config_json: Optional[Dict[str, Any]] = None  # JSON配置（entity_types, edge_types, edge_type_map）
    cognify_system_prompt: Optional[str] = None  # 自定义 System Prompt（LLM生成模式时使用）
    cognify_user_prompt_template: Optional[str] = None  # 自定义 User Prompt 模板（LLM生成模式时使用）
    cognify_template_type: str = "default"  # 模版类型
    # 模板配置（memify阶段）
    memify_template_mode: str = "llm_generate"  # "llm_generate" 或 "json_config"
    memify_template_config_json: Optional[Dict[str, Any]] = None  # JSON配置（extraction和enrichment配置）
    memify_system_prompt: Optional[str] = None  # 自定义 System Prompt（LLM生成模式时使用，用于enrichment任务）
    memify_user_prompt_template: Optional[str] = None  # 自定义 User Prompt 模板（LLM生成模式时使用，用于enrichment任务）
    memify_template_type: str = "default"  # 模版类型（暂时只有 default）
    memify_rules: Optional[List[str]] = None  # LLM生成模式下，前端已生成的规则列表（可选）


class Step3MilvusVectorizeRequest(BaseModel):
    upload_id: int
    group_id: str


class Step4MilvusRecallRequest(BaseModel):
    query: str
    top_k: int = 50
    group_ids: Optional[List[str]] = None


class Step5Neo4jRefineRequest(BaseModel):
    query: str
    recall_results: List[Dict[str, Any]]


class Step6Mem0InjectRequest(BaseModel):
    query: str
    refined_results: List[Dict[str, Any]]
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class Step7LLMGenerateRequest(BaseModel):
    query: str
    retrieval_results: Optional[List[Dict[str, Any]]] = None  # 智能检索结果（v3.0格式）
    provider: str = "local"
    temperature: float = 0.7


class Mem0ChatRequest(BaseModel):
    """Mem0 独立问答请求"""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    provider: str = "local"
    temperature: float = 0.7


class SmartRetrievalRequest(BaseModel):
    """智能检索请求"""
    query: str
    top_k: int = 50
    min_score: float = 70.0  # 新增：最小分数阈值（0-100）
    group_ids: Optional[List[str]] = None
    enable_refine: bool = True


# ==================== 文档入库流程 API ====================

@router.post("/preview-template")
async def preview_template(
    request: PreviewTemplateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    预览LLM生成的实体关系模板（不执行Graphiti）
    
    用于在执行前显示和编辑 entity_types、edge_types、edge_type_map
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 检查文档是否已解析
        if not document.parsed_content_path:
            raise HTTPException(status_code=400, detail="文档尚未解析，请先完成文档解析")
        
        service = IntelligentChatService()
        result = await service.preview_graphiti_template(
            db=db,
            upload_id=request.upload_id,
            provider=request.provider,
            temperature=request.temperature,
            system_prompt=request.system_prompt,
            user_prompt_template=request.user_prompt_template,
            parse_mode=request.parse_mode
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览模板生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.get("/preview-episode-body/{upload_id}")
async def preview_episode_body(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    预览 Episode body 内容（不执行处理）
    
    用于在执行前显示和编辑 Episode body
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={upload_id}")
        
        # 检查文档是否已解析
        if not document.parsed_content_path:
            raise HTTPException(status_code=400, detail="文档尚未解析，请先完成文档解析")
        
        service = IntelligentChatService()
        result = await service.preview_episode_body(upload_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览 Episode body 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.post("/step1/graphiti-episode")
async def step1_graphiti_episode(
    request: Step1GraphitiEpisodeRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤1: Graphiti文档级处理
    
    创建文档级Episode，提取Entity和Edge
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 检查文档是否已解析
        if not document.parsed_content_path:
            raise HTTPException(status_code=400, detail="文档尚未解析，请先完成文档解析")
        
        # 验证 template_mode
        if request.template_mode not in ["llm_generate", "json_config"]:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 template_mode: {request.template_mode}，只支持 'llm_generate' 或 'json_config'"
            )
        
        # 验证 json_config 模式必须提供 template_config_json
        if request.template_mode == "json_config" and not request.template_config_json:
            raise HTTPException(
                status_code=400,
                detail="json_config 模式必须提供 template_config_json 参数"
            )
        
        service = IntelligentChatService()
        result = await service.step1_graphiti_episode(
            upload_id=request.upload_id,
            provider=request.provider,
            temperature=request.temperature,
            template_mode=request.template_mode,
            template_config_json=request.template_config_json,
            episode_body=request.episode_body,
            parse_mode=request.parse_mode,
            system_prompt=request.system_prompt,
            user_prompt_template=request.user_prompt_template
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"步骤1执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.get("/graphiti-result/{upload_id}")
async def get_graphiti_result(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    获取 Graphiti 执行结果摘要
    
    从 Neo4j 查询 Episode 信息，统计实体和关系数量，从 MySQL 查询文档信息
    返回完整的执行结果摘要
    """
    try:
        from app.core.neo4j_client import neo4j_client
        from app.core.utils import serialize_neo4j_properties
        
        # 1. 从 MySQL 查询文档信息
        document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={upload_id}")
        
        # 2. 获取 group_id（document_id）
        group_id = document.document_id
        if not group_id:
            # 文档尚未执行过 Graphiti
            return {
                "success": False,
                "message": "文档尚未执行过 Graphiti",
                "upload_id": upload_id,
                "file_name": document.file_name,
                "upload_time": document.upload_time.isoformat() if document.upload_time else None
            }
        
        # 3. 从 Neo4j 查询 Episode 信息
        episode_query = """
        MATCH (e:Episodic)
        WHERE e.group_id = $group_id
        RETURN e.uuid as episode_uuid, e.episode_id as episode_id, 
               e.doc_id as doc_id, e.version as version, e.episode_type as episode_type,
               e.created_at as created_at, properties(e) as properties
        ORDER BY e.created_at DESC
        LIMIT 1
        """
        
        episode_results = neo4j_client.execute_query(episode_query, {"group_id": group_id})
        
        if not episode_results or len(episode_results) == 0:
            # Episode 不存在
            return {
                "success": False,
                "message": "Graphiti Episode 不存在",
                "upload_id": upload_id,
                "group_id": group_id,
                "file_name": document.file_name,
                "upload_time": document.upload_time.isoformat() if document.upload_time else None
            }
        
        episode_data = episode_results[0]
        episode_uuid = episode_data.get("episode_uuid")
        episode_id = episode_data.get("episode_id")
        doc_id = episode_data.get("doc_id")
        version = episode_data.get("version")
        episode_type = episode_data.get("episode_type")
        
        # 4. 统计实体和关系数量
        entity_count_query = """
        MATCH (n:Entity)
        WHERE n.group_id = $group_id
        RETURN count(n) as entity_count
        """
        
        edge_count_query = """
        MATCH ()-[r:RELATES_TO|MENTIONS|CONTAINS|HAS_MEMBER]->()
        WHERE r.group_id = $group_id
        RETURN count(r) as edge_count
        """
        
        entity_count_result = neo4j_client.execute_query(entity_count_query, {"group_id": group_id})
        edge_count_result = neo4j_client.execute_query(edge_count_query, {"group_id": group_id})
        
        entity_count = entity_count_result[0].get("entity_count", 0) if entity_count_result else 0
        edge_count = edge_count_result[0].get("edge_count", 0) if edge_count_result else 0
        
        # 5. 统计实体类型和关系类型数量
        entity_type_query = """
        MATCH (n:Entity)
        WHERE n.group_id = $group_id
        UNWIND labels(n) as label
        WITH label
        WHERE label <> 'Entity'
        RETURN label, count(*) as count
        ORDER BY count DESC
        """
        
        edge_type_query = """
        MATCH ()-[r:RELATES_TO|MENTIONS|CONTAINS|HAS_MEMBER]->()
        WHERE r.group_id = $group_id
        RETURN type(r) as type, count(*) as count
        ORDER BY count DESC
        """
        
        entity_type_results = neo4j_client.execute_query(entity_type_query, {"group_id": group_id})
        edge_type_results = neo4j_client.execute_query(edge_type_query, {"group_id": group_id})
        
        entity_type_counts = {item.get("label"): item.get("count", 0) for item in entity_type_results} if entity_type_results else {}
        edge_type_counts = {item.get("type"): item.get("count", 0) for item in edge_type_results} if edge_type_results else {}
        
        # 6. 返回完整的执行结果摘要
        return {
            "success": True,
            "upload_id": upload_id,
            "file_name": document.file_name,
            "upload_time": document.upload_time.isoformat() if document.upload_time else None,
            "episode_uuid": episode_uuid,
            "episode_id": episode_id,
            "doc_id": doc_id,
            "group_id": group_id,
            "episode_type": episode_type,
            "version": version,
            "entity_count": entity_count,
            "edge_count": edge_count,
            "entity_type_counts": entity_type_counts,
            "edge_type_counts": edge_type_counts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Graphiti 执行结果失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/cognify-template/preview")
async def preview_cognify_template(
    request: CognifyTemplatePreviewRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    预览生成 Cognify 模板 JSON
    
    使用批次处理方案，基于所有章节生成模板，与实际执行逻辑一致
    """
    try:
        import json
        import os
        import asyncio
        from app.services.cognee_service import CogneeService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 检查文档是否已分块
        if not document.chunks_path:
            raise HTTPException(status_code=400, detail="文档尚未分块，请先完成文档分块")
        
        # 读取分块内容
        chunks_file_abs = os.path.join("/app", document.chunks_path) if not os.path.isabs(document.chunks_path) else document.chunks_path
        if not os.path.exists(chunks_file_abs):
            raise HTTPException(status_code=404, detail="分块文件不存在")
        
        with open(chunks_file_abs, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        chunks = chunks_data.get("chunks", [])
        if not chunks:
            raise HTTPException(status_code=400, detail="文档分块为空")
        
        # 准备章节数据（与实际执行逻辑一致）
        section_texts = []
        section_metadata = []
        for idx, chunk in enumerate(chunks):
            section_title = chunk.get("title", f"章节_{idx+1}")
            section_content = chunk.get("content", "")
            if not section_content.strip():
                continue
            section_texts.append(section_content)
            section_metadata.append({
                "title": section_title,
                "section_uuid": chunk.get("uuid"),
                "index": idx
            })
        
        if not section_texts:
            raise HTTPException(status_code=400, detail="没有有效的章节内容")
        
        # 使用 CogneeService 的批次处理逻辑
        cognee_service = CogneeService()
        provider = getattr(request, 'provider', 'qianwen')  # 从请求获取 provider，默认为 qianwen
        
        # 1. 将章节分组
        batches = cognee_service._group_sections_by_token_limit(
            section_texts=section_texts,
            section_metadata=section_metadata,
            provider=provider
        )
        
        # 2. 并行处理批次（最大并发数=3）
        max_concurrent = 3
        semaphore = asyncio.Semaphore(max_concurrent)
        
        system_prompt = request.system_prompt
        user_prompt_template = request.user_prompt_template
        temperature = 0.3
        
        batch_tasks = [
            cognee_service._process_batch_template(
                batch=batch,
                batch_index=i+1,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
                temperature=temperature,
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
            logger.warning(f"⚠️ 预览时 {failed_count} 个批次处理失败，继续使用成功的结果")
        
        if not successful_results:
            raise HTTPException(status_code=500, detail="所有批次处理失败，无法生成模板")
        
        # 4. 合并批次结果
        template_json = await cognee_service._merge_batch_templates(
            batch_results=successful_results,
            provider=provider
        )
        
        # 返回预览信息
        return {
            "success": True,
            "template_json": template_json,
            "preview_info": {
                "total_sections": len(section_texts),
                "total_batches": len(batches),
                "successful_batches": len(successful_results),
                "failed_batches": failed_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览模板生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览模板生成失败: {str(e)}")


@router.post("/memify-rules/preview")
async def preview_memify_rules(
    request: MemifyRulesPreviewRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    预览生成 Memify 规则列表
    
    使用批次处理方案，基于所有章节生成规则列表，与实际执行逻辑一致
    支持长文档，自动分批处理，使用LLM统一格式
    """
    logger.info(f"📥 收到规则列表生成请求: upload_id={request.upload_id}, template_type={request.template_type}")
    try:
        import json
        import os
        from app.services.cognee_service import CogneeService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 检查文档是否已分块
        if not document.chunks_path:
            raise HTTPException(status_code=400, detail="文档尚未分块，请先完成文档分块")
        
        # 读取分块内容
        chunks_file_abs = os.path.join("/app", document.chunks_path) if not os.path.isabs(document.chunks_path) else document.chunks_path
        if not os.path.exists(chunks_file_abs):
            raise HTTPException(status_code=404, detail="分块文件不存在")
        
        with open(chunks_file_abs, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        chunks = chunks_data.get("chunks", [])
        if not chunks:
            raise HTTPException(status_code=400, detail="文档分块为空")
        
        # 准备章节数据（与实际执行逻辑一致）
        section_texts = []
        section_metadata = []
        for idx, chunk in enumerate(chunks):
            section_title = chunk.get("title", f"章节_{idx+1}")
            section_content = chunk.get("content", "")
            if not section_content.strip():
                continue
            section_texts.append(section_content)
            section_metadata.append({
                "title": section_title,
                "section_uuid": chunk.get("uuid"),
                "index": idx
            })
        
        if not section_texts:
            raise HTTPException(status_code=400, detail="没有有效的章节内容")
        
        # 准备提示词
        system_prompt = request.system_prompt
        user_prompt_template = request.user_prompt_template
        
        document_name = document.file_name or "文档"
        provider = getattr(request, 'provider', 'qianwen')  # 从请求获取 provider，默认为 qianwen
        max_concurrent = 3  # 最大并发数
        
        # 使用 CogneeService 的批次处理逻辑
        cognee_service = CogneeService()
        rules = await cognee_service._generate_memify_rules_batch(
            section_texts=section_texts,
            section_metadata=section_metadata,
            document_name=document_name,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            provider=provider,
            max_concurrent=max_concurrent
        )
        
        logger.info(f"✅ 规则列表生成成功，共 {len(rules)} 条规则")
        for i, rule in enumerate(rules[:5], 1):  # 只记录前5条
            logger.info(f"  规则 {i}: {rule[:100]}...")
        
        return {
            "success": True,
            "rules": rules,
            "rules_count": len(rules),
            "document_name": document_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览规则列表生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览规则列表生成失败: {str(e)}")


@router.post("/memify-prompt/preview")
async def preview_memify_prompt(
    request: MemifyPromptPreviewRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    预览 Memify 完整提示词（替换占位符后）
    
    用于在执行前预览 enrichment 任务的完整提示词
    """
    try:
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 获取文档名称
        document_name = document.file_name or "文档"
        
        # 准备占位符数据
        placeholder_data = {
            "document_name": document_name,
            "chat": "[示例对话内容：这是从文档中提取的文本内容，用于生成规则关联]",
            "rules": "[示例规则列表：\n- 规则1：示例规则内容\n- 规则2：示例规则内容]"
        }
        
        # 获取默认提示词（如果未提供）
        if not request.system_prompt:
            # 使用默认的System Prompt
            from cognee.infrastructure.llm.prompts import render_prompt
            try:
                default_system_prompt = render_prompt("coding_rule_association_agent_system.txt", context={})
            except Exception:
                default_system_prompt = "你是一个专业的规则关联专家，擅长从对话内容中提取和关联编码规则。"
        else:
            default_system_prompt = request.system_prompt
        
        if not request.user_prompt_template:
            # 使用默认的User Prompt
            from cognee.infrastructure.llm.prompts import render_prompt
            try:
                default_user_prompt_template = render_prompt("coding_rule_association_agent_user.txt", context=placeholder_data)
            except Exception:
                default_user_prompt_template = f"""分析以下对话内容，提取并关联编码规则。

对话内容：
{{chat}}

现有规则：
{{rules}}

请提取与对话内容相关的编码规则。"""
        else:
            # 替换占位符
            default_user_prompt_template = request.user_prompt_template.replace("{document_name}", placeholder_data["document_name"])
            default_user_prompt_template = default_user_prompt_template.replace("{chat}", placeholder_data["chat"])
            default_user_prompt_template = default_user_prompt_template.replace("{rules}", placeholder_data["rules"])
        
        return {
            "success": True,
            "system_prompt": default_system_prompt,
            "user_prompt": default_user_prompt_template,
            "placeholder_data": placeholder_data,
            "message": "提示词预览成功（占位符已替换为示例数据）"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览Memify提示词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.delete("/cognee-graph/{upload_id}", response_model=Dict[str, Any])
async def delete_cognee_graph(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    删除文档的Cognee图谱数据
    
    删除包括：
    1. Neo4j中的Cognee节点（TextDocument、DataNode、DocumentChunk、Entity、EntityType等）
    2. Milvus中的向量数据（相关collection）
    3. Cognee内部的dataset记录
    """
    try:
        from app.services.cognee_service import CogneeService
        
        # 获取文档信息
        document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={upload_id}")
        
        group_id = document.document_id
        if not group_id:
            raise HTTPException(status_code=400, detail=f"文档未处理，没有group_id: upload_id={upload_id}")
        
        logger.info(f"开始删除Cognee图谱: upload_id={upload_id}, group_id={group_id}")
        
        cognee_service = CogneeService()
        result = await cognee_service.delete_cognee_kg(group_id)
        
        if result.get("success"):
            return {
                "success": True,
                "upload_id": upload_id,
                "group_id": group_id,
                "results": result.get("results", {}),
                "message": "Cognee图谱删除成功"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"删除失败: {result.get('error', '未知错误')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Cognee图谱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/step2/cognee-build")
async def step2_cognee_build(
    request: Step2CogneeBuildRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤2: Cognee章节级处理
    
    构建章节级知识图谱
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        # 检查文档是否已分块
        if not document.chunks_path:
            raise HTTPException(status_code=400, detail="文档尚未分块，请先完成文档分块")
        
        service = IntelligentChatService()
        result = await service.step2_cognee_build(
            upload_id=request.upload_id,
            group_id=request.group_id,  # 可选，如果没有则自动生成
            provider=request.provider,
            temperature=request.temperature,
            cognify_template_mode=request.cognify_template_mode,
            cognify_template_config_json=request.cognify_template_config_json,
            cognify_system_prompt=request.cognify_system_prompt,
            cognify_user_prompt_template=request.cognify_user_prompt_template,
            cognify_template_type=request.cognify_template_type,
            memify_template_mode=request.memify_template_mode,
            memify_template_config_json=request.memify_template_config_json,
            memify_system_prompt=request.memify_system_prompt,
            memify_user_prompt_template=request.memify_user_prompt_template,
            memify_template_type=request.memify_template_type,
            memify_rules=request.memify_rules
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"步骤2执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.get("/linkage/check")
async def check_linkage(
    group_id: str = Query(..., description="文档组ID"),
    upload_id: Optional[int] = Query(None, description="文档上传ID（可选，用于验证doc_id）")
):
    """
    检查 Graphiti 和 Cognee 的关联状态
    
    验证：
    1. Graphiti Episode 是否存在
    2. Cognee TextDocument 是否存在
    3. 两者之间的关联关系是否建立
    4. doc_id、group_id、version 是否一致
    """
    try:
        from app.core.neo4j_client import neo4j_client
        from app.core.mysql_client import SessionLocal
        from app.models.document_upload import DocumentUpload
        from app.services.word_document_service import WordDocumentService
        
        result = {
            "group_id": group_id,
            "graphiti": {
                "exists": False,
                "episode_uuid": None,
                "episode_id": None,
                "doc_id": None,
                "version": None
            },
            "cognee": {
                "exists": False,
                "text_document_uuid": None,
                "dataset_name": None
            },
            "linkage": {
                "established": False,
                "relation_type": None,
                "doc_id_match": False,
                "group_id_match": False,
                "version_match": False
            }
        }
        
        # 1. 查找 Graphiti Episode
        find_episode_query = """
        MATCH (e:Episodic)
        WHERE e.group_id = $group_id
        RETURN e.uuid as episode_uuid, e.episode_id as episode_id, 
               e.doc_id as doc_id, e.version as version
        ORDER BY e.created_at DESC
        LIMIT 1
        """
        
        episode_results = neo4j_client.execute_query(find_episode_query, {
            "group_id": group_id
        })
        
        if episode_results and len(episode_results) > 0:
            episode_data = episode_results[0]
            result["graphiti"]["exists"] = True
            result["graphiti"]["episode_uuid"] = episode_data.get("episode_uuid")
            result["graphiti"]["episode_id"] = episode_data.get("episode_id")
            result["graphiti"]["doc_id"] = episode_data.get("doc_id")
            result["graphiti"]["version"] = episode_data.get("version")
        
        # 2. 查找 Cognee TextDocument
        find_text_document_query = """
        MATCH (td:TextDocument)
        WHERE '__Node__' IN labels(td)
          AND 'TextDocument' IN labels(td)
        RETURN td.id as text_document_uuid, td.name as dataset_name
        ORDER BY td.created_at DESC
        LIMIT 1
        """
        
        text_doc_results = neo4j_client.execute_query(find_text_document_query)
        
        if text_doc_results and len(text_doc_results) > 0:
            text_doc_data = text_doc_results[0]
            result["cognee"]["exists"] = True
            result["cognee"]["text_document_uuid"] = text_doc_data.get("text_document_uuid")
            result["cognee"]["dataset_name"] = text_doc_data.get("dataset_name")
        
        # 3. 检查关联关系
        if result["graphiti"]["exists"] and result["cognee"]["exists"]:
            check_linkage_query = """
            MATCH (td:TextDocument {id: $text_doc_uuid})-[r]->(e:Episodic {uuid: $episode_uuid})
            RETURN type(r) as relation_type, id(r) as relation_id
            LIMIT 1
            """
            
            linkage_results = neo4j_client.execute_query(check_linkage_query, {
                "text_doc_uuid": result["cognee"]["text_document_uuid"],
                "episode_uuid": result["graphiti"]["episode_uuid"]
            })
            
            if linkage_results and len(linkage_results) > 0:
                result["linkage"]["established"] = True
                result["linkage"]["relation_type"] = linkage_results[0].get("relation_type")
            
            # 4. 验证一致性
            if upload_id:
                db = SessionLocal()
                try:
                    document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
                    if document:
                        doc_id = f"DOC_{upload_id}"
                        base_name = WordDocumentService._extract_base_name(document.file_name)
                        version, version_number = WordDocumentService._extract_version(document.file_name)
                        doc_version = version or "v1.0"
                        
                        result["linkage"]["doc_id_match"] = (result["graphiti"]["doc_id"] == doc_id)
                        result["linkage"]["group_id_match"] = True  # group_id 已匹配（通过查询条件）
                        result["linkage"]["version_match"] = (result["graphiti"]["version"] == doc_version)
                finally:
                    db.close()
        
        return result
        
    except Exception as e:
        logger.error(f"检查关联状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.get("/step2/cognee-graph")
async def get_cognee_graph(
    group_id: str = Query(..., description="文档组ID"),
    limit: int = Query(500, ge=1, le=2000, description="返回节点数量限制")
):
    """
    获取Cognee图谱数据
    
    查询指定group_id的Cognee节点和关系
    """
    try:
        from app.core.neo4j_client import neo4j_client
        from app.core.utils import serialize_neo4j_properties
        
        # 注意：Cognee 创建的节点没有 group_id、dataset_name 或 dataset_id 属性
        # 所以直接查询所有 Cognee 节点（通过标签识别）
        # 如果 Neo4j 中有多个 group_id 的节点，可能需要通过其他方式区分
        query = """
        // 查询所有 Cognee 节点（Cognee 节点没有 group_id 属性，只能通过标签查询）
        MATCH (n)
        WHERE '__Node__' IN labels(n)
           AND ('Entity' IN labels(n)
           OR 'DocumentChunk' IN labels(n)
           OR 'TextDocument' IN labels(n)
           OR 'EntityType' IN labels(n)
           OR 'TextSummary' IN labels(n)
           OR 'KnowledgeNode' IN labels(n))
        WITH collect(DISTINCT n)[0..$limit] as nodes
        
        // 查询这些节点之间的关系
        MATCH (a)-[r]->(b)
        WHERE a IN nodes AND b IN nodes
        
        WITH nodes, collect(DISTINCT r)[0..$limit] as relations
        
        RETURN 
          [node IN nodes | {
            id: id(node),
            labels: labels(node),
            properties: properties(node)
          }] as nodes,
          [rel IN relations | {
            id: id(rel),
            source: id(startNode(rel)),
            target: id(endNode(rel)),
            type: type(rel),
            properties: properties(rel)
          }] as edges
        """
        
        result = neo4j_client.execute_query(query, {
            "group_id": group_id,
            "limit": limit
        })
        
        if not result:
            return {"nodes": [], "edges": []}
        
        data = result[0]
        
        # 处理节点
        nodes_dict = {}
        for node_data in data.get("nodes", []):
            if node_data.get("id") is not None:
                node_id = str(node_data["id"])
                props = node_data.get("properties", {})
                nodes_dict[node_id] = {
                    "id": node_id,
                    "labels": node_data.get("labels", []),
                    "name": props.get("name", ""),
                    "type": node_data.get("labels", ["Node"])[0] if node_data.get("labels") else "Node",
                    "properties": serialize_neo4j_properties(props)
                }
        
        # 处理边
        edges = []
        for edge_data in data.get("edges", []):
            if edge_data.get("id") is not None and edge_data.get("source") is not None:
                source_id = str(edge_data["source"])
                target_id = str(edge_data["target"])
                # 确保source和target节点都存在
                if source_id in nodes_dict and target_id in nodes_dict:
                    edges.append({
                        "id": str(edge_data["id"]),
                        "source": source_id,
                        "target": target_id,
                        "type": edge_data.get("type", ""),
                        "properties": serialize_neo4j_properties(edge_data.get("properties", {}))
                    })
        
        return {
            "nodes": list(nodes_dict.values()),
            "edges": edges,
            "group_id": group_id
        }
        
    except Exception as e:
        logger.error(f"获取Cognee图谱数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/step3/milvus-vectorize")
async def step3_milvus_vectorize(
    request: Step3MilvusVectorizeRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤3: Milvus向量化处理
    
    生成文档摘要、Requirement、流程/规则向量并存储到Milvus
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 验证文档存在
        document = db.query(DocumentUpload).filter(DocumentUpload.id == request.upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={request.upload_id}")
        
        service = IntelligentChatService()
        result = await service.step3_milvus_vectorize(
            upload_id=request.upload_id,
            group_id=request.group_id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"步骤3执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


# ==================== 检索生成流程 API ====================

@router.post("/step4/milvus-recall")
async def step4_milvus_recall(
    request: Step4MilvusRecallRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤4: Milvus快速召回
    
    向量相似性检索，返回Top K相似结果
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.step4_milvus_recall(
            query=request.query,
            top_k=request.top_k,
            group_ids=request.group_ids
        )
        
        return result
        
    except Exception as e:
        logger.error(f"步骤4执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/step5/neo4j-refine")
async def step5_neo4j_refine(
    request: Step5Neo4jRefineRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤5: Neo4j精筛
    
    使用Graphiti和Cognee联合查询，精筛Milvus召回结果
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.step5_neo4j_refine(
            query=request.query,
            recall_results=request.recall_results
        )
        
        return result
        
    except Exception as e:
        logger.error(f"步骤5执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/step6/mem0-inject")
async def step6_mem0_inject(
    request: Step6Mem0InjectRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤6: Mem0记忆注入
    
    检索用户偏好、会话上下文、反馈记忆，注入到检索结果
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 获取用户ID
        user_id = str(current_user.id) if current_user else request.user_id or "anonymous"
        
        service = IntelligentChatService()
        result = await service.step6_mem0_inject(
            query=request.query,
            refined_results=request.refined_results,
            user_id=user_id,
            session_id=request.session_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"步骤6执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/mem0-chat")
async def mem0_chat(
    request: Mem0ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Mem0 独立问答接口
    
    用于验证 Mem0 的上下文管理能力：
    - 检索 Mem0 记忆
    - 使用 LLM 生成回答（结合记忆和对话历史）
    - 保存对话到 Mem0
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        # 获取用户ID
        user_id = str(current_user.id) if current_user else request.user_id or "anonymous"
        
        service = IntelligentChatService()
        result = await service.mem0_chat(
            query=request.query,
            user_id=user_id,
            session_id=request.session_id,
            conversation_history=request.conversation_history,
            provider=request.provider,
            temperature=request.temperature
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Mem0 问答失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/step7/llm-generate")
async def step7_llm_generate(
    request: Step7LLMGenerateRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤7: LLM生成
    
    生成新需求文档、对比分析、复用建议、风险提示
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.step7_llm_generate(
            query=request.query,
            retrieval_results=request.retrieval_results or [],
            provider=request.provider,
            temperature=request.temperature
        )
        
        return result
        
    except Exception as e:
        logger.error(f"步骤7执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/step7/llm-generate-stream")
async def step7_llm_generate_stream(
    request: Step7LLMGenerateRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    步骤7: LLM流式生成（仅主要回答）
    
    使用Server-Sent Events (SSE)流式返回生成的回答
    支持 qianwen、deepseek、kimi
    """
    try:
        logger.info(f"收到流式生成请求: query={request.query[:50]}..., provider={request.provider}, retrieval_results数量={len(request.retrieval_results or [])}")
        from app.services.intelligent_chat_service import IntelligentChatService
        
        if request.provider not in ["qianwen", "deepseek", "kimi"]:
            raise HTTPException(
                status_code=400, 
                detail=f"流式输出仅支持 qianwen、deepseek、kimi，当前provider: {request.provider}"
            )
        
        service = IntelligentChatService()
        
        async def generate():
            """生成SSE格式的流式响应"""
            try:
                import time
                stream_start_time = time.time()
                statistics = None
                
                async for chunk in service.step7_llm_generate_stream(
                    query=request.query,
                    retrieval_results=request.retrieval_results or [],
                    provider=request.provider,
                    temperature=request.temperature
                ):
                    # 检查chunk是否是统计信息（dict类型且包含__statistics__字段）
                    if isinstance(chunk, dict) and '__statistics__' in chunk:
                        statistics = chunk['__statistics__']
                    else:
                        # 普通文本chunk，SSE格式: data: {json}\n\n
                        yield f"data: {json.dumps({'content': chunk, 'done': False})}\n\n"
                
                # 流式生成完成后，发送统计信息
                if statistics:
                    yield f"data: {json.dumps({'statistics': statistics, 'done': False})}\n\n"
                else:
                    # 如果没有统计信息，计算耗时（备用方案）
                    main_answer_time = time.time() - stream_start_time
                    yield f"data: {json.dumps({'statistics': {'main_answer_time': round(main_answer_time, 2), 'temperature': request.temperature}, 'done': False})}\n\n"
                
                # 发送完成信号
                yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
            except Exception as e:
                logger.error(f"流式生成失败: {e}", exc_info=True)
                # 发送错误信息
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用Nginx缓冲
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"步骤7流式生成参数错误: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"参数错误: {str(e)}")
    except Exception as e:
        logger.error(f"步骤7流式生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


# ==================== 智能检索 API ====================

@router.post("/smart-retrieval")
async def smart_retrieval(
    request: SmartRetrievalRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    智能检索：两阶段检索策略
    
    阶段1：Milvus快速召回（文档级别）
    - 只使用Document相关的四个向量类型
    - 按文档聚合结果
    - 选择Top3文档
    
    阶段2：精细处理（文档级别）
    - 对Top3文档，使用Graphiti和Cognee知识图谱
    - 使用Milvus和Neo4j进行深度检索
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.smart_retrieval(
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score,
            group_ids=request.group_ids,
            enable_refine=request.enable_refine
        )
        
        return result
        
    except Exception as e:
        logger.error(f"智能检索执行失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


# ==================== 文档层级查询 API ====================

@router.get("/document-hierarchy/{upload_id}")
async def get_document_hierarchy(
    upload_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    获取文档的完整层级结构
    
    返回文档级别、章节级别、分块级别的所有节点和属性信息
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.get_document_hierarchy(upload_id=upload_id)
        
        return result
        
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询文档层级结构失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/chunks-cognee-mapping/{upload_id}")
async def get_chunks_cognee_mapping(
    upload_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    获取chunks与Cognee节点的映射关系
    
    返回每个chunk对应的TextDocument/DataNode和DocumentChunk信息
    """
    try:
        from app.services.intelligent_chat_service import IntelligentChatService
        
        service = IntelligentChatService()
        result = await service.get_chunks_cognee_mapping(upload_id=upload_id)
        
        return result
        
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询chunks-Cognee映射关系失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/graphiti-graph/{upload_id}", response_model=Dict[str, Any])
async def delete_graphiti_graph(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    删除文档的Graphiti图谱数据
    
    删除包括：
    1. Neo4j中的Entity、Edge、Episode、Community节点和关系
    2. Milvus中的向量数据（Episode、Entity、Edge、Community向量）
    3. MySQL中的模板配置记录（EntityEdgeTemplate）
    4. 清空DocumentUpload中的document_id字段（保留记录）
    """
    try:
        from app.core.neo4j_client import neo4j_client
        from app.services.milvus_service import MilvusService, VectorType
        from app.models.template import EntityEdgeTemplate
        
        # 1. 获取文档信息
        document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
        if not document:
            raise HTTPException(status_code=404, detail=f"文档不存在: upload_id={upload_id}")
        
        group_id = document.document_id
        if not group_id:
            raise HTTPException(status_code=400, detail=f"文档未处理，没有group_id: upload_id={upload_id}")
        
        logger.info(f"开始删除Graphiti图谱: upload_id={upload_id}, group_id={group_id}")
        
        deletion_results = {
            "neo4j": {"success": False, "details": {}},
            "milvus": {"success": False, "details": {}},
            "mysql_template": {"success": False, "details": {}},
            "mysql_document": {"success": False, "details": {}}
        }
        
        # 2. 删除Neo4j中的图谱数据
        try:
            # 2.1 统计要删除的数据
            stats_query = """
            MATCH (e:Episodic)
            WHERE e.group_id = $group_id
            WITH collect(e.uuid) as episode_uuids
            
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
            
            MATCH ()-[r:RELATES_TO|MENTIONS|CONTAINS|HAS_MEMBER]->()
            WHERE r.group_id = $group_id OR (size(episode_uuids) > 0 AND r.episode_uuid IN episode_uuids)
            
            RETURN 
              size(episode_uuids) as episode_count,
              count(DISTINCT n) as entity_count,
              count(DISTINCT r) as relationship_count
            """
            
            stats_result = neo4j_client.execute_query(stats_query, {"group_id": group_id})
            stats = stats_result[0] if stats_result else {}
            episode_count = stats.get("episode_count", 0)
            entity_count = stats.get("entity_count", 0)
            relationship_count = stats.get("relationship_count", 0)
            
            # 2.2 删除所有相关的关系（先删除关系，避免约束问题）
            delete_relationships_query = """
            MATCH (e:Episodic)
            WHERE e.group_id = $group_id
            WITH collect(e.uuid) as episode_uuids
            
            MATCH ()-[r:RELATES_TO|MENTIONS|CONTAINS|HAS_MEMBER]->()
            WHERE r.group_id = $group_id OR (size(episode_uuids) > 0 AND r.episode_uuid IN episode_uuids)
            DELETE r
            RETURN count(r) as deleted_count
            """
            
            neo4j_client.execute_write(delete_relationships_query, {"group_id": group_id})
            logger.info(f"已删除 {relationship_count} 个关系")
            
            # 2.3 删除所有相关的Entity节点
            delete_entities_query = """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
            DETACH DELETE n
            RETURN count(n) as deleted_count
            """
            
            neo4j_client.execute_write(delete_entities_query, {"group_id": group_id})
            logger.info(f"已删除 {entity_count} 个实体")
            
            # 2.4 删除所有相关的Episode节点
            delete_episodes_query = """
            MATCH (e:Episodic)
            WHERE e.group_id = $group_id
            DETACH DELETE e
            RETURN count(e) as deleted_count
            """
            
            neo4j_client.execute_write(delete_episodes_query, {"group_id": group_id})
            logger.info(f"已删除 {episode_count} 个Episode")
            
            # 2.5 删除所有相关的Community节点
            count_communities_query = """
            MATCH (c:Community)
            WHERE (c.group_id = $group_id OR 
                   (c.group_id IS NOT NULL AND 
                    (toString(c.group_id) CONTAINS $group_id OR 
                     $group_id IN c.group_id)))
            RETURN count(c) as deleted_count
            """
            count_result = neo4j_client.execute_query(count_communities_query, {"group_id": group_id})
            deleted_communities = count_result[0].get("deleted_count", 0) if count_result else 0
            
            delete_communities_query = """
            MATCH (c:Community)
            WHERE (c.group_id = $group_id OR 
                   (c.group_id IS NOT NULL AND 
                    (toString(c.group_id) CONTAINS $group_id OR 
                     $group_id IN c.group_id)))
            DETACH DELETE c
            """
            neo4j_client.execute_write(delete_communities_query, {"group_id": group_id})
            logger.info(f"已删除 {deleted_communities} 个Community")
            
            deletion_results["neo4j"] = {
                "success": True,
                "details": {
                    "episode_count": episode_count,
                    "entity_count": entity_count,
                    "relationship_count": relationship_count,
                    "community_count": deleted_communities
                }
            }
        except Exception as e:
            logger.error(f"删除Neo4j图谱数据失败: {e}", exc_info=True)
            deletion_results["neo4j"] = {
                "success": False,
                "error": str(e)
            }
        
        # 3. 删除Milvus中的向量数据
        try:
            milvus_service = MilvusService()
            deleted_vectors = {}
            vector_errors = {}
            
            for vector_type in VectorType:
                try:
                    if milvus_service.delete_by_group_id(vector_type, group_id):
                        deleted_vectors[vector_type.value] = True
                    else:
                        deleted_vectors[vector_type.value] = False
                        vector_errors[vector_type.value] = "删除返回False（可能collection未加载或数据不存在）"
                except Exception as e:
                    deleted_vectors[vector_type.value] = False
                    vector_errors[vector_type.value] = str(e)
                    logger.error(f"删除 {vector_type.value} 向量失败: {e}", exc_info=True)
            
            deletion_results["milvus"] = {
                "success": all(deleted_vectors.values()),
                "details": deleted_vectors,
                "errors": vector_errors if vector_errors else None
            }
            logger.info(f"已删除Milvus向量: {deleted_vectors}")
            if vector_errors:
                logger.warning(f"Milvus向量删除部分失败: {vector_errors}")
        except Exception as e:
            logger.error(f"删除Milvus向量失败: {e}", exc_info=True)
            deletion_results["milvus"] = {
                "success": False,
                "error": str(e)
            }
        
        # 4. 删除MySQL中的模板配置记录
        try:
            templates = db.query(EntityEdgeTemplate).filter(
                EntityEdgeTemplate.source_document_id == upload_id,
                EntityEdgeTemplate.analysis_mode == "graphiti_document"
            ).all()
            
            template_count = len(templates)
            for template in templates:
                db.delete(template)
            
            db.commit()
            logger.info(f"已删除 {template_count} 个模板配置记录")
            
            deletion_results["mysql_template"] = {
                "success": True,
                "details": {"deleted_count": template_count}
            }
        except Exception as e:
            db.rollback()
            logger.error(f"删除MySQL模板配置记录失败: {e}", exc_info=True)
            deletion_results["mysql_template"] = {
                "success": False,
                "error": str(e)
            }
        
        # 5. 清空DocumentUpload中的document_id字段（保留记录）
        try:
            document.document_id = None
            db.commit()
            logger.info(f"已清空文档的document_id字段")
            
            deletion_results["mysql_document"] = {
                "success": True,
                "details": {"cleared": True}
            }
        except Exception as e:
            db.rollback()
            logger.error(f"清空文档document_id字段失败: {e}", exc_info=True)
            deletion_results["mysql_document"] = {
                "success": False,
                "error": str(e)
            }
        
        # 6. 汇总结果
        all_success = all([
            deletion_results["neo4j"]["success"],
            deletion_results["milvus"]["success"],
            deletion_results["mysql_template"]["success"],
            deletion_results["mysql_document"]["success"]
        ])
        
        if all_success:
            logger.info(f"Graphiti图谱删除成功: upload_id={upload_id}, group_id={group_id}")
            return {
                "success": True,
                "message": "图谱删除成功",
                "upload_id": upload_id,
                "group_id": group_id,
                "deletion_results": deletion_results
            }
        else:
            # 部分成功，返回详细错误信息
            errors = []
            for key, result in deletion_results.items():
                if not result["success"]:
                    error_msg = result.get('error', '未知错误')
                    # 如果是Milvus错误，尝试获取更详细的错误信息
                    if key == "milvus" and result.get("errors"):
                        error_details = []
                        for vec_type, vec_error in result["errors"].items():
                            error_details.append(f"{vec_type}: {vec_error}")
                        if error_details:
                            error_msg = "; ".join(error_details)
                    errors.append(f"{key}: {error_msg}")
            
            logger.warning(f"Graphiti图谱删除部分成功: upload_id={upload_id}, errors={errors}")
            return {
                "success": False,
                "message": f"图谱删除部分成功，部分失败: {', '.join(errors)}",
                "upload_id": upload_id,
                "group_id": group_id,
                "deletion_results": deletion_results
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Graphiti图谱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

