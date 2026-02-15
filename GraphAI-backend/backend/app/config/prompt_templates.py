"""
Prompt模板配置
定义不同领域的预设模板和默认Prompt
"""
from typing import Dict, Any

# ==================== System Prompt ====================

DEFAULT_SYSTEM_PROMPT = """你是一个专业的知识图谱模板生成专家，擅长从文档中提取实体和关系结构，生成规范的模板配置。你的任务是：
1. 准确识别文档中的核心实体类型
2. 为每个实体定义合适的字段（包含类型、是否必需、描述）
3. 识别实体之间的关系类型
4. 确保生成的JSON格式规范且可解析
5. 避免使用系统保留字段"""


# ==================== User Prompt 模板 ====================

DEFAULT_USER_PROMPT_TEMPLATE = """你是一个知识图谱模板生成专家。请分析以下文档内容，生成适合的实体和关系模板配置。

文档名称：{document_name}

{structure_info}

关键章节内容：
{key_sections}

请根据文档内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别文档中的核心实体{entity_hints}
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么
     * **fields**：字段定义（字段类型、是否必需、描述）
   - 字段类型支持：str, Optional[str], int, Optional[int], bool, Optional[bool], list[str]
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型{relation_hints}
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么
     * **fields**：字段定义
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, source_node_uuid, target_node_uuid, name, fact, attributes

3. **关系映射（edge_type_map）**：
   - 定义哪些实体之间可以使用哪些关系
   - 格式：{{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}

要求：
- 返回标准JSON格式
- 实体类型和关系类型要符合文档的实际内容
- 字段定义要完整（type, required, description）
- 关系映射要准确反映文档中的实体关系
- ⚠️ **严禁使用保留字段名**

返回JSON格式：
{{
  "entity_types": {{
    "EntityName": {{
      "description": "实体类型的描述，说明这个实体类型代表什么",
      "fields": {{
        "field_name": {{
          "type": "str|Optional[str]|int|Optional[int]|bool|Optional[bool]|list[str]",
          "required": true|false,
          "description": "字段描述"
        }}
      }}
    }}
  }},
  "edge_types": {{
    "EdgeName": {{
      "description": "关系类型的描述，说明这个关系类型代表什么",
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


# ==================== 领域预设模板 ====================

DOMAIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "enterprise": {
        "name": "企业管理",
        "description": "适用于企业需求文档、系统设计文档、流程规范等",
        "entity_hints": "（如：需求、功能、模块、系统、流程、人员、部门等）",
        "relation_hints": "（如：HAS_FEATURE包含功能, BELONGS_TO属于, IMPLEMENTS实现, DEPENDS_ON依赖, USED_BY被使用等）",
        "example_entities": ["需求", "功能", "模块", "系统", "流程", "人员", "部门"],
        "example_relations": ["HAS_FEATURE", "BELONGS_TO", "IMPLEMENTS", "DEPENDS_ON", "USED_BY"],
        "system_prompt_suffix": "你特别擅长识别企业管理领域的实体和关系，如需求、功能、模块、系统、流程等。"
    },
    "ecommerce": {
        "name": "电商业务",
        "description": "适用于电商平台、商品管理、订单系统等文档",
        "entity_hints": "（如：商品、订单、用户、优惠券、物流、支付、库存、店铺等）",
        "relation_hints": "（如：ORDERS下单, CONTAINS包含, SHIPS发货, PAYS_WITH支付, BELONGS_TO属于, REVIEWS评价等）",
        "example_entities": ["商品", "订单", "用户", "优惠券", "物流", "支付", "库存", "店铺"],
        "example_relations": ["ORDERS", "CONTAINS", "SHIPS", "PAYS_WITH", "BELONGS_TO", "REVIEWS"],
        "system_prompt_suffix": "你特别擅长识别电商业务领域的实体和关系，如商品、订单、用户、物流等。"
    },
    "medical": {
        "name": "医疗健康",
        "description": "适用于医疗系统、病历管理、诊疗流程等文档",
        "entity_hints": "（如：疾病、药物、治疗方案、患者、医生、医院、科室、检查项目等）",
        "relation_hints": "（如：DIAGNOSES诊断, TREATS治疗, PRESCRIBES开药, WORKS_AT工作于, HAS_SYMPTOM有症状等）",
        "example_entities": ["疾病", "药物", "治疗方案", "患者", "医生", "医院", "科室", "检查项目"],
        "example_relations": ["DIAGNOSES", "TREATS", "PRESCRIBES", "WORKS_AT", "HAS_SYMPTOM"],
        "system_prompt_suffix": "你特别擅长识别医疗健康领域的实体和关系，如疾病、药物、治疗方案、患者等。"
    },
    "financial": {
        "name": "金融业务",
        "description": "适用于金融系统、账户管理、交易流程等文档",
        "entity_hints": "（如：账户、交易、产品、客户、风险、合规、投资组合等）",
        "relation_hints": "（如：OWNS拥有, TRADES交易, MANAGES管理, ASSOCIATED_WITH关联, COMPLIES_WITH符合等）",
        "example_entities": ["账户", "交易", "产品", "客户", "风险", "合规", "投资组合"],
        "example_relations": ["OWNS", "TRADES", "MANAGES", "ASSOCIATED_WITH", "COMPLIES_WITH"],
        "system_prompt_suffix": "你特别擅长识别金融业务领域的实体和关系，如账户、交易、产品、客户等。"
    },
    "custom": {
        "name": "自定义领域",
        "description": "用户自定义实体类型和关系",
        "entity_hints": "",
        "relation_hints": "",
        "example_entities": [],
        "example_relations": [],
        "system_prompt_suffix": "你需要根据文档内容灵活识别实体和关系。"
    }
}


# ==================== 预设完整Prompt模板 ====================

PRESET_PROMPT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "default": {
        "name": "默认通用模板",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE
    },
    "enterprise_strict": {
        "name": "企业管理（严格模式）",
        "system_prompt": DEFAULT_SYSTEM_PROMPT + "\n你倾向于生成严格定义的实体和关系，字段定义清晰，关系明确，避免模糊的描述。",
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE + "\n\n⚠️ **严格模式要求**：\n- 每个实体至少包含3个字段\n- 每个字段都必须有清晰的业务含义\n- 关系类型名称必须使用动词或动词短语\n- 避免使用RELATES_TO等过于宽泛的关系"
    },
    "enterprise_creative": {
        "name": "企业管理（创新模式）",
        "system_prompt": DEFAULT_SYSTEM_PROMPT + "\n你倾向于创新性地发现文档中隐含的实体和关系，可以推理出文档未明确提及但逻辑上存在的实体类型。",
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE + "\n\n💡 **创新模式建议**：\n- 可以推理出文档隐含的实体类型\n- 可以识别潜在的实体关系\n- 可以为实体添加更多元数据字段\n- 鼓励发现跨层级的关系"
    },
    "ecommerce": {
        "name": "电商业务模板",
        "system_prompt": DEFAULT_SYSTEM_PROMPT + "\n" + DOMAIN_TEMPLATES["ecommerce"]["system_prompt_suffix"],
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE
    }
}


def get_domain_template(domain_type: str) -> Dict[str, Any]:
    """
    获取领域模板
    
    Args:
        domain_type: 领域类型（enterprise, ecommerce, medical, financial, custom）
    
    Returns:
        领域模板配置
    """
    return DOMAIN_TEMPLATES.get(domain_type, DOMAIN_TEMPLATES["enterprise"])


def get_preset_prompt_template(preset_name: str) -> Dict[str, str]:
    """
    获取预设Prompt模板
    
    Args:
        preset_name: 预设模板名称（default, enterprise_strict, enterprise_creative, ecommerce）
    
    Returns:
        预设Prompt模板
    """
    return PRESET_PROMPT_TEMPLATES.get(preset_name, PRESET_PROMPT_TEMPLATES["default"])


def build_prompt(
    document_name: str,
    structure_info: str,
    key_sections: str,
    domain_type: str = "enterprise",
    custom_entities: str = "",
    user_prompt_template: str = None
) -> str:
    """
    构建User Prompt
    
    Args:
        document_name: 文档名称
        structure_info: 文档结构信息
        key_sections: 关键章节内容
        domain_type: 领域类型
        custom_entities: 自定义实体提示
        user_prompt_template: 自定义User Prompt模板（可选）
    
    Returns:
        构建好的User Prompt
    """
    # 获取领域模板
    domain_template = get_domain_template(domain_type)
    
    # 构建实体提示
    if domain_type == "custom" and custom_entities:
        entity_hints = f"（如：{custom_entities}）"
    else:
        entity_hints = domain_template["entity_hints"]
    
    # 构建关系提示
    relation_hints = domain_template["relation_hints"]
    
    # 使用自定义模板或默认模板
    template = user_prompt_template or DEFAULT_USER_PROMPT_TEMPLATE
    
    # 替换占位符
    prompt = template.format(
        document_name=document_name,
        structure_info=structure_info,
        key_sections=key_sections,
        entity_hints=entity_hints,
        relation_hints=relation_hints
    )
    
    return prompt


def build_system_prompt(
    domain_type: str = "enterprise",
    custom_system_prompt: str = None
) -> str:
    """
    构建System Prompt
    
    Args:
        domain_type: 领域类型
        custom_system_prompt: 自定义System Prompt（可选）
    
    Returns:
        构建好的System Prompt
    """
    if custom_system_prompt:
        return custom_system_prompt
    
    # 获取领域模板
    domain_template = get_domain_template(domain_type)
    
    # 组合默认System Prompt + 领域特定后缀
    return DEFAULT_SYSTEM_PROMPT + "\n" + domain_template.get("system_prompt_suffix", "")
