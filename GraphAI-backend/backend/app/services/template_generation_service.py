"""
LLM模板生成服务
实现方案B（智能分段）和方案D（全文分块）两种分析模式
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional
from app.core.llm_client import get_llm_client
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)


class TemplateGenerationService:
    """模板生成服务"""
    
    @staticmethod
    def _remove_reserved_fields(template_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        后处理：移除保留字段
        
        Args:
            template_config: LLM生成的模板配置
        
        Returns:
            清理后的模板配置
        """
        entity_reserved = TemplateService.ENTITY_RESERVED_FIELDS
        edge_reserved = TemplateService.EDGE_RESERVED_FIELDS
        
        # 处理实体类型
        entity_types = template_config.get("entity_types", {})
        if isinstance(entity_types, dict):
            for entity_name, entity_config in entity_types.items():
                if isinstance(entity_config, dict) and "fields" in entity_config:
                    fields = entity_config["fields"]
                    if isinstance(fields, dict):
                        # 移除保留字段
                        fields_to_remove = [f for f in fields.keys() if f in entity_reserved]
                        for field in fields_to_remove:
                            logger.warning(f"自动移除实体类型 '{entity_name}' 的保留字段 '{field}'")
                            del fields[field]
        
        # 处理关系类型
        edge_types = template_config.get("edge_types", {})
        if isinstance(edge_types, dict):
            for edge_name, edge_config in edge_types.items():
                if isinstance(edge_config, dict) and "fields" in edge_config:
                    fields = edge_config["fields"]
                    if isinstance(fields, dict):
                        # 移除保留字段
                        fields_to_remove = [f for f in fields.keys() if f in edge_reserved]
                        for field in fields_to_remove:
                            logger.warning(f"自动移除关系类型 '{edge_name}' 的保留字段 '{field}'")
                            del fields[field]
        
        return template_config
    
    @staticmethod
    def smart_segment(content: str) -> Dict[str, Any]:
        """
        方案B：智能分段，提取文档结构
        
        Args:
            content: 文档内容（Markdown格式）
        
        Returns:
            分段结果，包含标题、关键章节、目录等
        """
        # 提取所有标题
        headings = []
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append({
                'level': level,
                'title': title,
                'position': match.start()
            })
        
        # 识别关键章节（包含关键词的章节）
        keywords = ['需求', '功能', '架构', '设计', '模块', '系统', '用户', '产品', 
                   'requirement', 'feature', 'architecture', 'design', 'module', 
                   'system', 'user', 'product']
        key_sections = []
        for i, heading in enumerate(headings):
            if any(kw.lower() in heading['title'].lower() for kw in keywords):
                # 获取章节内容范围
                start = heading['position']
                end = headings[i+1]['position'] if i+1 < len(headings) else len(content)
                section_content = content[start:end]
                # 限制每个章节内容长度（避免过长）
                if len(section_content) > 5000:
                    section_content = section_content[:5000] + "\n\n[内容已截断...]"
                key_sections.append({
                    'title': heading['title'],
                    'level': heading['level'],
                    'content': section_content
                })
        
        # 提取目录部分（第一个一级标题之前）
        first_h1 = next((h for h in headings if h['level'] == 1), None)
        toc_content = content[:first_h1['position']] if first_h1 and first_h1['position'] > 0 else ""
        # 限制目录长度
        if len(toc_content) > 2000:
            toc_content = toc_content[:2000] + "\n\n[目录已截断...]"
        
        # 提取章节标题列表（用于结构分析）
        headings_text = "\n".join([
            f"{'  ' * (h['level'] - 1)}- {h['title']}"
            for h in headings[:30]  # 最多30个标题
        ])
        
        return {
            'headings': headings[:30],  # 最多30个标题
            'headings_text': headings_text,
            'key_sections': key_sections[:5],  # 最多5个关键章节
            'toc_content': toc_content,
            'total_length': len(content)
        }
    
    @staticmethod
    def chunk_document(content: str, chunk_size: int = 20000, overlap: int = 5000) -> List[Dict[str, Any]]:
        """
        方案D：将文档分成多个块，有重叠
        
        Args:
            content: 文档内容
            chunk_size: 每块大小（字符数）
            overlap: 重叠大小（字符数）
        
        Returns:
            分块列表
        """
        chunks = []
        start = 0
        
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk = content[start:end]
            chunks.append({
                'index': len(chunks),
                'content': chunk,
                'start': start,
                'end': end,
                'total_chunks': 0  # 稍后更新
            })
            # 重叠部分，避免在句子中间断开
            start = end - overlap
            if start >= len(content):
                break
        
        # 更新总块数
        for chunk in chunks:
            chunk['total_chunks'] = len(chunks)
        
        return chunks
    
    @staticmethod
    async def generate_template_smart_segment(
        content: str,
        document_name: str = "文档",
        provider: str = "local",
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        方案B：智能分段 + 分层分析生成模板
        
        Args:
            content: 文档内容
            document_name: 文档名称（用于生成描述）
            provider: LLM提供商
            temperature: 温度
            system_prompt: 自定义System Prompt
            user_prompt_template: 自定义User Prompt模板（需要包含 {document_name}, {structure_info}, {key_sections_text} 占位符）
        
        Returns:
            生成的模板配置
        """
        logger.info(f"开始智能分段分析: provider={provider}, temperature={temperature}")
        
        # 第一步：智能分段
        segments = TemplateGenerationService.smart_segment(content)
        
        # 构建综合Prompt
        structure_info = f"""
文档目录结构：
{segments['toc_content'][:2000] if segments['toc_content'] else '无目录'}

章节标题列表：
{segments['headings_text']}
"""
        
        key_sections_text = "\n\n".join([
            f"## {s['title']}\n{s['content']}"
            for s in segments['key_sections']
        ])
        
        if not key_sections_text:
            # 如果没有关键章节，使用前5000字符
            key_sections_text = content[:5000]
        
        # 使用自定义Prompt或默认Prompt
        if user_prompt_template:
            # 替换占位符（使用 replace 而不是 format，避免 JSON 中的花括号被错误解析）
            prompt = user_prompt_template.replace("{document_name}", document_name)
            prompt = prompt.replace("{structure_info}", structure_info)
            prompt = prompt.replace("{key_sections_text}", key_sections_text)
        else:
            # 默认User Prompt
            prompt = f"""你是一个知识图谱模板生成专家。请分析以下文档内容，生成适合的实体和关系模板配置。

{document_name}

{structure_info}

关键章节内容：
{key_sections_text}

请根据文档内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别文档中的核心实体（如：需求、功能、模块、系统、用户、产品等）
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么（例如："需求实体，代表系统中的各种功能需求"）
     * **fields**：字段定义（字段类型、是否必需、描述）
   - 字段类型支持：str, Optional[str], int, Optional[int], bool, Optional[bool] 等
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型（如：HAS_FEATURE, BELONGS_TO, USED_BY等）
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么（例如："包含关系，表示一个实体包含另一个实体"）
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
      "description": "实体类型的描述，说明这个实体类型代表什么（例如：\"角色实体，代表系统中的各种角色和岗位\"）",
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
      "description": "关系类型的描述，说明这个关系类型代表什么（例如：\"审批关系，表示一个实体对另一个实体的审批行为\"）",
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

        # 准备System Prompt
        final_system_prompt = system_prompt if system_prompt else "你是一个专业的知识图谱模板生成专家，擅长从文档中提取实体和关系结构，生成规范的模板配置。"
        
        # 调用LLM
        llm_client = get_llm_client()
        logger.info(f"调用LLM生成模板（智能分段模式）")
        
        response = await llm_client.chat(
            provider,
            [
                {
                    "role": "system",
                    "content": final_system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            use_thinking=False
        )
        
        # 解析JSON响应
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                template_config = json.loads(json_match.group())
            else:
                template_config = json.loads(response)
            
            # 后处理：移除保留字段
            template_config = TemplateGenerationService._remove_reserved_fields(template_config)
            
            logger.info(f"模板生成成功（智能分段模式）：{len(template_config.get('entity_types', {}))} 个实体类型，{len(template_config.get('edge_types', {}))} 个关系类型")
            return template_config
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM响应失败: {e}\n响应内容: {response[:500]}")
            raise Exception(f"LLM返回的JSON格式错误: {str(e)}")
    
    @staticmethod
    async def generate_template_from_summary(
        episode_body: str,
        document_name: str = "文档",
        provider: str = "local",
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        摘要解析模式：使用 Episode Body 内容生成模板
        
        Args:
            episode_body: Episode Body 内容（包含文档基本信息、功能概述、业务信息、系统信息、流程信息）
            document_name: 文档名称（用于生成描述）
            provider: LLM提供商
            temperature: 温度
            system_prompt: 自定义System Prompt
            user_prompt_template: 自定义User Prompt模板（需要包含 {document_name}, {summary_content} 占位符）
        
        Returns:
            生成的模板配置
        """
        logger.info(f"开始摘要解析模式: provider={provider}, temperature={temperature}")
        
        # 截断处理：如果内容过长（> 20000字符），进行截断
        MAX_LENGTH = 20000
        if len(episode_body) > MAX_LENGTH:
            logger.warning(f"Episode Body 内容过长 ({len(episode_body)} 字符)，截断至 {MAX_LENGTH} 字符")
            episode_body = episode_body[:MAX_LENGTH]
            # 尝试在句子或段落边界截断
            if '\n\n' in episode_body:
                episode_body = episode_body.rsplit('\n\n', 1)[0]
            elif '\n' in episode_body:
                episode_body = episode_body.rsplit('\n', 1)[0]
        
        # 使用自定义Prompt或默认Prompt
        if user_prompt_template:
            # 替换占位符（使用 replace 而不是 format，避免 JSON 中的花括号被错误解析）
            prompt = user_prompt_template.replace("{document_name}", document_name)
            prompt = prompt.replace("{summary_content}", episode_body)
        else:
            # 默认User Prompt（针对摘要内容优化）
            prompt = f"""你是一个知识图谱模板生成专家。请分析以下文档摘要内容，生成适合的实体和关系模板配置。

**注意：以下内容是文档的摘要信息（Episode Body），包含了文档的基本信息和关键提取内容，而非完整文档。**

文档名称: {document_name}

文档摘要内容:
{episode_body}

请根据文档摘要内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别文档中的核心实体（如：需求、功能、模块、系统、用户、产品等）
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么（例如："需求实体，代表系统中的各种功能需求"）
     * **fields**：字段定义（字段类型、是否必需、描述）
   - 字段类型支持：str, Optional[str], int, Optional[int], bool, Optional[bool] 等
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型（如：HAS_FEATURE, BELONGS_TO, USED_BY等）
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么（例如："包含关系，表示一个实体包含另一个实体"）
     * **fields**：字段定义
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, source_node_uuid, target_node_uuid, name, fact, attributes

3. **关系映射（edge_type_map）**：
   - 定义哪些实体之间可以使用哪些关系
   - 格式：{{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}

要求：
- 返回标准JSON格式
- 实体类型和关系类型要符合文档摘要的实际内容
- 字段定义要完整（type, required, description）
- 关系映射要准确反映文档中的实体关系
- ⚠️ **严禁使用保留字段名**

返回JSON格式：
{{
  "entity_types": {{
    "EntityName": {{
      "description": "实体类型的描述，说明这个实体类型代表什么（例如：\"角色实体，代表系统中的各种角色和岗位\"）",
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
      "description": "关系类型的描述，说明这个关系类型代表什么（例如：\"审批关系，表示一个实体对另一个实体的审批行为\"）",
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

        # 准备System Prompt
        final_system_prompt = system_prompt if system_prompt else "你是一个专业的知识图谱模板生成专家，擅长从文档摘要中提取实体和关系结构，生成规范的模板配置。"

        # 调用LLM
        llm_client = get_llm_client()
        logger.info(f"调用LLM生成模板（摘要解析模式），输入内容长度: {len(episode_body)} 字符")
        
        response = await llm_client.chat(
            provider,
            [
                {
                    "role": "system",
                    "content": final_system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            use_thinking=False
        )
        
        # 解析JSON响应
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                template_config = json.loads(json_match.group())
            else:
                template_config = json.loads(response)
            
            # 后处理：移除保留字段
            template_config = TemplateGenerationService._remove_reserved_fields(template_config)
            
            logger.info(f"模板生成成功（摘要解析模式）：{len(template_config.get('entity_types', {}))} 个实体类型，{len(template_config.get('edge_types', {}))} 个关系类型")
            return template_config
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM响应失败: {e}\n响应内容: {response[:500]}")
            raise Exception(f"LLM返回的JSON格式错误: {str(e)}")
    
    @staticmethod
    async def generate_template_full_chunk(
        content: str,
        document_name: str = "文档",
        provider: str = "local",
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        方案D：全文 + 分块分析生成模板
        
        Args:
            content: 文档内容
            document_name: 文档名称（用于生成描述）
            provider: LLM提供商
            temperature: 温度
            system_prompt: 自定义System Prompt
            user_prompt_template: 自定义User Prompt模板（需要包含 {document_name}, {summary_content} 占位符）
        
        Returns:
            生成的模板配置
        """
        logger.info("开始全文分块分析")
        
        # 判断是否需要分块
        CHUNK_THRESHOLD = 50000  # 50,000字符阈值
        
        if len(content) <= CHUNK_THRESHOLD:
            # 小文档，直接全文分析
            logger.info(f"文档长度 {len(content)} 字符，直接全文分析")
            return await TemplateGenerationService._analyze_full_content(
                content, 
                document_name,
                provider=provider,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template
            )
        else:
            # 大文档，分块分析
            logger.info(f"文档长度 {len(content)} 字符，分块分析")
            chunks = TemplateGenerationService.chunk_document(content)
            logger.info(f"文档分为 {len(chunks)} 个块")
            
            # 对每个块进行分析
            all_entity_types = {}
            all_edge_types = {}
            all_edge_maps = {}
            
            llm_client = get_llm_client()
            
            for i, chunk in enumerate(chunks):
                logger.info(f"分析第 {i+1}/{len(chunks)} 个块")
                chunk_prompt = f"""分析以下文档片段，提取实体和关系类型：

文档片段（第{chunk['index']+1}部分，共{chunk['total_chunks']}部分）：
{chunk['content']}

请提取：
1. 实体类型及其字段定义
   - ⚠️ **禁止使用保留字段**：uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，如：entity_name, title, description, status 等
   - 格式：{{"EntityName": {{"description": "实体类型描述", "fields": {{"field_name": {{"type": "str", "required": true, "description": "字段描述"}}}}}}}}
2. 关系类型及其字段定义
   - ⚠️ **禁止使用保留字段**：uuid, source_node_uuid, target_node_uuid, name, fact, attributes
   - 格式：{{"EdgeName": {{"description": "关系类型描述", "fields": {{"field_name": {{"type": "str", "required": false, "description": "字段描述"}}}}}}}}
3. 实体之间的关系映射
   - ⚠️ **格式要求**：必须是字典，key格式为 "SourceEntity -> TargetEntity"（注意中间有空格和箭头）
   - 示例：{{"Product -> Order": ["HAS_ORDER"], "User -> Product": ["OWNS"]}}
   - ❌ 错误格式：{{"Product": ["HAS_ORDER"]}} 或单个实体名称作为key

返回JSON格式：
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
                
                try:
                    response = await llm_client.chat(
                        "local",
                        [
                            {
                                "role": "system",
                                "content": "你是一个专业的知识图谱模板生成专家，擅长从文档片段中提取实体和关系结构。"
                            },
                            {
                                "role": "user",
                                "content": chunk_prompt
                            }
                        ],
                        temperature=0.3,
                        use_thinking=False
                    )
                    
                    # 解析JSON
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        chunk_result = json.loads(json_match.group())
                    else:
                        chunk_result = json.loads(response)
                    
                    # 合并结果（去重，后出现的覆盖先出现的）
                    all_entity_types.update(chunk_result.get('entity_types', {}))
                    all_edge_types.update(chunk_result.get('edge_types', {}))
                    all_edge_maps.update(chunk_result.get('edge_type_map', {}))
                    
                except Exception as e:
                    logger.warning(f"分析第 {i+1} 个块失败: {e}，跳过")
                    continue
            
            # 最终综合生成模板
            logger.info("综合所有分析结果，生成最终模板")
            final_prompt = f"""基于以下所有分析结果，生成统一的模板配置：

实体类型汇总：
{json.dumps(all_entity_types, ensure_ascii=False, indent=2)[:5000]}

关系类型汇总：
{json.dumps(all_edge_types, ensure_ascii=False, indent=2)[:5000]}

关系映射汇总：
{json.dumps(all_edge_maps, ensure_ascii=False, indent=2)[:5000]}

请合并、去重、统一，生成最终的模板配置。确保：
1. 实体类型定义完整（包含字段类型、是否必需、描述）
   - 格式：{{"EntityName": {{"fields": {{"field_name": {{"type": "str", "required": true, "description": "..."}}}}}}}}
2. 关系类型定义完整
   - 格式：{{"EdgeName": {{"fields": {{"field_name": {{"type": "str", "required": false, "description": "..."}}}}}}}}
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
  "entity_types": {{"EntityName": {{"fields": {{...}}}}}},
  "edge_types": {{"EdgeName": {{"fields": {{...}}}}}},
  "edge_type_map": {{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}
}}

只返回JSON，不要其他内容。"""
            
            final_response = await llm_client.chat(
                "local",
                [
                    {
                        "role": "system",
                        "content": "你是一个专业的知识图谱模板生成专家，擅长合并和统一多个分析结果。"
                    },
                    {
                        "role": "user",
                        "content": final_prompt
                    }
                ],
                temperature=0.3,
                use_thinking=False
            )
            
            # 解析最终结果
            json_match = re.search(r'\{.*\}', final_response, re.DOTALL)
            if json_match:
                final_template = json.loads(json_match.group())
            else:
                final_template = json.loads(final_response)
            
            # 后处理：移除保留字段
            final_template = TemplateGenerationService._remove_reserved_fields(final_template)
            
            logger.info(f"模板生成成功（全文分块模式）：{len(final_template.get('entity_types', {}))} 个实体类型，{len(final_template.get('edge_types', {}))} 个关系类型")
            return final_template
    
    @staticmethod
    async def _analyze_full_content(
        content: str, 
        document_name: str,
        provider: str = "local",
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        user_prompt_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析完整文档内容（不分块）
        
        Args:
            content: 文档内容
            document_name: 文档名称
            provider: LLM提供商
            temperature: 温度
            system_prompt: 自定义System Prompt
            user_prompt_template: 自定义User Prompt模板（需要包含 {document_name}, {summary_content} 占位符）
        
        Returns:
            生成的模板配置
        """
        # 使用自定义Prompt或默认Prompt
        if user_prompt_template:
            # 替换占位符（使用 replace 而不是 format，避免 JSON 中的花括号被错误解析）
            prompt = user_prompt_template.replace("{document_name}", document_name)
            prompt = prompt.replace("{summary_content}", content)
        else:
            # 默认User Prompt
            prompt = f"""你是一个知识图谱模板生成专家。请分析以下文档内容，生成适合的实体和关系模板配置。

文档名称: {document_name}

文档内容:
{content}

请根据文档内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别文档中的核心实体
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么（例如："需求实体，代表系统中的各种功能需求"）
     * **fields**：字段定义（字段类型、是否必需、描述）
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么（例如："包含关系，表示一个实体包含另一个实体"）
     * **fields**：字段定义
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, source_node_uuid, target_node_uuid, name, fact, attributes

3. **关系映射（edge_type_map）**：
   - 定义哪些实体之间可以使用哪些关系
   - ⚠️ **格式要求**：必须是字典，key格式为 "SourceEntity -> TargetEntity"（注意中间有空格和箭头）
   - 示例：{{"Product -> Order": ["HAS_ORDER"], "User -> Product": ["OWNS", "USES"]}}
   - ❌ 错误格式：{{"Product": ["HAS_ORDER"]}} 或 {{"产品": ["订单"]}}

返回标准JSON格式：
{{
  "entity_types": {{
    "EntityName": {{
      "description": "实体类型的描述，说明这个实体类型代表什么",
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

只返回JSON，不要其他内容。
⚠️ **格式要求**：
- entity_types 必须是字典：{{"EntityName": {{"description": "...", "fields": {{...}}}}}}
- edge_types 必须是字典：{{"EdgeName": {{"description": "...", "fields": {{...}}}}}}
- edge_type_map 必须是字典：{{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}}
⚠️ **严禁使用保留字段名**"""
        
        # 准备System Prompt
        final_system_prompt = system_prompt if system_prompt else "你是一个专业的知识图谱模板生成专家，擅长从文档中提取实体和关系结构，生成规范的模板配置。"
        
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
                    "content": prompt
                }
            ],
            temperature=temperature,
            use_thinking=False
        )
        
        # 解析JSON响应
        try:
            # 尝试提取JSON部分（可能包含markdown代码块或其他文本）
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                json_str = response.strip()
            
            # 尝试解析JSON
            template_config = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析LLM响应JSON失败: {e}\n响应内容前500字符: {response[:500]}")
            # 尝试更宽松的JSON提取
            # 查找 ```json 代码块
            json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_block_match:
                try:
                    template_config = json.loads(json_block_match.group(1))
                    logger.info("从markdown代码块中成功提取JSON")
                except json.JSONDecodeError as e2:
                    raise Exception(f"LLM返回的JSON格式错误: {str(e)}\n响应内容前500字符: {response[:500]}")
        else:
                raise Exception(f"LLM返回的JSON格式错误: {str(e)}\n响应内容前500字符: {response[:500]}")
        
        # 后处理：移除保留字段
        template_config = TemplateGenerationService._remove_reserved_fields(template_config)
        
        return template_config
