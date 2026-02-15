<template>
  <div class="stage2-result-list">
    <!-- 描述信息 -->
    <a-alert 
      :message="sourceLabel" 
      :description="description" 
      type="info" 
      show-icon 
      style="margin-bottom: 16px"
    />

    <!-- 结果列表 -->
    <a-list
      v-if="results.length > 0"
      :data-source="results"
      :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 条结果` }"
      item-layout="vertical"
    >
      <template #renderItem="{ item, index }">
        <a-list-item>
          <a-list-item-meta>
            <template #title>
              <a-space>
                <a-tag color="blue">{{ index + 1 }}</a-tag>
                <span style="font-weight: 600">{{ item.name || '(未命名)' }}</span>
                <a-tag :color="getTypeColor(item.type)">
                  {{ getTypeLabel(item.type) }}
                </a-tag>
                <a-tag color="orange">
                  相似度: {{ formatScore(item.score) }}
                </a-tag>
              </a-space>
            </template>
            <template #description>
              <!-- 基本信息 -->
              <a-descriptions :column="2" size="small" bordered style="margin-bottom: 12px">
                <a-descriptions-item label="UUID">
                  <span style="font-family: monospace; font-size: 11px">
                    {{ item.uuid ? (item.uuid.substring(0, 20) + '...') : '自动生成' }}
                  </span>
                </a-descriptions-item>
                <a-descriptions-item label="来源渠道">
                  <a-tag color="purple">{{ sourceLabel }}</a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="文档ID" :span="2">
                  <span style="font-family: monospace; font-size: 11px">{{ item.group_id || '-' }}</span>
                </a-descriptions-item>
                <a-descriptions-item label="分数详情" :span="2">
                  <a-progress 
                    :percent="Math.min(item.score || 0, 100)" 
                    :stroke-color="getScoreColor(item.score)"
                    size="small"
                  />
                </a-descriptions-item>
              </a-descriptions>

              <!-- 内容预览 -->
              <div style="margin-top: 12px">
                <div style="font-weight: 500; margin-bottom: 4px; color: #666">内容预览：</div>
                <div 
                  style="
                    padding: 12px; 
                    background: #fafafa; 
                    border-radius: 4px; 
                    border: 1px solid #e8e8e8;
                    max-height: 100px;
                    overflow: hidden;
                    font-size: 12px;
                    color: #333;
                    line-height: 1.6;
                  "
                >
                  {{ getContentPreview(item) }}
                </div>
              </div>

              <!-- 操作按钮 -->
              <div style="margin-top: 12px">
                <a-space>
                  <a-button 
                    type="link" 
                    size="small" 
                    @click="showFullContent(item)"
                    style="padding: 0"
                  >
                    查看完整内容
                  </a-button>
                  <a-button 
                    v-if="item.metadata"
                    type="link" 
                    size="small" 
                    @click="showMetadata(item)"
                    style="padding: 0"
                  >
                    查看元数据
                  </a-button>
                </a-space>
              </div>
            </template>
          </a-list-item-meta>
        </a-list-item>
      </template>
    </a-list>

    <a-empty v-else description="暂无结果" />

    <!-- 完整内容弹窗 -->
    <a-modal
      v-model:open="fullContentVisible"
      title="完整内容"
      width="800px"
      :footer="null"
    >
      <div v-if="selectedItem">
        <a-descriptions :column="1" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="名称">{{ selectedItem.name || '(未命名)' }}</a-descriptions-item>
          <a-descriptions-item label="类型">
            <a-tag :color="getTypeColor(selectedItem.type)">
              {{ getTypeLabel(selectedItem.type) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="UUID">
            <span style="font-family: monospace; font-size: 11px">{{ selectedItem.uuid || '自动生成' }}</span>
          </a-descriptions-item>
        </a-descriptions>
        <div style="margin-top: 16px">
          <div style="font-weight: 500; margin-bottom: 8px">内容：</div>
          <pre 
            style="
              background: #fafafa; 
              padding: 16px; 
              border-radius: 4px; 
              border: 1px solid #e8e8e8;
              max-height: 500px;
              overflow-y: auto;
              white-space: pre-wrap;
              word-break: break-word;
              font-size: 12px;
              line-height: 1.6;
            "
          >{{ selectedItem.content || '(无内容)' }}</pre>
        </div>
      </div>
    </a-modal>

    <!-- 元数据弹窗 -->
    <a-modal
      v-model:open="metadataVisible"
      title="元数据"
      width="800px"
      :footer="null"
    >
      <div v-if="selectedItem">
        <pre 
          style="
            background: #1e1e1e; 
            color: #d4d4d4; 
            padding: 16px; 
            border-radius: 4px;
            max-height: 600px;
            overflow-y: auto;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
            line-height: 1.5;
          "
        >{{ JSON.stringify(selectedItem.metadata, null, 2) }}</pre>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  results: {
    type: Array,
    required: true
  },
  sourceLabel: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  }
})

const fullContentVisible = ref(false)
const metadataVisible = ref(false)
const selectedItem = ref(null)

// 显示完整内容
const showFullContent = (item) => {
  selectedItem.value = item
  fullContentVisible.value = true
}

// 显示元数据
const showMetadata = (item) => {
  selectedItem.value = item
  metadataVisible.value = true
}

// 获取类型标签
const getTypeLabel = (type) => {
  const typeMap = {
    'entity': 'Entity',
    'edge': 'Edge',
    'episode': 'Episode',
    'community': 'Community',
    'graphiti_entity': 'Graphiti Entity',
    'graphiti_edge': 'Graphiti Edge',
    'cognee_datanode': 'Cognee DataNode',
    'cognee_entity': 'Cognee Entity',
    'cognee_edge': 'Cognee Edge',
    'document_chunk': 'Document Chunk'
  }
  return typeMap[type] || type || '未知类型'
}

// 获取类型颜色
const getTypeColor = (type) => {
  const colorMap = {
    'entity': 'blue',
    'edge': 'cyan',
    'episode': 'purple',
    'community': 'magenta',
    'graphiti_entity': 'blue',
    'graphiti_edge': 'cyan',
    'cognee_datanode': 'green',
    'cognee_entity': 'geekblue',
    'cognee_edge': 'lime',
    'document_chunk': 'orange'
  }
  return colorMap[type] || 'default'
}

// 格式化分数
const formatScore = (score) => {
  if (score === null || score === undefined) return '0.0%'
  return `${Math.min(score, 100).toFixed(1)}%`
}

// 获取分数颜色
const getScoreColor = (score) => {
  if (score >= 80) return '#52c41a'
  if (score >= 60) return '#1890ff'
  if (score >= 40) return '#faad14'
  return '#f5222d'
}

// 获取内容预览
const getContentPreview = (item) => {
  const content = item.content || item.summary || item.name || '(无内容)'
  return content.length > 200 ? content.substring(0, 200) + '...' : content
}
</script>

<style scoped>
.stage2-result-list {
  width: 100%;
}

:deep(.ant-list-item) {
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  margin-bottom: 12px;
  padding: 16px;
  background: #fff;
  transition: all 0.3s;
}

:deep(.ant-list-item:hover) {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.09);
  border-color: #1890ff;
}

:deep(.ant-list-pagination) {
  text-align: center;
  margin-top: 16px;
}
</style>
