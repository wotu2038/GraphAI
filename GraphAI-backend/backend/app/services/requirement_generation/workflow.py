"""
LangGraph工作流定义
"""
import logging
from typing import Dict, Any
from .state import DocumentGenerationState, GenerationStage
from .agents import (
    ContentRetriever,
    DocumentGenerator,
    DocumentReviewer,
    DocumentOptimizer,
    Orchestrator
)

logger = logging.getLogger(__name__)


async def run_document_generation_workflow(
    state: DocumentGenerationState,
    stream_callback=None,
    progress_callback=None
) -> DocumentGenerationState:
    """
    执行文档生成工作流（支持流式输出和进度回调）
    
    工作流流程：
    1. 检索相关内容（v4.0智能检索）
    2. 生成初始文档（流式输出）
    3. 评审文档质量（流式输出）
    4. 协调决策：是否需要优化
    5. 如果需要优化，执行优化（流式输出）并回到评审
    6. 如果不需要优化，输出最终文档
    
    Args:
        state: 文档生成状态
        stream_callback: 流式输出回调函数（异步），接收(chunk: str, stage: str) -> None
        progress_callback: 进度回调函数（异步），接收(state: DocumentGenerationState) -> None
    """
    try:
        # 步骤1: 检索
        logger.info("开始检索相关内容")
        if progress_callback:
            state["current_stage"] = GenerationStage.RETRIEVING
            state["current_step"] = "正在检索相关内容..."
            await progress_callback(state)
        state = await ContentRetriever.retrieve(state)
        if progress_callback:
            await progress_callback(state)
        
        # 步骤2: 生成（流式输出）
        logger.info("开始生成文档")
        if progress_callback:
            state["current_stage"] = GenerationStage.GENERATING
            state["current_step"] = "正在生成文档..."
            await progress_callback(state)
        state = await DocumentGenerator.generate(state, stream_callback=stream_callback)
        if progress_callback:
            await progress_callback(state)
        
        # 步骤3-6: 迭代优化循环
        max_iterations = state.get("max_iterations", 3)
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            state["iteration_count"] = iteration
            
            # 步骤3: 评审（流式输出）
            logger.info(f"开始评审文档（第{iteration}次迭代）")
            if progress_callback:
                state["current_stage"] = GenerationStage.REVIEWING
                state["current_step"] = f"正在评审文档（第{iteration}次迭代）..."
                await progress_callback(state)
            state = await DocumentReviewer.review(state, stream_callback=stream_callback)
            if progress_callback:
                await progress_callback(state)
            
            # 步骤4: 协调决策
            logger.info("开始协调决策")
            state = await Orchestrator.decide(state)
            if progress_callback:
                await progress_callback(state)
            
            # 步骤5: 判断是否需要优化
            if not state.get("should_continue", False):
                logger.info("文档质量达标，结束迭代")
                break
            
            # 步骤6: 优化（流式输出）
            logger.info(f"开始优化文档（第{iteration}次迭代）")
            if progress_callback:
                state["current_stage"] = GenerationStage.OPTIMIZING
                state["current_step"] = f"正在优化文档（第{iteration}次迭代）..."
                await progress_callback(state)
            state = await DocumentOptimizer.optimize(state, stream_callback=stream_callback)
            if progress_callback:
                await progress_callback(state)
        
        # 如果达到最大迭代次数仍未达标，标记为最终版本
        if iteration >= max_iterations:
            state["is_final"] = True
            state["current_stage"] = GenerationStage.COMPLETED
            state["progress"] = 100
            state["current_step"] = f"达到最大迭代次数（{max_iterations}），输出最终文档"
            logger.info(f"达到最大迭代次数（{max_iterations}），结束迭代")
            if progress_callback:
                await progress_callback(state)
        
        return state
        
    except Exception as e:
        logger.error(f"工作流执行失败: {e}", exc_info=True)
        state["current_stage"] = GenerationStage.FAILED
        state["current_step"] = f"工作流执行失败: {str(e)}"
        if progress_callback:
            await progress_callback(state)
        raise

