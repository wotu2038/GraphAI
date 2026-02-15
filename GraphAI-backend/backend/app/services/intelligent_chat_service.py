"""
智能对话服务

实现文档入库流程和检索生成流程的分步执行
"""
import logging
import asyncio
import re
import json
import os
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime
from app.core.graphiti_client import get_graphiti_instance
from app.core.neo4j_client import neo4j_client
from app.core.embedding_client import embedding_client
from app.core.llm_client import LLMClient
# Mem0 延迟导入，只在步骤6需要时导入
# from app.core.mem0_client import get_mem0_client
from app.services.milvus_service import get_milvus_service, VectorType
from app.services.cognee_service import get_cognee, CogneeService
from app.services.graphiti_service import GraphitiService
from app.core.mysql_client import SessionLocal
from sqlalchemy.orm import Session
from app.models.document_upload import DocumentUpload
from app.models.graphiti_entities import (
    LIGHTWEIGHT_ENTITY_TYPES,
    LIGHTWEIGHT_EDGE_TYPES,
    LIGHTWEIGHT_EDGE_TYPE_MAP
)
from app.core.utils import serialize_neo4j_properties
from app.services.template_service import TemplateService
from app.services.template_generation_service import TemplateGenerationService
from app.models.template import EntityEdgeTemplate
from typing import Type
from pydantic import BaseModel
import os
import json

logger = logging.getLogger(__name__)


class IntelligentChatService:
    """智能对话服务"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.milvus = get_milvus_service()
    
    # ==================== 文档入库流程 ====================
    
    async def _save_graphiti_template_to_db(
        self,
        template_config: Dict[str, Any],
        upload_id: int,
        document_name: str,
        template_mode: str,  # "llm_generate" 或 "json_config"
        provider: str = "local"
    ) -> Optional[int]:
        """
        保存 Graphiti 模板到数据库
        
        Args:
            template_config: 模板配置（entity_types, edge_types, edge_type_map）
            upload_id: 文档上传ID
            document_name: 文档名称
            template_mode: 模板模式（llm_generate 或 json_config）
            provider: LLM 提供商
            
        Returns:
            模板ID（如果保存成功），否则返回 None
        """
        try:
            # 1. 验证模板配置
            is_valid, errors, warnings = TemplateService.validate_template(
                template_config.get("entity_types", {}),
                template_config.get("edge_types", {}),
                template_config.get("edge_type_map", {})
            )
            
            if not is_valid:
                logger.warning(f"Graphiti 模板验证失败，不保存: {', '.join(errors)}")
                return None
            
            logger.info(
                f"Graphiti 模板验证通过: "
                f"实体类型数={len(template_config.get('entity_types', {}))}, "
                f"关系类型数={len(template_config.get('edge_types', {}))}"
            )
            
            # 2. 生成模板名称
            doc_name = document_name.rsplit('.', 1)[0] if '.' in document_name else document_name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            mode_label = "LLM自动生成" if template_mode == "llm_generate" else "JSON手动配置"
            template_name = f"Graphiti-文档级-{mode_label}-{doc_name}-{timestamp}"
            
            # 3. 生成模板描述
            description = f"基于文档'{document_name}'的Graphiti文档级模板（{mode_label}）"
            
            # 4. 创建模板记录
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
                    is_llm_generated=(template_mode == "llm_generate"),
                    source_document_id=upload_id,
                    analysis_mode="graphiti_document",
                    llm_provider=provider,
                    generated_at=datetime.now(),
                    usage_count=0
                )
                
                db.add(template)
                db.commit()
                db.refresh(template)
                
                logger.info(
                    f"Graphiti 模板已保存到数据库: "
                    f"template_id={template.id}, "
                    f"name={template_name}, "
                    f"mode={template_mode}, "
                    f"实体类型数={len(template_config.get('entity_types', {}))}, "
                    f"关系类型数={len(template_config.get('edge_types', {}))}"
                )
                
                return template.id
            except Exception as e:
                db.rollback()
                logger.error(f"保存 Graphiti 模板到数据库失败: {e}", exc_info=True)
                return None
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"保存 Graphiti 模板到数据库时发生异常: {e}", exc_info=True)
            return None
    
    def _parse_entity_types_from_json(
        self,
        template_config: Dict[str, Any]
    ) -> Dict[str, Type[BaseModel]]:
        """
        从 JSON 配置解析实体类型为 Pydantic 模型
        
        Args:
            template_config: 模板配置
            
        Returns:
            实体类型字典 {"EntityName": PydanticModel, ...}
        """
        entity_types_config = template_config.get("entity_types", {})
        edge_types_config = template_config.get("edge_types", {})
        edge_type_map_config = template_config.get("edge_type_map", {})
        
        entity_types_dict, _, _ = TemplateService.convert_to_pydantic(
            entity_types_config,
            edge_types_config,
            edge_type_map_config
        )
        
        return entity_types_dict
    
    def _parse_edge_types_from_json(
        self,
        template_config: Dict[str, Any]
    ) -> Dict[str, Type[BaseModel]]:
        """
        从 JSON 配置解析关系类型为 Pydantic 模型
        
        Args:
            template_config: 模板配置
            
        Returns:
            关系类型字典 {"EdgeName": PydanticModel, ...}
        """
        entity_types_config = template_config.get("entity_types", {})
        edge_types_config = template_config.get("edge_types", {})
        edge_type_map_config = template_config.get("edge_type_map", {})
        
        _, edge_types_dict, _ = TemplateService.convert_to_pydantic(
            entity_types_config,
            edge_types_config,
            edge_type_map_config
        )
        
        return edge_types_dict
    
    def _parse_edge_type_map_from_json(
        self,
        template_config: Dict[str, Any]
    ) -> Dict[tuple, List[str]]:
        """
        从 JSON 配置解析关系类型映射
        
        Args:
            template_config: 模板配置
            
        Returns:
            关系类型映射字典 {("SourceEntity", "TargetEntity"): ["EdgeName1", ...]}
        """
        entity_types_config = template_config.get("entity_types", {})
        edge_types_config = template_config.get("edge_types", {})
        edge_type_map_config = template_config.get("edge_type_map", {})
        
        _, _, edge_type_map_dict = TemplateService.convert_to_pydantic(
            entity_types_config,
            edge_types_config,
            edge_type_map_config
        )
        
        return edge_type_map_dict
    
    async def _generate_episode_body(
        self,
        upload_id: int
    ) -> str:
        """
        生成 Episode body 内容
        
        Args:
            upload_id: 文档上传ID
            
        Returns:
            Episode body 文本内容
        """
        from app.services.word_document_service import WordDocumentService
        
        db = SessionLocal()
        try:
            # 获取文档
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 提取文档版本信息
            base_name = WordDocumentService._extract_base_name(document.file_name)
            version, version_number = WordDocumentService._extract_version(document.file_name)
            
            # 提取文档类型（NEW / CHANGE）
            # V1 或 v1.0 为 NEW，其他版本为 CHANGE
            episode_type = "NEW"
            related_docs = []
            if version_number and version_number > 1:
                episode_type = "CHANGE"
            
            # 从优化后的 summary_content.md 提取功能概述、业务信息、系统信息、流程信息
            function_overview = None
            business_info = None
            system_info = None
            process_info = None
            
            if document.summary_content_path:
                summary_content_file_abs = os.path.join("/app", document.summary_content_path)
                if os.path.exists(summary_content_file_abs):
                    try:
                        with open(summary_content_file_abs, 'r', encoding='utf-8') as f:
                            summary_content = f.read()
                        
                        # 提取各个部分
                        summary_lines = summary_content.split('\n')
                        
                        def extract_section(section_title: str) -> Optional[str]:
                            """提取指定标题部分的内容"""
                            section_start = None
                            section_end = None
                            
                            for idx, line in enumerate(summary_lines):
                                # 查找标题行（支持 ### 或 ## 格式）
                                if line.strip() == f"### {section_title}" or line.strip() == f"## {section_title}":
                                    section_start = idx + 1
                                elif section_start is not None:
                                    # 如果遇到下一个 ### 或 ## 开头的行，说明当前部分结束
                                    if line.strip().startswith("### ") or line.strip().startswith("## "):
                                        section_end = idx
                                        break
                            
                            if section_start is not None:
                                section_content = '\n'.join(
                                    summary_lines[section_start:section_end if section_end else len(summary_lines)]
                                ).strip()
                                
                                # 去除 Markdown 格式标记，但保留结构
                                # 去除 **粗体**、*斜体*、`代码` 等格式
                                section_content = re.sub(r'\*\*([^*]+)\*\*', r'\1', section_content)
                                section_content = re.sub(r'\*([^*]+)\*', r'\1', section_content)
                                section_content = re.sub(r'`([^`]+)`', r'\1', section_content)
                                
                                return section_content if section_content else None
                            
                            return None
                        
                        # 提取各个部分
                        function_overview = extract_section("功能概述")
                        business_info = extract_section("业务信息")
                        system_info = extract_section("系统信息")
                        process_info = extract_section("流程信息")
                        
                        logger.info(
                            f"从 summary_content.md 提取内容: "
                            f"功能概述={len(function_overview) if function_overview else 0}字符, "
                            f"业务信息={len(business_info) if business_info else 0}字符, "
                            f"系统信息={len(system_info) if system_info else 0}字符, "
                            f"流程信息={len(process_info) if process_info else 0}字符"
                        )
                    except Exception as e:
                        logger.warning(f"从 summary_content.md 提取内容失败: {e}")
            
            
            # 构建 Episode body
            doc_id = f"DOC_{upload_id}"
            episode_body_parts = [
                f"文档ID: {doc_id}",
                f"文档标题: {base_name or document.file_name.rsplit('.', 1)[0]}",
                f"文档类型: {episode_type}",
                f"版本号: {version or 'v1.0'}",
                f"文档上传时间: {document.upload_time.isoformat() if document.upload_time else datetime.now().isoformat()}",
            ]
            
            if related_docs:
                episode_body_parts.append(f"关联文档: {', '.join(related_docs)}")
            
            # 添加从 summary_content.md 提取的内容
            if function_overview:
                episode_body_parts.append(f"\n功能概述:\n{function_overview}")
            
            if business_info:
                episode_body_parts.append(f"\n业务信息:\n{business_info}")
            
            if system_info:
                episode_body_parts.append(f"\n系统信息:\n{system_info}")
            
            if process_info:
                episode_body_parts.append(f"\n流程信息:\n{process_info}")
            
            # 构建 episode_body
            episode_body = "\n".join(episode_body_parts)
            
            # 验证长度：确保不超过3000字符
            if len(episode_body) > 3000:
                logger.warning(f"Episode body 超过3000字符，已截断: {len(episode_body)}")
                episode_body = episode_body[:3000]
            
            logger.info(
                f"Episode body 生成完成: 长度={len(episode_body)} 字符, "
                f"文档类型={episode_type}, "
                f"功能概述={'是' if function_overview else '否'}, "
                f"业务信息={'是' if business_info else '否'}, "
                f"系统信息={'是' if system_info else '否'}, "
                f"流程信息={'是' if process_info else '否'}"
            )
            
            return episode_body
            
        finally:
            db.close()
    
    async def preview_episode_body(
        self,
        upload_id: int
    ) -> Dict[str, Any]:
        """
        预览 Episode body 内容（不执行处理）
        
        Args:
            upload_id: 文档上传ID
            
        Returns:
            包含 episode_body 的字典
        """
        try:
            episode_body = await self._generate_episode_body(upload_id)
            return {
                "success": True,
                "episode_body": episode_body,
                "length": len(episode_body)
            }
        except Exception as e:
            logger.error(f"预览 Episode body 失败: {e}", exc_info=True)
            raise
    
    async def preview_graphiti_template(
        self,
        db: Session,
        upload_id: int,
        provider: str = "qianwen",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None,
        parse_mode: str = "summary_parse"
    ) -> Dict[str, Any]:
        """
        预览LLM生成的实体关系模板（不执行Graphiti）
        
        Args:
            db: 数据库会话
            upload_id: 文档上传ID
            provider: LLM提供商
            temperature: 温度参数
            system_prompt: 自定义System Prompt（可选，不传则使用Git已提交版本的默认值）
            user_prompt_template: 自定义User Prompt模板（可选，不传则使用Git已提交版本的默认值）
            parse_mode: 解析模式："summary_parse"（摘要解析）或 "full_parse"（全文解析）
            
        Returns:
            包含 entity_types, edge_types, edge_type_map 的字典
        """
        try:
            # 验证解析模式
            if parse_mode not in ["summary_parse", "full_parse"]:
                raise ValueError(f"不支持的 parse_mode: {parse_mode}，只支持 'summary_parse' 或 'full_parse'")
            
            # 1. 获取文档信息
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 2. 根据解析模式选择数据源和方法
            if parse_mode == "summary_parse":
                # 摘要解析模式：使用 Episode Body 内容
                # 生成 Episode Body
                episode_body = await self._generate_episode_body(upload_id)
                if not episode_body:
                    raise ValueError("摘要解析模式需要 Episode Body 内容，请先完成文档解析并生成 Episode Body")
                
                logger.info(f"开始使用摘要解析模式生成模板: provider={provider}, temperature={temperature}, Episode Body 长度: {len(episode_body)} 字符")
                template_config = await TemplateGenerationService.generate_template_from_summary(
                    episode_body=episode_body,
                    document_name=document.file_name,
                    provider=provider,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template
                )
                
            elif parse_mode == "full_parse":
                # 全文解析模式：使用 parsed_content.md 完整内容
                if not document.parsed_content_path:
                    raise ValueError("全文解析模式需要文档解析内容，请先完成文档解析")
                
                parsed_content_file_abs = os.path.join("/app", document.parsed_content_path)
                if not os.path.exists(parsed_content_file_abs):
                    raise ValueError(f"文档解析内容文件不存在: {parsed_content_file_abs}")
                
                try:
                    with open(parsed_content_file_abs, 'r', encoding='utf-8') as f:
                        full_content = f.read()
                    logger.info(f"开始使用全文解析模式生成模板: provider={provider}, temperature={temperature}, 内容长度: {len(full_content)} 字符")
                except Exception as e:
                    logger.error(f"读取文档解析内容失败: {e}")
                    raise ValueError(f"读取文档解析内容失败: {e}")
                
                # 使用全文内容生成模板
                template_config = await TemplateGenerationService.generate_template_full_chunk(
                    content=full_content,
                    document_name=document.file_name,
                    provider=provider,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template
                )
            
            logger.info(
                f"模板生成成功: "
                f"实体类型数={len(template_config.get('entity_types', {}))}, "
                f"关系类型数={len(template_config.get('edge_types', {}))}, "
                f"关系映射数={len(template_config.get('edge_type_map', {}))}"
            )
            
            # 4. 返回生成的模板（JSON格式）
            return {
                "success": True,
                "template_config": template_config,
                "template_json": json.dumps(template_config, indent=2, ensure_ascii=False),
                "entity_types_count": len(template_config.get('entity_types', {})),
                "edge_types_count": len(template_config.get('edge_types', {})),
                "edge_type_map_count": len(template_config.get('edge_type_map', {}))
            }
            
        except Exception as e:
            logger.error(f"预览模板生成失败: {e}", exc_info=True)
            raise
    
    async def step1_graphiti_episode(
        self,
        upload_id: int,
        # 必选参数：用户必须选择一种模式（必须在有默认值的参数之前）
        template_mode: str,  # "llm_generate" 或 "json_config"（必选，无默认值）
        provider: str = "qianwen",
        temperature: float = 0.7,
        template_config_json: Optional[Dict[str, Any]] = None,  # JSON配置（json_config 模式时必填）
        episode_body: Optional[str] = None,  # 用户自定义的 Episode body（可选）
        parse_mode: str = "summary_parse",  # 解析模式："summary_parse"（摘要解析）或 "full_parse"（全文解析）
        system_prompt: Optional[str] = None,  # 自定义System Prompt（LLM生成模式）
        user_prompt_template: Optional[str] = None  # 自定义User Prompt模板（LLM生成模式）
    ) -> Dict[str, Any]:
        """
        步骤1: Graphiti文档级处理（轻量化设计）
        
        根据实施方案，创建轻量级的 Episode：
        - 只存储"业务事件信息"，不存正文、表格、图片
        - 用于时间线和依赖关系推理
        - 轻量化，便于快速建图
        
        Episode Content 字段：
        - episode_id: UUID
        - doc_id: 文档ID
        - type: NEW / CHANGE / DEPRECATE / DEPENDENCY
        - title: 文档标题
        - version: 文档版本号
        - created_at: 创建时间
        - related_docs: 关联文档ID列表
        - system: 所属系统/模块（可选）
        - summary: 1-2句话摘要（可选）
        - author: 创建人（可选）
        - status: ACTIVE / OBSOLETE / ARCHIVED（可选）
        
        Args:
            upload_id: 文档上传ID
            provider: LLM 提供商
            temperature: 温度参数
            template_mode: 模板模式（"llm_generate" 或 "json_config"）
            template_config_json: JSON配置（json_config 模式时必填）
        """
        # 验证 template_mode 参数
        if template_mode not in ["llm_generate", "json_config"]:
            raise ValueError(
                f"不支持的 template_mode: {template_mode}，只支持 'llm_generate' 或 'json_config'"
            )
        import uuid as uuid_lib
        from app.services.word_document_service import WordDocumentService
        
        db = SessionLocal()
        try:
            # 获取文档
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 生成或获取 group_id（统一使用标准生成规则）
            if document.document_id:
                group_id = document.document_id
                logger.info(f"使用已有的 group_id: {group_id}")
            else:
                # 使用标准规则生成 group_id
                base_name = WordDocumentService._extract_base_name(document.file_name)
                safe_base_name = WordDocumentService._sanitize_group_id(base_name)
                date_str = datetime.now().strftime('%Y%m%d')
                group_id = f"doc_{safe_base_name}_{date_str}"
                
                # 保存到数据库
                document.document_id = group_id
                db.commit()
                logger.info(f"自动生成并保存 group_id: {group_id}")
            
            # ========== 0. 检查是否已存在Episode ==========
            from app.core.neo4j_client import neo4j_client
            check_episode_query = """
            MATCH (e:Episodic)
            WHERE e.group_id = $group_id
            RETURN e.uuid as uuid, e.episode_id as episode_id, 
                   e.created_at as created_at, e.version as version
            ORDER BY e.created_at DESC
            LIMIT 1
            """
            existing_episode = neo4j_client.execute_query(check_episode_query, {"group_id": group_id})
            
            if existing_episode and len(existing_episode) > 0:
                episode_info = existing_episode[0]
                logger.warning(
                    f"⚠️ 已存在Episode: group_id={group_id}, "
                    f"episode_uuid={episode_info.get('uuid')}, "
                    f"created_at={episode_info.get('created_at')}"
                )
                # 格式化 created_at 为字符串
                created_at = episode_info.get("created_at")
                if created_at:
                    if isinstance(created_at, str):
                        created_at_str = created_at
                    else:
                        # 如果是 datetime 对象或其他格式，转换为字符串
                        # 注意：datetime 已在文件顶部导入
                        if isinstance(created_at, datetime):
                            created_at_str = created_at.isoformat()
                        else:
                            created_at_str = str(created_at)
                else:
                    created_at_str = None
                
                return {
                    "success": False,
                    "needs_confirmation": True,
                    "message": "已存在Graphiti Episode，需要删除后重建",
                    "existing_episode": {
                        "uuid": episode_info.get("uuid"),
                        "episode_id": episode_info.get("episode_id"),
                        "created_at": created_at_str,
                        "version": episode_info.get("version")
                    },
                    "group_id": group_id,
                    "upload_id": upload_id
                }
            
            # ========== 1. 提取文档元数据 ==========
            logger.info(f"开始提取文档元数据: upload_id={upload_id}, group_id={group_id}")
            
            # 提取文档版本信息
            base_name = WordDocumentService._extract_base_name(document.file_name)
            version, version_number = WordDocumentService._extract_version(document.file_name)
            
            # 提取文档类型（NEW / CHANGE）
            episode_type = "NEW"
            related_docs = []
            if version and version != "v1.0":
                episode_type = "CHANGE"
                # TODO: 查找前一个版本（后续实现）
                # previous_version = find_previous_version(document)
                # if previous_version:
                #     related_docs = [previous_version.doc_id]
            
            # 提取系统/模块信息（从文件名或元数据中提取）
            system = None
            # 优先使用下划线分隔（例如："订单系统_需求文档.docx" -> "订单系统"）
            if "_" in base_name:
                parts = base_name.split("_")
                if len(parts) > 1:
                    system = parts[0]
            # 如果没有下划线，尝试使用短横线分隔（例如："CRM-ZQ-202512-02-SD-WAN跨境直播下沉支撑.docx"）
            # 优先提取第一个有意义的部分（跳过纯数字或日期格式）
            elif "-" in base_name:
                parts = base_name.split("-")
                # 跳过纯数字、日期格式的部分，找到第一个有意义的文本
                for part in parts:
                    part = part.strip()
                    # 跳过纯数字、日期格式（如 "202512"、"02"）
                    if part and not part.isdigit() and len(part) > 1:
                        # 如果包含中文或字母，认为是系统名
                        if any(c.isalnum() for c in part):
                            system = part
                            break
            
            # ========== 2. 提取文档摘要（1-2句话）==========
            summary = None
            if document.summary_content_path and os.path.exists(document.summary_content_path):
                try:
                    with open(document.summary_content_path, 'r', encoding='utf-8') as f:
                        summary_content = f.read()
                    
                    # 提取"文档概览"部分的第一段作为摘要
                    summary_lines = summary_content.split('\n')
                    overview_start = None
                    overview_end = None
                    
                    for idx, line in enumerate(summary_lines):
                        if line.strip() == "## 文档概览":
                            overview_start = idx + 1
                        elif overview_start is not None and line.startswith("## ") and line.strip() != "## 文档概览":
                            overview_end = idx
                            break
                    
                    if overview_start is not None:
                        overview_content = '\n'.join(
                            summary_lines[overview_start:overview_end if overview_end else len(summary_lines)]
                        )
                        # 提取第一段（1-2句话）
                        paragraphs = [p.strip() for p in overview_content.split('\n\n') if p.strip()]
                        if paragraphs:
                            # 取第一段，限制在200字符以内
                            summary = paragraphs[0][:200]
                            # 如果超过200字符，截取到最后一个句号
                            if len(paragraphs[0]) > 200:
                                last_period = summary.rfind('。')
                                if last_period > 100:  # 确保至少100字符
                                    summary = summary[:last_period + 1]
                    
                    # 如果没有找到"文档概览"，使用摘要的前200字符
                    if not summary and summary_content:
                        summary = summary_content[:200]
                        last_period = summary.rfind('。')
                        if last_period > 100:
                            summary = summary[:last_period + 1]
                
                except Exception as e:
                    logger.warning(f"提取文档摘要失败: {e}")
            
            # ========== 2.5 处理模板配置（根据 template_mode）==========
            logger.info(f"开始处理模板配置: template_mode={template_mode}")
            entity_types = None
            edge_types = None
            edge_type_map = None
            template_id = None
            
            # 读取完整摘要内容（用于 LLM 生成模板）
            full_summary_content = None
            if document.summary_content_path and os.path.exists(document.summary_content_path):
                try:
                    with open(document.summary_content_path, 'r', encoding='utf-8') as f:
                        full_summary_content = f.read()
                except Exception as e:
                    logger.warning(f"读取完整摘要内容失败: {e}")
            
            if template_mode == "json_config":
                # JSON 配置模式
                if not template_config_json:
                    raise ValueError("json_config 模式必须提供 template_config_json 参数")
                
                # 验证 JSON 配置
                is_valid, errors, warnings = TemplateService.validate_template(
                    template_config_json.get("entity_types", {}),
                    template_config_json.get("edge_types", {}),
                    template_config_json.get("edge_type_map", {})
                )
                if not is_valid:
                    raise ValueError(f"JSON 配置验证失败: {', '.join(errors)}")
                
                # 解析实体和关系类型
                entity_types = self._parse_entity_types_from_json(template_config_json)
                edge_types = self._parse_edge_types_from_json(template_config_json)
                edge_type_map = self._parse_edge_type_map_from_json(template_config_json)
                
                logger.info(
                    f"JSON 配置解析成功: "
                    f"实体类型数={len(entity_types)}, "
                    f"关系类型数={len(edge_types)}, "
                    f"关系映射数={len(edge_type_map)}"
                )
                
                # 保存 JSON 配置模板到数据库
                template_id = await self._save_graphiti_template_to_db(
                    template_config=template_config_json,
                    upload_id=upload_id,
                    document_name=document.file_name,
                    template_mode="json_config",
                    provider=provider
                )
                if template_id:
                    logger.info(f"Graphiti JSON配置模板已保存: template_id={template_id}")
                    
            elif template_mode == "llm_generate":
                # LLM 生成模板模式
                if template_config_json:
                    # 如果已经提供了模板配置（预览时生成的），直接使用
                    logger.info("使用预览时生成的模板配置，跳过LLM生成")
                    template_config = template_config_json
                    
                    # 验证 JSON 配置
                    is_valid, errors, warnings = TemplateService.validate_template(
                        template_config.get("entity_types", {}),
                        template_config.get("edge_types", {}),
                        template_config.get("edge_type_map", {})
                    )
                    if not is_valid:
                        raise ValueError(f"模板配置验证失败: {', '.join(errors)}")
                    
                    # 解析实体和关系类型
                    entity_types = self._parse_entity_types_from_json(template_config)
                    edge_types = self._parse_edge_types_from_json(template_config)
                    edge_type_map = self._parse_edge_type_map_from_json(template_config)
                    
                    logger.info(
                        f"使用预览模板配置: "
                        f"实体类型数={len(entity_types)}, "
                        f"关系类型数={len(edge_types)}, "
                        f"关系映射数={len(edge_type_map)}"
                    )
                    
                    # 保存 LLM 生成模板到数据库
                    template_id = await self._save_graphiti_template_to_db(
                        template_config=template_config,
                        upload_id=upload_id,
                        document_name=document.file_name,
                        template_mode="llm_generate",
                        provider=provider
                    )
                    if template_id:
                        logger.info(f"Graphiti LLM生成模板已保存: template_id={template_id}")
                else:
                    # 如果没有提供模板配置，根据 parse_mode 调用 LLM 生成（后备方案）
                    # 验证解析模式
                    if parse_mode not in ["summary_parse", "full_parse"]:
                        raise ValueError(f"不支持的 parse_mode: {parse_mode}，只支持 'summary_parse' 或 'full_parse'")
                    
                    if parse_mode == "summary_parse":
                        # 摘要解析模式：使用 Episode Body 内容
                        # 如果用户提供了 episode_body，直接使用；否则自动生成
                        if not episode_body:
                            logger.info("未提供 episode_body，自动生成...")
                            episode_body = await self._generate_episode_body(upload_id)
                        
                        if not episode_body:
                            raise ValueError("摘要解析模式需要 Episode Body 内容，请先完成文档解析并生成 Episode Body")
                
                        logger.info(f"使用摘要解析模式生成模板，Episode Body 长度: {len(episode_body)} 字符")
                
                        # 使用 Episode Body 生成模板
                        template_config = await TemplateGenerationService.generate_template_from_summary(
                            episode_body=episode_body,
                            document_name=document.file_name,
                            provider=provider,
                            temperature=temperature,
                            system_prompt=system_prompt,
                            user_prompt_template=user_prompt_template
                        )
                        
                    elif parse_mode == "full_parse":
                        # 全文解析模式：使用 parsed_content.md 完整内容
                        if not document.parsed_content_path:
                            raise ValueError("全文解析模式需要文档解析内容，请先完成文档解析")
                        
                        parsed_content_file_abs = os.path.join("/app", document.parsed_content_path)
                        if not os.path.exists(parsed_content_file_abs):
                            raise ValueError(f"文档解析内容文件不存在: {parsed_content_file_abs}")
                        
                        try:
                            with open(parsed_content_file_abs, 'r', encoding='utf-8') as f:
                                full_content = f.read()
                            logger.info(f"使用全文解析模式生成模板，内容长度: {len(full_content)} 字符")
                        except Exception as e:
                            logger.error(f"读取文档解析内容失败: {e}")
                            raise ValueError(f"读取文档解析内容失败: {e}")
                        
                        # 使用全文内容生成模板
                        template_config = await TemplateGenerationService.generate_template_full_chunk(
                            content=full_content,
                            document_name=document.file_name,
                            provider=provider,
                            temperature=temperature,
                            system_prompt=system_prompt,
                            user_prompt_template=user_prompt_template
                )
                
                # 解析实体和关系类型
                entity_types = self._parse_entity_types_from_json(template_config)
                edge_types = self._parse_edge_types_from_json(template_config)
                edge_type_map = self._parse_edge_type_map_from_json(template_config)
                
                logger.info(
                        f"LLM 模板生成成功（{parse_mode}模式）: "
                    f"实体类型数={len(entity_types)}, "
                    f"关系类型数={len(edge_types)}, "
                    f"关系映射数={len(edge_type_map)}"
                )
                
                # 保存 LLM 生成模板到数据库
                template_id = await self._save_graphiti_template_to_db(
                    template_config=template_config,
                    upload_id=upload_id,
                    document_name=document.file_name,
                    template_mode="llm_generate",
                    provider=provider
                )
                if template_id:
                    logger.info(f"Graphiti LLM生成模板已保存: template_id={template_id}")
            
            # 验证：确保模板配置已成功解析
            if not entity_types or not edge_types:
                raise ValueError(f"模板配置解析失败: template_mode={template_mode}")
            
            # ========== 3. 构建轻量化的 Episode Content ==========
            episode_id = str(uuid_lib.uuid4())
            doc_id = f"DOC_{upload_id}"
            
            episode_content = {
                # 必须字段
                "episode_id": episode_id,
                "doc_id": doc_id,
                "type": episode_type,
                "title": base_name or document.file_name.rsplit('.', 1)[0],
                "version": version or "v1.0",
                "created_at": document.upload_time.isoformat() if document.upload_time else datetime.now().isoformat(),
                "related_docs": related_docs,
                
                # 可选字段
                "system": system,
                "summary": summary,  # 1-2句话摘要，仅用于快速理解
                "author": None,  # TODO: 从文档元数据或用户信息中提取
                "status": "ACTIVE"
            }
            
            # 轻量化验证：确保不包含正文、表格、图片
            content_str = json.dumps(episode_content, ensure_ascii=False)
            assert len(content_str) < 3000, "Episode Content 应该轻量化，不超过3000字符"
            assert "tables" not in content_str.lower(), "Episode Content 不应包含表格数据"
            assert "images" not in content_str.lower() or "image" not in content_str.lower(), "Episode Content 不应包含图片数据"
            
            # 注意：不再验证轻量化要求，因为用户可能使用自定义模板
            logger.info("Episode Content 构建完成")
            
            logger.info(
                f"Episode Content 构建完成: "
                f"episode_id={episode_id}, doc_id={doc_id}, type={episode_type}, "
                f"version={version}, summary_length={len(summary) if summary else 0}"
            )
            
            # ========== 3.5 生成或使用用户提供的 Episode body ==========
            # 如果用户提供了 episode_body，直接使用；否则自动生成
            if episode_body:
                logger.info(f"使用用户提供的 Episode body，长度: {len(episode_body)} 字符")
                # 验证长度（可选，但建议不超过3000字符）
                if len(episode_body) > 3000:
                    logger.warning(f"用户提供的 Episode body 超过3000字符: {len(episode_body)}，建议控制在3000字符以内")
            else:
                # 自动生成 Episode body
                logger.info("自动生成 Episode body")
                episode_body = await self._generate_episode_body(upload_id)
            
            # 提取章节标题数量（用于日志）
            section_titles_count = episode_body.count('\n主要章节：') > 0 and len([line for line in episode_body.split('\n') if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.'))]) or 0
            
            logger.info(f"Episode body 长度: {len(episode_body)} 字符（包含约 {section_titles_count} 个章节标题）")
            
            # ========== 4. 使用 Graphiti 创建 Episode ==========
            logger.info(f"开始创建 Graphiti Episode: group_id={group_id}")
            graphiti = get_graphiti_instance(provider)
            
            # ========== 4.1 使用配置的实体和关系类型 ==========
            logger.info(
                f"使用模板配置的实体和关系类型: "
                f"template_mode={template_mode}, "
                f"实体类型数={len(entity_types)}, "
                f"关系类型数={len(edge_types)}, "
                f"关系映射数={len(edge_type_map) if edge_type_map else 0}"
            )
            
            episode_result = await graphiti.add_episode(
                name=f"{episode_content['title']}_文档级",
                episode_body=episode_body,  # 轻量化的元数据，不是完整文档内容
                source_description="需求文档（轻量化Episode）",
                reference_time=datetime.fromisoformat(episode_content["created_at"].replace('Z', '+00:00')) if 'T' in episode_content["created_at"] else datetime.now(),
                group_id=group_id,
                # 传入模板配置的实体和关系类型
                entity_types=entity_types,
                edge_types=edge_types,
                edge_type_map=edge_type_map
            )
            
            episode_uuid = episode_result.episode.uuid
            
            # 更新 Neo4j 中的 Episode 节点，添加额外的元数据属性
            logger.info(f"更新 Episode 节点元数据: episode_uuid={episode_uuid}")
            update_episode_query = """
            MATCH (e:Episodic)
            WHERE e.uuid = $episode_uuid
            SET e.episode_id = $episode_id,
                e.doc_id = $doc_id,
                e.episode_type = $episode_type,
                e.version = $version,
                e.system = $system,
                e.status = $status,
                e.related_docs = $related_docs
            RETURN e.uuid as uuid
            """
            
            try:
                neo4j_client.execute_query(update_episode_query, {
                    "episode_uuid": episode_uuid,
                    "episode_id": episode_id,
                    "doc_id": doc_id,
                    "episode_type": episode_type,
                    "version": version or "v1.0",
                    "system": system or "",
                    "status": "ACTIVE",
                    "related_docs": json.dumps(related_docs) if related_docs else "[]"
                })
                logger.info(f"Episode 节点元数据更新成功")
            except Exception as e:
                logger.warning(f"更新 Episode 节点元数据失败: {e}，继续执行")
            
            # 等待一下，确保Graphiti已经将数据写入Neo4j
            await asyncio.sleep(2)
            
            # ========== 4.5 建立与 Cognee TextSummary 的引用关系 ==========
            logger.info(f"尝试建立与 Cognee TextSummary 的引用关系: episode_uuid={episode_uuid}, group_id={group_id}")
            text_summary_reference = {
                "established": False,
                "text_summary_id": None,
                "text_summary_uuid": None,
                "text_summary_text": None,
                "error": None
            }
            
            try:
                # 查找 Cognee TextSummary 节点
                # 问题：Cognee 创建的节点（TextSummary、TextDocument、DocumentChunk）都没有 group_id 或 dataset_name 属性
                # 解决方案：直接查找所有有内容的 TextSummary，按创建时间排序，选择最新的
                # 这是一个简化的方案，因为无法通过 group_id 精确匹配
                find_text_summary_query = """
                MATCH (ts:TextSummary)
                WHERE '__Node__' IN labels(ts)
                  AND ts.text IS NOT NULL
                  AND ts.text <> ''
                RETURN id(ts) as text_summary_id, ts.text as text_summary_text, ts.id as text_summary_uuid, ts.created_at as created_at
                ORDER BY ts.created_at DESC
                LIMIT 1
                """
                
                logger.info(f"查找 Cognee TextSummary（简化方案：选择最新的有内容的 TextSummary）")
                
                text_summary_results = neo4j_client.execute_query(find_text_summary_query, {
                    "group_id": group_id
                })
                
                if text_summary_results and len(text_summary_results) > 0:
                    text_summary_id = text_summary_results[0].get("text_summary_id")
                    text_summary_uuid = text_summary_results[0].get("text_summary_uuid")
                    text_summary_text = text_summary_results[0].get("text_summary_text", "")
                    
                    logger.info(f"找到 Cognee TextSummary 节点: text_summary_id={text_summary_id}, text_summary_uuid={text_summary_uuid}, text_length={len(text_summary_text) if text_summary_text else 0}")
                    
                    # 建立引用关系：(DocumentEpisode)-[:SUMMARIZED_FROM]->(TextSummary)
                    create_reference_query = """
                    MATCH (e:Episodic {uuid: $episode_uuid})
                    MATCH (ts:TextSummary)
                    WHERE id(ts) = $text_summary_id
                    MERGE (e)-[r:SUMMARIZED_FROM]->(ts)
                    SET r.created_at = timestamp()
                    RETURN id(r) as relation_id
                    """
                    
                    reference_result = neo4j_client.execute_query(create_reference_query, {
                        "episode_uuid": episode_uuid,
                        "text_summary_id": text_summary_id
                    })
                    
                    if reference_result:
                        text_summary_reference["established"] = True
                        text_summary_reference["text_summary_id"] = text_summary_id
                        text_summary_reference["text_summary_uuid"] = text_summary_uuid
                        text_summary_reference["text_summary_text"] = text_summary_text[:200] if text_summary_text else None  # 只返回前200字符
                        logger.info(f"✅ 成功建立引用关系: (DocumentEpisode)-[:SUMMARIZED_FROM]->(TextSummary)")
                    else:
                        text_summary_reference["error"] = "建立引用关系失败"
                        logger.warning(f"⚠️ 建立引用关系失败，但继续执行")
                else:
                    text_summary_reference["error"] = f"未找到 Cognee TextSummary 节点（group_id={group_id}）。这可能是因为 Cognee 尚未处理该文档，或者 TextSummary 尚未生成。"
                    logger.info(text_summary_reference["error"])
            except Exception as e:
                text_summary_reference["error"] = str(e)
                logger.warning(f"建立引用关系时出错: {e}，继续执行", exc_info=True)
            
            # ========== 5. 查询创建的Entity和Edge ==========
            logger.info(f"查询创建的 Entity 和 Edge: group_id={group_id}")
            entity_query = """
            MATCH (n:Entity)
            WHERE n.group_id = $group_id
            RETURN id(n) as id, labels(n) as labels, properties(n) as properties
            LIMIT 1000
            """
            
            edge_query = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE r.group_id = $group_id 
              AND (r.episodes IS NULL OR $episode_uuid IN r.episodes)
            RETURN id(r) as id, id(a) as source, id(b) as target, type(r) as type, properties(r) as properties
            LIMIT 1000
            """
            
            entity_results = neo4j_client.execute_query(entity_query, {
                "group_id": group_id
            })
            
            edge_results = neo4j_client.execute_query(edge_query, {
                "group_id": group_id,
                "episode_uuid": episode_uuid
            })
            
            # 处理Entity
            entities = []
            entity_type_counts = {}  # 统计各类型实体数量
            for entity_data in entity_results:
                props = entity_data.get("properties", {})
                labels = entity_data.get("labels", [])
                
                # 统计实体类型
                for label in labels:
                    if label != "Entity":  # 排除基础标签
                        entity_type_counts[label] = entity_type_counts.get(label, 0) + 1
                
                entities.append({
                    "id": str(entity_data.get("id", "")),
                    "labels": labels,
                    "properties": serialize_neo4j_properties(props)
                })
            
            # 处理Edge
            edges = []
            edge_type_counts = {}  # 统计各类型关系数量
            for edge_data in edge_results:
                edge_type = edge_data.get("type", "RELATES_TO")
                edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
                
                edges.append({
                    "id": str(edge_data.get("id", "")),
                    "source": str(edge_data.get("source", "")),
                    "target": str(edge_data.get("target", "")),
                    "type": edge_type,
                    "properties": serialize_neo4j_properties(edge_data.get("properties", {}))
                })
            
            # ========== 6. 依赖关系推理（可选）==========
            # 根据提取的实体和关系，推理文档之间的依赖关系
            dependency_analysis = None
            try:
                dependency_analysis = await self._analyze_dependencies(
                    group_id=group_id,
                    entities=entities,
                    edges=edges,
                    episode_content=episode_content
                )
                logger.info(f"依赖关系分析完成: {dependency_analysis}")
            except Exception as e:
                logger.warning(f"依赖关系分析失败: {e}，继续执行")
            
            # group_id 已经在前面生成并保存，这里不需要再次保存
            
            logger.info(
                f"Graphiti Episode 创建完成: "
                f"episode_uuid={episode_uuid}, group_id={group_id}, "
                f"entity_count={len(entities)}, edge_count={len(edges)}, "
                f"entity_types={entity_type_counts}, edge_types={edge_type_counts}"
            )
            
            # ========== 7. 保存向量到Milvus（步骤2：Graphiti构建后立即保存）==========
            vectors_saved = {
                "episode": 0,
                "entity": 0,
                "edge": 0,
                "community": 0
            }
            
            if self.milvus.is_available():
                logger.info(f"开始保存Graphiti向量到Milvus: group_id={group_id}")
                try:
                    # 7.1 保存Episode向量
                    episode_embedding = None
                    episode_content_text = episode_body  # 使用轻量化的episode_body
                    
                    # 尝试从Neo4j读取Graphiti生成的向量
                    episode_vector_query = """
                    MATCH (e:Episodic)
                    WHERE e.uuid = $episode_uuid
                    RETURN e.embedding as embedding, e.name as name, e.episode_body as episode_body
                    """
                    episode_vector_result = neo4j_client.execute_query(episode_vector_query, {
                        "episode_uuid": episode_uuid
                    })
                    
                    if episode_vector_result and episode_vector_result[0].get("embedding"):
                        episode_embedding = episode_vector_result[0].get("embedding")
                        logger.info(f"从Neo4j读取Episode向量: episode_uuid={episode_uuid}")
                    else:
                        # 如果没有向量，生成新的向量
                        episode_embedding = await embedding_client.get_embedding(episode_content_text)
                        logger.info(f"生成新的Episode向量: episode_uuid={episode_uuid}")
                    
                    if episode_embedding:
                        result = self.milvus.insert_vectors(
                            VectorType.EPISODE,
                            [{
                                "uuid": episode_uuid,
                                "name": f"{episode_content['title']}_文档级",
                                "group_id": group_id,
                                "content": episode_content_text[:1000],  # 限制长度
                                "embedding": episode_embedding
                            }]
                        )
                        vectors_saved["episode"] = len(result)
                        logger.info(f"Episode向量保存完成: {len(result)} 个向量")
                    
                    # 7.2 保存Entity向量
                    entity_vectors = []
                    for entity_data in entity_results:
                        props = entity_data.get("properties", {})
                        entity_uuid = props.get("uuid")
                        entity_name = props.get("name", "")
                        entity_summary = props.get("summary", "")
                        
                        if not entity_uuid:
                            continue
                        
                        # 尝试从Neo4j读取Graphiti生成的向量
                        entity_embedding = props.get("name_embedding")
                        
                        if not entity_embedding:
                            # 如果没有向量，生成新的向量（使用name或summary）
                            entity_text = entity_summary if entity_summary else entity_name
                            entity_embedding = await embedding_client.get_embedding(entity_text)
                        
                        if entity_embedding:
                            entity_vectors.append({
                                "uuid": entity_uuid,
                                "name": entity_name,
                                "group_id": group_id,
                                "content": entity_summary[:1000] if entity_summary else entity_name[:1000],
                                "embedding": entity_embedding
                            })
                    
                    if entity_vectors:
                        # 批量插入Entity向量（每批50个）
                        batch_size = 50
                        for i in range(0, len(entity_vectors), batch_size):
                            batch = entity_vectors[i:i + batch_size]
                            result = self.milvus.insert_vectors(VectorType.ENTITY, batch)
                            vectors_saved["entity"] += len(result)
                        logger.info(f"Entity向量保存完成: {vectors_saved['entity']} 个向量")
                    
                    # 7.3 保存Edge向量
                    edge_vectors = []
                    for edge_data in edge_results:
                        props = edge_data.get("properties", {})
                        edge_uuid = props.get("uuid")
                        edge_name = props.get("name", "")
                        edge_fact = props.get("fact", "")
                        
                        if not edge_uuid:
                            continue
                        
                        # 尝试从Neo4j读取Graphiti生成的向量
                        edge_embedding = props.get("fact_embedding")
                        
                        if not edge_embedding:
                            # 如果没有向量，生成新的向量（使用fact或name）
                            edge_text = edge_fact if edge_fact else edge_name
                            edge_embedding = await embedding_client.get_embedding(edge_text)
                        
                        if edge_embedding:
                            edge_vectors.append({
                                "uuid": edge_uuid,
                                "name": edge_name or edge_fact[:100],
                                "group_id": group_id,
                                "content": edge_fact[:1000] if edge_fact else edge_name[:1000],
                                "embedding": edge_embedding
                            })
                    
                    if edge_vectors:
                        # 批量插入Edge向量（每批50个）
                        batch_size = 50
                        for i in range(0, len(edge_vectors), batch_size):
                            batch = edge_vectors[i:i + batch_size]
                            result = self.milvus.insert_vectors(VectorType.EDGE, batch)
                            vectors_saved["edge"] += len(result)
                        logger.info(f"Edge向量保存完成: {vectors_saved['edge']} 个向量")
                    
                    # 7.4 保存Community向量（如果有）
                    community_query = """
                    MATCH (c:Community)
                    WHERE c.group_id = $group_id
                    RETURN c.uuid as uuid, c.name as name, c.summary as summary, c.name_embedding as embedding
                    LIMIT 100
                    """
                    community_results = neo4j_client.execute_query(community_query, {
                        "group_id": group_id
                    })
                    
                    community_vectors = []
                    for comm_data in community_results:
                        comm_uuid = comm_data.get("uuid")
                        comm_name = comm_data.get("name", "")
                        comm_summary = comm_data.get("summary", "")
                        comm_embedding = comm_data.get("embedding")
                        
                        if not comm_uuid:
                            continue
                        
                        if not comm_embedding:
                            # 如果没有向量，生成新的向量
                            comm_text = comm_summary if comm_summary else comm_name
                            comm_embedding = await embedding_client.get_embedding(comm_text)
                        
                        if comm_embedding:
                            community_vectors.append({
                                "uuid": comm_uuid,
                                "name": comm_name,
                                "group_id": group_id,
                                "content": comm_summary[:1000] if comm_summary else comm_name[:1000],
                                "embedding": comm_embedding
                            })
                    
                    if community_vectors:
                        result = self.milvus.insert_vectors(VectorType.COMMUNITY, community_vectors)
                        vectors_saved["community"] = len(result)
                        logger.info(f"Community向量保存完成: {len(result)} 个向量")
                    
                    logger.info(
                        f"Graphiti向量保存到Milvus完成: "
                        f"episode={vectors_saved['episode']}, "
                        f"entity={vectors_saved['entity']}, "
                        f"edge={vectors_saved['edge']}, "
                        f"community={vectors_saved['community']}"
                    )
                except Exception as e:
                    logger.error(f"保存Graphiti向量到Milvus失败: {e}", exc_info=True)
                    # 不抛出异常，允许继续执行
            else:
                logger.warning("Milvus不可用，跳过向量保存")
            
            return {
                "success": True,
                "episode_uuid": episode_uuid,
                "episode_id": episode_id,
                "doc_id": doc_id,
                "group_id": group_id,
                "episode_type": episode_type,
                "version": version or "v1.0",
                "template_id": template_id,  # 保存的模板ID（如果成功保存）
                "template_mode": template_mode,  # 使用的模板模式
                "entity_count": len(entities),
                "edge_count": len(edges),
                "entity_type_counts": entity_type_counts,  # 各类型实体数量统计
                "edge_type_counts": edge_type_counts,      # 各类型关系数量统计
                "vectors_saved": vectors_saved,  # 向量保存统计
                "entities": entities[:50],  # 限制返回数量
                "edges": edges[:50],
                "episode_content": episode_content,  # 返回轻量化的 Episode Content
                "dependency_analysis": dependency_analysis,  # 依赖关系分析结果
                "text_summary_reference": text_summary_reference,  # Cognee TextSummary 引用关系信息
                # 新增：用于前端展示和 Cognee 关联的关键信息
                "cognee_reference": {
                    "established": False,
                    "text_document_uuid": None,
                    "dataset_name": None,
                    "message": "Cognee TextDocument 尚未创建，请在 Cognee章节级处理 Tab 中执行处理"
                }
            }
            
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            raise
        except Exception as e:
            logger.error(f"Graphiti Episode 创建失败: {e}", exc_info=True)
            raise
        finally:
            db.close()
    
    async def _analyze_dependencies(
        self,
        group_id: str,
        entities: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        episode_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        分析文档之间的依赖关系（轻量化推理）
        
        根据提取的实体和关系，推理文档之间的依赖关系：
        1. 查找 DEPENDS_ON 关系
        2. 查找 RELATES_TO 关系
        3. 根据实体类型（System, Module）推理依赖
        
        Args:
            group_id: 文档组ID
            entities: 提取的实体列表
            edges: 提取的关系列表
            episode_content: Episode 内容（包含 related_docs）
            
        Returns:
            依赖关系分析结果
        """
        from app.core.neo4j_client import neo4j_client
        
        try:
            # 1. 查找直接的 DEPENDS_ON 关系
            depends_on_query = """
            MATCH (a:Entity)-[r:DEPENDS_ON]->(b:Entity)
            WHERE r.group_id = $group_id
            RETURN a.name as source_name, b.name as target_name, 
                   labels(a) as source_labels, labels(b) as target_labels
            LIMIT 50
            """
            
            depends_on_results = neo4j_client.execute_query(depends_on_query, {
                "group_id": group_id
            })
            
            # 2. 查找 RELATES_TO 关系（可能表示依赖）
            relates_to_query = """
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
            WHERE r.group_id = $group_id
            RETURN a.name as source_name, b.name as target_name,
                   labels(a) as source_labels, labels(b) as target_labels
            LIMIT 50
            """
            
            relates_to_results = neo4j_client.execute_query(relates_to_query, {
                "group_id": group_id
            })
            
            # 3. 查找跨文档的依赖关系（如果 related_docs 不为空）
            cross_doc_dependencies = []
            if episode_content.get("related_docs"):
                # 查找与其他文档的关联
                for related_doc_id in episode_content["related_docs"]:
                    cross_doc_query = """
                    MATCH (e1:Episodic)-[:MENTIONS]->(ent1:Entity)
                    WHERE e1.doc_id = $doc_id
                    WITH ent1
                    MATCH (e2:Episodic)-[:MENTIONS]->(ent2:Entity)
                    WHERE e2.doc_id = $related_doc_id
                      AND (ent1)-[:DEPENDS_ON|RELATES_TO]->(ent2)
                    RETURN ent1.name as source_name, ent2.name as target_name,
                           e1.doc_id as source_doc, e2.doc_id as target_doc
                    LIMIT 10
                    """
                    
                    cross_results = neo4j_client.execute_query(cross_doc_query, {
                        "doc_id": episode_content["doc_id"],
                        "related_doc_id": related_doc_id
                    })
                    cross_doc_dependencies.extend(cross_results)
            
            # 4. 统计依赖关系
            dependency_stats = {
                "direct_dependencies": len(depends_on_results),
                "related_entities": len(relates_to_results),
                "cross_doc_dependencies": len(cross_doc_dependencies),
                "total_dependencies": len(depends_on_results) + len(relates_to_results) + len(cross_doc_dependencies)
            }
            
            return {
                "stats": dependency_stats,
                "depends_on": [
                    {
                        "source": r.get("source_name", ""),
                        "target": r.get("target_name", ""),
                        "source_type": r.get("source_labels", [])[0] if r.get("source_labels") else "Unknown",
                        "target_type": r.get("target_labels", [])[0] if r.get("target_labels") else "Unknown"
                    }
                    for r in depends_on_results[:20]  # 限制返回数量
                ],
                "relates_to": [
                    {
                        "source": r.get("source_name", ""),
                        "target": r.get("target_name", ""),
                        "source_type": r.get("source_labels", [])[0] if r.get("source_labels") else "Unknown",
                        "target_type": r.get("target_labels", [])[0] if r.get("target_labels") else "Unknown"
                    }
                    for r in relates_to_results[:20]  # 限制返回数量
                ],
                "cross_doc": cross_doc_dependencies[:10]  # 限制返回数量
            }
            
        except Exception as e:
            logger.error(f"依赖关系分析失败: {e}", exc_info=True)
            return {
                "error": str(e),
                "stats": {
                    "direct_dependencies": 0,
                    "related_entities": 0,
                    "cross_doc_dependencies": 0,
                    "total_dependencies": 0
                }
            }
    
    async def step2_cognee_build(
        self,
        upload_id: int,
        group_id: Optional[str] = None,
        provider: str = "local",
        temperature: float = 0.7,
        # 模板配置（cognify阶段）
        cognify_template_mode: str = "llm_generate",
        cognify_template_config_json: Optional[Dict[str, Any]] = None,
        cognify_system_prompt: Optional[str] = None,
        cognify_user_prompt_template: Optional[str] = None,
        cognify_template_type: str = "default",
        # 模板配置（memify阶段）
        memify_template_mode: str = "default",
        memify_template_config_json: Optional[Dict[str, Any]] = None,
        memify_system_prompt: Optional[str] = None,  # 自定义 System Prompt（LLM生成模式时使用，用于enrichment任务）
        memify_user_prompt_template: Optional[str] = None,  # 自定义 User Prompt 模板（LLM生成模式时使用，用于enrichment任务）
        memify_template_type: str = "default",  # 模版类型（暂时只有 default）
        memify_rules: Optional[List[str]] = None  # LLM生成模式下，前端已生成的规则列表（可选）
    ) -> Dict[str, Any]:
        """
        步骤2: Cognee章节级处理
        
        构建章节级知识图谱
        """
        from app.services.word_document_service import WordDocumentService
        
        db = SessionLocal()
        try:
            # 获取文档
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 生成或获取 group_id（统一使用标准生成规则）
            if group_id:
                # 如果传入了 group_id，使用传入的（但需要验证格式）
                import re
                if not re.match(r'^[a-zA-Z0-9\-_]+$', group_id):
                    raise ValueError(f"Group ID 格式不正确，只能包含字母、数字、破折号(-)和下划线(_): {group_id}")
                # 如果文档已有 document_id 且与传入的不同，使用文档的（确保一致性）
                if document.document_id and document.document_id != group_id:
                    logger.warning(f"文档已有 document_id ({document.document_id})，但传入了不同的 group_id ({group_id})，使用文档的 document_id")
                    group_id = document.document_id
                elif not document.document_id:
                    # 如果文档没有 document_id，保存传入的 group_id
                    document.document_id = group_id
                    db.commit()
                    logger.info(f"保存传入的 group_id 到数据库: {group_id}")
            elif document.document_id:
                # 如果文档已有 document_id，使用文档的
                group_id = document.document_id
                logger.info(f"使用文档已有的 group_id: {group_id}")
            else:
                # 使用标准规则生成 group_id
                base_name = WordDocumentService._extract_base_name(document.file_name)
                safe_base_name = WordDocumentService._sanitize_group_id(base_name)
                date_str = datetime.now().strftime('%Y%m%d')
                group_id = f"doc_{safe_base_name}_{date_str}"
                
                # 保存到数据库
                document.document_id = group_id
                db.commit()
                logger.info(f"自动生成并保存 group_id: {group_id}")
            
            # 读取分块内容
            if not document.chunks_path or not os.path.exists(document.chunks_path):
                raise ValueError("文档尚未分块，请先完成文档分块")
            
            with open(document.chunks_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
            
            # 获取Cognee实例并初始化
            cognee_service = CogneeService()
            await cognee_service.initialize()
            
            # 不再使用固定的 dataset_name，因为每次处理都生成新的
            
            # 准备章节数据
            chunks = chunks_data.get("chunks", [])
            sections = []
            for idx, chunk in enumerate(chunks):
                sections.append({
                    "title": chunk.get("title", f"章节_{idx+1}"),
                    "content": chunk.get("content", ""),
                    "uuid": chunk.get("uuid", f"{group_id}_chunk_{idx+1}")
                })
            
            # 提取文档版本信息（用于日志）
            doc_id = f"DOC_{upload_id}"
            base_name = WordDocumentService._extract_base_name(document.file_name)
            version, version_number = WordDocumentService._extract_version(document.file_name)
            doc_version = version or "v1.0"
            dataset_name_preview = f"knowledge_base_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 记录详细的联动信息日志
            logger.info(
                f"========================================\n"
                f"Cognee 章节级处理开始（与 Graphiti 联动）\n"
                f"========================================\n"
                f"【继承自 Graphiti Episode】\n"
                f"  - doc_id: {doc_id}\n"
                f"  - group_id: {group_id}\n"
                f"  - version: {doc_version}\n"
                f"  - 说明: 这些标识符从 Graphiti Episode 继承，确保跨层数据一致性\n"
                f"\n"
                f"【Cognee 三层结构】\n"
                f"  1. DataSet（逻辑容器）\n"
                f"     - dataset_name: {dataset_name_preview}\n"
                f"     - 说明: 不是 Neo4j 节点，通过 dataset_name 属性关联所有相关节点\n"
                f"\n"
                f"  2. TextDocument/DataNode（章节级）\n"
                f"     - 数量: {len(sections)} 个（对应我们的预处理 chunks）\n"
                f"     - 说明: 存储章节级完整内容，用于上下文补充\n"
                f"     - 属性: doc_id, group_id, version, upload_id（从 Episode 继承）\n"
                f"\n"
                f"  3. DocumentChunk（分块级）\n"
                f"     - 说明: Cognee 将自动分块（真正的向量检索单元）\n"
                f"     - 存储: 向量保存到 Milvus（collection: {dataset_name_preview}_text）\n"
                f"     - 属性: doc_id, group_id, version（从 Episode 继承）\n"
                f"\n"
                f"【联动关系】\n"
                f"  - 将建立: (TextDocument)-[:RELATES_TO]->(Episode)\n"
                f"  - 用途: 前端展示联动状态、跨层检索\n"
                f"\n"
                f"【完整回溯链路】\n"
                f"  Milvus向量 → DocumentChunk → TextDocument/DataNode → Graphiti Episode\n"
                f"  通过 doc_id={doc_id} 实现跨层关联\n"
                f"========================================"
            )
            
            # 构建章节级知识图谱
            build_result = await cognee_service.build_section_knowledge_graph(
                sections=sections,
                group_id=group_id,
                provider=provider,
                upload_id=upload_id,  # 传递upload_id以便保存模板
                document_name=document.file_name,  # 传递document_name以便保存模板
                doc_id=doc_id,  # 传递doc_id以便更新节点属性
                version=doc_version,  # 传递version以便更新节点属性
                cognify_template_mode=cognify_template_mode,
                cognify_template_config_json=cognify_template_config_json,
                memify_template_mode=memify_template_mode,
                memify_template_config_json=memify_template_config_json,
                memify_system_prompt=memify_system_prompt,
                memify_user_prompt_template=memify_user_prompt_template,
                memify_template_type=memify_template_type,
                memify_rules=memify_rules
            )
            
            # 检查是否需要确认（已存在Cognee知识图谱）
            if isinstance(build_result, dict) and build_result.get("needs_confirmation"):
                logger.warning(f"需要确认删除已存在的Cognee知识图谱: {build_result.get('message')}")
                return {
                    "success": False,
                    "needs_confirmation": True,
                    "message": build_result.get("message", "已存在Cognee知识图谱，需要删除后重建"),
                    "group_id": build_result.get("group_id"),
                    "dataset_name": build_result.get("dataset_name"),
                    "upload_id": upload_id
                }
            
            # 获取dataset_name（如果build_result中有）
            dataset_name = build_result.get("dataset_name") if isinstance(build_result, dict) else None
            
            # ========== 从 build_result 中获取更新的节点统计（由 build_section_knowledge_graph 返回）==========
            # build_section_knowledge_graph 内部已经更新了 DocumentChunk 和 TextSummary
            # 这里直接使用它的统计数据
            updated_nodes = build_result.get("updated_nodes", {}) if isinstance(build_result, dict) else {}
            updated_chunk_count = updated_nodes.get("document_chunk_count", 0)
            updated_text_summary_count = updated_nodes.get("text_summary_count", 0)
            
            logger.info(
                f"从 build_section_knowledge_graph 获取节点更新统计: "
                f"DocumentChunk={updated_chunk_count}, TextSummary={updated_text_summary_count}"
            )
            
            # ========== 更新 Cognee TextDocument 和 DataNode 的属性（符合顶层设计）==========
            # doc_id, doc_version 已在前面日志部分定义，直接使用
            logger.info(f"更新 Cognee TextDocument/DataNode 节点属性以符合顶层设计: doc_id={doc_id}, group_id={group_id}, version={doc_version}")
            
            # 初始化更新计数变量（确保在异常情况下也有默认值）
            updated_td_count = 0
            updated_dn_count = 0
            
            try:
                # 策略：由于 Cognee 节点可能没有 dataset_name 属性，我们通过以下方式匹配：
                # 1. 优先匹配最近创建的节点（通过 created_at 排序）
                # 2. 如果节点已有 doc_id 和 group_id，则不更新（避免重复更新）
                # 3. 使用 LIMIT 限制更新数量，避免更新过多节点
                
                # 1. 更新 TextDocument 节点属性
                update_text_document_query = """
                MATCH (td:TextDocument)
                WHERE '__Node__' IN labels(td)
                  AND 'TextDocument' IN labels(td)
                  AND (td.doc_id IS NULL OR td.group_id IS NULL)
                WITH td
                ORDER BY td.created_at DESC
                LIMIT 10
                SET td.doc_id = $doc_id,
                    td.group_id = $group_id,
                    td.version = $version,
                    td.upload_id = $upload_id
                RETURN count(td) as updated_count
                """
                
                text_doc_update_result = neo4j_client.execute_query(update_text_document_query, {
                    "doc_id": doc_id,
                    "group_id": group_id,
                    "version": doc_version,
                    "upload_id": upload_id
                })
                
                updated_td_count = text_doc_update_result[0].get("updated_count", 0) if text_doc_update_result else 0
                logger.info(f"✅ 更新了 {updated_td_count} 个 TextDocument 节点的属性（doc_id={doc_id}, group_id={group_id}, version={doc_version}）")
                
                # 2. 更新 DataNode 节点属性（如果存在）
                update_data_node_query = """
                MATCH (dn)
                WHERE '__Node__' IN labels(dn)
                  AND 'DataNode' IN labels(dn)
                  AND (dn.doc_id IS NULL OR dn.group_id IS NULL)
                WITH dn
                ORDER BY dn.created_at DESC
                LIMIT 100
                SET dn.doc_id = $doc_id,
                    dn.group_id = $group_id,
                    dn.version = $version,
                    dn.upload_id = $upload_id
                RETURN count(dn) as updated_count
                """
                
                data_node_update_result = neo4j_client.execute_query(update_data_node_query, {
                    "doc_id": doc_id,
                    "group_id": group_id,
                    "version": doc_version,
                    "upload_id": upload_id
                })
                
                updated_dn_count = data_node_update_result[0].get("updated_count", 0) if data_node_update_result else 0
                logger.info(f"✅ 更新了 {updated_dn_count} 个 DataNode 节点的属性")
                
                # 注意：DocumentChunk 和 TextSummary 的更新已经在 build_section_knowledge_graph() 内部完成
                # 这里不需要再次更新，直接使用从 build_result 获取的统计数据
                logger.info(
                    f"✅ DocumentChunk 和 TextSummary 已在 build_section_knowledge_graph() 中更新完成 "
                    f"(DocumentChunk={updated_chunk_count}, TextSummary={updated_text_summary_count})"
                )
                
                # 4. 更新 Entity 节点属性（cognify() 创建的实体节点）
                update_entity_query = """
                MATCH (e:Entity)
                WHERE '__Node__' IN labels(e)
                  AND 'Entity' IN labels(e)
                  AND (e.doc_id IS NULL OR e.group_id IS NULL)
                WITH e
                ORDER BY e.created_at DESC
                LIMIT 500
                SET e.doc_id = $doc_id,
                    e.group_id = $group_id,
                    e.version = $version,
                    e.upload_id = $upload_id
                RETURN count(e) as updated_count
                """
                
                entity_update_result = neo4j_client.execute_query(update_entity_query, {
                    "doc_id": doc_id,
                    "group_id": group_id,
                    "version": doc_version,
                    "upload_id": upload_id
                })
                
                updated_entity_count = entity_update_result[0].get("updated_count", 0) if entity_update_result else 0
                logger.info(f"✅ 更新了 {updated_entity_count} 个 Entity 节点的属性")
                
                # 5. 更新 EntityType 节点属性
                update_entity_type_query = """
                MATCH (et)
                WHERE '__Node__' IN labels(et)
                  AND 'EntityType' IN labels(et)
                  AND (et.doc_id IS NULL OR et.group_id IS NULL)
                WITH et
                ORDER BY et.created_at DESC
                LIMIT 100
                SET et.doc_id = $doc_id,
                    et.group_id = $group_id,
                    et.version = $version,
                    et.upload_id = $upload_id
                RETURN count(et) as updated_count
                """
                
                entity_type_update_result = neo4j_client.execute_query(update_entity_type_query, {
                    "doc_id": doc_id,
                    "group_id": group_id,
                    "version": doc_version,
                    "upload_id": upload_id
                })
                
                updated_entity_type_count = entity_type_update_result[0].get("updated_count", 0) if entity_type_update_result else 0
                logger.info(f"✅ 更新了 {updated_entity_type_count} 个 EntityType 节点的属性")
                
                if updated_td_count == 0 and updated_dn_count == 0 and updated_entity_count == 0:
                    logger.warning(f"⚠️ 未找到需要更新的节点（可能节点已有这些属性，或节点尚未创建）")
                else:
                    logger.info(
                        f"✅ Cognee 节点属性更新完成: "
                        f"TextDocument={updated_td_count}, DataNode={updated_dn_count}, DocumentChunk={updated_chunk_count}, "
                        f"TextSummary={updated_text_summary_count}, Entity={updated_entity_count}, EntityType={updated_entity_type_count}"
                    )
                
            except Exception as e:
                logger.error(f"更新 Cognee 节点属性失败: {e}", exc_info=True)
                # 不抛出异常，允许继续执行
            
            # 等待一下，确保节点已完全提交到Neo4j
            # 同时验证节点是否已创建
            import asyncio
            from app.core.neo4j_client import neo4j_client as check_neo4j
            
            max_wait = 10  # 最多等待10秒
            wait_interval = 1  # 每秒检查一次
            waited = 0
            
            while waited < max_wait:
                check_query = """
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
                check_result = check_neo4j.execute_query(check_query)
                node_count = check_result[0]["node_count"] if check_result else 0
                
                if node_count > 0:
                    logger.info(f"检测到 {node_count} 个节点已创建，继续执行向量保存")
                    break
                
                await asyncio.sleep(wait_interval)
                waited += wait_interval
                logger.info(f"等待节点创建... ({waited}/{max_wait}秒)")
            
            if waited >= max_wait:
                logger.warning(f"等待超时，可能节点尚未创建，但继续执行向量统计")
            
            # ========== 统计 Cognee 自动向量化结果 ==========
            # 🎯 核心原则：完全依赖 Cognee 自动向量化，不再手动向量化
            # Cognee 在 cognify() 阶段会自动创建6类 Milvus collection
            # 根据决策：仅使用 DocumentChunk_text 和 Entity_name，其他4类不使用
            
            cognee_vectors_stats = {
                # ✅ 使用的向量（2类）
                "DocumentChunk_text": 0,       # 粗召回核心
                "Entity_name": 0,              # 实体检索核心
                # ❌ 自动创建但不使用的向量（4类）
                "TextDocument_name": 0,        # 哈希值无语义
                "EntityType_name": 0,          # Neo4j更高效
                "EdgeType_relationship_name": 0,  # 内容混乱
                "TextSummary_text": 0          # DocumentChunk已足够
            }
            
            if self.milvus.is_available():
                try:
                    from pymilvus import connections, Collection, utility
                    
                    logger.info("正在统计 Cognee 自动向量化结果...")
                    
                    # 连接到 Milvus（使用已配置的连接参数）
                    milvus_host = os.getenv("MILVUS_HOST", "")
                    milvus_port = os.getenv("MILVUS_PORT", "19530")
                    milvus_user = os.getenv("MILVUS_USER", "root")
                    milvus_password = os.getenv("MILVUS_PASSWORD", "")
                        
                    # 查询每个 collection 的向量数量
                    for collection_name in cognee_vectors_stats.keys():
                        try:
                            if utility.has_collection(collection_name):
                                collection = Collection(collection_name)
                                cognee_vectors_stats[collection_name] = collection.num_entities
                                logger.info(f"  - {collection_name}: {collection.num_entities} 个向量")
                            else:
                                logger.info(f"  - {collection_name}: collection 不存在")
                        except Exception as e:
                            logger.warning(f"查询 {collection_name} 失败: {e}")
                    
                    # 汇总日志（区分使用/不使用）
                    logger.info(
                        f"\n"
                        f"========================================\n"
                        f"Cognee 自动向量化完成\n"
                        f"========================================\n"
                        f"【✅ 使用的向量】（2类）\n"
                        f"  - DocumentChunk_text: {cognee_vectors_stats['DocumentChunk_text']} 个向量（粗召回核心⭐⭐⭐⭐⭐）\n"
                        f"  - Entity_name: {cognee_vectors_stats['Entity_name']} 个向量（实体检索核心⭐⭐⭐⭐⭐）\n"
                        f"\n"
                        f"【❌ 自动创建但不使用的向量】（4类）\n"
                        f"  - TextDocument_name: {cognee_vectors_stats['TextDocument_name']} 个向量（哈希值无语义，已弃用）\n"
                        f"  - EntityType_name: {cognee_vectors_stats['EntityType_name']} 个向量（Neo4j更高效，已弃用）\n"
                        f"  - EdgeType_relationship_name: {cognee_vectors_stats['EdgeType_relationship_name']} 个向量（内容混乱，已弃用）\n"
                        f"  - TextSummary_text: {cognee_vectors_stats['TextSummary_text']} 个向量（DocumentChunk已足够，已弃用）\n"
                        f"\n"
                        f"【检索策略】\n"
                        f"  - Stage 1: Milvus DocumentChunk_text + Entity_name 并行检索\n"
                        f"  - Stage 2: Neo4j 图遍历补充关系和结构化知识\n"
                        f"\n"
                        f"【架构优势】\n"
                        f"  - ✅ 完全依赖 Cognee 自动向量化（无手动代码）\n"
                        f"  - ✅ 向量类型精简（6类→2类使用）\n"
                        f"  - ✅ 维护成本降低（无需手动embedding调用）\n"
                        f"========================================"
                    )
                except Exception as e:
                    logger.error(f"统计 Cognee 向量失败: {e}", exc_info=True)
            else:
                logger.warning("Milvus 不可用，跳过 Cognee 向量统计")
                # 设置默认值
                cognee_vectors_stats = {k: 0 for k in cognee_vectors_stats.keys()}
            
            # ========== 重新统计节点和关系数量（在更新节点属性之后）==========
            # 因为节点属性更新后，group_id已设置，可以准确统计
            logger.info("正在重新统计节点和关系数量（基于更新后的group_id）...")
            
            # 统计Entity节点（通过group_id过滤）
            final_entity_count_query = """
            MATCH (n:Entity)
            WHERE '__Node__' IN labels(n)
               AND n.group_id = $group_id
            RETURN count(n) as entity_count
            """
            final_entity_result = neo4j_client.execute_query(final_entity_count_query, {"group_id": group_id})
            final_entity_count = final_entity_result[0].get("entity_count", 0) if final_entity_result else 0
            
            # 统计关系（通过group_id过滤）
            final_edge_count_query = """
            MATCH (a)-[r]->(b)
            WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
               AND a.group_id = $group_id AND b.group_id = $group_id
            RETURN count(DISTINCT r) as edge_count
            """
            final_edge_result = neo4j_client.execute_query(final_edge_count_query, {"group_id": group_id})
            final_edge_count = final_edge_result[0].get("edge_count", 0) if final_edge_result else 0
            
            # 统计实体类型分布
            final_entity_type_query = """
            MATCH (n:Entity)
            WHERE '__Node__' IN labels(n)
               AND n.group_id = $group_id
            UNWIND labels(n) as label
            WITH label
            WHERE label <> 'Entity' AND label <> '__Node__'
            RETURN label, count(*) as count
            ORDER BY count DESC
            """
            final_entity_type_result = neo4j_client.execute_query(final_entity_type_query, {"group_id": group_id})
            final_entity_type_counts = {row.get("label"): row.get("count", 0) for row in final_entity_type_result} if final_entity_type_result else {}
            
            # 统计关系类型分布
            final_edge_type_query = """
            MATCH (a)-[r]->(b)
            WHERE '__Node__' IN labels(a) AND '__Node__' IN labels(b)
               AND a.group_id = $group_id AND b.group_id = $group_id
            RETURN type(r) as edge_type, count(*) as count
            ORDER BY count DESC
            """
            final_edge_type_result = neo4j_client.execute_query(final_edge_type_query, {"group_id": group_id})
            final_edge_type_counts = {row.get("edge_type"): row.get("count", 0) for row in final_edge_type_result} if final_edge_type_result else {}
            
            logger.info(
                f"✅ 重新统计完成（基于更新后的group_id）: "
                f"Entity={final_entity_count}个, "
                f"关系={final_edge_count}个, "
                f"实体类型={len(final_entity_type_counts)}种, "
                f"关系类型={len(final_edge_type_counts)}种"
            )
            
            # 使用重新统计的结果（优先使用更新后的统计）
            entity_count = final_entity_count
            edge_count = final_edge_count
            entity_type_counts = final_entity_type_counts
            edge_type_counts = final_edge_type_counts
            
            # ========== 建立与 Graphiti Episode 的关联 ==========
            logger.info(
                f"========================================\n"
                f"建立 Cognee-Graphiti 联动关系\n"
                f"========================================\n"
                f"【当前 Cognee 处理结果】\n"
                f"  - Neo4j 节点数: {entity_count}\n"
                f"  - Neo4j 关系数: {edge_count}\n"
                f"  - Milvus 向量数（使用）: DocumentChunk_text={cognee_vectors_stats.get('DocumentChunk_text', 0)}, Entity_name={cognee_vectors_stats.get('Entity_name', 0)}\n"
                f"\n"
                f"【查找 Graphiti Episode】\n"
                f"  - 通过 group_id={group_id} 查找对应的 Episode\n"
                f"  - 用途: 建立 (TextDocument)-[:RELATES_TO]->(Episode) 关系\n"
                f"========================================"
            )
            
            graphiti_reference = {
                "established": False,
                "episode_uuid": None,
                "episode_id": None,
                "doc_id": None,
                "doc_id_match": False,
                "group_id_match": False,
                "version": None,
                "version_match": False,
                "message": None
            }
            
            try:
                # 1. 查找 Graphiti Episode（通过 group_id）
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
                    episode_uuid = episode_data.get("episode_uuid")
                    episode_id = episode_data.get("episode_id")
                    episode_doc_id = episode_data.get("doc_id")
                    episode_version = episode_data.get("version")
                    
                    graphiti_reference["episode_uuid"] = episode_uuid
                    graphiti_reference["episode_id"] = episode_id
                    graphiti_reference["doc_id"] = episode_doc_id
                    graphiti_reference["version"] = episode_version
                    
                    logger.info(
                        f"✅ 找到 Graphiti Episode:\n"
                        f"  - episode_uuid: {episode_uuid}\n"
                        f"  - episode_id: {episode_id}\n"
                        f"  - Episode doc_id: {episode_doc_id}\n"
                        f"  - Episode version: {episode_version}"
                    )
                    
                    # 2. doc_id 和 version 已在前面定义，直接使用
                    
                    # 3. 验证关联
                    graphiti_reference["doc_id_match"] = (episode_doc_id == doc_id)
                    graphiti_reference["group_id_match"] = True  # group_id 已匹配（通过查询条件）
                    graphiti_reference["version_match"] = (episode_version == doc_version)
                    
                    # 4. 建立关联关系（如果尚未建立）
                    # 查找 Cognee TextDocument（通过查询最新的 TextDocument）
                    find_text_document_query = """
                    MATCH (td:TextDocument)
                    WHERE '__Node__' IN labels(td)
                      AND 'TextDocument' IN labels(td)
                    RETURN id(td) as text_document_id, td.id as text_document_uuid
                    ORDER BY td.created_at DESC
                    LIMIT 1
                    """
                    
                    text_doc_results = neo4j_client.execute_query(find_text_document_query)
                    
                    if text_doc_results and len(text_doc_results) > 0:
                        text_doc_id = text_doc_results[0].get("text_document_id")
                        text_doc_uuid = text_doc_results[0].get("text_document_uuid")
                        
                        # 建立关联关系：(TextDocument)-[:RELATES_TO]->(Episodic)
                        create_link_query = """
                        MATCH (e:Episodic {uuid: $episode_uuid})
                        MATCH (td:TextDocument)
                        WHERE id(td) = $text_doc_id
                        MERGE (td)-[r:RELATES_TO]->(e)
                        SET r.created_at = timestamp(),
                            r.link_type = 'document_level_to_chapter_level'
                        RETURN id(r) as relation_id
                        """
                        
                        link_result = neo4j_client.execute_query(create_link_query, {
                            "episode_uuid": episode_uuid,
                            "text_doc_id": text_doc_id
                        })
                        
                        if link_result:
                            graphiti_reference["established"] = True
                            graphiti_reference["message"] = f"✅ 成功建立关联：Cognee TextDocument ({text_doc_uuid}) <-> Graphiti Episode ({episode_uuid})"
                            
                            # 记录详细的联动成功信息
                            logger.info(
                                f"========================================\n"
                                f"✅ Cognee-Graphiti 联动建立成功\n"
                                f"========================================\n"
                                f"【关联关系】\n"
                                f"  (TextDocument)-[:RELATES_TO]->(Episode)\n"
                                f"  - TextDocument UUID: {text_doc_uuid}\n"
                                f"  - Episode UUID: {episode_uuid}\n"
                                f"\n"
                                f"【数据一致性验证】\n"
                                f"  - doc_id 匹配: {'✓' if graphiti_reference['doc_id_match'] else '✗'} "
                                f"(Cognee: {doc_id}, Episode: {episode_doc_id})\n"
                                f"  - group_id 匹配: {'✓' if graphiti_reference['group_id_match'] else '✗'} "
                                f"({group_id})\n"
                                f"  - version 匹配: {'✓' if graphiti_reference['version_match'] else '✗'} "
                                f"(Cognee: {doc_version}, Episode: {episode_version})\n"
                                f"\n"
                                f"【完整回溯链路已建立】\n"
                                f"  Milvus向量 → DocumentChunk → TextDocument → Episode\n"
                                f"  通过 doc_id={doc_id} 实现跨层关联\n"
                                f"========================================"
                            )
                        else:
                            graphiti_reference["message"] = "⚠️ 建立关联关系失败"
                            logger.warning(graphiti_reference["message"])
                    else:
                        graphiti_reference["message"] = "⚠️ 未找到 Cognee TextDocument 节点"
                        logger.warning(graphiti_reference["message"])
                else:
                    graphiti_reference["message"] = f"未找到 Graphiti Episode（group_id={group_id}），请先执行 Graphiti 文档级处理"
                    logger.info(graphiti_reference["message"])
                    
            except Exception as e:
                graphiti_reference["message"] = f"建立关联时出错: {str(e)}"
                logger.warning(f"建立 Graphiti-Cognee 关联时出错: {e}", exc_info=True)
            
            # 提取文档版本信息（用于返回）
            base_name = WordDocumentService._extract_base_name(document.file_name)
            version, version_number = WordDocumentService._extract_version(document.file_name)
            doc_id = f"DOC_{upload_id}"
            
            # ========== 构建处理步骤详细信息 ==========
            processing_steps = []
            
            # 步骤1: 读取文档和分块数据
            processing_steps.append({
                "step": 1,
                "name": "读取文档和分块数据",
                "status": "completed",
                "message": f"成功读取 {len(chunks)} 个章节",
                "details": {
                    "chunks_count": len(chunks),
                    "chunks_path": document.chunks_path
                }
            })
            
            # 步骤2: 准备章节数据
            processing_steps.append({
                "step": 2,
                "name": "准备章节数据",
                "status": "completed",
                "message": f"已准备 {len(sections)} 个章节数据",
                "details": {
                    "sections_count": len(sections),
                    "section_titles": [s.get("title", "") for s in sections[:10]]  # 只显示前10个标题
                }
            })
            
            # 步骤3: Cognee构建知识图谱
            # 使用重新统计后的值（entity_count, edge_count, entity_type_counts, edge_type_counts）
            if build_result and isinstance(build_result, dict):
                memify_info = build_result.get("memify_result", {})
                processing_steps.append({
                    "step": 3,
                    "name": "Cognee构建知识图谱",
                    "status": "completed",
                    "message": f"Cognify: {entity_count} 个实体, {edge_count} 个关系",
                    "details": {
                        "dataset_name": dataset_name,
                        "cognify": {
                            "entity_count": entity_count,  # 使用重新统计后的值
                            "edge_count": edge_count,      # 使用重新统计后的值
                            "entity_types": entity_type_counts,  # 使用重新统计后的值
                            "edge_types": edge_type_counts       # 使用重新统计后的值
                        },
                        "memify": {
                            "enabled": memify_info.get("enabled", False),
                            "extraction_count": memify_info.get("extraction_count", 0),
                            "enrichment_count": memify_info.get("enrichment_count", 0)
                        }
                    }
                })
            else:
                processing_steps.append({
                    "step": 3,
                    "name": "Cognee构建知识图谱",
                    "status": "completed",
                    "message": "知识图谱构建完成",
                    "details": {
                        "dataset_name": dataset_name
                    }
                })
            
            # 步骤4: 更新Neo4j节点属性
            processing_steps.append({
                "step": 4,
                "name": "更新Neo4j节点属性",
                "status": "completed",
                "message": f"已更新 {updated_td_count} 个TextDocument, {updated_dn_count} 个DataNode, {updated_chunk_count} 个DocumentChunk, {updated_text_summary_count} 个TextSummary, {updated_entity_count} 个Entity, {updated_entity_type_count} 个EntityType",
                "details": {
                    "text_document_count": updated_td_count,
                    "data_node_count": updated_dn_count,
                    "document_chunk_count": updated_chunk_count,
                    "text_summary_count": updated_text_summary_count,
                    "entity_count": updated_entity_count,
                    "entity_type_count": updated_entity_type_count,
                    "doc_id": doc_id,
                    "group_id": group_id,
                    "version": doc_version
                }
            })
            
            # 步骤5: 保存向量到Milvus
            if self.milvus.is_available():
                processing_steps.append({
                    "step": 5,
                    "name": "Cognee自动向量化",
                    "status": "completed",
                    "message": f"Cognee自动创建 {cognee_vectors_stats['DocumentChunk_text']} 个DocumentChunk向量, {cognee_vectors_stats['Entity_name']} 个Entity向量",
                    "details": {
                        "used_vectors": {
                            "DocumentChunk_text": cognee_vectors_stats["DocumentChunk_text"],
                            "Entity_name": cognee_vectors_stats["Entity_name"]
                        },
                        "unused_vectors": {
                            "TextDocument_name": cognee_vectors_stats["TextDocument_name"],
                            "EntityType_name": cognee_vectors_stats["EntityType_name"],
                            "EdgeType_relationship_name": cognee_vectors_stats["EdgeType_relationship_name"],
                            "TextSummary_text": cognee_vectors_stats["TextSummary_text"]
                        },
                        "milvus_available": True
                    }
                })
            else:
                processing_steps.append({
                    "step": 5,
                    "name": "Cognee自动向量化",
                    "status": "skipped",
                    "message": "Milvus不可用，跳过向量统计",
                    "details": {
                        "milvus_available": False
                    }
                })
            
            # 计算 Cognee 三层结构统计
            cognee_structure = {
                "dataset": {
                    "name": dataset_name,
                    "description": "Cognee 逻辑容器，不是 Neo4j 节点"
                },
                "text_documents": {
                    "count": updated_td_count,
                    "description": f"章节级数据容器（对应 {len(sections)} 个预处理 chunks）"
                },
                "data_nodes": {
                    "count": updated_dn_count,
                    "description": "章节级数据容器（Cognee 可能创建 DataNode 或 TextDocument）"
                },
                "document_chunks": {
                    "count": updated_chunk_count,
                    "description": "分块级向量单元（Cognee 自动分块，存储到 Milvus）"
                }
            }
            
            # 完整回溯链路信息
            traceability = {
                "doc_id": doc_id,
                "group_id": group_id,
                "version": doc_version,
                "path": "Milvus向量 → DocumentChunk → TextDocument/DataNode → Graphiti Episode",
                "description": f"通过 doc_id={doc_id} 实现跨层关联和回溯",
                "linkage_established": graphiti_reference.get("established", False)
            }
            
            return {
                # 基本信息
                "group_id": group_id,
                "doc_id": doc_id,
                "version": doc_version,
                
                # Cognee 处理结果
                "node_count": entity_count,
                "relationship_count": edge_count,
                "dataset_name": dataset_name,
                
                # 🆕 Cognee 自动向量化统计
                "cognee_vectors": {
                    "used": {
                        "DocumentChunk_text": cognee_vectors_stats.get("DocumentChunk_text", 0),
                        "Entity_name": cognee_vectors_stats.get("Entity_name", 0)
                    },
                    "unused": {
                        "TextDocument_name": cognee_vectors_stats.get("TextDocument_name", 0),
                        "EntityType_name": cognee_vectors_stats.get("EntityType_name", 0),
                        "EdgeType_relationship_name": cognee_vectors_stats.get("EdgeType_relationship_name", 0),
                        "TextSummary_text": cognee_vectors_stats.get("TextSummary_text", 0)
                    },
                    "total_used": cognee_vectors_stats.get("DocumentChunk_text", 0) + cognee_vectors_stats.get("Entity_name", 0),
                    "total_unused": sum([
                        cognee_vectors_stats.get("TextDocument_name", 0),
                        cognee_vectors_stats.get("EntityType_name", 0),
                        cognee_vectors_stats.get("EdgeType_relationship_name", 0),
                        cognee_vectors_stats.get("TextSummary_text", 0)
                    ])
                },
                
                # 🆕 Cognee 三层结构统计
                "cognee_structure": cognee_structure,
                
                # 🆕 与 Graphiti 的联动状态（增强版）
                "graphiti_linkage": {
                    "episode_uuid": graphiti_reference.get("episode_uuid"),
                    "episode_id": graphiti_reference.get("episode_id"),
                    "linkage_established": graphiti_reference.get("established", False),
                    "relation_type": "RELATES_TO" if graphiti_reference.get("established") else None,
                    "data_consistency": {
                        "doc_id_match": graphiti_reference.get("doc_id_match", False),
                        "group_id_match": graphiti_reference.get("group_id_match", False),
                        "version_match": graphiti_reference.get("version_match", False)
                    },
                    "message": graphiti_reference.get("message")
                },
                
                # 🆕 完整回溯链路
                "traceability": traceability,
                
                # 详细的处理步骤信息
                "processing_steps": processing_steps,
                
                # 兼容旧版（保留 graphiti_reference）
                "graphiti_reference": graphiti_reference
            }
            
        finally:
            db.close()
    
    async def step3_milvus_vectorize(
        self,
        upload_id: int,
        group_id: str
    ) -> Dict[str, Any]:
        """
        步骤3: Milvus向量化处理（优化版）
        
        根据实施方案，实现以下功能：
        1. 文档摘要向量化（DOCUMENT_SUMMARY）
        2. 章节向量化（SECTION）- 核心功能，用于快速召回
        3. 图片向量化（IMAGE）- 可选
        4. 表格向量化（TABLE）- 可选
        
        注意：
        - 流程/规则向量化已在步骤2中完成（保存到Cognee_entity_vectors），此处不再重复
        - Requirement向量化已在步骤2中完成（保存到graphiti_entity_vectors），此处不再重复
        
        优化点：
        - 添加完善的元数据（doc_id, section_index, section_level等）
        - 批量插入优化
        - 错误处理和日志完善
        """
        db = SessionLocal()
        try:
            # 获取文档
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            # 检查 Milvus 是否可用
            if not self.milvus.is_available():
                raise ValueError("Milvus 不可用，请检查配置")
            
            # 读取解析后的内容
            parsed_content_path = document.parsed_content_path
            if not parsed_content_path or not os.path.exists(parsed_content_path):
                raise ValueError("文档尚未解析，请先完成文档解析")
            
            # 读取分块内容
            chunks = []
            chunks_data = None
            if document.chunks_path and os.path.exists(document.chunks_path):
                with open(document.chunks_path, 'r', encoding='utf-8') as f:
                    chunks_data = json.load(f)
                    chunks = chunks_data.get("chunks", [])
            
            if not chunks:
                logger.warning(f"文档 {upload_id} 没有分块数据，跳过章节向量化")
            
            vectors_inserted = {
                "summary": 0,
                "chunks": 0,
                "images": 0,
                "tables": 0
            }
            
            doc_id = f"DOC_{upload_id}"
            
            # ========== 1. 文档摘要向量化（已移除）==========
            # 注意：文档摘要不再单独向量化
            # 原因：在智能检索中未使用，且 Graphiti Episode 已包含文档级语义
            logger.info(f"文档摘要向量化：跳过（已弃用）")
            
            # ========== 2. 章节向量化（已移除）==========
            # 注意：章节向量化已由 Cognee 自动完成（DocumentChunk_text collection）
            # Cognee 在 step2_cognee_build 中会自动将章节内容向量化
            # 不再需要手动插入 document_section_vectors
            logger.info(f"章节向量化：跳过（由 Cognee 自动完成，collection: DocumentChunk_text）")
            
            # ========== 3. 图片向量化（已移除）==========
            # 注意：图片向量化未实际使用（代码空转）
            # 原因：在智能检索中未使用，且图片信息已包含在文档内容中
            logger.info(f"图片向量化：跳过（未使用）")
            
            # ========== 4. 表格向量化（已移除）==========
            # 注意：表格向量化未实际使用（代码空转）
            # 原因：在智能检索中未使用，且表格信息已包含在文档内容中
            logger.info(f"表格向量化：跳过（未使用）")
            
            total_count = sum(vectors_inserted.values())
            
            logger.info(
                f"Milvus 向量化处理完成: upload_id={upload_id}, group_id={group_id}, "
                f"总计={total_count} 个向量 "
                f"(摘要={vectors_inserted['summary']}, "
                f"章节={vectors_inserted['chunks']}, "
                f"图片={vectors_inserted['images']}, "
                f"表格={vectors_inserted['tables']})"
            )
            
            return {
                "success": True,
                "upload_id": upload_id,
                                    "group_id": group_id,
                "doc_id": doc_id,
                "summary_vector_count": vectors_inserted["summary"],
                "chunk_vector_count": vectors_inserted["chunks"],
                "image_vector_count": vectors_inserted["images"],
                "table_vector_count": vectors_inserted["tables"],
                "total_vector_count": total_count
            }
            
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            raise
        except Exception as e:
            logger.error(f"Milvus 向量化处理失败: {e}", exc_info=True)
            raise
        finally:
            db.close()
    
    async def get_document_hierarchy(
        self,
        upload_id: int
    ) -> Dict[str, Any]:
        """
        获取文档的完整层级结构
        
        返回文档级别、章节级别、分块级别的所有节点和属性信息
        """
        from app.services.word_document_service import WordDocumentService
        from app.core.utils import serialize_neo4j_properties
        
        db = SessionLocal()
        try:
            # 获取文档信息
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            group_id = document.document_id
            doc_id = f"DOC_{upload_id}"
            base_name = WordDocumentService._extract_base_name(document.file_name)
            version, _ = WordDocumentService._extract_version(document.file_name)
            doc_version = version or "v1.0"
            
            hierarchy = {
                "upload_id": upload_id,
                "file_name": document.file_name,
                "doc_id": doc_id,
                "group_id": group_id,
                "version": doc_version,
                "document_level": {
                    "graphiti_episode": None,
                    "cognee_text_document": None,
                    "linkage": {
                        "established": False,
                        "relation_type": None
                    }
                },
                "section_level": [],
                "chunk_level": [],
                "consistency_check": {
                    "doc_id_match": False,
                    "group_id_match": False,
                    "version_match": False,
                    "issues": []
                }
            }
            
            if not group_id:
                hierarchy["consistency_check"]["issues"].append("文档尚未处理，缺少 group_id")
                return hierarchy
            
            # ========== 1. 查询文档级别：Graphiti Episode ==========
            episode_query = """
            MATCH (e:Episodic)
            WHERE e.group_id = $group_id
            RETURN e.uuid as episode_uuid, e.episode_id as episode_id,
                   e.doc_id as doc_id, e.group_id as group_id, e.version as version,
                   e.episode_type as episode_type, e.content as content,
                   e.created_at as created_at, e.updated_at as updated_at,
                   properties(e) as properties
            ORDER BY e.created_at DESC
            LIMIT 1
            """
            episode_results = neo4j_client.execute_query(episode_query, {"group_id": group_id})
            
            if episode_results and len(episode_results) > 0:
                episode_data = episode_results[0]
                hierarchy["document_level"]["graphiti_episode"] = {
                    "episode_uuid": episode_data.get("episode_uuid"),
                    "episode_id": episode_data.get("episode_id"),
                    "doc_id": episode_data.get("doc_id"),
                    "group_id": episode_data.get("group_id"),
                    "version": episode_data.get("version"),
                    "episode_type": episode_data.get("episode_type"),
                    "content": episode_data.get("content", "")[:500] if episode_data.get("content") else "",  # 截断内容
                    "created_at": episode_data.get("created_at"),
                    "updated_at": episode_data.get("updated_at"),
                    "properties": serialize_neo4j_properties(episode_data.get("properties", {}))
                }
            
            # ========== 2. 查询文档级别：Cognee TextDocument ==========
            text_document_query = """
            MATCH (td:TextDocument)
            WHERE '__Node__' IN labels(td)
              AND 'TextDocument' IN labels(td)
              AND td.group_id = $group_id
            RETURN td.id as text_document_uuid, td.dataset_name as dataset_name,
                   td.doc_id as doc_id, td.group_id as group_id, td.version as version,
                   td.upload_id as upload_id, td.created_at as created_at,
                   td.updated_at as updated_at, properties(td) as properties
            ORDER BY td.created_at DESC
            LIMIT 1
            """
            text_doc_results = neo4j_client.execute_query(text_document_query, {
                                "group_id": group_id,
                "upload_id": upload_id
            })
            
            if text_doc_results and len(text_doc_results) > 0:
                text_doc_data = text_doc_results[0]
                hierarchy["document_level"]["cognee_text_document"] = {
                    "text_document_uuid": text_doc_data.get("text_document_uuid"),
                    "dataset_name": text_doc_data.get("dataset_name"),
                    "doc_id": text_doc_data.get("doc_id"),
                    "group_id": text_doc_data.get("group_id"),
                    "version": text_doc_data.get("version"),
                    "upload_id": text_doc_data.get("upload_id"),
                    "created_at": text_doc_data.get("created_at"),
                    "updated_at": text_doc_data.get("updated_at"),
                    "properties": serialize_neo4j_properties(text_doc_data.get("properties", {}))
                }
            
            # ========== 3. 检查 Graphiti Episode 和 Cognee TextDocument 的关联 ==========
            if hierarchy["document_level"]["graphiti_episode"] and hierarchy["document_level"]["cognee_text_document"]:
                episode_uuid = hierarchy["document_level"]["graphiti_episode"]["episode_uuid"]
                text_doc_uuid = hierarchy["document_level"]["cognee_text_document"]["text_document_uuid"]
                
                linkage_query = """
                MATCH (td:TextDocument {id: $text_doc_uuid})-[r:RELATES_TO]->(e:Episodic {uuid: $episode_uuid})
                RETURN type(r) as relation_type, properties(r) as relation_properties
                LIMIT 1
                """
                linkage_results = neo4j_client.execute_query(linkage_query, {
                    "text_doc_uuid": text_doc_uuid,
                    "episode_uuid": episode_uuid
                })
                
                if linkage_results and len(linkage_results) > 0:
                    hierarchy["document_level"]["linkage"]["established"] = True
                    hierarchy["document_level"]["linkage"]["relation_type"] = linkage_results[0].get("relation_type")
                    hierarchy["document_level"]["linkage"]["relation_properties"] = serialize_neo4j_properties(
                        linkage_results[0].get("relation_properties", {})
                    )
            
            # ========== 4. 查询章节级别：Cognee DataNode 或 TextDocument ==========
            # 注意：Cognee可能创建DataNode或TextDocument作为章节节点
            # 文档级别的TextDocument应该是最早创建的，章节级别的TextDocument是后续创建的
            # 策略：查询所有有upload_id的TextDocument节点作为章节节点（排除文档级别的）
            data_node_query = """
            MATCH (dn)
            WHERE '__Node__' IN labels(dn)
              AND ('DataNode' IN labels(dn) OR 'TextDocument' IN labels(dn))
              AND dn.group_id = $group_id
              AND dn.upload_id = $upload_id
            OPTIONAL MATCH (dc:DocumentChunk)-[:is_part_of]->(dn)
            WHERE '__Node__' IN labels(dc)
            WITH dn, collect(DISTINCT dc) as chunks
            RETURN dn.id as data_node_id, dn.name as name,
                   dn.doc_id as doc_id, dn.group_id as group_id, dn.version as version,
                   dn.upload_id as upload_id, dn.created_at as created_at,
                   COALESCE(dn.text, dn.name, '') as text,
                   COALESCE(dn.summary, '') as summary,
                   properties(dn) as properties,
                   labels(dn) as labels,
                   size(chunks) as chunk_count
            ORDER BY dn.created_at ASC
            """
            data_node_results = neo4j_client.execute_query(data_node_query, {
                "group_id": group_id,
                "upload_id": upload_id
            })
            
            for dn_data in data_node_results:
                section_info = {
                    "data_node_id": dn_data.get("data_node_id"),
                    "name": dn_data.get("name"),
                    "doc_id": dn_data.get("doc_id"),
                    "group_id": dn_data.get("group_id"),
                    "version": dn_data.get("version"),
                    "upload_id": dn_data.get("upload_id"),
                    "created_at": dn_data.get("created_at"),
                    "text": dn_data.get("text", "")[:200] if dn_data.get("text") else "",  # 截断内容
                    "summary": dn_data.get("summary", "")[:200] if dn_data.get("summary") else "",  # 截断内容
                    "chunk_count": dn_data.get("chunk_count", 0),
                    "properties": serialize_neo4j_properties(dn_data.get("properties", {}))
                }
                hierarchy["section_level"].append(section_info)
            
            # ========== 5. 查询分块级别：Cognee DocumentChunk ==========
            # 按章节分组查询分块
            for section in hierarchy["section_level"]:
                data_node_id = section.get("data_node_id")
                if not data_node_id:
                    continue
                
                chunk_query = """
                MATCH (dc:DocumentChunk)-[:is_part_of]->(dn)
                WHERE '__Node__' IN labels(dc)
                  AND 'DocumentChunk' IN labels(dc)
                  AND dn.id = $data_node_id
                  AND dc.group_id = $group_id
                RETURN dc.id as chunk_id, dc.name as name,
                       dc.doc_id as doc_id, dc.group_id as group_id, dc.version as version,
                       dc.upload_id as upload_id, dc.created_at as created_at,
                       dc.text as text, dc.chunk_index as chunk_index,
                       properties(dc) as properties
                ORDER BY COALESCE(dc.chunk_index, 0) ASC, dc.created_at ASC
                """
                chunk_results = neo4j_client.execute_query(chunk_query, {
                    "group_id": group_id,
                    "data_node_id": data_node_id
                })
                
                section["chunks"] = []
                for chunk_data in chunk_results:
                    chunk_info = {
                        "chunk_id": chunk_data.get("chunk_id"),
                        "name": chunk_data.get("name"),
                        "doc_id": chunk_data.get("doc_id"),
                        "group_id": chunk_data.get("group_id"),
                        "version": chunk_data.get("version"),
                        "upload_id": chunk_data.get("upload_id"),
                        "created_at": chunk_data.get("created_at"),
                        "chunk_index": chunk_data.get("chunk_index"),
                        "text": chunk_data.get("text", "")[:200] if chunk_data.get("text") else "",  # 截断内容
                        "properties": serialize_neo4j_properties(chunk_data.get("properties", {}))
                    }
                    section["chunks"].append(chunk_info)
                    hierarchy["chunk_level"].append(chunk_info)
            
            # ========== 6. 数据一致性检查 ==========
            issues = []
            
            # 检查 doc_id 一致性
            doc_ids = set()
            if hierarchy["document_level"]["graphiti_episode"]:
                doc_ids.add(hierarchy["document_level"]["graphiti_episode"].get("doc_id"))
            if hierarchy["document_level"]["cognee_text_document"]:
                doc_ids.add(hierarchy["document_level"]["cognee_text_document"].get("doc_id"))
            for section in hierarchy["section_level"]:
                if section.get("doc_id"):
                    doc_ids.add(section.get("doc_id"))
                for chunk in section.get("chunks", []):
                    if chunk.get("doc_id"):
                        doc_ids.add(chunk.get("doc_id"))
            
            doc_ids.discard(None)
            if len(doc_ids) == 1 and doc_id in doc_ids:
                hierarchy["consistency_check"]["doc_id_match"] = True
            elif len(doc_ids) > 1:
                issues.append(f"doc_id 不一致: {doc_ids}，期望: {doc_id}")
            
            # 检查 group_id 一致性
            group_ids = set()
            if hierarchy["document_level"]["graphiti_episode"]:
                group_ids.add(hierarchy["document_level"]["graphiti_episode"].get("group_id"))
            if hierarchy["document_level"]["cognee_text_document"]:
                group_ids.add(hierarchy["document_level"]["cognee_text_document"].get("group_id"))
            for section in hierarchy["section_level"]:
                if section.get("group_id"):
                    group_ids.add(section.get("group_id"))
                for chunk in section.get("chunks", []):
                    if chunk.get("group_id"):
                        group_ids.add(chunk.get("group_id"))
            
            group_ids.discard(None)
            if len(group_ids) == 1 and group_id in group_ids:
                hierarchy["consistency_check"]["group_id_match"] = True
            elif len(group_ids) > 1:
                issues.append(f"group_id 不一致: {group_ids}，期望: {group_id}")
            
            # 检查 version 一致性
            versions = set()
            if hierarchy["document_level"]["graphiti_episode"]:
                versions.add(hierarchy["document_level"]["graphiti_episode"].get("version"))
            if hierarchy["document_level"]["cognee_text_document"]:
                versions.add(hierarchy["document_level"]["cognee_text_document"].get("version"))
            for section in hierarchy["section_level"]:
                if section.get("version"):
                    versions.add(section.get("version"))
                for chunk in section.get("chunks", []):
                    if chunk.get("version"):
                        versions.add(chunk.get("version"))
            
            versions.discard(None)
            # 统一版本格式：将数字版本转换为字符串格式（如 1 -> "V1"）
            normalized_versions = set()
            for v in versions:
                if isinstance(v, (int, float)):
                    # 如果是数字，转换为字符串格式
                    normalized_versions.add(f"V{int(v)}")
                elif isinstance(v, str):
                    # 如果是字符串，统一格式（V1, v1, 1 -> V1）
                    v_upper = v.upper()
                    if v_upper.startswith('V'):
                        normalized_versions.add(v_upper)
                    elif v_upper.isdigit():
                        normalized_versions.add(f"V{v_upper}")
                    else:
                        normalized_versions.add(v)
                else:
                    normalized_versions.add(str(v))
            
            # 统一期望版本格式
            expected_version = doc_version.upper() if isinstance(doc_version, str) else f"V{doc_version}"
            if not expected_version.startswith('V'):
                expected_version = f"V{expected_version}"
            
            if len(normalized_versions) == 1 and expected_version in normalized_versions:
                hierarchy["consistency_check"]["version_match"] = True
            elif len(normalized_versions) > 1:
                issues.append(f"version 不一致: {normalized_versions}，期望: {expected_version}")
            
            hierarchy["consistency_check"]["issues"] = issues
            
            return hierarchy

        except Exception as e:
            logger.error(f"查询文档层级结构失败: {e}", exc_info=True)
            raise
        finally:
            db.close()
    
    async def get_chunks_cognee_mapping(
        self,
        upload_id: int
    ) -> Dict[str, Any]:
        """
        获取chunks与Cognee节点的映射关系
        
        返回每个chunk对应的TextDocument/DataNode和DocumentChunk信息
        """
        from app.services.word_document_service import WordDocumentService
        from app.core.utils import serialize_neo4j_properties
        
        db = SessionLocal()
        try:
            # 获取文档信息
            document = db.query(DocumentUpload).filter(DocumentUpload.id == upload_id).first()
            if not document:
                raise ValueError(f"文档不存在: upload_id={upload_id}")
            
            group_id = document.document_id
            doc_id = f"DOC_{upload_id}"
            
            result = {
                "upload_id": upload_id,
                "file_name": document.file_name,
                "group_id": group_id,
                "doc_id": doc_id,
                "dataset_name": None,
                "cognee_processed": False,  # 是否已执行Cognee处理
                "mappings": []  # chunk与Cognee节点的映射关系
            }
            
            # 读取chunks.json
            if not document.chunks_path or not os.path.exists(os.path.join("/app", document.chunks_path)):
                result["mappings"] = []
                return result
            
            with open(os.path.join("/app", document.chunks_path), 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
                    
            chunks = chunks_data.get("chunks", [])
            if not chunks:
                result["mappings"] = []
                return result
            
            # 如果没有group_id，说明尚未执行Cognee处理
            if not group_id:
                # 只返回预期映射关系
                for idx, chunk in enumerate(chunks):
                    result["mappings"].append({
                        "chunk_index": idx,
                        "chunk": {
                            "chunk_id": chunk.get("chunk_id", f"chunk_{idx+1}"),
                            "title": chunk.get("title", ""),
                            "level": chunk.get("level", 1),
                            "token_count": chunk.get("token_count", 0),
                            "content_length": len(chunk.get("content", ""))
                        },
                        "expected": {
                            "text_document": {
                                "will_create": True,
                                "description": "将创建一个TextDocument/DataNode节点"
                            },
                            "document_chunks": {
                                "will_create": True,
                                "description": "Cognee将自动分块，创建多个DocumentChunk节点"
                            }
                        },
                        "actual": None  # 尚未执行Cognee处理
                    })
                return result
            
            # 查询Cognee节点（按创建顺序排序，以便与chunks顺序匹配）
            # 查询所有TextDocument/DataNode节点（章节级别，排除文档级别）
            data_node_query = """
            MATCH (dn)
            WHERE '__Node__' IN labels(dn)
              AND ('DataNode' IN labels(dn) OR 'TextDocument' IN labels(dn))
              AND dn.group_id = $group_id
              AND dn.upload_id = $upload_id
            WITH dn
            ORDER BY dn.created_at ASC
            RETURN dn.id as data_node_id, dn.name as name,
                   dn.dataset_name as dataset_name,
                   dn.doc_id as doc_id, dn.group_id as group_id, dn.version as version,
                   dn.upload_id as upload_id, dn.created_at as created_at,
                   COALESCE(dn.text, dn.name, '') as text,
                   COALESCE(dn.summary, '') as summary,
                   properties(dn) as properties,
                   labels(dn) as labels
            """
            data_node_results = neo4j_client.execute_query(data_node_query, {
                                    "group_id": group_id,
                "upload_id": upload_id
            })
            
            # 获取dataset_name（从第一个节点获取）
            if data_node_results and len(data_node_results) > 0:
                result["dataset_name"] = data_node_results[0].get("dataset_name")
                result["cognee_processed"] = True
            
            # 为每个chunk匹配对应的TextDocument/DataNode
            for idx, chunk in enumerate(chunks):
                mapping = {
                    "chunk_index": idx,
                    "chunk": {
                        "chunk_id": chunk.get("chunk_id", f"chunk_{idx+1}"),
                        "title": chunk.get("title", ""),
                        "level": chunk.get("level", 1),
                        "token_count": chunk.get("token_count", 0),
                        "content_length": len(chunk.get("content", ""))
                    },
                    "expected": {
                        "text_document": {
                            "will_create": True,
                            "description": "将创建一个TextDocument/DataNode节点"
                        },
                        "document_chunks": {
                            "will_create": True,
                            "description": "Cognee将自动分块，创建多个DocumentChunk节点"
                        }
                    },
                    "actual": None
                }
                
                # 如果已执行Cognee处理，查找对应的节点
                if result["cognee_processed"] and idx < len(data_node_results):
                    data_node_data = data_node_results[idx]
                    data_node_id = data_node_data.get("data_node_id")
                    
                    # 查询该TextDocument/DataNode下的DocumentChunk
                    document_chunks = []
                    if data_node_id:
                        chunk_query = """
                        MATCH (dc:DocumentChunk)-[:is_part_of]->(dn)
                        WHERE '__Node__' IN labels(dc)
                          AND 'DocumentChunk' IN labels(dc)
                          AND dn.id = $data_node_id
                        RETURN dc.id as chunk_id, dc.name as name,
                               dc.text as text, dc.chunk_index as chunk_index,
                               dc.created_at as created_at,
                               properties(dc) as properties
                        ORDER BY COALESCE(dc.chunk_index, 0) ASC, dc.created_at ASC
                        """
                        chunk_results = neo4j_client.execute_query(chunk_query, {
                            "data_node_id": data_node_id
                        })
                        
                        for dc_data in chunk_results:
                            document_chunks.append({
                                "chunk_id": dc_data.get("chunk_id"),
                                "name": dc_data.get("name", ""),
                                "text": dc_data.get("text", "")[:200] if dc_data.get("text") else "",  # 截断
                                "chunk_index": dc_data.get("chunk_index"),
                                "created_at": dc_data.get("created_at"),
                                "text_length": len(dc_data.get("text", "")) if dc_data.get("text") else 0
                            })
                    
                    mapping["actual"] = {
                        "text_document": {
                            "exists": True,
                            "data_node_id": data_node_id,
                            "name": data_node_data.get("name", ""),
                            "dataset_name": data_node_data.get("dataset_name"),
                            "doc_id": data_node_data.get("doc_id"),
                            "group_id": data_node_data.get("group_id"),
                            "version": data_node_data.get("version"),
                            "created_at": data_node_data.get("created_at"),
                            "text_preview": data_node_data.get("text", "")[:200] if data_node_data.get("text") else "",
                            "labels": data_node_data.get("labels", [])
                        },
                        "document_chunks": {
                            "count": len(document_chunks),
                            "chunks": document_chunks
                        }
                    }
                else:
                    # 未执行Cognee处理，actual为None
                    mapping["actual"] = None
                
                result["mappings"].append(mapping)
            
            return result
            
        except Exception as e:
            logger.error(f"查询chunks-Cognee映射关系失败: {e}", exc_info=True)
            raise
        finally:
            db.close()
    
    # ==================== 检索生成流程 ====================
    
    async def step4_milvus_recall(
        self,
        query: str,
        top_k: int = 50,
        group_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        步骤4: Milvus快速召回
        
        向量相似性检索，返回Top K相似结果
        """
        # 获取查询向量
        query_embedding = await embedding_client.get_embedding(query)
        if not query_embedding:
            return {
                "total_count": 0,
                "results": [],
                "requirement_count": 0,
                "rule_count": 0,
                "flow_count": 0
            }
        
        # 搜索所有向量类型
        # 包括：Entity（实体）、Episode（文档级）、Section（章节）、Edge（关系）、Community（社区）
        all_results = []
        
        # 搜索所有向量类型（仅 Graphiti，Cognee 向量由其自动管理）
        vector_types_to_search = [
            VectorType.ENTITY,      # Graphiti实体
            VectorType.EPISODE,     # Graphiti Episode（文档级别）
            VectorType.EDGE,        # Graphiti关系
            VectorType.COMMUNITY    # Graphiti社区
        ]
        
        for vector_type in vector_types_to_search:
            results = self.milvus.search_vectors(
                vector_type=vector_type,
                query_embedding=query_embedding,
                top_k=top_k,  # 每个类型取top_k，最后合并后再取top_k
                group_ids=group_ids,
                min_score=0.3  # 降低阈值以获取更多结果
            )
            
            for sr in results:
                all_results.append({
                    "uuid": sr.uuid,
                    "name": sr.name,
                    "content": sr.content or sr.name,
                    "score": float(sr.score),
                    "type": sr.vector_type.value,  # entity/episode/section/edge/community
                    "group_id": sr.group_id,
                    "metadata": sr.metadata or {}
                })
        
        # 按分数排序
        all_results.sort(key=lambda x: x["score"], reverse=True)
        all_results = all_results[:top_k]  # 最终取Top K
        
        # 批量判断来源（优化性能）
        self._batch_determine_sources(all_results, group_ids)
        
        # 按来源分类统计
        graphiti_results = [r for r in all_results if r.get("source") == "graphiti"]
        cognee_results = [r for r in all_results if r.get("source") == "cognee"]
        milvus_results = [r for r in all_results if r.get("source") == "milvus"]
        
        # 统计各类型数量（支持中英文关键词匹配）
        # Requirement: 检查name/content中是否包含"需求"或"requirement"
        requirement_count = sum(1 for r in all_results 
            if ("需求" in r.get("name", "") or "需求" in r.get("content", "") or 
                "requirement" in r.get("name", "").lower() or "requirement" in r.get("content", "").lower() or
                r.get("type") == "requirement"))
        
        # Rule: 检查name/content中是否包含"规则"或"rule"，或type为rule
        rule_count = sum(1 for r in all_results 
            if ("规则" in r.get("name", "") or "规则" in r.get("content", "") or
                "rule" in r.get("name", "").lower() or "rule" in r.get("content", "").lower() or
                r.get("type") == "rule"))
        
        # Flow: 检查name/content中是否包含"流程"或"flow"，或type为flow
        flow_count = sum(1 for r in all_results 
            if ("流程" in r.get("name", "") or "流程" in r.get("content", "") or
                "flow" in r.get("name", "").lower() or "flow" in r.get("content", "").lower() or
                r.get("type") == "flow"))
        
        # 统计各向量类型数量
        entity_count = sum(1 for r in all_results if r.get("type") == "entity")
        episode_count = sum(1 for r in all_results if r.get("type") == "episode")
        section_count = sum(1 for r in all_results if r.get("type") == "section")
        edge_count = sum(1 for r in all_results if r.get("type") == "edge")
        community_count = sum(1 for r in all_results if r.get("type") == "community")
        image_count = sum(1 for r in all_results if r.get("type") == "image")
        table_count = sum(1 for r in all_results if r.get("type") == "table")
        
        return {
            "total_count": len(all_results),
            "results": all_results,
            # 按来源分类的结果
            "graphiti_results": graphiti_results,
            "cognee_results": cognee_results,
            "milvus_results": milvus_results,
            # 来源统计
            "graphiti_count": len(graphiti_results),
            "cognee_count": len(cognee_results),
            "milvus_count": len(milvus_results),
            # 业务类型统计
            "requirement_count": requirement_count,
            "rule_count": rule_count,
            "flow_count": flow_count,
            # 向量类型统计
            "entity_count": entity_count,
            "episode_count": episode_count,
            "section_count": section_count,
            "edge_count": edge_count,
            "community_count": community_count,
            "image_count": image_count,      # 新增
            "table_count": table_count       # 新增
        }
    
    async def _extract_image_text(self, image_path: str) -> str:
        """
        提取图片中的文字（OCR）
        
        方案2：使用 OCR 提取图片文字
        如果 OCR 不可用，返回空字符串
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            提取的文字内容
        """
        try:
            # 尝试使用 pytesseract 进行 OCR
            try:
                from PIL import Image
                import pytesseract
                
                # 检查图片文件是否存在
                if not os.path.exists(image_path):
                    logger.warning(f"图片文件不存在: {image_path}")
                    return ""
                
                # 打开图片
                image = Image.open(image_path)
                
                # 使用 OCR 提取文字（支持中文）
                # 注意：需要安装 tesseract 和中文语言包
                text = pytesseract.image_to_string(image, lang='chi_sim+eng')
                
                if text and text.strip():
                    logger.debug(f"图片 OCR 成功: {image_path}, 提取文字长度: {len(text)}")
                    return text.strip()
                else:
                    logger.debug(f"图片 OCR 未提取到文字: {image_path}")
                    return ""
                    
            except ImportError:
                logger.warning("pytesseract 未安装，跳过 OCR，使用图片描述")
                return ""
            except Exception as e:
                logger.warning(f"图片 OCR 失败: {image_path}, 错误: {e}")
                return ""
                
        except Exception as e:
            logger.error(f"提取图片文字失败: {e}", exc_info=True)
            return ""
    
    def _format_table_as_text(self, table_data: dict) -> str:
        """
        将表格数据转换为结构化文本
        
        方案2：表格结构化文本 + 向量化
        
        Args:
            table_data: 表格数据字典
            
        Returns:
            结构化文本
        """
        try:
            text_parts = []
            
            # 表格标题
            title = table_data.get("title", "")
            if title:
                text_parts.append(f"表格标题：{title}")
            
            # 表头
            headers = table_data.get("headers", [])
            if headers:
                text_parts.append(f"表头：{', '.join(str(h) for h in headers)}")
            
            # 数据行
            rows = table_data.get("rows", [])
            if rows:
                text_parts.append("数据：")
                for idx, row in enumerate(rows[:50], 1):  # 限制最多50行
                    row_text = ', '.join(str(cell) for cell in row if cell)
                    text_parts.append(f"  行{idx}: {row_text}")
                
                if len(rows) > 50:
                    text_parts.append(f"  ...（共 {len(rows)} 行，仅显示前50行）")
            
            result = "\n".join(text_parts)
            
            # 限制总长度（为向量化留空间）
            if len(result) > 2000:
                result = result[:2000] + "..."
            
            return result
            
        except Exception as e:
            logger.error(f"格式化表格文本失败: {e}", exc_info=True)
            return table_data.get("title", "表格") or "表格"
    
    def _batch_determine_sources(self, results: List[Dict[str, Any]], group_ids: Optional[List[str]]) -> None:
        """
        批量判断结果的来源（优化性能）
        
        避免对每个结果单独查询Neo4j，而是批量查询
        """
        # 先快速判断：Section直接归为Milvus，Episode/Edge/Community归为Graphiti
        for result in results:
            result_type = result.get("type", "")
            
            if result_type == "section":
                result["source"] = "milvus"
            elif result_type in ["episode", "edge", "community"]:
                result["source"] = "graphiti"
            else:
                # Entity类型需要进一步判断，先标记为待判断
                result["source"] = None
        
        # 收集需要判断的Entity的uuid和group_id
        entity_uuids_to_check = []
        entity_group_ids = set()
        
        for result in results:
            if result.get("source") is None:  # 待判断的Entity
                uuid = result.get("uuid", "")
                group_id = result.get("group_id", "")
                if uuid and group_id:
                    entity_uuids_to_check.append({
                        "uuid": uuid,
                        "group_id": group_id,
                        "result": result
                    })
                    entity_group_ids.add(group_id)
        
        # 如果没有需要判断的Entity，直接返回
        if not entity_uuids_to_check:
            # 将所有None设置为graphiti（默认）
            for result in results:
                if result.get("source") is None:
                    result["source"] = "graphiti"
            return
        
        # 批量查询Cognee节点（一次性查询所有group_id）
        try:
            # 使用 group_id 列表查询所有相关的节点
            # 批量查询：查找所有可能是Cognee节点的Entity
            cognee_query = """
            MATCH (n)
            WHERE (n.uuid IN $uuids OR n.id IN $uuids)
              AND '__Node__' IN labels(n)
              AND (
                n.group_id IN $group_ids
                OR any(gid IN $group_ids WHERE n.dataset_name CONTAINS gid)
                OR any(gid IN $group_ids WHERE n.dataset_id CONTAINS gid)
              )
            RETURN n.uuid as uuid, n.id as id, n.dataset_name as dataset_name
            """
            
            uuids = [item["uuid"] for item in entity_uuids_to_check]
            cognee_results = neo4j_client.execute_query(cognee_query, {
                "uuids": uuids,
                "group_ids": entity_group_ids
            })
            
            # 构建Cognee节点集合
            cognee_uuids = set()
            for cognee_result in cognee_results:
                uuid = cognee_result.get("uuid") or cognee_result.get("id")
                if uuid:
                    cognee_uuids.add(str(uuid))
            
            # 判断每个Entity的来源
            for item in entity_uuids_to_check:
                result = item["result"]
                uuid = item["uuid"]
                
                # 检查metadata
                metadata = result.get("metadata", {})
                if metadata.get("source") == "cognee":
                    result["source"] = "cognee"
                    continue
                
                # 检查是否在Cognee节点集合中
                if uuid in cognee_uuids:
                    result["source"] = "cognee"
                else:
                    # 检查关键词（快速判断）
                    name = result.get("name", "").lower()
                    content = result.get("content", "").lower()
                    cognee_keywords = ["规则", "流程", "约束", "rule", "flow", "constraint"]
                    
                    # 如果包含关键词，可能是Cognee，但为了性能，默认归为Graphiti
                    # 只有在Neo4j中确认是Cognee节点时才标记为Cognee
                    result["source"] = "graphiti"
        
        except Exception as e:
            logger.warning(f"批量判断来源失败: {e}，默认归为Graphiti")
            # 出错时默认归为Graphiti
            for result in results:
                if result.get("source") is None:
                    result["source"] = "graphiti"
    
    def _determine_result_source(self, search_result, vector_type: VectorType, group_ids: Optional[List[str]]) -> str:
        """
        判断召回结果的来源（仅 Graphiti）
        
        Returns:
            "graphiti": Graphiti创建的知识图谱（Entity, Episode, Edge, Community）
        
        注意：Cognee 向量由 Cognee 自动管理，不在此处理
        """
        # Episode、Edge、Community 来自 Graphiti
        if vector_type in [VectorType.EPISODE, VectorType.EDGE, VectorType.COMMUNITY]:
            return "graphiti"
        
        # Entity类型需要判断：可能是Graphiti Entity或Cognee节点
        if vector_type == VectorType.ENTITY:
            uuid = search_result.uuid
            group_id = search_result.group_id
            
            # 如果uuid包含特定模式，可能是Cognee节点
            # Cognee节点的uuid通常包含rule/flow等标识，或者通过metadata判断
            metadata = search_result.metadata or {}
            
            # 检查metadata中是否有Cognee标识
            if metadata.get("source") == "cognee":
                return "cognee"
            
            # 检查name或content中是否包含Cognee特有的关键词
            name = search_result.name or ""
            content = search_result.content or ""
            
            # Cognee通常处理规则、流程、约束等
            cognee_keywords = ["规则", "流程", "约束", "rule", "flow", "constraint"]
            if any(keyword in name.lower() or keyword in content.lower() for keyword in cognee_keywords):
                # 进一步通过Neo4j确认
                try:
                    # 使用 group_id 查询所有相关的节点
                    cognee_query = """
                    MATCH (n)
                    WHERE (n.uuid = $uuid OR n.id = $uuid)
                      AND '__Node__' IN labels(n)
                      AND (
                          n.group_id = $group_id
                          OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                          OR (n.dataset_id IS NOT NULL AND n.dataset_id CONTAINS $group_id)
                      )
                    RETURN n
                    LIMIT 1
                    """
                    
                    cognee_result = neo4j_client.execute_query(cognee_query, {
                        "uuid": uuid,
                        "group_id": group_id
                    })
                    
                    if cognee_result:
                        return "cognee"
                except Exception as e:
                    logger.debug(f"查询Cognee节点失败: {e}")
            
            # 默认归为Graphiti
            return "graphiti"
        
        # 默认归为Graphiti
        return "graphiti"
    
    async def step5_neo4j_refine(
        self,
        query: str,
        recall_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        步骤5: Neo4j精筛
        
        使用Graphiti和Cognee联合查询，精筛Milvus召回结果
        """
        if not recall_results:
            return {
                "original_count": 0,
                "refined_count": 0,
                "refined_results": []
            }
        
        refined_results = []
        
        for result in recall_results:
            uuid = result.get("uuid", "")
            group_id = result.get("group_id", "")
            content = result.get("content", "")
            
            # 查询Graphiti Entity的详细信息
            graphiti_query = """
            MATCH (n:Entity)
            WHERE n.uuid = $uuid OR n.group_id = $group_id
            OPTIONAL MATCH (n)-[r:RELATES_TO]->(related:Entity)
            WHERE r.group_id = $group_id
            RETURN n, collect(DISTINCT related) as related_entities
            LIMIT 1
            """
            
            graphiti_result = neo4j_client.execute_query(graphiti_query, {
                "uuid": uuid,
                "group_id": group_id
            })
            
            # 查询Cognee节点的详细信息
            cognee_query = """
            MATCH (n)
            WHERE (n.id = $uuid OR n.name = $name OR n.content CONTAINS $content)
              AND '__Node__' IN labels(n)
              AND (
                n.group_id = $group_id
                OR (n.dataset_name IS NOT NULL AND n.dataset_name CONTAINS $group_id)
                OR (n.dataset_id IS NOT NULL AND n.dataset_id CONTAINS $group_id)
              )
            OPTIONAL MATCH (n)-[r]->(related)
            WHERE '__Node__' IN labels(related)
              AND (
                related.group_id = $group_id
                OR (related.dataset_name IS NOT NULL AND related.dataset_name CONTAINS $group_id)
                OR (related.dataset_id IS NOT NULL AND related.dataset_id CONTAINS $group_id)
              )
            RETURN n, collect(DISTINCT related) as related_nodes
            LIMIT 1
            """
            
            # 使用 group_id 查询所有相关的节点
            cognee_result = neo4j_client.execute_query(cognee_query, {
                "uuid": uuid,
                "name": result.get("name", ""),
                "content": content[:100],
                "group_id": group_id
            })
            
            # 构建精筛结果
            refined_item = {
                **result,
                "filter_reason": None,
                "graph_path": None
            }
            
            # 如果找到Graphiti或Cognee的关联，标记为同系统/同业务能力
            if graphiti_result or cognee_result:
                refined_item["filter_reason"] = "图关联匹配"
                refined_results.append(refined_item)
        
        # 统计
        same_system_count = sum(1 for r in refined_results if r.get("filter_reason") == "图关联匹配")
        same_capability_count = same_system_count  # 简化处理
        conflict_rule_count = 0  # 需要更复杂的逻辑来检测冲突
        
        return {
            "original_count": len(recall_results),
            "refined_count": len(refined_results),
            "refined_results": refined_results,
            "same_system_count": same_system_count,
            "same_capability_count": same_capability_count,
            "conflict_rule_count": conflict_rule_count
        }
    
    async def step6_mem0_inject(
        self,
        query: str,
        refined_results: List[Dict[str, Any]],
        user_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        步骤6: Mem0记忆注入
        
        检索用户偏好、会话上下文、反馈记忆，注入到检索结果
        """
        try:
            # 延迟导入mem0，只在需要时才导入
            from app.core.mem0_client import get_mem0_client
            mem0 = get_mem0_client()
            
            # 检索记忆
            memories = mem0.search(query, limit=5)
            
            # 注入记忆到结果
            injected_results = []
            for result in refined_results:
                injected_item = {
                    **result,
                    "memory_injection": None,
                    "preference_match": 0.0
                }
                
                # 检查是否有匹配的记忆
                for memory in memories:
                    if memory.get("content") and query.lower() in memory.get("content", "").lower():
                        injected_item["memory_injection"] = memory.get("content", "")
                        injected_item["preference_match"] = 0.8  # 简化处理
                        break
                
                injected_results.append(injected_item)
            
            # 统计记忆类型
            user_preference_count = sum(1 for m in memories if m.get("type") == "user_preference")
            session_context_count = sum(1 for m in memories if m.get("type") == "session_context")
            feedback_count = sum(1 for m in memories if m.get("type") == "feedback")
            
            return {
                "injected_count": len(injected_results),
                "injected_results": injected_results,
                "memories": memories,
                "user_preference_count": user_preference_count,
                "session_context_count": session_context_count,
                "feedback_count": feedback_count
            }
            
        except ImportError as e:
            logger.warning(f"Mem0模块未安装，跳过记忆注入: {e}")
            # 如果Mem0未安装，返回原始结果
            return {
                "injected_count": len(refined_results),
                "injected_results": refined_results,
                "memories": [],
                "user_preference_count": 0,
                "session_context_count": 0,
                "feedback_count": 0,
                "warning": "Mem0模块未安装，已跳过记忆注入"
            }
        except Exception as e:
            logger.error(f"Mem0记忆注入失败: {e}", exc_info=True)
            # 如果Mem0失败，返回原始结果
            return {
                "injected_count": len(refined_results),
                "injected_results": refined_results,
                "memories": [],
                "user_preference_count": 0,
                "session_context_count": 0,
                "feedback_count": 0,
                "error": f"Mem0记忆注入失败: {str(e)}"
            }
    
    async def mem0_chat(
        self,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        provider: str = "local",
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Mem0 独立问答接口
        
        用于验证 Mem0 的上下文管理能力：
        1. 检索 Mem0 记忆（展示检索到的记忆）
        2. 使用 LLM 生成回答（结合记忆和对话历史）
        3. 保存对话到 Mem0
        4. 返回回答、检索到的记忆、对话历史
        
        Args:
            query: 用户问题
            user_id: 用户ID（必需）
            session_id: 会话ID（可选，用于会话级上下文）
            conversation_history: 对话历史（可选，格式：[{"role": "user", "content": "..."}, ...]）
            provider: LLM提供商（默认 "local"）
            temperature: 温度参数（默认 0.7）
            
        Returns:
            包含以下字段的字典：
            - answer: 生成的回答
            - memories: 检索到的记忆列表
            - memory_count: 记忆数量
            - conversation_history: 更新后的对话历史
        """
        try:
            # 延迟导入mem0，只在需要时才导入
            from app.core.mem0_client import get_mem0_client
            mem0 = get_mem0_client()
            
            # 1. 检索 Mem0 记忆
            logger.info(f"检索 Mem0 记忆: query='{query[:50]}...', user_id={user_id}")
            memories_result = mem0.search(query=query, user_id=user_id, limit=5)
            
            # 处理返回格式（Mem0 返回 {"results": [...]} 或直接返回列表）
            memories = []
            if isinstance(memories_result, dict) and "results" in memories_result:
                memories = memories_result["results"]
            elif isinstance(memories_result, list):
                memories = memories_result
            else:
                logger.warning(f"Mem0 search 返回格式异常: {type(memories_result)}")
                memories = []
            
            logger.info(f"检索到 {len(memories)} 条相关记忆")
            
            # 2. 构建记忆上下文
            memory_context = ""
            if memories:
                memory_context = "相关记忆：\n"
                for i, mem in enumerate(memories, 1):
                    # Mem0 返回格式可能是 {"memory": "...", "metadata": {...}, "score": ...}
                    memory_text = mem.get("memory", "") or mem.get("content", "") or str(mem)
                    score = mem.get("score", 0.0)
                    memory_context += f"{i}. {memory_text}"
                    if score:
                        memory_context += f" (相关性: {score:.2f})"
                    memory_context += "\n"
            
            # 3. 构建对话历史上下文
            history_context = ""
            if conversation_history:
                history_context = "对话历史：\n"
                for msg in conversation_history[-5:]:  # 只取最近5轮对话
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        history_context += f"用户: {content}\n"
                    elif role == "assistant":
                        history_context += f"助手: {content}\n"
            
            # 4. 构建消息列表
            system_prompt = """你是一个智能助手，能够基于用户的记忆和对话历史来回答问题。
请根据以下信息回答用户的问题：
1. 如果提供了相关记忆，请优先考虑这些记忆信息
2. 如果提供了对话历史，请保持对话的连贯性
3. 回答要准确、友好、有帮助"""
            
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            # 构建用户消息内容（包含记忆、对话历史和当前问题）
            user_content_parts = []
            
            if memory_context:
                user_content_parts.append(memory_context)
            if history_context:
                user_content_parts.append(history_context)
            
            user_content_parts.append(f"用户问题：{query}")
            
            # 将所有内容合并为一个用户消息
            user_content = "\n\n".join(user_content_parts)
            messages.append({"role": "user", "content": user_content})
            
            # 6. 调用 LLM 生成回答
            logger.info(f"调用 LLM 生成回答: provider={provider}")
            answer = await self.llm_client.chat(
                provider=provider,
                messages=messages,
                temperature=temperature
            )
            
            logger.info(f"LLM 生成回答完成，长度: {len(answer)}")
            
            # 7. 保存对话到 Mem0
            try:
                mem0_messages = [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": answer}
                ]
                mem0.add(mem0_messages, user_id=user_id)
                logger.info(f"对话已保存到 Mem0: user_id={user_id}, session_id={session_id}")
            except Exception as e:
                logger.error(f"保存对话到 Mem0 失败: {e}", exc_info=True)
                # 不影响返回结果，只记录错误
            
            # 8. 更新对话历史
            updated_history = conversation_history.copy() if conversation_history else []
            updated_history.append({"role": "user", "content": query})
            updated_history.append({"role": "assistant", "content": answer})
            
            # 9. 格式化返回的记忆信息
            formatted_memories = []
            for mem in memories:
                formatted_mem = {
                    "memory": mem.get("memory", "") or mem.get("content", "") or str(mem),
                    "score": mem.get("score", 0.0),
                    "metadata": mem.get("metadata", {})
                }
                formatted_memories.append(formatted_mem)
            
            return {
                "answer": answer,
                "memories": formatted_memories,
                "memory_count": len(formatted_memories),
                "conversation_history": updated_history,
                "has_memory": len(formatted_memories) > 0
            }
            
        except ImportError as e:
            logger.warning(f"Mem0模块未安装: {e}")
            # 如果Mem0未安装，仍然可以生成回答（但不使用记忆）
            answer = await self.llm_client.chat(
                provider=provider,
                messages=[{"role": "user", "content": query}],
                temperature=temperature
            )
            updated_history = conversation_history.copy() if conversation_history else []
            updated_history.append({"role": "user", "content": query})
            updated_history.append({"role": "assistant", "content": answer})
            
            return {
                "answer": answer,
                "memories": [],
                "memory_count": 0,
                "conversation_history": updated_history,
                "has_memory": False,
                "warning": "Mem0模块未安装，已跳过记忆功能"
            }
        except Exception as e:
            logger.error(f"Mem0 问答失败: {e}", exc_info=True)
            raise
    
    async def step7_llm_generate(
        self,
        query: str,
        retrieval_results: List[Dict[str, Any]] = None,
        provider: str = "local",
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        步骤7: LLM生成
        
        基于智能检索结果（v4.0），生成回答
        
        Args:
            query: 用户问题
            retrieval_results: 智能检索结果（v4.0格式，包含source、source_channel、doc_id、version等元数据）
            provider: LLM提供商
            temperature: 温度参数
        """
        retrieval_results = retrieval_results or []
        
        # 构建智能检索上下文（按相似度排序，取Top 20）
        retrieval_context_parts = []
        chunk_count = 0
        entity_count = 0
        graphiti_count = 0
        cognee_count = 0
        
        if retrieval_results:
            # 按score降序排序
            sorted_results = sorted(retrieval_results, key=lambda x: x.get('score', 0), reverse=True)
            top_results = sorted_results[:20]  # 取Top 20
            
            for idx, r in enumerate(top_results, 1):
                source = r.get('source', 'unknown')
                source_channel = r.get('source_channel', 'unknown')
                name = r.get('name', '')
                content = r.get('content', '')
                score = r.get('score', 0)
                doc_id = r.get('doc_id', 'unknown')
                version = r.get('version', 'unknown')
                
                # 统计各类型结果数量
                if source_channel == 'DocumentChunk':
                    chunk_count += 1
                    type_label = "文本片段"
                elif source_channel == 'Entity':
                    entity_count += 1
                    type_label = "实体"
                else:
                    type_label = source_channel
                
                if source == 'Graphiti':
                    graphiti_count += 1
                elif source == 'Cognee' or source == 'Cognee_Neo4j':
                    cognee_count += 1
                
                # 格式化内容（限制长度）
                content_preview = content[:300] if len(content) > 300 else content
                
                retrieval_context_parts.append(
                    f"{idx}. 【来源:{source}】【类型:{type_label}】【相似度:{score:.2%}】\n"
                    f"   标题: {name}\n"
                    f"   文档ID: {doc_id} (版本:{version})\n"
                    f"   内容: {content_preview}"
                )
        
        retrieval_context = "\n\n".join(retrieval_context_parts) if retrieval_context_parts else "（未检索到相关知识）"
        
        logger.info(f"开始LLM生成: 检索结果数={len(retrieval_results)}, DocumentChunk={chunk_count}, Entity={entity_count}, Graphiti={graphiti_count}, Cognee={cognee_count}")
        
        # 构建完整的Prompt模板
        main_prompt = f"""你是一个智能助手，基于以下知识库检索结果回答用户问题。

【检索策略】v4.0
- 阶段1: DocumentChunk（文本片段）单路检索 + 分数阈值过滤 + Top K选择
- 阶段2: Graphiti（文档级业务结构化）+ Cognee（章节级语义实体）知识图谱扩展

【检索到的相关知识（Top 20，按相似度排序）】
{retrieval_context}

【用户问题】
{query}

【回答要求】
1. 优先引用相似度高的内容
2. 区分文本片段（DocumentChunk）和实体（Entity）的不同作用：
   - DocumentChunk: 提供详细的文本描述和上下文
   - Entity: 提供关键概念和结构化信息（Graphiti为文档级业务实体，Cognee为章节级语义实体）
3. 回答要结构清晰、逻辑严谨、准确详细
4. 如果检索结果不足以回答问题，请明确说明
5. 引用内容时，标注来源文档ID和版本号
6. 如果用户问题涉及多个方面，请分点作答
"""
        
        # 生成回答
        logger.info("正在调用LLM生成主要回答...")
        import time
        llm_start_time = time.time()
        generated_answer = await self.llm_client.chat(
            provider=provider,
            messages=[{"role": "user", "content": main_prompt}],
            temperature=temperature
        )
        llm_time = time.time() - llm_start_time
        logger.info(f"LLM主要回答生成完成，耗时: {llm_time:.2f}秒")
        
        # 生成对比分析（可选，基于检索结果）- 简化处理，减少LLM调用
        comparison_analysis = None
        if retrieval_results and len(retrieval_results) > 0:
            logger.info("正在生成对比分析...")
            try:
                # 获取前3条检索结果的格式化文本
                top3_context = "\n\n".join(retrieval_context_parts[:3]) if len(retrieval_context_parts) >= 3 else "\n\n".join(retrieval_context_parts)
                comparison_prompt = f"""基于以下检索结果，简要分析用户问题与知识库内容的关联（100字以内）：

用户问题：{query}

检索到的相关内容（前3条）：
{top3_context}

请简要分析关联性。
"""
                comparison_start = time.time()
                comparison_analysis = await self.llm_client.chat(
                    provider=provider,
                    messages=[{"role": "user", "content": comparison_prompt}],
                    temperature=temperature
                )
                logger.info(f"对比分析生成完成，耗时: {time.time() - comparison_start:.2f}秒")
            except Exception as e:
                logger.warning(f"生成对比分析失败: {e}")
        
        # 生成复用建议（基于检索结果）- 简化处理
        reuse_suggestions = []
        if retrieval_results and len(retrieval_results) > 0:
            logger.info("正在生成复用建议...")
            try:
                # 获取前3条检索结果的格式化文本
                top3_context = "\n\n".join(retrieval_context_parts[:3]) if len(retrieval_context_parts) >= 3 else "\n\n".join(retrieval_context_parts)
                reuse_prompt = f"""基于以下检索结果，提供可以复用的组件或建议（最多3条，每条一句话）：

用户问题：{query}

检索到的相关内容（前3条）：
{top3_context}

请列出可以复用的组件或建议。
"""
                reuse_start = time.time()
                reuse_suggestions_text = await self.llm_client.chat(
                    provider=provider,
                    messages=[{"role": "user", "content": reuse_prompt}],
                    temperature=temperature
                )
                logger.info(f"复用建议生成完成，耗时: {time.time() - reuse_start:.2f}秒")

                # 解析复用建议
                reuse_suggestions = [
                    {
                        "type": "复用建议",
                        "title": item.strip().replace('- ', '').replace('* ', '').replace('1. ', '').replace('2. ', '').replace('3. ', ''),
                        "content": item.strip(),
                        "source": "LLM生成"
                    }
                    for item in reuse_suggestions_text.split("\n")
                    if item.strip() and len(item.strip()) > 10
                ][:3]  # 最多3条
            except Exception as e:
                logger.warning(f"生成复用建议失败: {e}")

        # 生成风险提示 - 简化处理
        risk_warnings = []
        logger.info("正在生成风险提示...")
        try:
            # 获取前3条检索结果的格式化文本
            top3_context = "\n\n".join(retrieval_context_parts[:3]) if len(retrieval_context_parts) >= 3 else "\n\n".join(retrieval_context_parts)
            risk_prompt = f"""基于以下信息，识别潜在风险或注意事项（最多3条，每条一句话）：

用户问题：{query}

检索到的相关内容（前3条）：
{top3_context}

请列出潜在的风险和注意事项。
"""
            risk_start = time.time()
            risk_warnings_text = await self.llm_client.chat(
                provider=provider,
                messages=[{"role": "user", "content": risk_prompt}],
                temperature=temperature
            )
            logger.info(f"风险提示生成完成，耗时: {time.time() - risk_start:.2f}秒")

            # 解析风险提示
            risk_warnings = [
                {
                    "title": "风险提示",
                    "content": item.strip().replace('- ', '').replace('* ', '').replace('1. ', '').replace('2. ', '').replace('3. ', '')
                }
                for item in risk_warnings_text.split("\n")
                if item.strip() and len(item.strip()) > 10
            ][:3]  # 最多3条
        except Exception as e:
            logger.warning(f"生成风险提示失败: {e}")
        
        total_time = time.time() - llm_start_time
        logger.info(f"LLM生成全部完成，总耗时: {total_time:.2f}秒")
        
        return {
            "generated_document": generated_answer,  # 主要回答
            "comparison_analysis": comparison_analysis,
            "reuse_suggestions": reuse_suggestions,
            "risk_warnings": risk_warnings,
            "retrieval_statistics": {  # 检索统计信息
                "total_results": len(retrieval_results),
                "chunk_count": chunk_count,
                "entity_count": entity_count,
                "graphiti_count": graphiti_count,
                "cognee_count": cognee_count
            },
            "llm_statistics": {  # LLM统计信息
                "total_time": total_time,
                "main_answer_time": llm_time,
                "temperature": temperature
            }
        }
    
    async def step7_llm_generate_stream(
        self,
        query: str,
        retrieval_results: List[Dict[str, Any]] = None,
        provider: str = "qianwen",
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        步骤7: LLM流式生成（仅主要回答）
        
        基于智能检索结果（v4.0），流式生成回答
        
        Args:
            query: 用户问题
            retrieval_results: 智能检索结果（v4.0格式）
            provider: LLM提供商（支持 qianwen, deepseek, kimi）
            temperature: 温度参数
            
        Yields:
            生成的文本片段（逐个chunk）
        """
        if provider not in ["qianwen", "deepseek", "kimi"]:
            raise ValueError(f"流式输出仅支持 qianwen、deepseek、kimi，当前provider: {provider}")
        
        retrieval_results = retrieval_results or []
        
        # 构建智能检索上下文（同非流式版本）
        retrieval_context_parts = []
        chunk_count = 0
        entity_count = 0
        graphiti_count = 0
        cognee_count = 0
        
        if retrieval_results:
            # 按score降序排序
            sorted_results = sorted(retrieval_results, key=lambda x: x.get('score', 0), reverse=True)
            top_results = sorted_results[:20]  # 取Top 20
            
            for idx, r in enumerate(top_results, 1):
                source = r.get('source', 'unknown')
                source_channel = r.get('source_channel', 'unknown')
                name = r.get('name', '')
                content = r.get('content', '')
                score = r.get('score', 0)
                doc_id = r.get('doc_id', 'unknown')
                version = r.get('version', 'unknown')
                
                # 统计各类型结果数量
                if source_channel == 'DocumentChunk':
                    chunk_count += 1
                    type_label = "文本片段"
                elif source_channel == 'Entity':
                    entity_count += 1
                    type_label = "实体"
                else:
                    type_label = source_channel
                
                if source == 'Graphiti':
                    graphiti_count += 1
                elif source == 'Cognee' or source == 'Cognee_Neo4j':
                    cognee_count += 1
                
                # 格式化内容（限制长度）
                content_preview = content[:300] if len(content) > 300 else content
                
                retrieval_context_parts.append(
                    f"{idx}. 【来源:{source}】【类型:{type_label}】【相似度:{score:.2%}】\n"
                    f"   标题: {name}\n"
                    f"   文档ID: {doc_id} (版本:{version})\n"
                    f"   内容: {content_preview}"
                )
        
        retrieval_context = "\n\n".join(retrieval_context_parts) if retrieval_context_parts else "（未检索到相关知识）"
        
        logger.info(f"开始LLM流式生成: 检索结果数={len(retrieval_results)}, DocumentChunk={chunk_count}, Entity={entity_count}, Graphiti={graphiti_count}, Cognee={cognee_count}")
        
        # 构建完整的Prompt模板（同非流式版本）
        main_prompt = f"""你是一个智能助手，基于以下知识库检索结果回答用户问题。

【检索策略】v4.0
- 阶段1: DocumentChunk（文本片段）单路检索 + 分数阈值过滤 + Top K选择
- 阶段2: Graphiti（文档级业务结构化）+ Cognee（章节级语义实体）知识图谱扩展

【检索到的相关知识（Top 20，按相似度排序）】
{retrieval_context}

【用户问题】
{query}

【回答要求】
1. 优先引用相似度高的内容
2. 区分文本片段（DocumentChunk）和实体（Entity）的不同作用：
   - DocumentChunk: 提供详细的文本描述和上下文
   - Entity: 提供关键概念和结构化信息（Graphiti为文档级业务实体，Cognee为章节级语义实体）
3. 回答要结构清晰、逻辑严谨、准确详细
4. 如果检索结果不足以回答问题，请明确说明
5. 引用内容时，标注来源文档ID和版本号
6. 如果用户问题涉及多个方面，请分点作答
"""
        
        # 流式生成回答
        logger.info("正在调用LLM流式生成主要回答...")
        import time
        llm_start_time = time.time()
        
        async for chunk in self.llm_client.chat_stream(
            provider=provider,
            messages=[{"role": "user", "content": main_prompt}],
            temperature=temperature
        ):
            yield chunk
        
        llm_time = time.time() - llm_start_time
        logger.info(f"LLM流式回答生成完成，耗时: {llm_time:.2f}秒")
        
        # 流式生成完成后，发送统计信息（使用特殊标记，让API层识别）
        # 注意：这里返回dict，API层会识别并转换为SSE格式
        yield {"__statistics__": {
            "main_answer_time": round(llm_time, 2),
            "temperature": temperature
        }}
    
    # ==================== 智能检索（两阶段检索）====================
    
    async def _search_cognee_milvus_collection(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 50,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        直接查询 Cognee 自动创建的 Milvus collection
        
        Args:
            collection_name: Cognee collection 名称（DocumentChunk_text 或 Entity_name）
            query_embedding: 查询向量
            top_k: 返回数量
            filter_expr: Milvus 过滤表达式（可选）
            
        Returns:
            查询结果列表
        """
        from pymilvus import connections, Collection, utility
        import os
        
        results = []
        
        try:
            # Milvus 连接参数
            milvus_host = os.getenv("MILVUS_HOST", "")
            milvus_port = os.getenv("MILVUS_PORT", "19530")
            
            # 检查 collection 是否存在
            if not utility.has_collection(collection_name):
                logger.warning(f"❌ Milvus collection '{collection_name}' 不存在")
                return []
            
            # 获取 collection
            collection = Collection(collection_name)
            collection.load()
            
            # 构建搜索参数
            search_params = {
                "metric_type": "COSINE",  # 余弦相似度（Cognee 使用的度量）
                "params": {"nprobe": 10}
            }
            
            # 根据collection类型选择不同的输出字段
            if collection_name == "Entity_name":
                output_fields = ["id", "text", "metadata"]
            else:
                output_fields = ["id", "text"]
            
            # 执行搜索
            search_results = collection.search(
                data=[query_embedding],
                anns_field="vector",  # Cognee 的向量字段名
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=output_fields
            )
            
            # 解析结果
            for hits in search_results:
                for hit in hits:
                    result = {
                        "id": hit.id,
                        "text": hit.entity.get("text", ""),
                        "score": float(hit.score),
                        "distance": float(hit.distance)
                    }
                    
                    # Entity_name集合需要额外处理metadata
                    if collection_name == "Entity_name":
                        metadata = hit.entity.get("metadata", {})
                        if isinstance(metadata, str):
                            import json
                            try:
                                metadata = json.loads(metadata)
                            except:
                                metadata = {}
                        result["metadata"] = metadata
                        # 从metadata中提取group_id等信息
                        result["group_id"] = metadata.get("group_id", "") if isinstance(metadata, dict) else ""
                        # 调试：前3个结果的metadata
                        if len(results) < 3:
                            logger.info(f"🔍 Entity_name结果{len(results)}: text={result['text']}, group_id={result['group_id']}, metadata={metadata}, metadata类型={type(metadata)}")
                    
                    results.append(result)
            
            logger.info(f"✅ 查询 {collection_name}: 找到 {len(results)} 个结果")
            
        except Exception as e:
            logger.error(f"❌ 查询 Milvus collection '{collection_name}' 失败: {e}", exc_info=True)
        
        return results
    
    async def smart_retrieval(
        self,
        query: str,
        top_k: int = 50,
        min_score: float = 70.0,
        group_ids: Optional[List[str]] = None,
        enable_refine: bool = True
    ) -> Dict[str, Any]:
        """
        智能检索：两阶段检索策略（优化版 v4.0）
        
        ========== 阶段1：DocumentChunk粒度检索 ==========
        
        **核心改进**：
        1. 只使用DocumentChunk_text（移除Entity_name）
        2. 先过滤分数阈值，再取Top K
        3. 批量查询Neo4j补充元数据（性能优化90%）
        4. 直接返回chunk列表（不聚合到文档）
        
        **检索流程**：
        1. Milvus检索DocumentChunk_text（返回top_k*2个候选）
        2. 过滤分数阈值：只保留 score >= min_score 的chunk
        3. 批量查询Neo4j：补充章节、文档信息（1次查询）
        4. 排序并截取：取Top K个chunk
        
        ========== 阶段2：精细处理（可选）==========
        
        对阶段1的chunk进行精细扩展：
        1. Graphiti知识图谱扩展
        2. Cognee上下文补充
        
        Args:
            query: 查询文本
            top_k: 最多返回多少个chunk（默认50）
            min_score: 最小分数阈值，0-100（默认70）
            group_ids: 检索范围（可选，过滤指定文档）
            enable_refine: 是否启用阶段2精细处理（默认True）
            
        Returns:
            {
                "success": bool,
                "stage1": {
                    "chunk_results": [
                        {
                            "uuid": str,
                            "score": float,  # 0-100
                            "content": str,  # chunk完整内容
                            "chunk_index": int,
                            "section_name": str,  # 章节名称
                            "section_id": str,
                            "document_name": str,  # 文档名称
                            "document_id": str,
                            "group_id": str,
                            "metadata": dict
                        }
                    ],
                    "summary": {
                        "total_chunks": int,  # 返回的chunk总数
                        "total_documents": int,  # 涉及的文档数
                        "score_range": [float, float],  # [最高分, 最低分]
                        "threshold": float,  # 使用的阈值
                        "top_k": int,  # 使用的Top K
                        "filtered_count": int,  # 满足阈值的总数
                        "execution_time": float
                        }
                },
                "stage2": {
                    "refined_results": [...],
                    "total_count": int
                }
            }
        """
        import time
        start_time = time.time()
        
        logger.info(f"🚀 开始智能检索 v4.0: query='{query[:50]}...', top_k={top_k}, min_score={min_score}, enable_refine={enable_refine}")
        
        # ========== 阶段1：DocumentChunk粒度检索 ==========
        stage1_start = time.time()
        
        # 1. 生成查询向量
        query_embedding = await embedding_client.get_embedding(query)
        if not query_embedding:
            return {
                "success": False,
                "error": "查询向量生成失败",
                "stage1": {"chunk_results": [], "summary": {}},
                "stage2": {"refined_results": [], "total_count": 0}
            }
        
        logger.info(f"  ✅ 查询向量生成成功（维度：{len(query_embedding)}）")
        
        # 2. Milvus检索DocumentChunk_text
        # 注意：DocumentChunk_text collection 中没有 group_id 字段（group_id 在 metadata 中）
        # 因此不能在 Milvus 查询时直接过滤 group_id
        # 改为：先检索更多结果，然后在应用层通过 Neo4j 查询后的 group_id 进行过滤
        
        # 如果指定了 group_ids，需要检索更多结果以确保过滤后仍有足够数量
        milvus_top_k = top_k * 3 if group_ids else top_k * 2
        logger.info(f"  🔍 Milvus检索 DocumentChunk_text (候选数={milvus_top_k})")
        if group_ids:
            logger.info(f"    - 指定了 group_ids: {group_ids}, 将在应用层过滤（Neo4j查询后）")
        
        chunk_results = await self._search_cognee_milvus_collection(
            collection_name="DocumentChunk_text",
            query_embedding=query_embedding,
            top_k=milvus_top_k,  # 多检索一些，确保过滤后仍有足够数量
            filter_expr=None  # 不在 Milvus 层过滤 group_id
        )
        
        logger.info(f"  ✅ Milvus返回: {len(chunk_results)} 个chunk")
        
        if not chunk_results:
            logger.warning("  ⚠️ Milvus未返回任何结果")
            return {
                "success": True,
                "stage1": {
                    "chunk_results": [],
                    "summary": {
                        "total_chunks": 0,
                        "total_documents": 0,
                        "score_range": [0, 0],
                        "threshold": min_score,
                        "top_k": top_k,
                        "filtered_count": 0,
                        "execution_time": time.time() - stage1_start
                    }
                },
                "stage2": {"refined_results": [], "total_count": 0}
            }
        
        # 3. 过滤分数阈值（转换为百分制并过滤）
        logger.info(f"  🔍 过滤分数阈值: score >= {min_score}")
        
        filtered_chunks = []
        for chunk in chunk_results:
            score_100 = float(chunk.get("score", 0.0)) * 100  # 转换为百分制
            if score_100 >= min_score:
                chunk["score"] = score_100  # 更新为百分制分数
                filtered_chunks.append(chunk)
        
        logger.info(f"  ✅ 阈值过滤: {len(chunk_results)} → {len(filtered_chunks)} (threshold={min_score})")
        
        if not filtered_chunks:
            logger.warning(f"  ⚠️ 没有chunk满足阈值 {min_score}")
            return {
                "success": True,
                "stage1": {
                    "chunk_results": [],
                    "summary": {
                        "total_chunks": 0,
                        "total_documents": 0,
                        "score_range": [0, 0],
                        "threshold": min_score,
                        "top_k": top_k,
                        "filtered_count": 0,
                        "execution_time": time.time() - stage1_start
                    }
                },
                "stage2": {"refined_results": [], "total_count": 0}
            }
        
        # 4. 排序（按分数从高到低）
        filtered_chunks.sort(key=lambda x: x["score"], reverse=True)
        
        # 5. 截取Top K
        top_k_chunks = filtered_chunks[:top_k]
        logger.info(f"  ✅ Top K截取: {len(filtered_chunks)} → {len(top_k_chunks)} (top_k={top_k})")
        
        # 6. 批量查询Neo4j补充元数据（关键优化：1次查询代替N次）
        logger.info(f"  🔍 批量查询Neo4j补充元数据")
        
        chunk_ids = [chunk.get("id") for chunk in top_k_chunks if chunk.get("id")]
        
        if not chunk_ids:
            logger.warning("  ⚠️ 没有有效的chunk ID")
            return {
                "success": True,
                "stage1": {
                    "chunk_results": [],
                    "summary": {
                        "total_chunks": 0,
                        "total_documents": 0,
                        "score_range": [0, 0],
                        "threshold": min_score,
                        "top_k": top_k,
                        "filtered_count": len(filtered_chunks),
                        "execution_time": time.time() - stage1_start
                    }
                },
                "stage2": {"refined_results": [], "total_count": 0}
            }
        
        # 批量查询Neo4j（关键：只查1次！）
        # 同时获取真实的文档名称（通过group_id）
        neo4j_query = """
        MATCH (dc:DocumentChunk)
        WHERE dc.id IN $chunk_ids
        OPTIONAL MATCH (dc)-[:is_part_of]->(td:TextDocument)
        OPTIONAL MATCH (doc:Document)
        WHERE doc.document_id = dc.group_id OR doc.group_id = dc.group_id
        RETURN 
            dc.id as chunk_id,
            dc.name as chunk_name,
            dc.group_id as group_id,
            dc.doc_id as doc_id,
            dc.chunk_index as chunk_index,
            td.name as section_name,
            td.id as section_id,
            COALESCE(doc.name, doc.filename, doc.title) as document_name
        """
        
        # 初始化 metadata_map，确保在所有情况下都有定义
        metadata_map = {}
        try:
            neo4j_results = neo4j_client.execute_query(neo4j_query, {"chunk_ids": chunk_ids})
            logger.info(f"  ✅ Neo4j返回: {len(neo4j_results)} 条元数据")
            
            # 构建ID到元数据的映射
            for result in neo4j_results:
                chunk_id = result.get("chunk_id")
                if chunk_id:
                    metadata_map[chunk_id] = {
                        "chunk_name": result.get("chunk_name", ""),
                        "group_id": result.get("group_id", ""),
                        "doc_id": result.get("doc_id", ""),
                        "chunk_index": result.get("chunk_index", 0),
                        "section_name": result.get("section_name", ""),
                        "section_id": result.get("section_id", "")
                    }
        except Exception as e:
            logger.error(f"  ❌ Neo4j批量查询失败: {e}", exc_info=True)
            metadata_map = {}  # 确保即使出错也有定义
        
        # 6.0 根据TextDocument分组计算章节号
        # 收集所有TextDocument的id，按创建顺序排序
        section_id_to_index = {}
        section_ids = set()
        for metadata in metadata_map.values():
            section_id = metadata.get("section_id")
            if section_id:
                section_ids.add(section_id)
        
        # 如果有多个不同的TextDocument，按id排序分配章节号
        if len(section_ids) > 1:
            sorted_section_ids = sorted(section_ids)
            for idx, sid in enumerate(sorted_section_ids):
                section_id_to_index[sid] = idx + 1
        elif len(section_ids) == 1:
            # 只有一个TextDocument，所有chunk都是第1章
            section_id_to_index[list(section_ids)[0]] = 1
        
        # 将章节号添加到metadata_map
        for chunk_id, metadata in metadata_map.items():
            section_id = metadata.get("section_id", "")
            if section_id in section_id_to_index:
                metadata["section_index"] = section_id_to_index[section_id]
            else:
                metadata["section_index"] = 1  # 默认第1章
        
        # 6.1 批量查询MySQL获取文档名称
        from app.core.mysql_client import SessionLocal
        from app.models.document_upload import DocumentUpload
        
        unique_group_ids = set()
        for metadata in metadata_map.values():
            group_id = metadata.get("group_id")
            if group_id:
                unique_group_ids.add(group_id)
        
        document_name_map = {}
        if unique_group_ids:
            db = SessionLocal()
            try:
                documents = db.query(DocumentUpload).filter(
                    DocumentUpload.document_id.in_(unique_group_ids)
                ).all()
                for doc in documents:
                    document_name_map[doc.document_id] = doc.file_name or "未知文档"
                logger.info(f"  ✅ MySQL返回: {len(document_name_map)} 个文档名称")
            except Exception as e:
                logger.error(f"  ❌ MySQL查询失败: {e}", exc_info=True)
            finally:
                db.close()
        
        for chunk_id, metadata in metadata_map.items():
            group_id = metadata.get("group_id", "")
            if group_id in document_name_map:
                metadata["document_name"] = document_name_map[group_id]
        
        # 7. 组装完整的chunk信息
        logger.info(f"  🔧 组装完整chunk信息")
        
        final_chunks = []
        for chunk in top_k_chunks:
            chunk_id = chunk.get("id")
            metadata = metadata_map.get(chunk_id, {})
            
            # 如果Neo4j查询失败，使用默认值
            group_id = metadata.get("group_id", "unknown")
            if group_ids and group_id not in group_ids:
                # 如果指定了group_ids，但这个chunk不属于，跳过
                continue
            
            final_chunks.append({
                "uuid": chunk_id,
                "score": chunk.get("score", 0.0),
                "content": chunk.get("text", ""),
                "chunk_index": metadata.get("chunk_index", 0),
                "section_name": (metadata.get("section_name") if metadata.get("section_name") and not metadata.get("section_name", "").startswith("text_") else f"第{metadata.get('section_index', 1)}章"),
                "section_id": metadata.get("section_id", ""),
                "document_name": metadata.get("document_name") or "未知文档",
                "document_id": metadata.get("doc_id", ""),
                "group_id": group_id,
                "metadata": {
                    "source": "DocumentChunk_text",
                    "milvus_search": True,
                    "neo4j_enriched": bool(metadata)
                }
                    })
        
        # 8. 统计信息
        scores = [chunk["score"] for chunk in final_chunks]
        documents = set(chunk["group_id"] for chunk in final_chunks)
        
        stage1_time = time.time() - stage1_start
        
        stage1_result = {
            "chunk_results": final_chunks,
            "summary": {
                "total_chunks": len(final_chunks),
                "total_documents": len(documents),
                "score_range": [max(scores), min(scores)] if scores else [0, 0],
                "threshold": min_score,
                "top_k": top_k,
                "filtered_count": len(filtered_chunks),
                "execution_time": round(stage1_time, 2)
            }
        }
        
        logger.info(
            f"✅ 阶段1完成: 返回 {len(final_chunks)} 个chunk, "
            f"涉及 {len(documents)} 个文档, "
            f"分数范围: {stage1_result['summary']['score_range']}, "
            f"耗时: {stage1_time:.2f}秒"
        )
        
        # ========== 阶段2：精细处理（可选）==========
        stage2_start = time.time()
        stage2_result = {
            "graphiti": {
                "entities": [],
                "relationship_graph": {
                    "nodes": [],
                    "edges": []
                },
                "statistics": {
                    "entity_count": 0,
                    "relationship_count": 0,
                    "path_count": 0
                }
            },
            "cognee": {
                "entities": [],
                "relationship_graph": {
                    "nodes": [],
                    "edges": []
                },
                "statistics": {
                    "entity_count": 0,
                    "relationship_count": 0,
                    "path_count": 0
                }
            }
        }
        
        if enable_refine and final_chunks:
            logger.info(f"🚀 阶段2开始：Graphiti + Cognee 双路扩展")
            
            try:
                # 收集doc_ids和group_ids
                unique_doc_ids = list(set(chunk.get("document_id", "") for chunk in final_chunks if chunk.get("document_id")))
                unique_group_ids = list(set(chunk["group_id"] for chunk in final_chunks if chunk.get("group_id")))
                logger.info(f"  📋 涉及 {len(unique_doc_ids)} 个文档, {len(unique_group_ids)} 个group_id")
                
                # 生成查询向量
                query_embedding = await embedding_client.get_embedding(query)
                if not query_embedding:
                    logger.warning("  ⚠️ 查询向量生成失败，跳过阶段2")
                else:
                    # ========== Graphiti扩展（文档级）==========
                    graphiti_entities = []
                    graphiti_entity_uuids = []
                    graphiti_entity_map = {}
                    
                    try:
                        logger.info(f"  🔍 Graphiti扩展：基于Episode检索文档级Entity")
        
                        # 步骤1：通过doc_id找到Episode
                        episode_query = """
                        MATCH (e:Episodic)
                        WHERE e.doc_id IN $doc_ids
                        RETURN DISTINCT e.doc_id as doc_id, e.group_id as group_id, e.version as version
                        LIMIT 10
                        """
                        episodes = neo4j_client.execute_query(episode_query, {"doc_ids": unique_doc_ids}) if unique_doc_ids else []
                        
                        if episodes:
                            episode_group_ids = [ep.get("group_id") for ep in episodes if ep.get("group_id")]
                            logger.info(f"    ✅ 找到 {len(episodes)} 个Episode, group_ids={len(episode_group_ids)}")
                            
                            # 步骤2：使用Milvus的graphiti_entity_vectors检索文档级Entity
                            if self.milvus.is_available():
                                milvus_results = self.milvus.search_vectors(
                                    vector_type=VectorType.ENTITY,
                                    query_embedding=query_embedding,
                                    top_k=30,
                                    group_ids=episode_group_ids,
                                    min_score=0.5
                                )
                                
                                logger.info(f"    ✅ Milvus返回 {len(milvus_results)} 个Graphiti Entity")
                                
                                # 步骤3：从Neo4j获取Entity详细信息
                                if milvus_results:
                                    entity_uuids = [r.uuid for r in milvus_results if r.uuid]
                                    entity_details_query = """
                                    MATCH (e:Entity)
                                    WHERE e.uuid IN $entity_uuids
                                    RETURN 
                                        COALESCE(e.uuid, toString(id(e))) as uuid,
                                        e.name as name,
                                        labels(e) as labels,
                                        properties(e) as properties,
                                        e.group_id as group_id
                                    """
                                    entity_details = neo4j_client.execute_query(entity_details_query, {"entity_uuids": entity_uuids})
                                    
                                    # 构建Entity信息
                                    for detail in entity_details:
                                        entity_uuid = detail.get("uuid", "")
                                        entity_name = detail.get("name", "")
                                        labels = detail.get("labels", [])
                                        properties = detail.get("properties", {})
                                        
                                        # 找到对应的Milvus结果获取分数
                                        milvus_result = next((r for r in milvus_results if r.uuid == entity_uuid), None)
                                        entity_score = (milvus_result.score * 100) if milvus_result else 0.0
                                        
                                        if entity_uuid and entity_uuid not in graphiti_entity_map:
                                            graphiti_entity_uuids.append(entity_uuid)
                                            # 从labels中获取类型
                                            entity_type = "Entity"
                                            for label in labels:
                                                if label not in ["Entity", "__Node__"]:
                                                    entity_type = label
                                                    break
                                            
                                            if entity_type == "Entity":
                                                entity_type = properties.get("type", "Entity")
                                            
                                            entity_info = {
                                                "uuid": entity_uuid,
                                                "name": entity_name or "未命名实体",
                                                "type": entity_type,
                                                "properties": serialize_neo4j_properties(properties),
                                                "score": entity_score,
                                                "relationships": [],
                                                "paths": [],
                                                "related_chunks": []
                                            }
                                            graphiti_entity_map[entity_uuid] = entity_info
                                            graphiti_entities.append(entity_info)
                                    
                                    logger.info(f"    ✅ 提取到 {len(graphiti_entities)} 个有效Graphiti Entity")
                            else:
                                logger.warning("    ⚠️ Milvus不可用，跳过Graphiti Entity检索")
                        else:
                            logger.warning("    ⚠️ 未找到Episode，跳过Graphiti扩展")
                            
                    except Exception as e:
                        logger.error(f"  ❌ Graphiti扩展失败: {e}", exc_info=True)
                    
                    # ========== Cognee扩展（章节级）==========
                    cognee_entities = []
                    cognee_entity_ids = []
                    cognee_entity_map = {}
                    
                    try:
                        logger.info(f"  🔍 Cognee扩展：基于TextDocument/DataNode检索章节级Entity")
                        
                        # 步骤1：通过chunk_id找到TextDocument/DataNode
                        chunk_ids = [chunk.get("uuid", "") for chunk in final_chunks[:20] if chunk.get("uuid")]
                        if chunk_ids:
                            text_doc_query = """
                        MATCH (dc:DocumentChunk)
                            WHERE dc.id IN $chunk_ids
                        OPTIONAL MATCH (dc)-[:is_part_of]->(td:TextDocument)
                            RETURN DISTINCT 
                                COALESCE(td.group_id, dc.group_id) as group_id,
                                COALESCE(td.doc_id, dc.doc_id) as doc_id
                            LIMIT 10
                            """
                            text_docs = neo4j_client.execute_query(text_doc_query, {"chunk_ids": chunk_ids})
                            
                            if text_docs:
                                text_doc_group_ids = [td.get("group_id") for td in text_docs if td.get("group_id")]
                                logger.info(f"    ✅ 找到 {len(text_docs)} 个TextDocument, group_ids={len(text_doc_group_ids)}")
                                
                                # 步骤2：使用Milvus的Entity_name检索章节级Entity
                                if text_doc_group_ids:
                                    # ⚠️ 重要：Entity_name集合的metadata中没有group_id
                                    # 因此不能通过Milvus过滤，需要先检索更多结果
                                    # 然后在Neo4j查询时通过group_id过滤
                                    cognee_results = await self._search_cognee_milvus_collection(
                                        collection_name="Entity_name",
                                        query_embedding=query_embedding,
                                        top_k=100,  # 检索更多结果，因为无法在Milvus阶段过滤
                                        filter_expr=None  # 不使用过滤表达式
                                    )
                                    
                                    logger.info(f"    ✅ Milvus返回 {len(cognee_results)} 个Cognee Entity (未过滤，将在Neo4j阶段过滤)")
                                    
                                    # 步骤3：从Neo4j获取Entity详细信息，并在Neo4j查询时通过group_id过滤
                                    if cognee_results:
                                        # Entity_name集合返回的id是Milvus的id，需要通过text字段匹配Neo4j的Entity
                                        entity_names = [r.get("text", "") for r in cognee_results if r.get("text")]
                                        entity_details_query = """
                                        MATCH (e:Entity)
                                        WHERE e.name IN $entity_names
                                          AND e.group_id IN $group_ids
                        RETURN 
                                            e.id as id,
                                            e.name as name,
                                            labels(e) as labels,
                                            properties(e) as properties,
                                            e.group_id as group_id
                        LIMIT 50
                        """
                                        entity_details = neo4j_client.execute_query(entity_details_query, {
                                            "entity_names": entity_names,
                                            "group_ids": text_doc_group_ids
                        })

                                        logger.info(f"    ✅ Neo4j返回 {len(entity_details)} 个Cognee Entity (已通过group_id过滤)")
                                        
                                        # 构建Entity信息
                                        for detail in entity_details:
                                            entity_id = detail.get("id", "")
                                            entity_name = detail.get("name", "")
                                            labels = detail.get("labels", [])
                                            properties = detail.get("properties", {})
                                            
                                            # 通过name匹配找到对应的Milvus结果获取分数
                                            milvus_result = next((r for r in cognee_results if r.get("text", "") == entity_name), None)
                                            entity_score = (milvus_result.get("score", 0.0) * 100) if milvus_result else 0.0
                                            
                                            if entity_id and entity_id not in cognee_entity_map:
                                                cognee_entity_ids.append(entity_id)
                                                # 从labels中获取类型
                                                entity_type = "Entity"
                                                for label in labels:
                                                    if label not in ["Entity", "__Node__"]:
                                                        entity_type = label
                                                        break
                                                
                                                if entity_type == "Entity":
                                                    entity_type = properties.get("type", "Entity")
                                                
                                                entity_info = {
                                                    "id": entity_id,
                                                    "name": entity_name or "未命名实体",
                                                    "type": entity_type,
                                                    "properties": serialize_neo4j_properties(properties),
                                                    "score": entity_score,
                                                    "relationships": [],
                                                    "paths": [],
                                                    "related_chunks": []
                                                }
                                                cognee_entity_map[entity_id] = entity_info
                                                cognee_entities.append(entity_info)
                                        
                                        logger.info(f"    ✅ 提取到 {len(cognee_entities)} 个有效Cognee Entity")
                        else:
                            logger.warning("    ⚠️ 未找到chunk_id，跳过Cognee扩展")
                            
                    except Exception as e:
                        logger.error(f"  ❌ Cognee扩展失败: {e}", exc_info=True)
                    
                    # ========== Graphiti关系扩展 ==========
                    if graphiti_entity_uuids:
                        logger.info(f"  🔗 Graphiti图遍历1-2跳关系: {len(graphiti_entity_uuids)} 个Entity")
                        graphiti_relationships, graphiti_paths = await self._traverse_graphiti_relationships(
                            entity_uuids=graphiti_entity_uuids,
                            group_ids=unique_group_ids,
                            max_depth=2
                )
                
                        # 将关系关联到Entity
                        for rel in graphiti_relationships:
                            source_uuid = rel.get("source_uuid", "")
                            target_uuid = rel.get("target_uuid", "")
                            
                            if source_uuid in graphiti_entity_map:
                                graphiti_entity_map[source_uuid]["relationships"].append({
                                    "type": rel.get("type", ""),
                                    "target": rel.get("target_name", ""),
                                    "target_uuid": target_uuid,
                                    "target_type": rel.get("target_type", "Entity"),
                                    "fact": rel.get("fact", "")
                                })
                            
                            if target_uuid in graphiti_entity_map:
                                graphiti_entity_map[target_uuid]["relationships"].append({
                                    "type": rel.get("type", ""),
                                    "target": rel.get("source_name", ""),
                                    "target_uuid": source_uuid,
                                    "target_type": rel.get("source_type", "Entity"),
                                    "fact": rel.get("fact", ""),
                                    "reverse": True
                                })
                        
                        # 将路径关联到Entity
                        for path in graphiti_paths:
                            path_entities = path.get("entities", [])
                            if path_entities:
                                first_entity_uuid = path_entities[0].get("uuid", "")
                                if first_entity_uuid in graphiti_entity_map:
                                    graphiti_entity_map[first_entity_uuid]["paths"].append({
                                        "path": [e.get("name", "") for e in path_entities],
                                        "relationships": path.get("relationships", []),
                                        "depth": path.get("depth", 0)
                                    })
                        
                        logger.info(f"  ✅ Graphiti图遍历完成: {len(graphiti_relationships)} 个关系, {len(graphiti_paths)} 个路径")
                    
                    # ========== Cognee关系扩展 ==========
                    if cognee_entity_ids:
                        logger.info(f"  🔗 Cognee图遍历1-2跳关系: {len(cognee_entity_ids)} 个Entity")
                        # Cognee的关系扩展（简化版，使用通用关系查询）
                        cognee_relationships = []
                        cognee_paths = []
                        
                        try:
                            cognee_rel_query = """
                            MATCH (source:Entity)
                            WHERE source.id IN $entity_ids
                            MATCH (source)-[r]->(target:Entity)
                            WHERE ($group_ids IS NULL OR target.group_id IN $group_ids)
                            RETURN DISTINCT
                                source.id as source_id,
                                source.name as source_name,
                                labels(source) as source_labels,
                                target.id as target_id,
                                target.name as target_name,
                                labels(target) as target_labels,
                                type(r) as rel_type,
                                properties(r) as rel_props
                            LIMIT 50
                            """
                            cognee_rel_results = neo4j_client.execute_query(cognee_rel_query, {
                                "entity_ids": cognee_entity_ids,
                                "group_ids": unique_group_ids
                            })
                            
                            for record in cognee_rel_results:
                                source_id = record.get("source_id", "")
                                target_id = record.get("target_id", "")
                                rel_type = record.get("rel_type", "")
                                
                                if source_id in cognee_entity_map:
                                    cognee_entity_map[source_id]["relationships"].append({
                                        "type": rel_type,
                                        "target": record.get("target_name", ""),
                                        "target_id": target_id,
                                        "target_type": record.get("target_labels", ["Entity"])[0] if record.get("target_labels") else "Entity"
                                    })
                                
                                cognee_relationships.append({
                                    "source_id": source_id,
                                    "target_id": target_id,
                                    "type": rel_type
                                })
                            
                            logger.info(f"  ✅ Cognee图遍历完成: {len(cognee_relationships)} 个关系")
                        except Exception as e:
                            logger.error(f"  ❌ Cognee关系扩展失败: {e}", exc_info=True)
                            
                    # ========== 关联Entity到chunk ==========
                    logger.info(f"  🔗 关联Entity到chunk")
                    chunk_keywords = self._extract_keywords_from_chunks(final_chunks[:10])
                    
                    # Graphiti Entity关联chunk
                    for entity in graphiti_entities:
                        entity_name = entity.get("name", "").lower()
                        related_chunks = []
                        
                        for chunk in final_chunks:
                            chunk_content = chunk.get("content", "").lower()
                            if entity_name in chunk_content or any(
                                keyword in entity_name for keyword in chunk_keywords if len(keyword) > 3
                            ):
                                related_chunks.append({
                                    "uuid": chunk.get("uuid", ""),
                                    "score": chunk.get("score", 0.0),
                                    "content_preview": chunk.get("content", "")[:200] + "...",
                                    "section_name": chunk.get("section_name", ""),
                                    "document_name": chunk.get("document_name", "")
                                })
                        
                        entity["related_chunks"] = related_chunks[:5]
                    
                    # Cognee Entity关联chunk
                    for entity in cognee_entities:
                        entity_name = entity.get("name", "").lower()
                        related_chunks = []
                        
                        for chunk in final_chunks:
                            chunk_content = chunk.get("content", "").lower()
                            if entity_name in chunk_content or any(
                                keyword in entity_name for keyword in chunk_keywords if len(keyword) > 3
                            ):
                                related_chunks.append({
                                    "uuid": chunk.get("uuid", ""),
                                    "score": chunk.get("score", 0.0),
                                    "content_preview": chunk.get("content", "")[:200] + "...",
                                    "section_name": chunk.get("section_name", ""),
                                    "document_name": chunk.get("document_name", "")
                                })
                        
                        entity["related_chunks"] = related_chunks[:5]
                    
                    # ========== 构建关系图 ==========
                    # Graphiti关系图
                    graphiti_nodes = []
                    graphiti_edges = []
                    graphiti_node_map = {}
                    
                    for idx, entity in enumerate(graphiti_entities):
                        graphiti_node_map[entity["uuid"]] = idx
                        graphiti_nodes.append({
                            "id": entity["uuid"],
                            "name": entity["name"],
                            "type": entity["type"],
                            "score": entity["score"],
                            "properties": entity["properties"]
                        })
                    
                    graphiti_edge_set = set()
                    # 先添加所有检索到的Entity作为节点（即使target不在检索结果中，也添加为节点）
                    for entity in graphiti_entities:
                        for rel in entity["relationships"]:
                            target_uuid = rel.get("target_uuid", "")
                            target_name = rel.get("target", "")
                            target_type = rel.get("target_type", "Entity")
                            
                            # 如果target不在节点映射中，添加为节点
                            if target_uuid and target_uuid not in graphiti_node_map:
                                graphiti_node_map[target_uuid] = len(graphiti_nodes)
                                graphiti_nodes.append({
                                    "id": target_uuid,
                                    "name": target_name,
                                    "type": target_type,
                                    "score": 0.0,  # target不在检索结果中，分数为0
                                    "properties": {}
                                })
                            
                            # 添加边（无论target是否在检索结果中）
                            if target_uuid:
                                edge_key = (entity["uuid"], target_uuid, rel.get("type", ""))
                                if edge_key not in graphiti_edge_set:
                                    graphiti_edge_set.add(edge_key)
                                    graphiti_edges.append({
                                        "source": entity["uuid"],
                                        "target": target_uuid,
                                        "type": rel.get("type", ""),
                                        "fact": rel.get("fact", "")
                                    })
                    
                    # Cognee关系图
                    cognee_nodes = []
                    cognee_edges = []
                    cognee_node_map = {}
                    
                    for idx, entity in enumerate(cognee_entities):
                        cognee_node_map[entity["id"]] = idx
                        cognee_nodes.append({
                            "id": entity["id"],
                            "name": entity["name"],
                            "type": entity["type"],
                            "score": entity["score"],
                            "properties": entity["properties"]
                        })
                    
                    cognee_edge_set = set()
                    # 先添加所有检索到的Entity作为节点（即使target不在检索结果中，也添加为节点）
                    for entity in cognee_entities:
                        for rel in entity["relationships"]:
                            target_id = rel.get("target_id", "")
                            target_name = rel.get("target", "")
                            target_type = rel.get("target_type", "Entity")
                    
                            # 如果target不在节点映射中，添加为节点
                            if target_id and target_id not in cognee_node_map:
                                cognee_node_map[target_id] = len(cognee_nodes)
                                cognee_nodes.append({
                                    "id": target_id,
                                    "name": target_name,
                                    "type": target_type,
                                    "score": 0.0,  # target不在检索结果中，分数为0
                                    "properties": {}
                                })
                            
                            # 添加边（无论target是否在检索结果中）
                            if target_id:
                                edge_key = (entity["id"], target_id, rel.get("type", ""))
                                if edge_key not in cognee_edge_set:
                                    cognee_edge_set.add(edge_key)
                                    cognee_edges.append({
                                        "source": entity["id"],
                                        "target": target_id,
                                        "type": rel.get("type", "")
                                    })
                    
                    # ========== 更新结果 ==========
                    stage2_result = {
                        "graphiti": {
                            "entities": graphiti_entities,
                            "relationship_graph": {
                                "nodes": graphiti_nodes,
                                "edges": graphiti_edges
                            },
                            "statistics": {
                                "entity_count": len(graphiti_entities),
                                "relationship_count": len(graphiti_edges),
                                "path_count": sum(len(e.get("paths", [])) for e in graphiti_entities)
                            }
                        },
                        "cognee": {
                            "entities": cognee_entities,
                            "relationship_graph": {
                                "nodes": cognee_nodes,
                                "edges": cognee_edges
                            },
                            "statistics": {
                                "entity_count": len(cognee_entities),
                                "relationship_count": len(cognee_edges),
                                "path_count": 0
                            }
                        }
                    }
                    
                    stage2_time = time.time() - stage2_start
                    logger.info(
                        f"✅ 阶段2完成: "
                        f"Graphiti(Entity={len(graphiti_entities)}, 关系={len(graphiti_edges)}), "
                        f"Cognee(Entity={len(cognee_entities)}, 关系={len(cognee_edges)}), "
                        f"耗时={stage2_time:.2f}秒"
                    )
            except Exception as e:
                logger.error(f"❌ 阶段2执行失败: {e}", exc_info=True)
                # 失败时返回空结果，不影响阶段1
                stage2_result = {
                    "graphiti": {
                        "entities": [],
                        "relationship_graph": {"nodes": [], "edges": []},
                        "statistics": {"entity_count": 0, "relationship_count": 0, "path_count": 0}
                    },
                    "cognee": {
                        "entities": [],
                        "relationship_graph": {"nodes": [], "edges": []},
                        "statistics": {"entity_count": 0, "relationship_count": 0, "path_count": 0}
                    },
                    "error": str(e)
                }
                stage2_time = time.time() - stage2_start
        else:
            stage2_time = 0.0
        
        # ========== 返回最终结果 ==========
        total_time = time.time() - start_time
        
        logger.info(
            f"✅ 智能检索v4.0完成: "
            f"阶段1={stage1_time:.2f}秒 (chunk={len(final_chunks)}, doc={len(documents)}), "
            f"阶段2={stage2_time:.2f}秒, "
            f"总计={total_time:.2f}秒"
        )
        
        return {
            "success": True,
            "stage1": stage1_result,
            "stage2": stage2_result,
            "summary": {
                "total_time": round(total_time, 2),
                "stage1_time": round(stage1_time, 2),
                "stage2_time": round(stage2_time, 2),
                "version": "4.0"
            }
        }
    
    # ==================== 辅助方法 ====================
    
    async def _traverse_graphiti_relationships(
        self,
        entity_uuids: List[str],
        group_ids: Optional[List[str]] = None,
        max_depth: int = 2
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        图遍历Graphiti Entity的1-2跳关系
        
        Args:
            entity_uuids: Entity UUID列表
            group_ids: 文档组ID列表（可选，用于过滤）
            max_depth: 最大遍历深度（1或2）
            
        Returns:
            (relationships, paths): 关系列表和路径列表
        """
        relationships = []
        paths = []
        
        if not entity_uuids:
            return relationships, paths
        
        try:
            # 限制种子数量，避免查询过大
            seed_uuids = entity_uuids[:20]
            
            # 构建查询：1-2跳关系遍历
            # 查询所有关系类型：RELATES_TO, HAS_FEATURE, BELONGS_TO, HAS_MODULE, DEPENDS_ON, IMPLEMENTS等
            query = """
            MATCH (source:Entity)
            WHERE source.uuid IN $entity_uuids
            WITH source
            
            // 1跳关系
            MATCH (source)-[r1]->(target1:Entity)
            WHERE ($group_ids IS NULL OR target1.group_id IN $group_ids)
            WITH source, target1, r1, 1 as depth
            
            // 可选：2跳关系
            OPTIONAL MATCH (target1)-[r2]->(target2:Entity)
            WHERE ($group_ids IS NULL OR target2.group_id IN $group_ids)
              AND depth = 1
              AND $max_depth >= 2
            
            WITH source, target1, r1, target2, r2, depth
            ORDER BY depth, source.uuid
            
            RETURN DISTINCT
                source.uuid as source_uuid,
                source.name as source_name,
                labels(source) as source_labels,
                target1.uuid as target1_uuid,
                target1.name as target1_name,
                labels(target1) as target1_labels,
                type(r1) as rel1_type,
                r1.fact as rel1_fact,
                properties(r1) as rel1_props,
                target2.uuid as target2_uuid,
                target2.name as target2_name,
                labels(target2) as target2_labels,
                type(r2) as rel2_type,
                r2.fact as rel2_fact,
                properties(r2) as rel2_props,
                depth
            LIMIT 100
            """
            
            params = {
                "entity_uuids": seed_uuids,
                "group_ids": group_ids,
                "max_depth": max_depth
            }
            
            results = neo4j_client.execute_query(query, params)
            
            # 处理1跳关系
            for record in results or []:
                source_uuid = record.get("source_uuid", "")
                source_name = record.get("source_name", "")
                source_labels = record.get("source_labels", [])
                source_type = source_labels[0] if source_labels else "Entity"
                
                target1_uuid = record.get("target1_uuid", "")
                target1_name = record.get("target1_name", "")
                target1_labels = record.get("target1_labels", [])
                target1_type = target1_labels[0] if target1_labels else "Entity"
                
                rel1_type = record.get("rel1_type", "")
                rel1_fact = record.get("rel1_fact", "")
                rel1_props = record.get("rel1_props", {})
                
                # 添加1跳关系
                relationships.append({
                    "source_uuid": source_uuid,
                    "source_name": source_name,
                    "source_type": source_type,
                    "target_uuid": target1_uuid,
                    "target_name": target1_name,
                    "target_type": target1_type,
                    "type": rel1_type,
                    "fact": rel1_fact,
                    "properties": serialize_neo4j_properties(rel1_props),
                    "depth": 1
                })
                
                # 处理2跳关系（如果存在）
                target2_uuid = record.get("target2_uuid")
                if target2_uuid and max_depth >= 2:
                    target2_name = record.get("target2_name", "")
                    target2_labels = record.get("target2_labels", [])
                    target2_type = target2_labels[0] if target2_labels else "Entity"
                    
                    rel2_type = record.get("rel2_type", "")
                    rel2_fact = record.get("rel2_fact", "")
                    rel2_props = record.get("rel2_props", {})
                    
                    # 添加2跳关系
                    relationships.append({
                        "source_uuid": target1_uuid,
                        "source_name": target1_name,
                        "source_type": target1_type,
                        "target_uuid": target2_uuid,
                        "target_name": target2_name,
                        "target_type": target2_type,
                        "type": rel2_type,
                        "fact": rel2_fact,
                        "properties": serialize_neo4j_properties(rel2_props),
                        "depth": 2
                    })
                    
                    # 构建路径
                    paths.append({
                        "entities": [
                            {"uuid": source_uuid, "name": source_name, "type": source_type},
                            {"uuid": target1_uuid, "name": target1_name, "type": target1_type},
                            {"uuid": target2_uuid, "name": target2_name, "type": target2_type}
                        ],
                        "relationships": [rel1_type, rel2_type],
                        "depth": 2
                    })
            
            # 去重关系
            seen_rels = set()
            unique_relationships = []
            for rel in relationships:
                rel_key = (rel["source_uuid"], rel["target_uuid"], rel["type"])
                if rel_key not in seen_rels:
                    seen_rels.add(rel_key)
                    unique_relationships.append(rel)
            
            return unique_relationships, paths
            
        except Exception as e:
            logger.error(f"图遍历失败: {e}", exc_info=True)
            return [], []
    
    def _extract_keywords_from_chunks(self, chunks: List[Dict[str, Any]], max_keywords: int = 20) -> List[str]:
        """
        从chunk内容中提取关键词
        
        Args:
            chunks: chunk列表
            max_keywords: 最大关键词数量
            
        Returns:
            关键词列表
        """
        keywords = set()
        
        # 简单的关键词提取：提取长度>=2的中文词和英文词
        for chunk in chunks:
            content = chunk.get("content", "")
            
            # 提取中文词（连续的中文字符）
            chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', content)
            keywords.update(chinese_words)
            
            # 提取英文词（连续的字母，长度>=3）
            english_words = re.findall(r'[a-zA-Z]{3,}', content)
            keywords.update(word.lower() for word in english_words)
            
            # 提取数字+字母组合（如"SD-WAN"）
            alphanumeric = re.findall(r'[a-zA-Z0-9-]{4,}', content)
            keywords.update(word.upper() for word in alphanumeric)
        
        # 过滤太短的关键词，按长度排序
        filtered_keywords = [kw for kw in keywords if len(kw) >= 2]
        filtered_keywords.sort(key=len, reverse=True)
        
        return filtered_keywords[:max_keywords]