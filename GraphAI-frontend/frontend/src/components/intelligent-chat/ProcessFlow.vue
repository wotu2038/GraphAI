<template>
  <div class="process-flow">
    <a-card title="处理流程" size="small" style="margin-bottom: 24px">
      <div class="flow-steps">
        <div 
          v-for="(step, index) in steps" 
          :key="index"
          class="flow-step"
          :class="{ 
            'active': step.status === 'active',
            'completed': step.status === 'completed',
            'pending': step.status === 'pending'
          }"
        >
          <div class="step-icon">
            <CheckCircleOutlined v-if="step.status === 'completed'" class="icon-completed" />
            <LoadingOutlined v-else-if="step.status === 'active'" class="icon-active" spin />
            <ClockCircleOutlined v-else class="icon-pending" />
          </div>
          <div class="step-content">
            <div class="step-title">{{ step.title }}</div>
            <div class="step-desc">{{ step.description }}</div>
          </div>
          <div v-if="index < steps.length - 1" class="step-arrow">
            <ArrowRightOutlined />
          </div>
        </div>
      </div>
    </a-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CheckCircleOutlined, LoadingOutlined, ClockCircleOutlined, ArrowRightOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  currentStep: {
    type: String,
    default: 'document-parse'
  },
  stepsData: {
    type: Object,
    default: () => ({})
  }
})

const defaultSteps = [
  {
    key: 'document-parse',
    title: '文档解析',
    description: '解析文档内容',
    status: 'pending'
  },
  {
    key: 'graphiti',
    title: 'Graphiti文档级处理',
    description: '创建文档级Episode',
    status: 'pending'
  },
  {
    key: 'cognee',
    title: 'Cognee章节级处理',
    description: '构建章节级知识图谱',
    status: 'pending'
  }
]

const steps = computed(() => {
  return defaultSteps.map(step => {
    // 如果提供了自定义状态，使用自定义状态
    if (props.stepsData[step.key]) {
      return {
        ...step,
        status: props.stepsData[step.key].status || step.status,
        description: props.stepsData[step.key].description || step.description
      }
    }
    
    // 根据当前步骤自动计算状态
    const stepIndex = defaultSteps.findIndex(s => s.key === step.key)
    const currentIndex = defaultSteps.findIndex(s => s.key === props.currentStep)
    
    if (stepIndex < currentIndex) {
      return { ...step, status: 'completed' }
    } else if (stepIndex === currentIndex) {
      return { ...step, status: 'active' }
    } else {
      return { ...step, status: 'pending' }
    }
  })
})
</script>

<style scoped>
.process-flow {
  width: 100%;
}

.flow-steps {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  flex-wrap: wrap;
  gap: 8px;
}

.flow-step {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 150px;
  position: relative;
}

.step-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  margin-right: 12px;
  flex-shrink: 0;
}

.step-icon .icon-completed {
  color: #52c41a;
  font-size: 24px;
}

.step-icon .icon-active {
  color: #1890ff;
  font-size: 24px;
}

.step-icon .icon-pending {
  color: #d9d9d9;
  font-size: 24px;
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-title {
  font-weight: 500;
  font-size: 14px;
  margin-bottom: 4px;
  color: #262626;
}

.step-desc {
  font-size: 12px;
  color: #8c8c8c;
}

.flow-step.completed .step-title {
  color: #52c41a;
}

.flow-step.active .step-title {
  color: #1890ff;
}

.flow-step.pending .step-title {
  color: #bfbfbf;
}

.step-arrow {
  margin: 0 8px;
  color: #d9d9d9;
  font-size: 16px;
  flex-shrink: 0;
}

.flow-step.completed + .step-arrow {
  color: #52c41a;
}

@media (max-width: 1200px) {
  .flow-steps {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .flow-step {
    width: 100%;
    margin-bottom: 16px;
  }
  
  .step-arrow {
    display: none;
  }
}
</style>
