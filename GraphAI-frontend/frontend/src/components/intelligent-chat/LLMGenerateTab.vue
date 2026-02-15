<template>
  <div>
    <!-- 检索策略版本标识 -->
    <a-alert
      message="🚀 检索策略：v4.0"
      description="单路DocumentChunk检索 + 分数阈值过滤 + Graphiti/Cognee知识图谱扩展"
      type="info"
      show-icon
      style="margin-bottom: 24px"
    />

    <!-- 配置区域 -->
    <a-form :label-col="{ span: 4 }" :wrapper-col="{ span: 20 }" style="margin-bottom: 24px">
      <a-form-item label="用户需求">
        <a-textarea
          v-model:value="userQuery"
          :rows="4"
          placeholder="描述你的需求或问题..."
          :disabled="executing"
        />
      </a-form-item>

      <a-form-item label="LLM配置">
        <a-space>
          <a-select v-model:value="provider" :disabled="executing" style="width: 150px">
            <a-select-option value="qianwen">千问</a-select-option>
            <a-select-option value="deepseek">DeepSeek</a-select-option>
            <a-select-option value="kimi">Kimi</a-select-option>
          </a-select>
          <a-slider
            v-model:value="temperature"
            :min="0"
            :max="2"
            :step="0.1"
            style="width: 200px; margin-left: 24px"
            :tooltip-formatter="(val) => `温度: ${val}`"
            :disabled="executing"
          />
          <span style="color: #999; font-size: 12px">温度: {{ temperature }}</span>
        </a-space>
      </a-form-item>

      <a-form-item label="检索配置">
        <a-space direction="vertical" style="width: 100%">
          <a-space>
            <a-radio-group v-model:value="retrievalScope">
              <a-radio value="all">全部文档</a-radio>
              <a-radio value="specified">指定文档</a-radio>
            </a-radio-group>
            <a-input-number
              v-model:value="topK"
              :min="10"
              :max="100"
              :step="10"
              style="width: 100px; margin-left: 24px"
              :disabled="executing"
            />
            <span style="color: #999; font-size: 12px">Top K</span>
          </a-space>
          
          <a-space>
            <span style="color: #666; font-size: 12px; margin-right: 8px">分数阈值:</span>
            <a-slider
              v-model:value="minScore"
              :min="0"
              :max="100"
              :step="5"
              style="width: 200px"
              :tooltip-formatter="(val) => `${val}分`"
              :disabled="executing"
            />
            <span style="color: #999; font-size: 12px">{{ minScore }}分</span>
          </a-space>
          
          <a-space>
            <span style="color: #666; font-size: 12px; margin-right: 8px">传给LLM的结果数:</span>
            <a-input-number
              v-model:value="maxResultsForLLM"
              :min="10"
              :max="50"
              :step="5"
              style="width: 100px"
              :disabled="executing"
            />
            <span style="color: #999; font-size: 12px">个</span>
          </a-space>
          
          <!-- 文档选择器 -->
          <a-select
            v-if="retrievalScope === 'specified'"
            v-model:value="selectedDocumentGroupIds"
            mode="multiple"
            placeholder="请选择要检索的文档（可多选）"
            :options="documentOptions"
            :disabled="executing"
            :loading="loadingDocuments"
            style="width: 100%"
            :filter-option="filterDocumentOption"
            show-search
          >
            <template #notFoundContent>
              <a-empty description="暂无已处理的文档" />
            </template>
          </a-select>
        </a-space>
      </a-form-item>

      <a-form-item label="精筛配置">
        <a-space>
          <a-checkbox v-model:checked="enableRefine" :disabled="executing">
            启用精细处理（阶段2）
          </a-checkbox>
          <span style="color: #999; font-size: 12px">
            使用Graphiti和Cognee进行知识图谱扩展
          </span>
        </a-space>
      </a-form-item>
    </a-form>

    <!-- 执行区域 -->
    <a-form :label-col="{ span: 4 }" :wrapper-col="{ span: 20 }" style="margin-bottom: 24px">
      <a-form-item>
        <a-space>
          <a-button 
            type="primary" 
            @click="handleExecute" 
            :loading="executing"
            :disabled="!userQuery.trim() || executing || (retrievalScope === 'specified' && (!selectedDocumentGroupIds || selectedDocumentGroupIds.length === 0))"
          >
            执行LLM生成
          </a-button>
          <a-button @click="handleClear" :disabled="executing">
            清空结果
          </a-button>
        </a-space>
      </a-form-item>
    </a-form>

    <!-- 执行状态 -->
    <div v-if="executing" style="text-align: center; padding: 40px">
      <a-spin size="large">
        <template #indicator>
          <LoadingOutlined style="font-size: 24px" spin />
        </template>
      </a-spin>
      <div style="margin-top: 12px; color: #999">
        {{ executionStatus }}
      </div>
    </div>

    <!-- LLM生成结果展示（在前面） -->
    <div v-if="executionResult && !executing" style="margin-bottom: 24px">
      <!-- LLM生成统计 -->
      <a-card title="LLM生成统计" size="small" style="margin-bottom: 16px">
        <a-descriptions :column="3" bordered size="small">
          <a-descriptions-item label="主回答耗时">
            {{ formatTime(executionResult.llm_statistics?.main_answer_time || 0) }}
          </a-descriptions-item>
          <a-descriptions-item label="检索耗时">
            {{ formatTime(retrievalResult?.summary?.total_time || 0) }}
          </a-descriptions-item>
          <a-descriptions-item label="总耗时">
            {{ formatTime(getTotalTime()) }}
          </a-descriptions-item>
          <a-descriptions-item label="温度参数">
            {{ executionResult.llm_statistics?.temperature || temperature }}
          </a-descriptions-item>
          <a-descriptions-item label="输入结果数" :span="2">
            总计: {{ executionResult.retrieval_statistics?.total_results || 0 }} | 
            DocumentChunk: {{ executionResult.retrieval_statistics?.chunk_count || 0 }} | 
            Entity: {{ executionResult.retrieval_statistics?.entity_count || 0 }} | 
            Graphiti: {{ executionResult.retrieval_statistics?.graphiti_count || 0 }} | 
            Cognee: {{ executionResult.retrieval_statistics?.cognee_count || 0 }}
          </a-descriptions-item>
        </a-descriptions>
      </a-card>

      <!-- 生成的回答 -->
      <a-card title="生成的回答" style="margin-bottom: 24px">
        <div 
          v-html="formatMarkdown(streamingContent || executionResult.generated_document || '')"
          style="font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.8; padding: 16px; background: #fafafa; border-radius: 4px; max-height: 600px; overflow-y: auto;"
        ></div>
        <div v-if="isStreaming" style="text-align: center; padding: 8px; color: #999; font-size: 12px;">
          <a-spin size="small" /> 正在生成中...
        </div>
      </a-card>

      <!-- 对比分析 -->
      <a-card v-if="executionResult.comparison_analysis" title="对比分析" style="margin-bottom: 24px">
        <div 
          v-html="formatMarkdown(executionResult.comparison_analysis)"
          style="font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.8; padding: 16px; background: #fafafa; border-radius: 4px; max-height: 400px; overflow-y: auto;"
        ></div>
      </a-card>

      <!-- 复用建议 -->
      <a-card v-if="executionResult.reuse_suggestions && executionResult.reuse_suggestions.length > 0" title="复用建议" style="margin-bottom: 24px">
        <a-list
          :data-source="executionResult.reuse_suggestions"
          :pagination="{ pageSize: 5 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <a-space>
                    <a-tag color="green">{{ item.type || '建议' }}</a-tag>
                    <span>{{ item.title || item.content }}</span>
                  </a-space>
                </template>
                <template #description>
                  <div v-if="item.content" style="margin-top: 8px; color: #666">
                    {{ item.content }}
                  </div>
                  <div v-if="item.source" style="margin-top: 4px; font-size: 12px; color: #999">
                    来源: {{ item.source }}
                  </div>
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </a-card>

      <!-- 风险提示 -->
      <a-card v-if="executionResult.risk_warnings && executionResult.risk_warnings.length > 0" title="风险提示">
        <a-alert
          v-for="(warning, index) in executionResult.risk_warnings"
          :key="index"
          :message="warning.title || '风险提示'"
          :description="warning.content || warning"
          type="warning"
          show-icon
          style="margin-bottom: 12px"
        />
      </a-card>
    </div>

    <!-- 智能检索结果展示（在后面，复用SmartRetrievalResults组件） -->
    <SmartRetrievalResults 
      v-if="retrievalResult && !executing && retrievalResult.success"
      :result="retrievalResult"
    />

    <!-- 空状态 -->
    <a-empty
      v-if="!executing && !executionResult && !retrievalResult"
      description="请输入用户需求，然后点击执行按钮（将自动执行智能检索和LLM生成）"
      style="margin: 60px 0"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { 
  LoadingOutlined
} from '@ant-design/icons-vue'
import { step7LLMGenerate, step7LLMGenerateStream, smartRetrieval } from '../../api/intelligentChat'
import { getDocumentUploadList } from '../../api/documentUpload'
import { SOURCE_CONFIG, TYPE_CONFIG } from './recall/constants'
import SmartRetrievalResults from './SmartRetrievalResults.vue'

const userQuery = ref('')
const provider = ref('qianwen')
const temperature = ref(0.2)
const executing = ref(false)
const executionStatus = ref('')
const executionResult = ref(null)
const retrievalResult = ref(null)
const retrievalScope = ref('all')
const topK = ref(50)
const minScore = ref(70)
const maxResultsForLLM = ref(20)
const enableRefine = ref(true)

// 流式输出相关
const streamingContent = ref('')
const isStreaming = ref(false)
const streamingAbortController = ref(null)

// 文档选择相关
const selectedDocumentGroupIds = ref([])
const documentOptions = ref([])
const loadingDocuments = ref(false)

// 加载文档列表
const loadDocuments = async () => {
  loadingDocuments.value = true
    try {
    const response = await getDocumentUploadList(1, 100)  // 获取前100个文档
    const documents = response && response.documents ? response.documents : []
    
    // 筛选已处理的文档（有document_id的）
    const processedDocuments = documents.filter(doc => doc.document_id)
    
    documentOptions.value = processedDocuments.map(doc => ({
      value: doc.document_id,  // 使用document_id作为group_id
      label: `${doc.file_name} (${doc.document_id})`,
      disabled: !doc.document_id
    }))
    
    console.log('已加载文档列表:', documentOptions.value.length, '个已处理文档')
  } catch (error) {
    console.error('加载文档列表失败:', error)
    message.error('加载文档列表失败')
  } finally {
    loadingDocuments.value = false
  }
}

// 文档选择器过滤
const filterDocumentOption = (input, option) => {
  return option.label.toLowerCase().includes(input.toLowerCase())
  }

// 组件挂载时加载文档
onMounted(() => {
  loadDocuments()
})

// 转换v4.0格式为LLM期望格式
function convertV4ResultsToLLMFormat(retrievalResult, maxResults = 20) {
  const results = []
  
  // 1. 转换阶段1的chunk_results
  if (retrievalResult.stage1?.chunk_results) {
    for (const chunk of retrievalResult.stage1.chunk_results) {
      results.push({
        source: 'DocumentChunk',
        source_channel: 'DocumentChunk',
        name: chunk.section_name || `第${(chunk.chunk_index || 0) + 1}章`,
        content: chunk.content || '',
        score: chunk.score / 100,  // 转换为0-1
        doc_id: chunk.doc_id || chunk.group_id || 'unknown',
        version: chunk.metadata?.version || 'unknown',
        group_id: chunk.group_id,
        chunk_index: chunk.chunk_index
      })
    }
  }
  
  // 2. 转换阶段2的Graphiti entities
  if (retrievalResult.stage2?.graphiti?.entities) {
    for (const entity of retrievalResult.stage2.graphiti.entities) {
      results.push({
        source: 'Graphiti',
        source_channel: 'Entity',
        name: entity.name || '未命名实体',
        content: formatEntityContent(entity),
        score: entity.score / 100,
        doc_id: entity.properties?.doc_id || entity.properties?.group_id || 'unknown',
        version: entity.properties?.version || 'unknown',
        group_id: entity.properties?.group_id,
        uuid: entity.uuid,
        type: entity.type
      })
    }
  }
  
  // 3. 转换阶段2的Cognee entities
  if (retrievalResult.stage2?.cognee?.entities) {
    for (const entity of retrievalResult.stage2.cognee.entities) {
      results.push({
        source: 'Cognee',
        source_channel: 'Entity',
        name: entity.name || '未命名实体',
        content: formatEntityContent(entity),
        score: entity.score / 100,
        doc_id: entity.properties?.doc_id || entity.properties?.group_id || 'unknown',
        version: entity.properties?.version || 'unknown',
        group_id: entity.properties?.group_id,
        id: entity.id,
        type: entity.type
      })
    }
  }
  
  // 4. 按score降序排序，取Top N
  results.sort((a, b) => b.score - a.score)
  return results.slice(0, maxResults)
}

// 格式化Entity内容为结构化文本
function formatEntityContent(entity) {
  const parts = []
  
  // 1. Entity名称
  if (entity.name) {
    parts.push(`实体名称: ${entity.name}`)
  }
  
  // 2. Entity类型
  if (entity.type) {
    parts.push(`类型: ${entity.type}`)
  }
  
  // 3. 关键属性（从properties中提取）
  if (entity.properties) {
    const props = entity.properties
    // 提取常见的关键字段
    if (props.description) parts.push(`描述: ${props.description}`)
    if (props.definition) parts.push(`定义: ${props.definition}`)
    if (props.specification) parts.push(`规格: ${props.specification}`)
    if (props.status) parts.push(`状态: ${props.status}`)
    if (props.priority) parts.push(`优先级: ${props.priority}`)
    // 其他重要字段
    if (props.content && typeof props.content === 'string') {
      parts.push(`内容: ${props.content.substring(0, 200)}${props.content.length > 200 ? '...' : ''}`)
    }
  }
  
  // 4. 关联信息（如果有related_chunks）
  if (entity.related_chunks && entity.related_chunks.length > 0) {
    const sectionNames = entity.related_chunks
      .map(c => c.section_name || `第${(c.chunk_index || 0) + 1}章`)
      .filter(Boolean)
    if (sectionNames.length > 0) {
      parts.push(`关联章节: ${sectionNames.join(', ')}`)
    }
  }
  
  // 5. 关系信息（如果有relationships）
  if (entity.relationships && entity.relationships.length > 0) {
    const relNames = entity.relationships
      .slice(0, 3)  // 只取前3个关系
      .map(rel => `${rel.type}: ${rel.target}`)
      .filter(Boolean)
    if (relNames.length > 0) {
      parts.push(`关系: ${relNames.join('; ')}`)
    }
  }
  
  return parts.length > 0 ? parts.join('\n') : (entity.name || '实体信息')
}

const handleExecute = async () => {
  if (!userQuery.value.trim()) {
    message.warning('请输入用户需求')
    return
  }

  if (retrievalScope.value === 'specified' && (!selectedDocumentGroupIds.value || selectedDocumentGroupIds.value.length === 0)) {
    message.warning('请至少选择一个文档')
    return
  }

  executing.value = true
  executionStatus.value = '正在执行智能检索...'
  executionResult.value = null
  retrievalResult.value = null

  try {
    // 步骤1: 执行智能检索（v4.0）
    executionStatus.value = '正在执行智能检索（v4.0）...'
    const retrievalParams = {
      query: userQuery.value,
      top_k: topK.value,
      min_score: minScore.value,
      group_ids: retrievalScope.value === 'specified' ? selectedDocumentGroupIds.value : null,
      enable_refine: enableRefine.value
    }
    
    console.log('智能检索参数:', retrievalParams)
    
    const retrieval = await smartRetrieval(retrievalParams)
    retrievalResult.value = retrieval
    
    if (!retrieval.success) {
      throw new Error(retrieval.error || '智能检索失败')
    }
    
    // 转换v4.0格式为LLM期望格式
    const llmFormatResults = convertV4ResultsToLLMFormat(retrieval, maxResultsForLLM.value)
    
    if (llmFormatResults.length === 0) {
      message.warning('智能检索未找到相关结果，将基于通用知识生成回答')
    } else {
      message.success(`智能检索完成，找到 ${llmFormatResults.length} 个相关结果（将传给LLM）`)
    }

    // 步骤2: 执行LLM生成（使用流式生成）
    executionStatus.value = '正在执行LLM生成...'
    
    // 流式生成（支持 qianwen、deepseek、kimi）
    if (['qianwen', 'deepseek', 'kimi'].includes(provider.value)) {
      // 使用流式生成（打字机效果）
      streamingContent.value = ''
      isStreaming.value = true
      executionResult.value = {
        generated_document: '',
        comparison_analysis: null,
        reuse_suggestions: [],
        risk_warnings: [],
        retrieval_statistics: {
          total_results: llmFormatResults.length,
          chunk_count: llmFormatResults.filter(r => r.source_channel === 'DocumentChunk').length,
          entity_count: llmFormatResults.filter(r => r.source_channel === 'Entity').length,
          graphiti_count: llmFormatResults.filter(r => r.source === 'Graphiti').length,
          cognee_count: llmFormatResults.filter(r => r.source === 'Cognee').length
        },
        llm_statistics: {
          temperature: temperature.value
        }
      }
      
      // 创建AbortController用于取消请求
      streamingAbortController.value = new AbortController()
      
      // 打字机效果：逐字符显示
      let pendingText = '' // 待显示的完整文本
      let displayedLength = 0 // 已显示的字符数
      let typewriterTimer = null
      
      const typewriterEffect = () => {
        if (displayedLength < pendingText.length) {
          // 每次显示1-3个字符（根据内容长度动态调整）
          const chunkSize = Math.min(3, pendingText.length - displayedLength)
          streamingContent.value = pendingText.substring(0, displayedLength + chunkSize)
          displayedLength += chunkSize
          
          // 继续打字机效果
          typewriterTimer = setTimeout(typewriterEffect, 15) // 每15ms显示一次
        } else if (isStreaming.value) {
          // 继续等待新内容
          typewriterTimer = setTimeout(typewriterEffect, 50)
        }
      }
      
      // 启动打字机效果
      typewriterEffect()
      
      // 调试：打印请求参数
      const requestParams = {
        query: userQuery.value,
        retrieval_results: llmFormatResults,
        provider: provider.value,
        temperature: temperature.value
      }
      console.log('流式生成请求参数:', requestParams)
      console.log('retrieval_results数量:', llmFormatResults.length)
      console.log('retrieval_results示例:', llmFormatResults[0])
      
      step7LLMGenerateStream(
        requestParams,
        (chunk) => {
          // 检查是否是统计信息
          if (typeof chunk === 'object' && chunk.type === 'statistics') {
            // 更新统计信息
            if (executionResult.value) {
              executionResult.value.llm_statistics = {
                ...executionResult.value.llm_statistics,
                ...chunk.data
              }
              // 计算总耗时 = 检索耗时 + 主要回答耗时
              const retrievalTime = retrievalResult.value?.summary?.total_time || 0
              const mainAnswerTime = chunk.data.main_answer_time || 0
              executionResult.value.llm_statistics.total_time = retrievalTime + mainAnswerTime
            }
            return
          }
          // 接收文本chunk，追加到待显示文本
          if (typeof chunk === 'string') {
            pendingText += chunk
          }
        },
        () => {
          // 流式生成完成
          isStreaming.value = false
          executionStatus.value = ''
          
          // 清除打字机定时器
          if (typewriterTimer) {
            clearTimeout(typewriterTimer)
            typewriterTimer = null
          }
          
          // 确保所有内容都已显示
          streamingContent.value = pendingText
          displayedLength = pendingText.length
          
          // 更新executionResult
          if (executionResult.value) {
            executionResult.value.generated_document = streamingContent.value
            // 确保总耗时已计算（如果统计信息已更新）
            if (executionResult.value.llm_statistics && !executionResult.value.llm_statistics.total_time) {
              const retrievalTime = retrievalResult.value?.summary?.total_time || 0
              const mainAnswerTime = executionResult.value.llm_statistics.main_answer_time || 0
              executionResult.value.llm_statistics.total_time = retrievalTime + mainAnswerTime
            }
          }
          
          message.success('LLM生成完成')
        },
        (error) => {
          // 流式生成出错
          isStreaming.value = false
          executionStatus.value = ''
          
          // 清除打字机定时器
          if (typewriterTimer) {
            clearTimeout(typewriterTimer)
            typewriterTimer = null
          }
          
          console.error('流式生成失败:', error)
          message.error(`LLM生成失败: ${error.message || '未知错误'}`)
          executionResult.value = null
        }
      )
    } else {
      // 使用非流式生成（千问等）
    const result = await step7LLMGenerate({
      query: userQuery.value,
        retrieval_results: llmFormatResults,
      provider: provider.value,
      temperature: temperature.value
    })

    executionResult.value = result
      
      // 非流式模式下，后端已返回total_time（包含所有LLM调用），但我们需要重新计算
      // 总耗时 = 检索耗时 + 主要回答耗时（非流式模式中total_time可能包含其他内容，我们只取main_answer_time）
      if (executionResult.value.llm_statistics) {
        const retrievalTime = retrievalResult.value?.summary?.total_time || 0
        const mainAnswerTime = executionResult.value.llm_statistics.main_answer_time || 0
        executionResult.value.llm_statistics.total_time = retrievalTime + mainAnswerTime
      }
      
    message.success('LLM生成完成')
    }
  } catch (error) {
    console.error('执行失败:', error)
    message.error(`执行失败: ${error.response?.data?.detail || error.message || '未知错误'}`)
    executionResult.value = null
    retrievalResult.value = null
  } finally {
    executing.value = false
    executionStatus.value = ''
  }
}

const handleClear = () => {
  // 取消流式请求
  if (streamingAbortController.value) {
    streamingAbortController.value.abort()
    streamingAbortController.value = null
  }
  
  executionResult.value = null
  retrievalResult.value = null
  streamingContent.value = ''
  isStreaming.value = false
  userQuery.value = ''
  selectedDocumentGroupIds.value = []
  message.success('结果已清空')
}

const formatTime = (seconds) => {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`
  }
  return `${seconds.toFixed(2)}s`
}

// 计算总耗时 = 检索耗时 + 主要回答耗时
const getTotalTime = () => {
  const retrievalTime = retrievalResult.value?.summary?.total_time || 0
  const mainAnswerTime = executionResult.value?.llm_statistics?.main_answer_time || 0
  return retrievalTime + mainAnswerTime
}

const getSourceColor = (source) => {
  const colors = {
    'Graphiti': 'purple',
    'Cognee_Neo4j': 'orange',
    'Milvus': 'blue'
  }
  return colors[source] || 'default'
}

const getTypeColor = (type) => {
  const colors = {
    'DocumentChunk': 'green',
    'Entity': 'red',
    'Episode': 'purple',
    'Edge': 'cyan'
  }
  return colors[type] || 'default'
}

// 格式化Markdown为HTML（简化版）
const formatMarkdown = (text) => {
  if (!text) return ''
  
  // 转义HTML特殊字符
  const escapeHtml = (str) => {
    const div = document.createElement('div')
    div.textContent = str
    return div.innerHTML
  }
  
  let processedText = text
  
  // 处理标题
  processedText = processedText.replace(/^#### (.*$)/gim, '<h4 style="margin: 16px 0 8px 0; font-size: 16px; font-weight: 600;">$1</h4>')
  processedText = processedText.replace(/^### (.*$)/gim, '<h3 style="margin: 20px 0 12px 0; font-size: 18px; font-weight: 600;">$1</h3>')
  processedText = processedText.replace(/^## (.*$)/gim, '<h2 style="margin: 24px 0 16px 0; font-size: 20px; font-weight: 600;">$1</h2>')
  processedText = processedText.replace(/^# (.*$)/gim, '<h1 style="margin: 28px 0 20px 0; font-size: 24px; font-weight: 600;">$1</h1>')
  
  // 处理粗体
  processedText = processedText.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>')
  
  // 处理列表
  processedText = processedText.replace(/^[\-\*\+] (.+)$/gim, '<li style="margin: 4px 0;">$1</li>')
  processedText = processedText.replace(/(<li[^>]*>.*?<\/li>(?:\s*<li[^>]*>.*?<\/li>)*)/gs, '<ul style="margin: 8px 0; padding-left: 24px;">$1</ul>')
  
  // 处理换行
  processedText = processedText.replace(/\n\n/g, '<br><br>')
  processedText = processedText.replace(/\n/g, '<br>')
  
  return processedText
}
</script>

<style scoped>
</style>
