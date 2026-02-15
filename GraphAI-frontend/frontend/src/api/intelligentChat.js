import api from './index'

// ==================== 文档入库流程 API ====================

/**
 * 预览LLM生成的实体关系模板（不执行Graphiti）
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.provider - LLM提供商
 * @param {number} params.temperature - 温度参数
 */
export const previewTemplate = (params) => {
  return api.post('/intelligent-chat/preview-template', params)
}

/**
 * 预览 Episode body 内容（不执行处理）
 * @param {number} upload_id - 文档上传ID
 */
export const previewEpisodeBody = (upload_id) => {
  return api.get(`/intelligent-chat/preview-episode-body/${upload_id}`)
}

/**
 * 步骤1: Graphiti文档级处理
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.provider - LLM提供商
 * @param {number} params.temperature - 温度参数
 * @param {string} params.episode_body - 用户自定义的 Episode body（可选）
 */
export const step1GraphitiEpisode = (params) => {
  return api.post('/intelligent-chat/step1/graphiti-episode', params)
}

/**
 * 获取 Graphiti 执行结果摘要
 * @param {number} upload_id - 文档上传ID
 */
export const getGraphitiResult = (upload_id) => {
  return api.get(`/intelligent-chat/graphiti-result/${upload_id}`)
}

/**
 * 获取Graphiti图谱数据
 * @param {string} group_id - 文档组ID
 */
export const getGraphitiGraph = (group_id) => {
  return api.get(`/word-document/${group_id}/graph`)
}

/**
 * 删除Graphiti图谱数据
 * @param {number} upload_id - 文档上传ID
 */
export const deleteGraphitiGraph = (upload_id) => {
  return api.delete(`/intelligent-chat/graphiti-graph/${upload_id}`)
}

/**
 * 删除Cognee图谱数据
 * @param {number} upload_id - 文档上传ID
 */
export const deleteCogneeGraph = (upload_id) => {
  return api.delete(`/intelligent-chat/cognee-graph/${upload_id}`)
}

/**
 * 预览生成 Cognify 模板 JSON
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.system_prompt - 自定义 System Prompt（可选）
 * @param {string} params.user_prompt_template - 自定义 User Prompt 模板（可选）
 * @param {string} params.template_type - 模版类型（默认: "default"）
 */
export const previewCognifyTemplate = (params) => {
  return api.post('/intelligent-chat/cognify-template/preview', params)
}

/**
 * 预览 Memify 完整提示词（替换占位符后）
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.system_prompt - 自定义 System Prompt（可选）
 * @param {string} params.user_prompt_template - 自定义 User Prompt 模板（可选）
 * @param {string} params.template_type - 模版类型（默认: "default"）
 */
export const previewMemifyPrompt = (params) => {
  return api.post('/intelligent-chat/memify-prompt/preview', params)
}

/**
 * 预览生成 Memify 规则列表
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.system_prompt - 自定义 System Prompt（可选）
 * @param {string} params.user_prompt_template - 自定义 User Prompt 模板（可选）
 * @param {string} params.template_type - 模版类型（默认: "default"）
 */
export const previewMemifyRules = (params) => {
  return api.post('/intelligent-chat/memify-rules/preview', params)
}

/**
 * 步骤2: Cognee章节级处理
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.group_id - 文档组ID
 * @param {string} params.provider - LLM提供商
 */
export const step2CogneeBuild = (params) => {
  return api.post('/intelligent-chat/step2/cognee-build', params)
}

/**
 * 获取Cognee图谱数据
 * @param {string} group_id - 文档组ID
 */
export const getCogneeGraph = (group_id) => {
  return api.get('/intelligent-chat/step2/cognee-graph', {
    params: { group_id }
  })
}

/**
 * 检查 Graphiti 和 Cognee 的关联状态
 * @param {string} group_id - 文档组ID
 * @param {number} upload_id - 文档上传ID（可选）
 */
export const checkLinkage = (group_id, upload_id = null) => {
  return api.get('/intelligent-chat/linkage/check', {
    params: { group_id, upload_id }
  })
}

/**
 * 步骤3: Milvus向量化处理
 * @param {Object} params - 参数对象
 * @param {number} params.upload_id - 文档上传ID
 * @param {string} params.group_id - 文档组ID
 */
export const step3MilvusVectorize = (params) => {
  return api.post('/intelligent-chat/step3/milvus-vectorize', params)
}

// ==================== 检索生成流程 API ====================

/**
 * 步骤4: Milvus快速召回
 * @param {Object} params - 参数对象
 * @param {string} params.query - 查询文本
 * @param {number} params.top_k - 返回数量
 * @param {Array<string>} params.group_ids - 文档组ID列表（可选）
 */
export const step4MilvusRecall = (params) => {
  return api.post('/intelligent-chat/step4/milvus-recall', params)
}

/**
 * 步骤5: Neo4j精筛
 * @param {Object} params - 参数对象
 * @param {Array} params.recall_results - Milvus召回结果
 * @param {string} params.query - 查询文本
 */
export const step5Neo4jRefine = (params) => {
  return api.post('/intelligent-chat/step5/neo4j-refine', params)
}

/**
 * 步骤6: Mem0记忆注入
 * @param {Object} params - 参数对象
 * @param {Array} params.refined_results - Neo4j精筛结果
 * @param {string} params.user_id - 用户ID
 * @param {string} params.session_id - 会话ID
 */
export const step6Mem0Inject = (params) => {
  return api.post('/intelligent-chat/step6/mem0-inject', params)
}

/**
 * Mem0 独立问答
 * @param {Object} params - 参数对象
 * @param {string} params.query - 用户问题
 * @param {string} params.user_id - 用户ID（可选，未登录时使用）
 * @param {string} params.session_id - 会话ID（可选）
 * @param {Array} params.conversation_history - 对话历史（可选）
 * @param {string} params.provider - LLM提供商（默认 "local"）
 * @param {number} params.temperature - 温度参数（默认 0.7）
 */
export const mem0Chat = (params) => {
  return api.post('/intelligent-chat/mem0-chat', params)
}

/**
 * 步骤7: LLM生成
 * @param {Object} params - 参数对象
 * @param {string} params.query - 用户查询
 * @param {Array} params.retrieval_results - 智能检索结果
 * @param {string} params.provider - LLM提供商
 * @param {number} params.temperature - 温度参数
 */
export const step7LLMGenerate = (params) => {
  return api.post('/intelligent-chat/step7/llm-generate', params)
}

/**
 * 步骤7: LLM流式生成（仅主要回答，仅支持本地大模型）
 * @param {Object} params - 参数对象
 * @param {string} params.query - 用户查询
 * @param {Array} params.retrieval_results - 智能检索结果
 * @param {string} params.provider - LLM提供商（必须为"local"）
 * @param {number} params.temperature - 温度参数
 * @param {Function} onChunk - 接收chunk的回调函数 (chunk) => void
 * @param {Function} onDone - 完成回调函数 () => void
 * @param {Function} onError - 错误回调函数 (error) => void
 */
export const step7LLMGenerateStream = (params, onChunk, onDone, onError) => {
  const baseURL = api.defaults.baseURL || ''
  const url = `${baseURL}/intelligent-chat/step7/llm-generate-stream`
  
  console.log('发送流式生成请求:', url, params)
  
  // 构建请求头，只包含必要的headers
  const headers = {
    'Content-Type': 'application/json'
  }
  
  // 添加Authorization token（如果有）
  const token = localStorage.getItem('token') || sessionStorage.getItem('token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  return fetch(url, {
    method: 'POST',
    headers: headers,
    body: JSON.stringify(params)
  }).then(async response => {
    if (!response.ok) {
      // 尝试读取错误详情
      let errorDetail = `HTTP error! status: ${response.status}`
      try {
        const errorData = await response.json()
        errorDetail = errorData.detail || JSON.stringify(errorData)
        console.error('422错误详情:', errorData)
      } catch (e) {
        const errorText = await response.text()
        errorDetail = errorText || errorDetail
        console.error('422错误文本:', errorText)
      }
      throw new Error(errorDetail)
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    
    const readStream = () => {
      reader.read().then(({ done, value }) => {
        if (done) {
          if (onDone) onDone()
          return
        }
        
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || '' // 保留最后一个不完整的行
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.error) {
                if (onError) onError(new Error(data.error))
                return
              }
              if (data.done) {
                if (onDone) onDone()
                return
              }
              // 处理统计信息
              if (data.statistics) {
                if (onChunk) {
                  // 将统计信息作为特殊chunk传递，前端需要识别
                  onChunk({ type: 'statistics', data: data.statistics })
                }
              }
              // 处理文本内容
              if (data.content && onChunk) {
                onChunk(data.content)
              }
            } catch (e) {
              console.error('解析SSE数据失败:', e, line)
            }
          }
        }
        
        readStream()
      }).catch(error => {
        if (onError) onError(error)
      })
    }
    
    readStream()
  }).catch(error => {
    if (onError) onError(error)
  })
}

/**
 * 智能检索：两阶段检索策略
 * @param {Object} params - 参数对象
 * @param {string} params.query - 查询文本
 * @param {number} params.top_k - 阶段1的Top K（默认50）
 * @param {boolean} params.top3 - 是否选择Top3文档（默认true）
 * @param {Array<string>} params.group_ids - 检索范围（可选）
 * @param {boolean} params.enable_refine - 是否启用阶段2精细处理（默认true）
 * @param {boolean} params.enable_bm25 - 是否启用BM25检索（默认true）
 * @param {boolean} params.enable_graph_traverse - 是否启用图遍历（默认true）
 */
export const smartRetrieval = (params) => {
  return api.post('/intelligent-chat/smart-retrieval', params)
}

/**
 * 获取文档的完整层级结构
 * @param {number} upload_id - 文档上传ID
 */
export const getDocumentHierarchy = (upload_id) => {
  return api.get(`/intelligent-chat/document-hierarchy/${upload_id}`)
}

/**
 * 获取chunks与Cognee节点的映射关系
 * @param {number} upload_id - 文档上传ID
 */
export const getChunksCogneeMapping = (upload_id) => {
  return api.get(`/intelligent-chat/chunks-cognee-mapping/${upload_id}`)
}
