"""
知识库管理API
"""
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import os
import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.core.mysql_client import get_db
from app.core.auth import get_current_user, get_current_admin_user
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseMember, MemberRole, document_knowledge_base_association
from app.models.document_upload import DocumentUpload, DocumentStatus
from app.models.document_library import DocumentLibrary
from app.models.task_queue import TaskQueue, TaskStatus, TaskType
from app.services.knowledge_base_service import KnowledgeBaseService
from app.tasks.enhanced_document_processing import process_document_enhanced_task
from app.models.schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
    KnowledgeBaseMemberResponse,
    KnowledgeBaseMemberListResponse,
    AddMemberRequest
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-bases", tags=["知识库管理"])


@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建知识库"""
    try:
        kb = KnowledgeBaseService.create_knowledge_base(
            db=db,
            name=request.name,
            creator_name=current_user.username,  # 使用当前登录用户
            description=request.description,
            visibility=request.visibility
        )
        return KnowledgeBaseResponse(**kb.to_dict())
    except Exception as e:
        logger.error(f"创建知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@router.get("/discover", response_model=KnowledgeBaseListResponse)
async def discover_knowledge_bases(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词（搜索名称和描述）"),
    category: Optional[str] = Query(None, description="分类筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """发现知识库（搜索、分类筛选、综合排序）"""
    try:
        knowledge_bases, total = KnowledgeBaseService.discover_knowledge_bases(
            db=db,
            keyword=keyword,
            category=category,
            page=page,
            page_size=page_size,
            username=current_user.username
        )
        
        # 为每个知识库添加当前用户的成员信息
        kb_responses = []
        for kb in knowledge_bases:
            kb_dict = kb.to_dict()
            # 检查当前用户是否是成员
            has_permission, role = KnowledgeBaseService.check_member_permission(
                db, kb.id, current_user.username
            )
            kb_dict["is_member"] = has_permission
            kb_dict["user_role"] = role.value if role else None
            kb_responses.append(KnowledgeBaseResponse(**kb_dict))
        
        return KnowledgeBaseListResponse(
            knowledge_bases=kb_responses,
            total=total
        )
    except Exception as e:
        logger.error(f"发现知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"发现知识库失败: {str(e)}")


@router.post("/{kb_id}/share-to-all")
async def share_knowledge_base_to_all(
    kb_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """一键共享：将所有激活用户添加为知识库成员（仅Admin）"""
    try:
        result = KnowledgeBaseService.share_to_all_users(
            db=db,
            kb_id=kb_id,
            default_role="viewer"
        )
        
        return {
            "message": "一键共享成功",
            "success_count": result["success_count"],
            "skipped_count": result["skipped_count"],
            "total_users": result["total_users"]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"一键共享失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"一键共享失败: {str(e)}")


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库详情"""
    kb = KnowledgeBaseService.get_knowledge_base(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return KnowledgeBaseResponse(**kb.to_dict())


@router.get("", response_model=KnowledgeBaseListResponse)
async def get_knowledge_bases(
    filter_type: Optional[str] = Query(None, description="筛选类型：my_created（我创建的）/my_joined（我加入的）/shared（共享知识库）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取知识库列表"""
    try:
        knowledge_bases = []
        username = current_user.username
        
        if filter_type == "my_created":
            # 获取我创建的
            knowledge_bases = KnowledgeBaseService.get_knowledge_bases_by_creator(db, username)
        elif filter_type == "my_joined":
            # 获取我加入的
            knowledge_bases = KnowledgeBaseService.get_joined_knowledge_bases(db, username)
        elif filter_type == "shared":
            # 获取共享知识库（排除我创建的）
            knowledge_bases = KnowledgeBaseService.get_shared_knowledge_bases(db, exclude_creator=username)
        else:
            # 默认：获取我创建的 + 我加入的 + 共享的（排除我创建的）
            created = KnowledgeBaseService.get_knowledge_bases_by_creator(db, username)
            joined = KnowledgeBaseService.get_joined_knowledge_bases(db, username)
            shared = KnowledgeBaseService.get_shared_knowledge_bases(db, exclude_creator=username)
            # 合并并去重
            kb_ids = set()
            knowledge_bases = []
            for kb in created + joined + shared:
                if kb.id not in kb_ids:
                    kb_ids.add(kb.id)
                    knowledge_bases.append(kb)
        
        # 为每个知识库添加当前用户的成员信息
        kb_responses = []
        for kb in knowledge_bases:
            kb_dict = kb.to_dict()
            # 检查当前用户是否是成员
            has_permission, role = KnowledgeBaseService.check_member_permission(
                db, kb.id, username
            )
            kb_dict["is_member"] = has_permission
            kb_dict["user_role"] = role.value if role else None
            kb_responses.append(KnowledgeBaseResponse(**kb_dict))
        
        return KnowledgeBaseListResponse(
            knowledge_bases=kb_responses,
            total=len(kb_responses)
        )
    except Exception as e:
        logger.error(f"获取知识库列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int,
    request: KnowledgeBaseUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新知识库（仅创建者）"""
    # 检查权限
    has_permission, role = KnowledgeBaseService.check_member_permission(
        db, kb_id, current_user.username, MemberRole.OWNER
    )
    if not has_permission or role != MemberRole.OWNER:
        raise HTTPException(status_code=403, detail="只有创建者可以编辑知识库")
    
    try:
        kb = KnowledgeBaseService.update_knowledge_base(
            db=db,
            kb_id=kb_id,
            name=request.name,
            description=request.description,
            visibility=request.visibility
        )
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return KnowledgeBaseResponse(**kb.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新知识库失败: {str(e)}")


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除知识库（仅创建者）"""
    # 检查权限
    has_permission, role = KnowledgeBaseService.check_member_permission(
        db, kb_id, current_user.username, MemberRole.OWNER
    )
    if not has_permission or role != MemberRole.OWNER:
        raise HTTPException(status_code=403, detail="只有创建者可以删除知识库")
    
    try:
        success = KnowledgeBaseService.delete_knowledge_base(db, kb_id)
        if not success:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


@router.get("/{kb_id}/members", response_model=KnowledgeBaseMemberListResponse)
async def get_members(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库成员列表"""
    try:
        members = KnowledgeBaseService.get_members(db, kb_id)
        return KnowledgeBaseMemberListResponse(
            members=[KnowledgeBaseMemberResponse(**m.to_dict()) for m in members]
        )
    except Exception as e:
        logger.error(f"获取成员列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取成员列表失败: {str(e)}")


@router.post("/{kb_id}/members", response_model=KnowledgeBaseMemberResponse)
async def add_member(
    kb_id: int,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """添加成员（仅创建者）"""
    # 检查权限
    has_permission, role = KnowledgeBaseService.check_member_permission(
        db, kb_id, current_user.username, MemberRole.OWNER
    )
    if not has_permission or role != MemberRole.OWNER:
        raise HTTPException(status_code=403, detail="只有创建者可以添加成员")
    
    try:
        member = KnowledgeBaseService.add_member(
            db=db,
            kb_id=kb_id,
            member_name=request.member_name,
            role=request.role
        )
        if not member:
            raise HTTPException(status_code=400, detail="成员已存在")
        return KnowledgeBaseMemberResponse(**member.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加成员失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加成员失败: {str(e)}")


@router.delete("/{kb_id}/members/{member_name}")
async def remove_member(
    kb_id: int,
    member_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """移除成员（仅创建者）"""
    # 检查权限
    has_permission, role = KnowledgeBaseService.check_member_permission(
        db, kb_id, current_user.username, MemberRole.OWNER
    )
    if not has_permission or role != MemberRole.OWNER:
        raise HTTPException(status_code=403, detail="只有创建者可以移除成员")
    
    try:
        success = KnowledgeBaseService.remove_member(db, kb_id, member_name)
        if not success:
            raise HTTPException(status_code=400, detail="移除成员失败（成员不存在或不能移除创建者）")
        return {"message": "移除成员成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移除成员失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"移除成员失败: {str(e)}")


@router.post("/{kb_id}/join", response_model=KnowledgeBaseMemberResponse)
async def join_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """加入知识库（仅共享知识库）"""
    try:
        member = KnowledgeBaseService.join_knowledge_base(
            db=db,
            kb_id=kb_id,
            member_name=current_user.username  # 使用当前登录用户
        )
        if not member:
            raise HTTPException(status_code=400, detail="加入失败（知识库不存在、不是共享知识库或已加入）")
        return KnowledgeBaseMemberResponse(**member.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"加入知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"加入知识库失败: {str(e)}")


@router.post("/{kb_id}/leave")
async def leave_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """退出知识库"""
    try:
        success = KnowledgeBaseService.leave_knowledge_base(
            db=db,
            kb_id=kb_id,
            member_name=current_user.username
        )
        if not success:
            raise HTTPException(status_code=400, detail="退出失败（不是成员或不能退出创建者身份）")
        return {"message": "退出成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"退出知识库失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"退出知识库失败: {str(e)}")


class DocumentUploadAndProcessRequest(BaseModel):
    """文档上传和处理请求"""
    chunk_strategy: str = Field("level_1", description="分块策略：level_1, level_2, level_3, level_4, level_5, fixed_token, no_split")
    max_tokens_per_section: int = Field(8000, ge=1000, le=20000, description="每个章节的最大token数")
    analysis_mode: str = Field("smart_segment", description="模板生成方案：smart_segment, full_chunk")
    provider: str = Field("local", description="LLM提供商")
    use_thinking: bool = Field(False, description="是否启用Thinking模式")


class DocumentUploadAndProcessResponse(BaseModel):
    """文档上传和处理响应"""
    task_id: str = Field(..., description="任务ID（用于追踪整个流程）")
    document_id: int = Field(..., description="文档ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="消息")


class AddDocumentsFromLibraryRequest(BaseModel):
    """从文档库添加文档到知识库的请求"""
    document_library_ids: List[int] = Field(..., description="文档库文档ID列表")
    chunk_strategy: str = Field("auto", description="分块策略")
    max_tokens_per_section: int = Field(8000, ge=1000, le=20000, description="每个章节的最大token数")
    analysis_mode: str = Field("smart_segment", description="模板生成方案：smart_segment, full_chunk")
    provider: str = Field("local", description="LLM提供商")
    use_thinking: bool = Field(False, description="是否启用Thinking模式")


class AddDocumentsFromLibraryResponse(BaseModel):
    """从文档库添加文档的响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")
    tasks: List[dict] = Field(default_factory=list, description="创建的任务列表")


@router.post("/{kb_id}/documents/add-from-library", response_model=AddDocumentsFromLibraryResponse)
async def add_documents_from_library(
    kb_id: int,
    request: AddDocumentsFromLibraryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    从文档库添加文档到知识库（只建立关联，不创建处理任务）
    
    前提条件：
    - 文档必须已完成Graphiti和Cognee处理
    
    流程：
    1. 验证文档是否已完成处理
    2. 建立 DocumentLibrary ↔ KnowledgeBase 关联
    3. 更新DocumentUpload记录的knowledge_base_id（如果存在）
    """
    try:
        # 验证知识库存在性和权限
        kb = KnowledgeBaseService.get_knowledge_base(db, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查用户权限（必须是成员）
        has_permission, role = KnowledgeBaseService.check_member_permission(
            db, kb_id, current_user.username
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="您没有权限向此知识库添加文档")
        
        # 验证文档库文档是否存在
        library_documents = db.query(DocumentLibrary).filter(
            DocumentLibrary.id.in_(request.document_library_ids)
        ).all()
        
        if len(library_documents) != len(request.document_library_ids):
            found_ids = {doc.id for doc in library_documents}
            missing_ids = set(request.document_library_ids) - found_ids
            raise HTTPException(status_code=404, detail=f"文档库文档不存在: {missing_ids}")
        
        # 验证文件格式（只支持 .docx）
        invalid_docs = [doc for doc in library_documents if doc.file_type != "docx"]
        if invalid_docs:
            invalid_names = [doc.original_name for doc in invalid_docs]
            raise HTTPException(status_code=400, detail=f"以下文档不支持（只支持 .docx 格式）: {', '.join(invalid_names)}")
        
        # 验证分块策略
        valid_strategies = ["auto", "level_1", "level_2", "level_3", "level_4", "level_5", "fixed_token", "no_split"]
        if request.chunk_strategy not in valid_strategies:
            raise HTTPException(status_code=400, detail=f"无效的分块策略: {request.chunk_strategy}")
        
        added_documents = []
        failed_documents = []
        
        # 为每个文档验证并建立关联
        for library_doc in library_documents:
            # 验证文档是否已完成处理
            verify_result = await KnowledgeBaseService.verify_document_processed(
                db, library_doc.id
            )
            
            if not verify_result["is_ready"]:
                failed_documents.append({
                    "library_document_id": library_doc.id,
                    "document_name": library_doc.original_name,
                    "reason": verify_result["message"]
                })
                continue
            
            # 建立 DocumentLibrary ↔ KnowledgeBase 关联
            from sqlalchemy import select, insert, delete
            existing_association = db.execute(
                select(document_knowledge_base_association).where(
                    document_knowledge_base_association.c.document_id == library_doc.id,
                    document_knowledge_base_association.c.knowledge_base_id == kb_id
                )
            ).first()
            
            if existing_association:
                # 关联已存在，跳过
                logger.info(f"文档已关联到知识库: Document_ID={library_doc.id}, KB_ID={kb_id}")
                added_documents.append({
                    "library_document_id": library_doc.id,
                    "upload_id": verify_result["upload_id"],
                    "document_name": library_doc.original_name,
                    "status": "already_associated"
                })
                continue
            
            # 创建关联
                db.execute(
                    insert(document_knowledge_base_association).values(
                        document_id=library_doc.id,
                        knowledge_base_id=kb_id
                    )
                )
                logger.info(f"建立文档库-知识库关联: Document_ID={library_doc.id}, KB_ID={kb_id}")
            
            # 更新DocumentUpload记录的knowledge_base_id（如果存在）
            if verify_result["upload_id"]:
                upload_record = db.query(DocumentUpload).filter(
                    DocumentUpload.id == verify_result["upload_id"]
                ).first()
                if upload_record:
                    upload_record.knowledge_base_id = kb_id
                    logger.info(f"更新DocumentUpload记录的knowledge_base_id: upload_id={verify_result['upload_id']}, kb_id={kb_id}")
            
            # 更新文档库文档状态
            from app.models.document_library import DocumentLibraryStatus
            library_doc.status = DocumentLibraryStatus.ASSIGNED.value
            
            added_documents.append({
                "library_document_id": library_doc.id,
                "upload_id": verify_result["upload_id"],
                "document_name": library_doc.original_name,
                "status": "added"
            })
        
        db.commit()
        
        # 构建返回消息
        success_count = len(added_documents)
        failed_count = len(failed_documents)
        
        if failed_count > 0:
            failed_names = [d["document_name"] for d in failed_documents]
            message = f"成功添加 {success_count} 个文档到知识库。{failed_count} 个文档添加失败：{', '.join(failed_names)}"
        else:
            message = f"成功添加 {success_count} 个文档到知识库"
        
        return AddDocumentsFromLibraryResponse(
            success=True,
            message=message,
            tasks=added_documents  # 返回添加的文档列表（不再是任务列表）
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"从文档库添加文档失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"添加文档失败: {str(e)}")


@router.post("/{kb_id}/documents/upload-and-process", response_model=DocumentUploadAndProcessResponse, deprecated=True)
async def upload_and_process_document(
    kb_id: int,
    file: UploadFile = File(...),
    chunk_strategy: str = Query("level_1", description="分块策略"),
    max_tokens_per_section: int = Query(8000, ge=1000, le=20000, description="每个章节的最大token数"),
    analysis_mode: str = Query("smart_segment", description="模板生成方案：smart_segment, full_chunk"),
    provider: str = Query("local", description="LLM提供商"),
    use_thinking: bool = Query(False, description="是否启用Thinking模式"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传文档到知识库并自动处理（整合步骤2-5）
    
    流程：
    1. 上传文件（步骤1）
    2. 解析文档（步骤2）
    3. 分块（步骤3）
    4. LLM生成模板（步骤4）
    5. 处理文档并保存到Neo4j（步骤5）
    """
    try:
        # 验证知识库存在性和权限
        kb = KnowledgeBaseService.get_knowledge_base(db, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查用户权限（必须是成员）
        has_permission, role = KnowledgeBaseService.check_member_permission(
            db, kb_id, current_user.username
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="您没有权限向此知识库上传文档")
        
        # 验证文件格式
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension != ".docx":
            raise HTTPException(status_code=400, detail="只支持 .docx 格式")
        
        # 读取文件内容
        content = await file.read()
        file_size = len(content)
        
        # 验证文件大小（50MB限制）
        max_size = 50 * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(status_code=400, detail=f"文件大小超过限制：最大支持 50MB，当前文件 {file_size / 1024 / 1024:.2f}MB")
        
        # 验证分块策略
        valid_strategies = ["level_1", "level_2", "level_3", "level_4", "level_5", "fixed_token", "no_split"]
        if chunk_strategy not in valid_strategies:
            raise HTTPException(status_code=400, detail=f"无效的分块策略: {chunk_strategy}")
        
        # 验证模板生成方案
        if analysis_mode not in ["smart_segment", "full_chunk"]:
            raise HTTPException(status_code=400, detail=f"无效的模板生成方案: {analysis_mode}")
        
        # 保存文件到uploads目录
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_name = file.filename or f"文档_{file_id}{file_extension}"
        file_path = os.path.join(upload_dir, f"{file_id}{file_extension}")
        
        # 保存文件
        with open(file_path, "wb") as f:
            f.write(content)
        
        logger.info(f"文件已保存: {file_path}, 大小: {file_size} 字节")
        
        # 保存到数据库
        db_document = DocumentUpload(
            file_name=file_name,
            file_size=file_size,
            file_path=file_path,
            file_extension=file_extension,
            status=DocumentStatus.VALIDATED,
            knowledge_base_id=kb_id,
            chunk_strategy=chunk_strategy,
            max_tokens_per_section=max_tokens_per_section,
            analysis_mode=analysis_mode
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        
        logger.info(f"文档上传记录已保存到数据库: ID={db_document.id}, KB_ID={kb_id}")
        
        # 创建Celery任务（使用增强版任务）
        celery_task = process_document_enhanced_task.delay(
            upload_id=db_document.id,
            chunk_strategy=chunk_strategy,  # 可以设置为 "auto" 使用智能分块
            max_tokens_per_section=max_tokens_per_section,
            analysis_mode=analysis_mode,
            provider=provider,
            use_thinking=use_thinking,
            enable_quality_gate=True,  # 启用质量门禁
            enable_concurrent=True      # 启用并发处理
        )
        
        # 创建任务记录
        task = TaskQueue(
            task_id=celery_task.id,
            upload_id=db_document.id,
            task_type=TaskType.PROCESS_DOCUMENT.value,
            status=TaskStatus.PENDING.value,
            progress=0,
            current_step="等待处理"
        )
        db.add(task)
        db.commit()
        
        logger.info(f"已创建知识库文档处理任务: task_id={celery_task.id}, upload_id={db_document.id}")
        
        return DocumentUploadAndProcessResponse(
            task_id=celery_task.id,
            document_id=db_document.id,
            status="pending",
            message="文档上传成功，正在处理..."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传和处理文档失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传和处理失败: {str(e)}")


@router.get("/{kb_id}/documents")
async def get_knowledge_base_documents(
    kb_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词（文件名）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取知识库的文档列表"""
    try:
        # 验证知识库存在性
        kb = KnowledgeBaseService.get_knowledge_base(db, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查用户权限（必须是成员）
        has_permission, role = KnowledgeBaseService.check_member_permission(
            db, kb_id, current_user.username
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="您没有权限查看此知识库的文档")
        
        # 查询文档
        from sqlalchemy import or_
        query = db.query(DocumentUpload).filter(DocumentUpload.knowledge_base_id == kb_id)
        
        # 搜索条件
        if search:
            query = query.filter(
                or_(
                    DocumentUpload.file_name.like(f"%{search}%"),
                    DocumentUpload.file_path.like(f"%{search}%")
                )
            )
        
        # 获取总数
        total = query.count()
        
        # 分页
        offset = (page - 1) * page_size
        documents = query.order_by(DocumentUpload.upload_time.desc()).offset(offset).limit(page_size).all()
        
        # 转换为字典列表
        documents_list = [doc.to_dict() for doc in documents]
        
        return {
            "documents": documents_list,
            "total": total,
            "page": page,
            "page_size": page_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库文档列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.delete("/{kb_id}/documents/{document_id}")
async def delete_knowledge_base_document(
    kb_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """从知识库移除文档（只删除关联关系，不删除文件和数据）"""
    try:
        # 验证知识库存在性
        kb = KnowledgeBaseService.get_knowledge_base(db, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查用户权限（必须是创建者或编辑者）
        has_permission, role = KnowledgeBaseService.check_member_permission(
            db, kb_id, current_user.username
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="您没有权限删除此知识库的文档")
        
        # 检查角色（只有owner和editor可以移除）
        if role not in [MemberRole.OWNER, MemberRole.EDITOR]:
            raise HTTPException(status_code=403, detail="只有创建者和编辑者可以从知识库移除文档")
        
        # 查询文档（通过DocumentUpload ID）
        document = db.query(DocumentUpload).filter(
            DocumentUpload.id == document_id,
            DocumentUpload.knowledge_base_id == kb_id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="文档不存在或不属于此知识库")
        
        # 获取文档库文档ID
        library_document_id = document.library_document_id
        
        if not library_document_id:
            raise HTTPException(status_code=400, detail="文档没有关联的文档库记录，无法移除")
        
        # 删除 DocumentLibrary ↔ KnowledgeBase 关联
        from sqlalchemy import delete, select
        deleted_count = db.execute(
            delete(document_knowledge_base_association).where(
                document_knowledge_base_association.c.document_id == library_document_id,
                document_knowledge_base_association.c.knowledge_base_id == kb_id
            )
        ).rowcount
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="关联关系不存在")
        
        # 清除DocumentUpload记录的knowledge_base_id（但不删除记录）
        document.knowledge_base_id = None
        
        # 检查文档是否还关联其他知识库
        remaining_associations = db.execute(
            select(document_knowledge_base_association).where(
                document_knowledge_base_association.c.document_id == library_document_id
            )
        ).fetchall()
        
        # 如果不再关联任何知识库，更新文档库文档状态
        if not remaining_associations:
            from app.models.document_library import DocumentLibrary, DocumentLibraryStatus
            library_doc = db.query(DocumentLibrary).filter(
                DocumentLibrary.id == library_document_id
            ).first()
            if library_doc:
                library_doc.status = DocumentLibraryStatus.UNASSIGNED.value
                logger.info(f"文档不再关联任何知识库，更新状态为UNASSIGNED: library_id={library_document_id}")
        
        db.commit()
        
        logger.info(f"已从知识库移除文档: document_id={document_id}, library_id={library_document_id}, kb_id={kb_id}")
        
        return {
            "message": "文档已从知识库移除",
            "id": document_id,
            "library_document_id": library_document_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库文档失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

