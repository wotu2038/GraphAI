<template>
  <a-modal
    v-model:open="visible"
    title="检索设置"
    width="600px"
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <a-form :label-col="{ span: 6 }" :wrapper-col="{ span: 18 }">
      <!-- 检索策略版本标识 -->
      <a-form-item :wrapper-col="{ offset: 6, span: 18 }">
        <a-alert
          message="🚀 检索策略：v4.0"
          description="单路DocumentChunk检索 + 分数阈值过滤 + Graphiti/Cognee知识图谱扩展"
          type="info"
          show-icon
        />
      </a-form-item>
      
      <!-- 检索配置 -->
      <a-divider orientation="left">检索配置</a-divider>
      
      <a-form-item label="Top K（检索数量）">
        <a-slider
          v-model:value="localSettings.topK"
          :min="5"
          :max="50"
          :step="5"
          :marks="{ 5: '5', 20: '20', 50: '50' }"
        />
        <span class="param-value">{{ localSettings.topK }} 条</span>
      </a-form-item>
      
      <a-form-item label="分数阈值">
        <a-slider
          v-model:value="localSettings.minScore"
          :min="0"
          :max="100"
          :step="5"
          :marks="{ 0: '0', 50: '50', 100: '100' }"
        />
        <span class="param-value">{{ localSettings.minScore }} 分</span>
      </a-form-item>
      
      <a-form-item label="Thinking模式" v-if="supportThinking">
        <a-switch v-model:checked="localSettings.useThinking" />
        <span style="margin-left: 8px; color: #999">启用LLM深度思考</span>
      </a-form-item>
      
      <!-- 精筛配置 -->
      <a-divider orientation="left">精筛配置</a-divider>
      
      <a-form-item label="阶段2处理">
        <a-switch v-model:checked="localSettings.enableRefine" />
        <span style="margin-left: 8px; color: #999">使用Graphiti和Cognee进行知识图谱扩展</span>
      </a-form-item>
      
      <!-- LLM配置 -->
      <a-divider orientation="left">LLM配置</a-divider>
      
      <a-form-item label="温度">
        <a-slider
          v-model:value="localSettings.temperature"
          :min="0"
          :max="2"
          :step="0.1"
          :marks="{ 0: '0', 1: '1', 2: '2' }"
        />
        <span class="param-value">{{ localSettings.temperature }}</span>
      </a-form-item>
      
      <!-- 其他配置 -->
      <a-divider orientation="left">其他配置</a-divider>
      
      <a-form-item label="传给LLM的结果数">
        <a-slider
          v-model:value="localSettings.maxResultsForLLM"
          :min="10"
          :max="50"
          :step="5"
          :marks="{ 10: '10', 20: '20', 50: '50' }"
        />
        <span class="param-value">{{ localSettings.maxResultsForLLM }} 个</span>
      </a-form-item>
      
      <!-- Agent模式特有配置 -->
      <template v-if="mode === 'agent'">
        <a-divider orientation="left">Agent配置</a-divider>
        
        <a-form-item label="最大迭代次数">
          <a-input-number
            v-model:value="localSettings.maxIterations"
            :min="1"
            :max="10"
            style="width: 100%"
          />
          <span style="margin-left: 8px; color: #999">文档生成和优化的最大迭代次数</span>
        </a-form-item>
        
        <a-form-item label="质量阈值">
          <a-slider
            v-model:value="localSettings.qualityThreshold"
            :min="0"
            :max="100"
            :step="5"
            :marks="{ 0: '0', 50: '50', 100: '100' }"
          />
          <span class="param-value">{{ localSettings.qualityThreshold }} 分</span>
          <div style="margin-top: 4px; color: #999; font-size: 12px">文档质量达到此分数时停止迭代</div>
        </a-form-item>
      </template>
      
      <!-- 记住选择 -->
      <a-form-item :wrapper-col="{ offset: 6, span: 18 }">
        <a-checkbox v-model:checked="localSettings.remember">
          记住我的选择
        </a-checkbox>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'

const props = defineProps({
  open: {
    type: Boolean,
    default: false
  },
  settings: {
    type: Object,
    default: () => ({})
  },
  supportThinking: {
    type: Boolean,
    default: true
  },
  mode: {
    type: String,
    default: 'conversation', // 'conversation' 或 'agent'
    validator: (val) => ['conversation', 'agent'].includes(val)
  }
})

const emit = defineEmits(['update:open', 'confirm'])

const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// 本地设置副本（v4.0格式）
const localSettings = ref({
  topK: 20,
  minScore: 60,
  useThinking: false,
  enableRefine: true,
  temperature: 0.7,
  maxResultsForLLM: 20,
  // Agent模式特有配置
  maxIterations: 3,
  qualityThreshold: 80,
  remember: true
})

// 从localStorage加载保存的设置
const loadSavedSettings = () => {
  const saved = localStorage.getItem('retrievalSettings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      Object.assign(localSettings.value, parsed)
    } catch (e) {
      console.error('加载保存的设置失败:', e)
    }
  }
}

// 保存设置到localStorage
const saveSettings = () => {
  if (localSettings.value.remember) {
    localStorage.setItem('retrievalSettings', JSON.stringify(localSettings.value))
  }
}

// 初始化时同步props.settings
watch(() => props.settings, (newVal) => {
  if (newVal && Object.keys(newVal).length > 0) {
    Object.assign(localSettings.value, newVal)
  }
}, { immediate: true, deep: true })

// 确认
const handleOk = () => {
  saveSettings()
  emit('confirm', { ...localSettings.value })
  visible.value = false
}

// 取消
const handleCancel = () => {
  visible.value = false
}

onMounted(() => {
  loadSavedSettings()
})
</script>

<style scoped>
.param-value {
  margin-left: 12px;
  color: #1890ff;
  font-weight: 500;
}
</style>

