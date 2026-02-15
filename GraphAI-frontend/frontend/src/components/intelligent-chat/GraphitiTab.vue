<template>
  <div class="graphiti-tab">
    <a-form layout="vertical" class="graphiti-tab-form">
      <div style="display: flex; justify-content: flex-end; margin-bottom: 16px">
        <a-space>
          <a-button 
            type="primary" 
            @click="handleExecuteGraphiti" 
            :loading="executing"
            :disabled="!selectedDocumentId"
          >
            <template #icon><PlayCircleOutlined /></template>
            执行Graphiti
          </a-button>
          <a-button @click="handleClearResult" :disabled="!executionResult && !executing">
            清空结果
          </a-button>
          <a-button 
            type="primary" 
            @click="handleLoadGraph" 
            :loading="loadingGraph"
            :disabled="!isDocumentProcessed"
          >
            <template #icon><ThunderboltOutlined /></template>
            加载图谱
          </a-button>
          <a-button 
            danger
            @click="handleDeleteGraph" 
            :loading="deletingGraph"
            :disabled="!isDocumentProcessed"
          >
            <template #icon><DeleteOutlined /></template>
            删除图谱
          </a-button>
        </a-space>
      </div>

      <a-form-item label="选择文档">
        <a-select
          v-model:value="selectedDocumentId"
          placeholder="请选择要处理的文档"
          @change="handleDocumentChange"
          :loading="loadingDocuments"
          :disabled="executing"
        >
          <a-select-option v-for="doc in documents" :key="doc.id" :value="doc.id">
            {{ doc.file_name }} (ID: {{ doc.id }})
          </a-select-option>
        </a-select>
      </a-form-item>

      <a-form-item label="LLM配置">
        <a-space>
          <a-select 
            v-model:value="llmProvider" 
            :disabled="executing"
            style="width: 150px"
          >
            <a-select-option value="qianwen">千问</a-select-option>
            <a-select-option value="deepseek">DeepSeek</a-select-option>
            <a-select-option value="kimi">Kimi</a-select-option>
            <a-select-option value="glm">GLM</a-select-option>
          </a-select>
          <div style="display: flex; align-items: center; margin-left: 24px">
            <span style="margin-right: 12px; color: #999">温度: {{ llmTemperature }}</span>
          <a-slider
              v-model:value="llmTemperature" 
            :min="0"
              :max="1" 
            :step="0.1"
              style="width: 150px"
            :disabled="executing"
          />
          </div>
        </a-space>
      </a-form-item>

      <!-- 实体关系模板配置 -->
      <a-card size="small" :bordered="true" style="margin-bottom: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05)">
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px">
            <ShareAltOutlined style="color: #1890ff" />
            <span style="font-weight: 600">实体关系模板配置</span>
          </div>
        </template>
        <template #extra>
          <a-radio-group v-model:value="templateMode" button-style="solid" size="small">
            <a-radio-button value="llm_generate">LLM自动生成</a-radio-button>
            <a-radio-button value="json_config">JSON手动配置</a-radio-button>
          </a-radio-group>
        </template>

        <!-- LLM 模式下的配置 -->
        <div v-if="templateMode === 'llm_generate'" style="padding-top: 8px">
          <!-- 模版类型选择 -->
          <a-form-item label="模版类型">
            <a-select v-model:value="templateType" :disabled="executing" placeholder="选择模版类型">
              <a-select-option value="default">默认模版</a-select-option>
            </a-select>
          </a-form-item>

          <!-- System Prompt -->
          <a-form-item>
            <template #label>
              <div style="display: flex; justify-content: space-between; width: 100%">
                <span>System Prompt</span>
                <a-button type="link" size="small" @click="resetSystemPrompt" style="padding: 0">恢复默认</a-button>
              </div>
            </template>
            <a-textarea 
              v-model:value="systemPrompt" 
              :rows="4" 
              placeholder="System Prompt"
              :disabled="executing"
              style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
            />
          </a-form-item>

          <!-- User Prompt 模板 -->
          <a-form-item>
            <template #label>
              <div style="display: flex; justify-content: space-between; width: 100%">
                <span>User Prompt 模板</span>
                <a-space>
                  <a-button type="link" size="small" @click="resetUserPrompt" style="padding: 0">恢复默认</a-button>
                  <a-button type="link" size="small" @click="previewActualPrompt" :disabled="!selectedDocumentId" style="padding: 0">预览完整</a-button>
                </a-space>
              </div>
            </template>
            <a-textarea
              v-model:value="userPromptTemplate" 
              :rows="12" 
              placeholder="User Prompt 模板（支持占位符: {document_name}, {summary_content}）"
              :disabled="executing"
              style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
            />
          </a-form-item>
        </div>

        <!-- 模板 JSON 编辑区 -->
        <div style="margin-top: 16px; border: 1px solid #d9d9d9; border-radius: 6px; overflow: hidden">
          <div style="background: #f5f5f5; padding: 8px 12px; border-bottom: 1px solid #d9d9d9; display: flex; justify-content: space-between; align-items: center">
            <div style="font-size: 12px; color: #595959; font-weight: 500">
              <CodeOutlined /> 模板 JSON 内容
              <span v-if="templateMode === 'llm_generate'" style="margin-left: 8px; color: #52c41a">
                {{ templateConfigJson ? '● 已生成' : '○ 待生成' }}
              </span>
            </div>
            <a-space v-if="templateMode === 'llm_generate'">
              <a-button type="primary" size="small" @click="handlePreviewTemplate" :loading="loadingTemplate" :disabled="!selectedDocumentId || executing">
                <ThunderboltOutlined /> LLM生成
              </a-button>
              <a-button size="small" @click="handleResetTemplate" :disabled="!generatedTemplateJson">重置</a-button>
            </a-space>
          </div>
          <a-textarea
            v-model:value="templateConfigJson"
            :placeholder="templateMode === 'llm_generate' ? '配置完成后点击「LLM生成」...' : '请输入符合规范的 JSON 结构...'"
            :rows="12"
            style="border: none; border-radius: 0; font-family: 'SFMono-Regular', Consolas, monospace; background: #fafafa; font-size: 13px"
            :disabled="executing"
          />
        </div>
      </a-card>

      <!-- Episode Body 区域 -->
      <a-card size="small" :bordered="true" style="margin-bottom: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05)">
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px">
            <FileTextOutlined style="color: #fa8c16" />
            <span style="font-weight: 600">Episode Body 内容（实体提取来源）</span>
          </div>
        </template>
        <template #extra>
        <a-space>
            <a-button size="small" @click="handleLoadEpisodeBody" :loading="loadingEpisodeBody" :disabled="!selectedDocumentId || executing">
              重新提取
          </a-button>
            <a-button size="small" @click="handleResetEpisodeBody" :disabled="!originalEpisodeBody || executing">
              重置
          </a-button>
        </a-space>
        </template>
        <a-textarea
          v-model:value="episodeBody"
          placeholder="请先选择文档..."
          :rows="8"
          style="font-family: 'SFMono-Regular', Consolas, monospace; background: #fafafa; font-size: 13px"
          :disabled="executing || !selectedDocumentId"
          :maxlength="3000"
          show-count
        />
      </a-card>
    </a-form>

    <!-- 结果区域 -->
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

    <div v-else-if="executionResult">
      <!-- 执行结果摘要 -->
      <a-card size="small" title="执行结果摘要" style="margin-bottom: 24px; border-radius: 8px">
        <a-descriptions :column="3" bordered size="small">
          <a-descriptions-item label="文档ID">
            <span style="font-family: monospace; font-size: 12px">{{ executionResult.doc_id || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="文档标题">
            <span>{{ executionResult.file_name || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="文档类型">
            <a-tag :color="executionResult.episode_type === 'NEW' ? 'green' : 'orange'">
              {{ executionResult.episode_type || '-' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="版本号">
            <span>{{ executionResult.version || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="文档上传时间">
            <span>{{ executionResult.upload_time ? new Date(executionResult.upload_time).toLocaleString('zh-CN') : '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="Group ID">
            <span style="font-family: monospace; font-size: 12px">{{ executionResult.group_id || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="Episode UUID">
            <span style="font-family: monospace; font-size: 12px">{{ executionResult.episode_uuid || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="实体/关系数量">
            <a-tag color="blue">{{ executionResult.entity_count || 0 }} 实体</a-tag>
            <a-tag color="cyan">{{ executionResult.edge_count || 0 }} 关系</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="关联状态">
            <a-tag color="green">处理成功</a-tag>
          </a-descriptions-item>
        </a-descriptions>
      </a-card>

      <!-- 结果详情展示 -->
      <a-card size="small" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08)">
        <a-tabs default-active-key="graph">
          <a-tab-pane key="graph" tab="知识图谱可视化">
            <div style="height: 600px; border: 1px solid #f0f0f0; border-radius: 4px; background: #fff">
              <GraphVisualization 
                v-if="graphData && graphData.nodes && graphData.nodes.length > 0"
                :data="graphData"
                @nodeClick="handleNodeClick"
                @edgeClick="handleEdgeClick"
              />
              <div v-else style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #bfbfbf">
                <LoadingOutlined v-if="loadingGraph" style="font-size: 32px; margin-bottom: 16px" />
                <InboxOutlined v-else style="font-size: 48px; margin-bottom: 16px" />
                <span>{{ loadingGraph ? '正在加载图谱数据...' : '暂无图谱数据' }}</span>
              </div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="entities" tab="实体列表">
        <a-table
          :columns="entityColumns"
          :data-source="entityListData"
              size="small"
          :pagination="{ pageSize: 10 }"
            />
          </a-tab-pane>
          <a-tab-pane key="edges" tab="关系列表">
        <a-table
          :columns="edgeColumns"
          :data-source="edgeListData"
              size="small"
          :pagination="{ pageSize: 10 }"
            />
          </a-tab-pane>
        </a-tabs>
      </a-card>
    </div>

    <div v-else style="text-align: center; padding: 100px 0; color: #bfbfbf">
      <div style="font-size: 48px; margin-bottom: 16px">
        <InboxOutlined />
      </div>
      <div>请选择文档并点击右上角"执行Graphiti"按钮开始处理</div>
    </div>

    <!-- 节点详情抽屉 -->
    <a-drawer v-model:open="nodeDrawerVisible" title="节点属性" :width="450">
      <div v-if="selectedNode">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="名称">{{ selectedNode.properties?.name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="标签">{{ selectedNode.labels?.join(', ') || '-' }}</a-descriptions-item>
          <a-descriptions-item label="属性">
            <pre style="font-size: 11px; max-height: 400px; overflow-y: auto">{{ JSON.stringify(selectedNode.properties, null, 2) }}</pre>
          </a-descriptions-item>
        </a-descriptions>
      </div>
    </a-drawer>

    <!-- 关系详情抽屉 -->
    <a-drawer v-model:open="edgeDrawerVisible" title="关系属性" :width="450">
      <div v-if="selectedEdge">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="类型">{{ selectedEdge.type || '-' }}</a-descriptions-item>
          <a-descriptions-item label="源">{{ selectedEdge.source }}</a-descriptions-item>
          <a-descriptions-item label="目标">{{ selectedEdge.target }}</a-descriptions-item>
          <a-descriptions-item label="数据">
            <pre style="font-size: 11px; max-height: 400px; overflow-y: auto">{{ JSON.stringify(selectedEdge, null, 2) }}</pre>
          </a-descriptions-item>
        </a-descriptions>
      </div>
    </a-drawer>

    <!-- 解析模式选择弹窗 -->
    <a-modal
      v-model:visible="parseModeModalVisible"
      title="选择解析模式"
      :width="600"
      @ok="handleConfirmParseMode"
      @cancel="parseModeModalVisible = false"
    >
      <div style="margin-bottom: 16px">
        <p style="margin-bottom: 16px">请选择模板生成使用的解析模式：</p>
        <a-radio-group v-model:value="selectedParseMode" style="display: block">
          <a-radio value="summary_parse" style="display: block; margin-bottom: 16px; padding: 12px; border: 1px solid #d9d9d9; border-radius: 4px">
            <div style="font-weight: bold; margin-bottom: 4px">摘要解析</div>
            <div style="color: #666; font-size: 12px">使用 Episode Body 内容（包含文档基本信息、功能概述、业务信息、系统信息、流程信息）</div>
          </a-radio>
          <a-radio value="full_parse" style="display: block; padding: 12px; border: 1px solid #d9d9d9; border-radius: 4px">
            <div style="font-weight: bold; margin-bottom: 4px">全文解析</div>
            <div style="color: #666; font-size: 12px">使用完整文档内容（parsed_content.md），适合大文档和完整分析</div>
          </a-radio>
        </a-radio-group>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { 
  PlayCircleOutlined, 
  ThunderboltOutlined, 
  LoadingOutlined,
  InboxOutlined,
  ShareAltOutlined,
  FileTextOutlined,
  CodeOutlined,
  DeleteOutlined
} from '@ant-design/icons-vue'
import GraphVisualization from '../GraphVisualization.vue'
import { getDocumentUploadList } from '@/api/documentUpload'
import { step1GraphitiEpisode, previewEpisodeBody, previewTemplate, getGraphitiGraph, getGraphitiResult, deleteGraphitiGraph } from '@/api/intelligentChat'

// Git 已提交版本的默认提示词
const DEFAULT_SYSTEM_PROMPT = `你是一个专业的知识图谱模板生成专家，擅长从文档中提取实体和关系结构，生成规范的模板配置。`

const DEFAULT_USER_PROMPT_TEMPLATE = `你是一个知识图谱模板生成专家。请分析以下文档内容，生成适合的实体和关系模板配置。

文档名称: {document_name}

文档内容:
{summary_content}

请根据文档内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别文档中的核心实体（如：需求、功能、模块、用户、产品等）
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
   - 格式：{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}

要求：
- 返回标准JSON格式
- 实体类型和关系类型要符合文档的实际内容
- 字段定义要完整（type, required, description）
- 关系映射要准确反映文档中的实体关系
- ⚠️ **严禁使用保留字段名**

返回JSON格式：
{
  "entity_types": {
    "EntityName": {
      "description": "实体类型的描述，说明这个实体类型代表什么（例如：\\"角色实体，代表系统中的各种角色和岗位\\"）",
      "fields": {
        "field_name": {
          "type": "str|Optional[str]|int|Optional[int]|bool|Optional[bool]",
          "required": true|false,
          "description": "字段描述"
        }
      }
    }
  },
  "edge_types": {
    "EdgeName": {
      "description": "关系类型的描述，说明这个关系类型代表什么（例如：\\"审批关系，表示一个实体对另一个实体的审批行为\\"）",
      "fields": {
        "field_name": {
          "type": "str|Optional[str]|int|Optional[int]|bool|Optional[bool]",
          "required": true|false,
          "description": "字段描述"
        }
      }
    }
  },
  "edge_type_map": {
    "SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]
  }
}

只返回JSON，不要其他内容。`

// 状态
const loadingDocuments = ref(false)
const documents = ref([])
const selectedDocumentId = ref(null)
const executing = ref(false)
const executionStatus = ref('')
const executionResult = ref(null)
const selectedDocumentHasGraph = ref(false) // 标记选中的文档是否有图谱
const loadingEpisodeBody = ref(false)
const episodeBody = ref('')
const originalEpisodeBody = ref('')

// 图谱相关
const graphData = ref(null)
const loadingGraph = ref(false)
const deletingGraph = ref(false)
const selectedNode = ref(null)
const selectedEdge = ref(null)
const nodeDrawerVisible = ref(false)
const edgeDrawerVisible = ref(false)
const entityListData = ref([])
const edgeListData = ref([])

// 配置
const llmProvider = ref('qianwen')
const llmTemperature = ref(0.7)
const templateMode = ref('llm_generate')
const templateType = ref('default')
const templateConfigJson = ref('')
const generatedTemplateJson = ref('')
const loadingTemplate = ref(false)

// 解析模式选择
const parseModeModalVisible = ref(false)
const selectedParseMode = ref('summary_parse') // 'summary_parse' 或 'full_parse'

// Prompt（使用 Git 已提交版本作为默认值）
const systemPrompt = ref(DEFAULT_SYSTEM_PROMPT)
const userPromptTemplate = ref(DEFAULT_USER_PROMPT_TEMPLATE)

// 计算属性：判断当前选中的文档是否已处理过（有 document_id）
const isDocumentProcessed = computed(() => {
  // 优先使用 selectedDocumentHasGraph（在 handleDocumentChange 中设置）
  // 如果没有设置，则检查 documents 数组
  if (selectedDocumentHasGraph.value) return true
  if (!selectedDocumentId.value) return false
  const selectedDoc = documents.value.find(doc => doc.id === selectedDocumentId.value)
  return selectedDoc && selectedDoc.document_id ? true : false
})

// 表格列
const entityColumns = [
  { 
    title: '名称', 
    key: 'name',
    customRender: ({ record }) => record.properties?.name || record.name || '-' 
  },
  { 
    title: '标签', 
    key: 'labels',
    customRender: ({ record }) => {
      const labels = record.labels || []
      return labels.filter(l => l !== 'Entity').join(', ') || 'Entity'
    }
  },
  { 
    title: 'UUID', 
    key: 'uuid',
    customRender: ({ record }) => record.properties?.uuid || record.uuid || record.id || '-' 
  }
]
const edgeColumns = [
  { 
    title: '源实体', 
    key: 'source',
    customRender: ({ record }) => {
      const sourceId = record.source || record.source_node_uuid
      if (!sourceId) return '-'
      // 尝试从graphData中查找源节点名称
      if (graphData.value?.nodes) {
        const sourceNode = graphData.value.nodes.find(n => n.id === String(sourceId))
        return sourceNode?.properties?.name || sourceNode?.name || sourceId
      }
      return sourceId
    }
  },
  { 
    title: '关系类型', 
    key: 'type',
    customRender: ({ record }) => record.type || record.label || '-' 
  },
  { 
    title: '目标实体', 
    key: 'target',
    customRender: ({ record }) => {
      const targetId = record.target || record.target_node_uuid
      if (!targetId) return '-'
      // 尝试从graphData中查找目标节点名称
      if (graphData.value?.nodes) {
        const targetNode = graphData.value.nodes.find(n => n.id === String(targetId))
        return targetNode?.properties?.name || targetNode?.name || targetId
      }
      return targetId
    }
  }
]

// 方法
const handleDocumentChange = async (val) => {
  if (val) {
    handleLoadEpisodeBody()
    
    // 直接调用API检查文档是否有Graphiti图谱（不依赖documents数组）
    // 因为documents数组可能被过滤，导致找不到文档
    try {
      const res = await getGraphitiResult(val)
      // 只要有 group_id，就认为文档已处理过（即使 Episode 不存在，也可能是因为数据被删除）
      if (res.group_id) {
        // 文档已执行过Graphiti（有 group_id）
        selectedDocumentHasGraph.value = true
        executionResult.value = res
        // 如果 success 为 false，说明 Episode 不存在，但不影响按钮可用性
        if (!res.success && res.message) {
          // 只显示信息提示，不阻止按钮使用
          // message.info(res.message)
        }
      } else {
        // 没有 group_id，文档未处理过Graphiti
        executionResult.value = null
        selectedDocumentHasGraph.value = false
        if (res.message) {
          message.info(res.message)
    }
      }
    } catch (err) {
      // API调用失败，可能是文档未处理过Graphiti
      executionResult.value = null
      selectedDocumentHasGraph.value = false
      // 不显示错误消息，因为文档可能确实未处理过
      // message.error('获取执行结果失败: ' + (err.response?.data?.detail || err.message))
    }
    
    graphData.value = null
    entityListData.value = []
    edgeListData.value = []
    } else {
      // 没有选择文档
      selectedDocumentHasGraph.value = false
      executionResult.value = null
    }
}

const handleLoadEpisodeBody = async () => {
  if (!selectedDocumentId.value) return
  loadingEpisodeBody.value = true
  try {
    const res = await previewEpisodeBody(selectedDocumentId.value)
    episodeBody.value = res.episode_body
    originalEpisodeBody.value = res.episode_body
  } catch (err) {
    message.error('加载 Episode Body 失败')
  } finally {
    loadingEpisodeBody.value = false
  }
}

const handleResetEpisodeBody = () => {
  episodeBody.value = originalEpisodeBody.value
}

const handlePreviewTemplate = () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }

  // 弹出模式选择弹窗
  parseModeModalVisible.value = true
  selectedParseMode.value = 'summary_parse' // 默认选择摘要解析
}

const handleConfirmParseMode = async () => {
  parseModeModalVisible.value = false
  loadingTemplate.value = true
  
  try {
    // 根据选择的模式调用不同的API
    const res = await previewTemplate({
      upload_id: selectedDocumentId.value,
      provider: llmProvider.value,
      temperature: llmTemperature.value,
      system_prompt: systemPrompt.value,
      user_prompt_template: userPromptTemplate.value,
      parse_mode: selectedParseMode.value
    })
    
    templateConfigJson.value = JSON.stringify(res.template_config, null, 2)
    generatedTemplateJson.value = templateConfigJson.value
    // 保存选择的模式，供"执行 Graphiti"时使用
    message.success(`模板生成成功（${selectedParseMode.value === 'summary_parse' ? '摘要解析' : '全文解析'}模式）`)
  } catch (err) {
    message.error('模板生成失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loadingTemplate.value = false
  }
}

const handleResetTemplate = () => {
  templateConfigJson.value = generatedTemplateJson.value
}

const resetSystemPrompt = () => {
  systemPrompt.value = DEFAULT_SYSTEM_PROMPT
  message.success('已恢复为默认 System Prompt')
}

const resetUserPrompt = () => {
  userPromptTemplate.value = DEFAULT_USER_PROMPT_TEMPLATE
  message.success('已恢复为默认 User Prompt 模板')
}

const previewActualPrompt = () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档以预览实际注入后的 Prompt')
    return
  }
  
  Modal.info({
    title: '预览完整 Prompt（模拟注入）',
    width: 900,
    content: h('div', { style: 'max-height: 600px; overflow-y: auto' }, [
      h('div', { style: 'margin-bottom: 24px' }, [
        h('div', { style: 'font-weight: bold; color: #1890ff; margin-bottom: 8px; font-size: 14px' }, 'System Prompt:'),
        h('pre', { style: 'background: #f5f5f5; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all' }, systemPrompt.value)
      ]),
      h('div', [
        h('div', { style: 'font-weight: bold; color: #1890ff; margin-bottom: 8px; font-size: 14px' }, 'User Prompt（已模拟注入文档元数据）:'),
        h('pre', { style: 'background: #f5f5f5; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all' }, 
          userPromptTemplate.value
            .replace('{document_name}', '【示例文档.pdf】')
            .replace('{summary_content}', '文档ID: DOC_123\n文档标题: 示例文档\n文档类型: NEW\n版本号: V1\n文档上传时间: 2026-02-05T10:00:00\n\n功能概述:\n本系统旨在实现...（示例内容）\n\n业务信息:\n业务目标：...\n业务场景：...\n\n系统信息:\n系统架构：...\n技术栈：...')
        )
      ])
    ]),
    okText: '知道了'
  })
}

const handleExecuteGraphiti = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }

  executing.value = true
  executionStatus.value = '正在处理...'

  try {
    let template_config = null
    if (templateConfigJson.value) {
      try {
        template_config = JSON.parse(templateConfigJson.value)
      } catch (e) {
        message.error('模板 JSON 格式错误')
        executing.value = false
        return
      }
    }

    // 如果是 LLM 生成模式，直接使用"LLM生成"时选择的模式
    // 如果没有生成过模板（selectedParseMode 未设置），默认使用摘要解析
    let parse_mode = selectedParseMode.value || 'summary_parse'
    
    // 直接执行，不再弹出确认框
    await executeGraphitiWithMode(parse_mode, template_config)
  } catch (err) {
    message.error('执行失败: ' + (err.response?.data?.detail || err.message))
    executing.value = false
  }
}

const executeGraphitiWithMode = async (parse_mode, template_config) => {
  try {
    const res = await step1GraphitiEpisode({
      upload_id: selectedDocumentId.value,
      episode_body: episodeBody.value,
      template_config_json: template_config,
      template_mode: templateMode.value,
      parse_mode: parse_mode,
      provider: llmProvider.value,
      temperature: llmTemperature.value,
      system_prompt: systemPrompt.value,
      user_prompt_template: userPromptTemplate.value
    })

    // 优先检查是否需要确认删除已存在的Episode（即使success为false也要检查）
    // 注意：必须在finally之前处理，避免状态被重置
    if (res && res.needs_confirmation === true) {
      // 显示确认对话框（异步，不阻塞）
      Modal.confirm({
        title: '确认删除',
        content: `已存在Graphiti Episode（创建时间: ${res.existing_episode?.created_at || '未知'}），是否删除后重建？`,
        okText: '确认删除并重建',
        cancelText: '取消',
        onOk: async () => {
          try {
            executing.value = true
            executionStatus.value = '正在删除旧的Episode...'
            // 删除已存在的Episode
            await deleteGraphitiGraph(selectedDocumentId.value)
            message.success('已删除旧的Episode，开始重建...')
            
            // 重新执行
            await executeGraphitiWithMode(parse_mode, template_config)
          } catch (err) {
            message.error('删除失败: ' + (err.response?.data?.detail || err.message))
            executing.value = false
            executionStatus.value = ''
          }
        },
        onCancel: () => {
          executing.value = false
          executionStatus.value = ''
        }
      })
      // 注意：这里不return，让finally块执行，重置状态
      // 但是对话框已经显示，用户可以选择
      executing.value = false
      executionStatus.value = ''
      return
    }

    // 如果success为false且不是needs_confirmation，说明是其他错误
    if (res && res.success === false && !res.needs_confirmation) {
      console.error('API返回错误:', res.message || '未知错误')
      message.error(res.message || '执行失败')
      executing.value = false
      executionStatus.value = ''
      return
    }

    message.success(`处理成功（${parse_mode === 'summary_parse' ? '摘要解析' : '全文解析'}模式），获取执行结果摘要...`)

    // 调用新API获取完整的执行结果摘要（包括文档标题、上传时间等）
    try {
      const resultRes = await getGraphitiResult(selectedDocumentId.value)
      if (resultRes.success) {
        executionResult.value = resultRes
        message.success('执行结果摘要加载成功，加载图谱...')
        
        if (resultRes.group_id) {
          await fetchGraphData(resultRes.group_id)
        }
      } else {
        // 如果获取摘要失败，使用原始返回结果
        executionResult.value = res
        message.warning('获取执行结果摘要失败，使用基础信息')
        
        if (res.group_id) {
          await fetchGraphData(res.group_id)
        }
      }
    } catch (err) {
      // 如果API调用失败，使用原始返回结果
      executionResult.value = res
      message.warning('获取执行结果摘要失败: ' + (err.response?.data?.detail || err.message))
      
      if (res.group_id) {
        await fetchGraphData(res.group_id)
      }
    }
  } catch (err) {
    message.error('执行失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    executing.value = false
    executionStatus.value = ''
  }
}

const handleLoadGraph = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  
  // 如果没有执行结果或没有 group_id，先尝试获取执行结果摘要
  if (!executionResult.value?.group_id) {
    try {
      const res = await getGraphitiResult(selectedDocumentId.value)
      if (res.success && res.group_id) {
        executionResult.value = res
      } else {
        message.warning('文档未处理或缺少 group_id，无法加载图谱')
        return
      }
    } catch (err) {
      message.error('获取执行结果失败: ' + (err.response?.data?.detail || err.message))
      return
    }
  }
  
  await fetchGraphData(executionResult.value.group_id)
}

const fetchGraphData = async (groupId) => {
  loadingGraph.value = true
  try {
    const res = await getGraphitiGraph(groupId)
    graphData.value = res
    
    // 从图谱数据中提取实体和关系列表
    if (res.nodes) {
      entityListData.value = res.nodes.map(node => ({
        id: node.id,
        name: node.properties?.name || node.name,
        uuid: node.properties?.uuid || node.id,
        labels: node.labels || [],
        properties: node.properties || {}
      }))
    } else {
      entityListData.value = []
    }
    
    if (res.edges) {
      edgeListData.value = res.edges.map(edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        source_node_uuid: edge.source,
        target_node_uuid: edge.target,
        label: edge.type,
        properties: edge.properties || {}
      }))
    } else {
      edgeListData.value = []
    }
    
    message.success(`图谱加载成功：${entityListData.value.length} 个实体，${edgeListData.value.length} 个关系`)
  } catch (err) {
    message.error('图谱加载失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loadingGraph.value = false
  }
}

const handleClearResult = () => {
  executionResult.value = null
  graphData.value = null
  entityListData.value = []
  edgeListData.value = []
  message.info('结果已清空')
}

const handleDeleteGraph = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  
  // 如果没有执行结果或没有 group_id，先尝试获取执行结果摘要
  if (!executionResult.value?.group_id) {
    try {
      const res = await getGraphitiResult(selectedDocumentId.value)
      if (res.success && res.group_id) {
        executionResult.value = res
      } else {
        message.warning('文档未处理或缺少 group_id，无法删除图谱')
        return
      }
    } catch (err) {
      message.error('获取执行结果失败: ' + (err.response?.data?.detail || err.message))
      return
    }
  }
  
  Modal.confirm({
    title: '确认删除图谱',
    content: h('div', [
      h('p', { style: 'margin-bottom: 8px' }, '确定要删除该文档的Graphiti图谱吗？'),
      h('p', { style: 'color: #ff4d4f; margin-bottom: 0' }, '此操作将永久删除以下数据：'),
      h('ul', { style: 'margin: 8px 0 0 20px; padding: 0' }, [
        h('li', 'Neo4j中的节点和关系（Entity、Edge、Episode、Community）'),
        h('li', 'Milvus中的向量数据'),
        h('li', 'MySQL中的模板配置记录'),
        h('li', '执行结果摘要')
      ]),
      h('p', { style: 'color: #ff4d4f; margin-top: 12px; margin-bottom: 0; fontWeight: bold' }, '此操作不可恢复！')
    ]),
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      deletingGraph.value = true
      try {
        const res = await deleteGraphitiGraph(selectedDocumentId.value)
        
        if (res.success) {
          message.success('图谱删除成功')
          
          // 清空所有相关数据
          executionResult.value = null
          graphData.value = null
          entityListData.value = []
          edgeListData.value = []
          
          // 清空模板配置（如果存在）
          templateConfigJson.value = ''
          generatedTemplateJson.value = null
          
          // 清空Episode Body（如果存在）
          episodeBody.value = ''
          originalEpisodeBody.value = ''
        } else {
          message.warning(`图谱删除部分成功: ${res.message || '部分数据删除失败'}`)
          
          // 即使部分失败，也清空前端显示的数据
          executionResult.value = null
          graphData.value = null
          entityListData.value = []
          edgeListData.value = []
        }
      } catch (err) {
        message.error('图谱删除失败: ' + (err.response?.data?.detail || err.message))
      } finally {
        deletingGraph.value = false
      }
    }
  })
}

const handleNodeClick = (node) => {
  selectedNode.value = node
  nodeDrawerVisible.value = true
}

const handleEdgeClick = (edge) => {
  selectedEdge.value = edge
  edgeDrawerVisible.value = true
}

onMounted(async () => {
  loadingDocuments.value = true
  try {
    const res = await getDocumentUploadList(1, 100)
    if (res && (res.documents || res.items)) {
      const list = res.documents || res.items
      documents.value = list.filter(doc => doc.parsed_content_path)
  }
  } catch (err) {
    message.error('获取文档列表失败')
  } finally {
    loadingDocuments.value = false
  }
})
</script>

<style scoped>
.graphiti-tab {
  padding: 12px 0;
}
.graphiti-tab-form :deep(.ant-form-item) {
  margin-bottom: 16px;
}
</style>
