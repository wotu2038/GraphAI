"""
Monkey patch for add_rule_associations to use simple BaseModel instead of DataPoint

这个 patch 解决了 Cognee 的 DataPoint 类导致 LLM 调用超时的问题。
通过使用简单的 Pydantic BaseModel 进行 LLM 调用，然后转换为 DataPoint 格式保存。

性能对比：
- 简单 BaseModel：6.17 秒 ✅
- Cognee DataPoint：212.23 秒 ❌ (Server disconnected)
"""

import logging
from typing import List, Optional
from uuid import NAMESPACE_OID, uuid5
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# 简单的 Pydantic 模型，用于 LLM 调用
# 注意：为了避免 Instructor 的 JSON Schema $ref 问题，我们使用内联定义而不是嵌套模型
class SimpleRuleSet(BaseModel):
    """简单的规则集合，用于 LLM 结构化输出"""
    rules: List[str] = Field(
        ...,
        description="List of developer rules extracted from the input text. Each rule is a string representing a coding best practice or guideline.",
    )


async def patched_add_rule_associations(
    data: str,
    rules_nodeset_name: str = "default_rules",  # 添加默认值
    user_prompt_location: str = "coding_rule_association_agent_user.txt",
    system_prompt_location: str = "coding_rule_association_agent_system.txt",
    user_prompt: Optional[str] = None,  # 直接传入的User Prompt内容（优先级高于user_prompt_location）
    system_prompt: Optional[str] = None,  # 直接传入的System Prompt内容（优先级高于system_prompt_location）
    **kwargs  # 接受额外的参数（Pipeline 可能传递）
):
    """
    修复版的 add_rule_associations，使用简单的 BaseModel 进行 LLM 调用
    
    关键修改：
    1. 使用 SimpleRuleSet 代替 Cognee 的 RuleSet（继承自 DataPoint）进行 LLM 调用
    2. LLM 调用成功后，将结果转换为 Cognee 的 Rule（DataPoint）格式
    3. 性能提升：从 212 秒（失败）降低到 6 秒（成功）
    """
    from cognee.infrastructure.databases.graph import get_graph_engine
    from cognee.infrastructure.databases.vector import get_vector_engine
    from cognee.infrastructure.llm.prompts import render_prompt
    from cognee.infrastructure.llm import LLMGateway
    from cognee.modules.engine.models import NodeSet
    from cognee.tasks.storage import add_data_points, index_graph_edges
    
    # 导入 Cognee 的原始 Rule 类（用于最终保存）
    from cognee.tasks.codingagents.coding_rule_associations import Rule, get_existing_rules, get_origin_edges
    
    logger.info("🔧 使用 patched_add_rule_associations（使用简单 BaseModel）")
    
    if isinstance(data, list):
        data = " ".join(data)
    
    # 步骤1: 获取现有规则
    graph_engine = await get_graph_engine()
    existing_rules = await get_existing_rules(rules_nodeset_name=rules_nodeset_name)
    existing_rules_str = "\n".join(f"- {rule}" for rule in existing_rules)
    
    # 步骤2: 构建 prompt
    # 如果直接传入了提示词内容，使用直接传入的内容；否则使用文件路径加载
    if user_prompt is not None:
        # 直接使用传入的user_prompt，替换占位符
        final_user_prompt = user_prompt.replace("{chat}", data)
        final_user_prompt = final_user_prompt.replace("{rules}", existing_rules_str)
        # 支持其他占位符（如 {document_name}, {section_title}, {section_content} 等）
        # 这些占位符在调用时已经替换，这里只替换 {chat} 和 {rules}
    else:
        # 使用文件路径加载
        user_context = {"chat": data, "rules": existing_rules_str}
        final_user_prompt = render_prompt(user_prompt_location, context=user_context)
    
    if system_prompt is not None:
        # 直接使用传入的system_prompt
        final_system_prompt = system_prompt
    else:
        # 使用文件路径加载
        final_system_prompt = render_prompt(system_prompt_location, context={})
    
    # 步骤3: 使用简单的 BaseModel 进行 LLM 调用（关键修复）
    logger.info(f"  调用 LLM（使用 SimpleRuleSet）...")
    simple_rule_list = await LLMGateway.acreate_structured_output(
        text_input=final_user_prompt,
        system_prompt=final_system_prompt,
        response_model=SimpleRuleSet  # ← 使用简单的 BaseModel
    )
    logger.info(f"  ✅ LLM 调用成功，返回 {len(simple_rule_list.rules)} 条规则")
    
    # 步骤4: 转换为 Cognee 的 Rule（DataPoint）格式
    rules_nodeset = NodeSet(
        id=uuid5(NAMESPACE_OID, name=rules_nodeset_name),
        name=rules_nodeset_name
    )
    
    cognee_rules = []
    for rule_text in simple_rule_list.rules:
        # 创建 Cognee 的 Rule 对象（现在 rules 直接是字符串列表）
        cognee_rule = Rule(
            text=rule_text,
            belongs_to_set=rules_nodeset
        )
        cognee_rules.append(cognee_rule)
    
    # 步骤5: 获取关联边
    edges_to_save = await get_origin_edges(data=data, rules=cognee_rules)
    
    # 步骤6: 保存到数据库
    await add_data_points(data_points=cognee_rules)
    
    if len(edges_to_save) > 0:
        await graph_engine.add_edges(edges_to_save)
        await index_graph_edges(edges_to_save)
    
    logger.info(f"  ✅ 已保存 {len(cognee_rules)} 条规则和 {len(edges_to_save)} 条边")


def apply_patch():
    """应用 monkey patch"""
    try:
        import cognee.tasks.codingagents.coding_rule_associations as module
        original_func = module.add_rule_associations
        module.add_rule_associations = patched_add_rule_associations
        logger.info("✅ 已应用 add_rule_associations monkey patch（使用简单 BaseModel）")
        return True
    except Exception as e:
        logger.error(f"❌ 无法应用 add_rule_associations monkey patch: {e}")
        return False
