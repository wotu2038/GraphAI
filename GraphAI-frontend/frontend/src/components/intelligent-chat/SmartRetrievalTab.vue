<template>
  <div class="smart-retrieval-tab">
    <!-- 配置区域 -->
    <RecallConfigForm
      v-model:query-text="queryText"
      v-model:search-mode="searchMode"
      v-model:selected-group-ids="selectedGroupIds"
      v-model:top-k="topK"
      :documents="documents"
      :loading-documents="loadingDocuments"
      :executing="executing"
      @load-documents="loadDocuments"
    />

    <!-- 高级配置 -->
    <a-card title="高级配置" class="config-card" size="small">
      <a-form :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
        <a-form-item label="分数阈值">
          <a-slider
            v-model:value="minScore"
            :min="0"
            :max="100"
            :step="5"
            :disabled="executing"
            :marks="{ 0: '0', 60: '60', 70: '70', 80: '80', 90: '90', 100: '100' }"
          />
          <div style="margin-top: 8px; color: #666; font-size: 12px">
            <span>最低分数：{{ minScore }}分 | </span>
            <span v-if="minScore >= 90">极高相关度，精确匹配</span>
            <span v-else-if="minScore >= 80">高相关度，常规检索</span>
            <span v-else-if="minScore >= 70">中等相关度，宽泛检索</span>
            <span v-else-if="minScore >= 60">低相关度，探索性检索</span>
            <span v-else>结果质量可能较差</span>
          </div>
        </a-form-item>
        <a-form-item label="启用精细处理">
          <a-switch
            v-model:checked="enableRefine"
            :disabled="executing"
          />
          <span style="margin-left: 8px; color: #666">阶段2：使用Graphiti和Cognee进行精细扩展</span>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 操作区域 -->
    <RecallActionBar
      :executing="executing"
      :has-query="!!queryText.trim()"
      @execute="handleExecute"
      @clear="handleClear"
    />

    <!-- 加载状态 -->
    <LoadingState
      v-if="executing"
      :status="executionStatus"
      :progress="executionProgress"
      :steps="executionSteps"
      :current-step-index="currentStepIndex"
      :elapsed-time="elapsedTime"
    />

    <!-- 结果区域 -->
    <SmartRetrievalResults
      v-else-if="executionResult"
      :result="executionResult"
    />

    <!-- 空状态 -->
    <EmptyState v-else />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { getDocumentUploadList } from '../../api/documentUpload'
import { smartRetrieval } from '../../api/intelligentChat'
import RecallConfigForm from './recall/RecallConfigForm.vue'
import RecallActionBar from './recall/RecallActionBar.vue'
import SmartRetrievalResults from './SmartRetrievalResults.vue'
import LoadingState from './recall/LoadingState.vue'
import EmptyState from './recall/EmptyState.vue'

const documents = ref([])
const loadingDocuments = ref(false)
const queryText = ref('')
const searchMode = ref('all')
const selectedGroupIds = ref([])
const topK = ref(50)
const minScore = ref(70)
const enableRefine = ref(true)  // 默认启用阶段2
const executing = ref(false)
const executionStatus = ref('')
const executionResult = ref(null)
const executionProgress = ref(0)
const executionSteps = ref([])
const currentStepIndex = ref(0)
const elapsedTime = ref('')
let elapsedInterval = null
let progressInterval = null

const loadDocuments = async () => {
  loadingDocuments.value = true
  try {
    const response = await getDocumentUploadList(1, 100, null, 'completed')
    if (response && response.documents) {
      documents.value = response.documents.filter(doc => doc.document_id)
    } else {
      documents.value = []
    }
  } catch (error) {
    console.error('加载文档列表失败:', error)
    message.error(`加载文档列表失败: ${error.message || '未知错误'}`)
    documents.value = []
  } finally {
    loadingDocuments.value = false
  }
}

const updateElapsedTime = () => {
  if (!executing.value) return
  const elapsed = Math.floor((Date.now() - startTime) / 1000)
  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60
  elapsedTime.value = `${minutes}分${seconds}秒`
}

const updateProgress = () => {
  if (!executing.value) return
  
  const elapsed = (Date.now() - startTime) / 1000 // 已用时间（秒）
  
  // v4.0进度估算（简化为阶段1，阶段2预留）
  if (elapsed < 1) {
    // 步骤1：生成查询向量
    currentStepIndex.value = 0
    executionProgress.value = Math.min(10, (elapsed / 1) * 10)
    executionStatus.value = '正在生成查询向量...'
  } else if (elapsed < 3) {
    // 步骤2：Milvus检索DocumentChunk
    currentStepIndex.value = 1
    executionProgress.value = Math.min(30, 10 + ((elapsed - 1) / 2) * 20)
    executionStatus.value = 'Milvus检索 DocumentChunk_text...'
    if (executionSteps.value[1]) {
      executionSteps.value[1].status = 'processing'
    }
  } else if (elapsed < 4) {
    // 步骤3：过滤分数阈值
    currentStepIndex.value = 2
    executionProgress.value = Math.min(50, 30 + ((elapsed - 3) / 1) * 20)
    executionStatus.value = `过滤分数阈值 (>= ${minScore.value})...`
    if (executionSteps.value[1]) {
      executionSteps.value[1].status = 'finish'
      executionSteps.value[1].time = (3 - 1).toFixed(1)
    }
    if (executionSteps.value[2]) {
      executionSteps.value[2].status = 'processing'
    }
  } else if (elapsed < 5) {
    // 步骤4：Top K截取
    currentStepIndex.value = 3
    executionProgress.value = Math.min(60, 50 + ((elapsed - 4) / 1) * 10)
    executionStatus.value = `截取 Top ${topK.value}...`
    if (executionSteps.value[2]) {
      executionSteps.value[2].status = 'finish'
      executionSteps.value[2].time = (4 - 3).toFixed(1)
    }
    if (executionSteps.value[3]) {
      executionSteps.value[3].status = 'processing'
    }
  } else if (elapsed < 7) {
    // 步骤5：Neo4j批量查询
    currentStepIndex.value = 4
    executionProgress.value = Math.min(85, 60 + ((elapsed - 5) / 2) * 25)
    executionStatus.value = 'Neo4j批量查询补充元数据...'
    if (executionSteps.value[3]) {
      executionSteps.value[3].status = 'finish'
      executionSteps.value[3].time = (5 - 4).toFixed(1)
    }
    if (executionSteps.value[4]) {
      executionSteps.value[4].status = 'processing'
    }
  } else {
    // 步骤6：组装结果
    currentStepIndex.value = 5
    executionProgress.value = Math.min(98, 85 + ((elapsed - 7) / 3) * 13)
    executionStatus.value = '组装完整的chunk信息...'
    if (executionSteps.value[4]) {
      executionSteps.value[4].status = 'finish'
      executionSteps.value[4].time = (7 - 5).toFixed(1)
    }
    if (executionSteps.value[5]) {
      executionSteps.value[5].status = 'processing'
    }
  }
}

let startTime = null

const handleExecute = async () => {
  if (!queryText.value.trim()) {
    message.warning('请输入查询文本')
    return
  }

  if (searchMode.value === 'selected' && (!selectedGroupIds.value || selectedGroupIds.value.length === 0)) {
    message.warning('请选择要检索的文档')
    return
  }

  executing.value = true
  executionStatus.value = '正在初始化...'
  executionResult.value = null
  executionProgress.value = 0
  currentStepIndex.value = 0
  elapsedTime.value = '0分0秒'
  startTime = Date.now()

  // 初始化步骤列表（v4.0：单路DocumentChunk检索）
  executionSteps.value = [
    { title: '生成查询向量', status: 'wait', message: '正在将查询文本转换为向量...', time: null },
    { title: 'Milvus检索DocumentChunk', status: 'wait', message: '在Milvus中搜索 DocumentChunk_text（Cognee自动向量）...', time: null },
    { title: '过滤分数阈值', status: 'wait', message: `过滤分数 >= ${minScore.value} 的chunk...`, time: null },
    { title: 'Top K截取', status: 'wait', message: `选择Top ${topK.value}个chunk...`, time: null },
    { title: 'Neo4j批量查询', status: 'wait', message: '批量查询Neo4j补充元数据（章节、文档信息）...', time: null },
    { title: '组装结果', status: 'wait', message: '组装完整的chunk信息...', time: null }
  ]

  // 启动进度更新
  elapsedInterval = setInterval(updateElapsedTime, 1000)
  progressInterval = setInterval(updateProgress, 500)

  try {
    console.log('🔍 执行智能检索，enableRefine:', enableRefine.value)
    const params = {
      query: queryText.value,
      top_k: topK.value,
      min_score: minScore.value,
      enable_refine: enableRefine.value
    }
    console.log('📤 发送参数:', params)

    if (searchMode.value === 'selected') {
      params.group_ids = selectedGroupIds.value
    }

    // 执行查询
    const result = await smartRetrieval(params)
    
    // 完成所有步骤
    executionProgress.value = 100
    currentStepIndex.value = executionSteps.value.length
    executionSteps.value.forEach(step => {
      if (step.status === 'processing') {
        step.status = 'finish'
      }
      if (step.status === 'wait') {
        step.status = 'finish'
      }
    })
    
    executionResult.value = result
    executionStatus.value = '检索完成！'
    
    // 阶段1统计
    const chunkCount = result.stage1?.summary?.total_chunks || 0
    const docCount = result.stage1?.summary?.total_documents || 0
    
    // 阶段2统计
    const graphitiEntityCount = result.stage2?.graphiti?.statistics?.entity_count || 0
    const graphitiRelCount = result.stage2?.graphiti?.statistics?.relationship_count || 0
    const cogneeEntityCount = result.stage2?.cognee?.statistics?.entity_count || 0
    const cogneeRelCount = result.stage2?.cognee?.statistics?.relationship_count || 0
    const totalEntityCount = graphitiEntityCount + cogneeEntityCount
    
    // 生成提示语
    if (enableRefine.value && totalEntityCount > 0) {
      message.success(
        `智能检索完成！阶段1返回 ${chunkCount} 个chunk（涉及 ${docCount} 个文档），` +
        `阶段2扩展：Graphiti(${graphitiEntityCount}个Entity, ${graphitiRelCount}个关系) + ` +
        `Cognee(${cogneeEntityCount}个Entity, ${cogneeRelCount}个关系)，总计 ${totalEntityCount} 个Entity`
      )
    } else if (enableRefine.value) {
      message.success(
        `智能检索完成！阶段1返回 ${chunkCount} 个chunk（涉及 ${docCount} 个文档），` +
        `阶段2未找到扩展结果（请检查是否已启用精细处理或数据是否已处理）`
      )
    } else {
      message.success(
        `智能检索完成！返回 ${chunkCount} 个chunk（涉及 ${docCount} 个文档）`
      )
    }
  } catch (error) {
    console.error('执行失败:', error)
    message.error(`执行失败: ${error.response?.data?.detail || error.message || '未知错误'}`)
    // 标记失败的步骤
    if (executionSteps.value[currentStepIndex.value]) {
      executionSteps.value[currentStepIndex.value].status = 'error'
    }
  } finally {
    executing.value = false
    executionStatus.value = ''
    if (elapsedInterval) {
      clearInterval(elapsedInterval)
      elapsedInterval = null
    }
    if (progressInterval) {
      clearInterval(progressInterval)
      progressInterval = null
    }
  }
}

const handleClear = () => {
  executionResult.value = null
  queryText.value = ''
  message.success('结果已清空')
}

onMounted(() => {
  loadDocuments()
})

onUnmounted(() => {
  if (elapsedInterval) {
    clearInterval(elapsedInterval)
  }
  if (progressInterval) {
    clearInterval(progressInterval)
  }
})
</script>

<style scoped>
.smart-retrieval-tab {
  padding: 0;
}

.config-card {
  margin-bottom: 24px;
}
</style>

