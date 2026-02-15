<template>
  <div class="document-hierarchy-tab">
    <a-card :bordered="false" style="margin-bottom: 24px;">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-select
            v-model:value="selectedUploadId"
            placeholder="选择文档"
            style="width: 100%"
            show-search
            :filter-option="filterOption"
            @change="handleDocumentChange"
          >
            <a-select-option
              v-for="doc in documents"
              :key="doc.id"
              :value="doc.id"
            >
              {{ doc.file_name }} (ID: {{ doc.id }})
            </a-select-option>
          </a-select>
        </a-col>
        <a-col :span="12">
          <a-button type="primary" @click="loadHierarchy" :loading="loading">
            查询层级结构
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <a-spin :spinning="loading">
      <div v-if="hierarchy">
        <!-- 文档基本信息 -->
        <a-card :bordered="false" style="margin-bottom: 24px;">
          <template #title>
            <span>文档基本信息</span>
          </template>
          <a-descriptions :column="2" bordered>
            <a-descriptions-item label="文件名">{{ hierarchy.file_name }}</a-descriptions-item>
            <a-descriptions-item label="Upload ID">{{ hierarchy.upload_id }}</a-descriptions-item>
            <a-descriptions-item label="Doc ID">{{ hierarchy.doc_id }}</a-descriptions-item>
            <a-descriptions-item label="Group ID">{{ hierarchy.group_id || '未设置' }}</a-descriptions-item>
            <a-descriptions-item label="Version">{{ hierarchy.version }}</a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 数据一致性检查 -->
        <a-card :bordered="false" style="margin-bottom: 24px;">
          <template #title>
            <span>数据一致性检查</span>
          </template>
          <a-descriptions :column="2" bordered>
            <a-descriptions-item label="Doc ID 一致性">
              <a-tag :color="hierarchy.consistency_check.doc_id_match ? 'green' : 'red'">
                {{ hierarchy.consistency_check.doc_id_match ? '✅ 一致' : '❌ 不一致' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="Group ID 一致性">
              <a-tag :color="hierarchy.consistency_check.group_id_match ? 'green' : 'red'">
                {{ hierarchy.consistency_check.group_id_match ? '✅ 一致' : '❌ 不一致' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="Version 一致性">
              <a-tag :color="hierarchy.consistency_check.version_match ? 'green' : 'red'">
                {{ hierarchy.consistency_check.version_match ? '✅ 一致' : '❌ 不一致' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="问题列表" :span="2">
              <div v-if="hierarchy.consistency_check.issues.length > 0">
                <a-alert
                  v-for="(issue, idx) in hierarchy.consistency_check.issues"
                  :key="idx"
                  :message="issue"
                  type="warning"
                  style="margin-bottom: 8px"
                />
              </div>
              <span v-else style="color: #52c41a">✅ 无问题</span>
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 文档级别 -->
        <a-card :bordered="false" style="margin-bottom: 24px;">
          <template #title>
            <span>文档级别（Document Level）</span>
          </template>
          
          <a-row :gutter="16">
            <!-- Graphiti Episode -->
            <a-col :span="12">
              <a-card size="small" title="Graphiti Episode">
                <div v-if="hierarchy.document_level.graphiti_episode">
                  <a-descriptions :column="1" size="small" bordered>
                    <a-descriptions-item label="Episode UUID">
                      {{ hierarchy.document_level.graphiti_episode.episode_uuid }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Episode ID">
                      {{ hierarchy.document_level.graphiti_episode.episode_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Doc ID">
                      {{ hierarchy.document_level.graphiti_episode.doc_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Group ID">
                      {{ hierarchy.document_level.graphiti_episode.group_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Version">
                      {{ hierarchy.document_level.graphiti_episode.version }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Episode Type">
                      {{ hierarchy.document_level.graphiti_episode.episode_type }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Content">
                      <div style="max-height: 100px; overflow: hidden; text-overflow: ellipsis;">
                        {{ hierarchy.document_level.graphiti_episode.content }}
                      </div>
                    </a-descriptions-item>
                    <a-descriptions-item label="Created At">
                      {{ hierarchy.document_level.graphiti_episode.created_at }}
                    </a-descriptions-item>
                  </a-descriptions>
                </div>
                <a-empty v-else description="未找到 Graphiti Episode" />
              </a-card>
            </a-col>

            <!-- Cognee TextDocument -->
            <a-col :span="12">
              <a-card size="small" title="Cognee TextDocument">
                <div v-if="hierarchy.document_level.cognee_text_document">
                  <a-descriptions :column="1" size="small" bordered>
                    <a-descriptions-item label="TextDocument UUID">
                      {{ hierarchy.document_level.cognee_text_document.text_document_uuid }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Dataset Name">
                      {{ hierarchy.document_level.cognee_text_document.dataset_name }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Doc ID">
                      {{ hierarchy.document_level.cognee_text_document.doc_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Group ID">
                      {{ hierarchy.document_level.cognee_text_document.group_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Version">
                      {{ hierarchy.document_level.cognee_text_document.version }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Upload ID">
                      {{ hierarchy.document_level.cognee_text_document.upload_id }}
                    </a-descriptions-item>
                    <a-descriptions-item label="Created At">
                      {{ hierarchy.document_level.cognee_text_document.created_at }}
                    </a-descriptions-item>
                  </a-descriptions>
                </div>
                <a-empty v-else description="未找到 Cognee TextDocument" />
              </a-card>
            </a-col>
          </a-row>

          <!-- 关联关系 -->
          <a-divider />
          <a-card size="small" title="关联关系">
            <a-descriptions :column="2" bordered>
              <a-descriptions-item label="关联状态">
                <a-tag :color="hierarchy.document_level.linkage.established ? 'green' : 'orange'">
                  {{ hierarchy.document_level.linkage.established ? '✅ 已关联' : '⚠️ 未关联' }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="关系类型">
                {{ hierarchy.document_level.linkage.relation_type || '无' }}
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-card>

        <!-- 章节级别 -->
        <a-card :bordered="false" style="margin-bottom: 24px;">
          <template #title>
            <span>章节级别（Section Level）</span>
          </template>
          <template #extra>
            <span>共 {{ hierarchy.section_level.length }} 个章节</span>
          </template>

          <a-collapse v-model:activeKey="activeSectionKeys" v-if="hierarchy.section_level && hierarchy.section_level.length > 0">
            <a-collapse-panel
              v-for="(section, idx) in hierarchy.section_level"
              :key="idx"
              :header="`章节 ${idx + 1}: ${(section && section.name) ? section.name : '未命名'}`"
            >
              <a-descriptions :column="2" bordered size="small" v-if="section">
                <a-descriptions-item label="DataNode ID">
                  {{ section.data_node_id || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Name">
                  {{ section.name || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Doc ID">
                  {{ section.doc_id || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Group ID">
                  {{ section.group_id || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Version">
                  {{ section.version || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Upload ID">
                  {{ section.upload_id || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Chunk Count">
                  {{ section.chunk_count || 0 }}
                </a-descriptions-item>
                <a-descriptions-item label="Created At">
                  {{ section.created_at || '-' }}
                </a-descriptions-item>
                <a-descriptions-item label="Summary" :span="2">
                  <div style="max-height: 60px; overflow: hidden; text-overflow: ellipsis;">
                    {{ (section && section.summary) ? section.summary : '无摘要' }}
                  </div>
                </a-descriptions-item>
                <a-descriptions-item label="Text" :span="2">
                  <div style="max-height: 90px; overflow: hidden; text-overflow: ellipsis;">
                    {{ (section && section.text) ? section.text : '无内容' }}
                  </div>
                </a-descriptions-item>
              </a-descriptions>

              <!-- 分块列表 -->
              <a-divider />
              <a-card size="small" title="分块列表" style="margin-top: 16px">
                <a-table
                  :columns="chunkColumns"
                  :data-source="section.chunks || []"
                  :pagination="{ pageSize: 5 }"
                  size="small"
                  row-key="chunk_id"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'text'">
                      <div style="max-height: 60px; overflow: hidden; text-overflow: ellipsis;">
                        {{ record.text || '无内容' }}
                      </div>
                    </template>
                  </template>
                </a-table>
              </a-card>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <!-- 分块级别统计 -->
        <a-card :bordered="false" v-if="hierarchy.chunk_level && hierarchy.chunk_level.length > 0">
          <template #title>
            <span>分块级别统计（Chunk Level）</span>
          </template>
          <template #extra>
            <span>共 {{ hierarchy.chunk_level.length }} 个分块</span>
          </template>
          <a-table
            :columns="chunkColumns"
            :data-source="hierarchy.chunk_level"
            :pagination="{ pageSize: 10 }"
            row-key="chunk_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column && column.key === 'text'">
                <div style="max-height: 60px; overflow: hidden; text-overflow: ellipsis;">
                  {{ (record && record.text) ? record.text : '无内容' }}
                </div>
              </template>
            </template>
          </a-table>
        </a-card>
      </div>

      <a-empty v-else description="请选择文档并查询层级结构" />
    </a-spin>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { getDocumentHierarchy } from '@/api/intelligentChat'
import { getDocumentUploadList } from '@/api/documentUpload'

const selectedUploadId = ref(null)
const documents = ref([])
const hierarchy = ref(null)
const loading = ref(false)
const activeSectionKeys = ref([])

const chunkColumns = [
  {
    title: 'Chunk ID',
    dataIndex: 'chunk_id',
    key: 'chunk_id',
    width: 200,
    ellipsis: true
  },
  {
    title: 'Name',
    dataIndex: 'name',
    key: 'name',
    width: 150,
    ellipsis: true
  },
  {
    title: 'Chunk Index',
    dataIndex: 'chunk_index',
    key: 'chunk_index',
    width: 100
  },
  {
    title: 'Doc ID',
    dataIndex: 'doc_id',
    key: 'doc_id',
    width: 120
  },
  {
    title: 'Group ID',
    dataIndex: 'group_id',
    key: 'group_id',
    width: 200,
    ellipsis: true
  },
  {
    title: 'Version',
    dataIndex: 'version',
    key: 'version',
    width: 100
  },
  {
    title: 'Text',
    dataIndex: 'text',
    key: 'text',
    ellipsis: true
  }
]

const filterOption = (input, option) => {
  const text = option.children?.[0]?.children || option.label || ''
  return text.toLowerCase().indexOf(input.toLowerCase()) >= 0
}

const loadDocuments = async () => {
  try {
    // 后端限制page_size最大为100，使用100获取文档列表
    const response = await getDocumentUploadList(1, 100)
    // API拦截器已经返回了response.data，所以直接使用response.documents
    documents.value = response && response.documents ? response.documents : []
    console.log('文档列表加载成功，数量:', documents.value.length)
  } catch (error) {
    console.error('加载文档列表失败:', error)
    message.error('加载文档列表失败: ' + (error.response?.data?.detail || error.message || '未知错误'))
    documents.value = []
  }
}

const handleDocumentChange = () => {
  hierarchy.value = null
}

const loadHierarchy = async () => {
  if (!selectedUploadId.value) {
    message.warning('请先选择文档')
    return
  }

  loading.value = true
  try {
    const response = await getDocumentHierarchy(selectedUploadId.value)
    // API拦截器已经返回了response.data，所以直接使用response
    hierarchy.value = response
    console.log('查询层级结构成功:', hierarchy.value)
    message.success('查询成功')
    
    // 默认展开所有章节
    if (hierarchy.value && hierarchy.value.section_level && hierarchy.value.section_level.length > 0) {
      activeSectionKeys.value = hierarchy.value.section_level.map((_, idx) => idx)
    }
  } catch (error) {
    console.error('查询层级结构失败:', error)
    message.error(error.response?.data?.detail || '查询失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.document-hierarchy-tab {
  padding: 16px;
}
</style>
