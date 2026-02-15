<template>
  <div class="cognee-tab">
    <a-form layout="vertical" class="cognee-tab-form">
      <!-- 顶部操作栏 -->
      <div style="display: flex; justify-content: flex-end; margin-bottom: 24px">
        <a-space>
          <a-button 
            type="primary" 
            @click="handleExecute" 
            :loading="executing"
            :disabled="!selectedDocumentId || executing || splitting || !selectedDoc?.chunks_path"
          >
            <template #icon><PlayCircleOutlined /></template>
            执行Cognee
          </a-button>
          
          <a-button @click="handleClear" :disabled="!executionResult && !executing && !graphData">
            清空结果
          </a-button>
    
          <a-button 
            @click="handleViewGraphModal" 
            :disabled="!selectedDocumentId || executing"
            v-if="selectedDoc?.document_id"
          >
            <template #icon><ShareAltOutlined /></template>
            加载图谱
          </a-button>

          <a-button 
            type="danger"
            @click="handleDeleteGraph" 
            :disabled="!selectedDocumentId || executing"
            v-if="selectedDoc?.document_id"
          >
            <template #icon><DeleteOutlined /></template>
            删除图谱
          </a-button>
        </a-space>
      </div>

      <!-- 独立配置区域 (外置) -->
      <div class="base-config-section" style="margin-bottom: 24px">
      <a-form-item label="选择文档">
        <a-select
          v-model:value="selectedDocumentId"
            placeholder="请选择要处理的文档"
          style="width: 100%"
            size="large"
          :loading="loadingDocuments"
          :disabled="loadingDocuments || executing || splitting"
          @change="handleDocumentChange"
          allow-clear
        >
          <a-select-option
            v-for="doc in documents"
            :key="doc.id"
            :value="doc.id"
          >
              {{ doc.file_name }} (ID: {{ doc.id }})
          </a-select-option>
        </a-select>
        <div v-if="documents.length === 0 && !loadingDocuments" style="color: #ff4d4f; font-size: 12px; margin-top: 4px">
          没有可用的文档，请先完成文档解析
        </div>
      </a-form-item>

        <a-form-item label="LLM配置">
          <a-space>
            <a-select 
              v-model:value="provider" 
              :disabled="executing || splitting"
              style="width: 150px"
            >
              <a-select-option value="qianwen">千问</a-select-option>
              <a-select-option value="deepseek">DeepSeek</a-select-option>
              <a-select-option value="kimi">Kimi</a-select-option>
              <a-select-option value="glm">GLM</a-select-option>
            </a-select>
            <div style="display: flex; align-items: center; margin-left: 24px">
              <span style="margin-right: 12px; color: #999">温度: {{ temperature }}</span>
              <a-slider
                v-model:value="temperature" 
                :min="0"
                :max="1" 
                :step="0.1"
                style="width: 150px"
                :disabled="executing || splitting"
              />
            </div>
          </a-space>
        </a-form-item>
      </div>

      <!-- 配置卡片区域 -->
      <a-row :gutter="24">
        <!-- 分块配置 -->
        <a-col :span="24">
          <a-card size="small" :bordered="true" style="margin-bottom: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05)">
            <template #title>
              <div style="display: flex; align-items: center; gap: 8px">
                <FileTextOutlined style="color: #1890ff" />
                <span style="font-weight: 600">分块配置</span>
              </div>
            </template>
            <template #extra>
              <a-space>
                 <span v-if="!selectedDoc?.chunks_path && selectedDocumentId" style="color: #ff4d4f; font-size: 12px">
                    尚未分块
                 </span>
                 <span v-else-if="selectedDoc?.chunks_path" style="color: #52c41a; font-size: 12px">
                    <CheckCircleOutlined /> 已分块 ({{ chunksData?.chunks?.length || 0 }} 章节)
                 </span>
                 <a-button 
                    type="default" 
                    size="small"
                    @click="handleSplitDocument" 
                    :loading="splitting"
                    :disabled="!selectedDocumentId || splitting || executing"
                  >
                    <template #icon><FileTextOutlined /></template>
                    {{ selectedDoc?.chunks_path ? '重新分块' : '执行分块' }}
                  </a-button>
              </a-space>
            </template>
            
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="分块模式" style="margin-bottom: 0">
        <a-radio-group v-model:value="chunkingMode" :disabled="executing || splitting">
          <a-radio value="smart">智能分块</a-radio>
          <a-radio value="manual">手动分块</a-radio>
        </a-radio-group>
      </a-form-item>
              </a-col>
              
              <a-col :span="12">
                <a-form-item label="Max Tokens" style="margin-bottom: 0">
                  <a-input-number
                    v-model:value="maxTokensPerSection"
                    :min="1000"
                    :max="20000"
                    :step="1000"
                    style="width: 100%"
                    :disabled="executing || splitting"
                  />
                </a-form-item>
              </a-col>

              <a-col :span="12" v-if="chunkingMode === 'manual'" style="margin-top: 16px">
                <a-form-item label="分块策略" style="margin-bottom: 0">
        <a-select
          v-model:value="chunkStrategy"
          placeholder="选择分块策略"
                    style="width: 100%"
          :disabled="executing || splitting"
        >
          <a-select-option value="level_1">按一级标题（推荐）</a-select-option>
          <a-select-option value="level_2">按二级标题</a-select-option>
          <a-select-option value="level_3">按三级标题</a-select-option>
          <a-select-option value="fixed_token">按固定Token</a-select-option>
        </a-select>
      </a-form-item>
              </a-col>
            </a-row>
          </a-card>
        </a-col>

        <!-- Cognify 模板配置 -->
        <a-col :span="12">
          <a-card size="small" :bordered="true" style="margin-bottom: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05)">
            <template #title>
              <div style="display: flex; align-items: center; gap: 8px">
                <ShareAltOutlined style="color: #fa8c16" />
                <span style="font-weight: 600">Cognify 模板 (实体/关系)</span>
        </div>
            </template>
            <template #extra>
              <a-radio-group v-model:value="cognifyTemplateMode" button-style="solid" size="small">
                <a-radio-button value="llm_generate">LLM自动生成</a-radio-button>
                <a-radio-button value="json_config">JSON手动配置</a-radio-button>
          </a-radio-group>
            </template>

            <div v-if="cognifyTemplateMode === 'json_config'">
              <div style="background: #f5f5f5; padding: 8px 12px; border: 1px solid #d9d9d9; border-bottom: none; border-radius: 6px 6px 0 0; display: flex; justify-content: space-between; align-items: center">
                <span style="font-size: 12px; color: #595959"><CodeOutlined /> JSON 编辑器</span>
                <a-space size="small">
                  <a-button type="link" size="small" @click="loadCognifyExample" style="padding: 0">加载示例</a-button>
                  <a-button type="link" size="small" @click="validateCognifyJson" style="padding: 0">验证</a-button>
                  <a-button type="link" size="small" @click="clearCognifyJson" style="padding: 0; color: #ff4d4f">清空</a-button>
            </a-space>
              </div>
            <a-textarea
              v-model:value="cognifyTemplateConfigJson"
                placeholder='{"entity_types": {...}, "edge_types": {...}, ...}'
              :rows="8"
                :disabled="executing"
                style="border-radius: 0 0 6px 6px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; background: #fafafa"
              :class="{ 'error-border': cognifyJsonError }"
            />
              <div v-if="cognifyJsonError" style="color: #ff4d4f; font-size: 12px; margin-top: 4px">{{ cognifyJsonError }}</div>
            </div>
            <div v-else>
              <!-- 模版类型选择 -->
              <a-form-item label="模版类型" style="margin-bottom: 16px">
                <a-select v-model:value="cognifyTemplateType" style="width: 100%" :disabled="executing">
                  <a-select-option value="default">默认模版</a-select-option>
                </a-select>
      </a-form-item>

              <!-- System Prompt -->
              <a-form-item style="margin-bottom: 16px">
                <template #label>
                  <div style="display: flex; justify-content: space-between; width: 100%">
                    <span>System Prompt</span>
                    <a-button type="link" size="small" @click="resetCognifySystemPrompt" style="padding: 0">恢复默认</a-button>
            </div>
                </template>
            <a-textarea
                  v-model:value="cognifySystemPrompt" 
                  :rows="4" 
                  placeholder="System Prompt"
                  :disabled="executing"
                  style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
                />
      </a-form-item>

              <!-- User Prompt 模板 -->
              <a-form-item style="margin-bottom: 16px">
                <template #label>
                  <div style="display: flex; justify-content: space-between; width: 100%">
                    <span>User Prompt</span>
        <a-space>
                      <a-button type="link" size="small" @click="resetCognifyUserPrompt" style="padding: 0">恢复默认</a-button>
                      <a-button type="link" size="small" @click="previewCognifyFullPrompt" :disabled="!selectedDocumentId" style="padding: 0">预览完整</a-button>
            </a-space>
        </div>
                </template>
            <a-textarea
                  v-model:value="cognifyUserPromptTemplate" 
                  :rows="8" 
                  placeholder="User Prompt 模板（支持占位符: {section_title}, {section_content}）"
                  :disabled="executing"
                  style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
                />
      </a-form-item>

              <!-- 模板 JSON 内容 -->
              <div style="margin-top: 16px; border: 1px solid #d9d9d9; border-radius: 6px; overflow: hidden">
                <div style="background: #f5f5f5; padding: 8px 12px; border-bottom: 1px solid #d9d9d9; display: flex; justify-content: space-between; align-items: center">
                  <div style="font-size: 12px; color: #595959; font-weight: 500">
                    <CodeOutlined /> 模板 JSON 内容
                    <span style="margin-left: 8px" :style="{ color: cognifyGeneratedJson ? '#52c41a' : '#999' }">
                      {{ cognifyGeneratedJson ? '● 已生成' : '○ 待生成' }}
                    </span>
                  </div>
        <a-space>
                    <a-button type="primary" size="small" @click="handlePreviewCognifyTemplate" :loading="generatingCognifyTemplate" :disabled="!selectedDocumentId || executing || splitting || !selectedDoc?.chunks_path">
                      <ThunderboltOutlined /> LLM生成
          </a-button>
                    <a-button size="small" @click="handlePreviewCustomPrompt" :disabled="!cognifyGeneratedJson || executing">预览custom_prompt</a-button>
                    <a-button size="small" @click="handleResetCognifyTemplate" :disabled="!cognifyGeneratedJson">重置</a-button>
        </a-space>
        </div>
                <a-textarea
                  v-model:value="cognifyGeneratedJson"
                  placeholder="配置完成后点击「LLM生成」..."
                  :rows="8"
                  style="border: none; border-radius: 0; font-family: 'SFMono-Regular', Consolas, monospace; background: #fafafa; font-size: 13px"
                  :disabled="executing"
                />
                        </div>
                            </div>
    </a-card>
        </a-col>

        <!-- Memify 模板配置 -->
        <a-col :span="12">
          <a-card size="small" :bordered="true" style="margin-bottom: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05)">
            <template #title>
              <div style="display: flex; align-items: center; gap: 8px">
                <ThunderboltOutlined style="color: #722ed1" />
                <span style="font-weight: 600">Memify 模板 (提取/增强)</span>
                    </div>
                  </template>
      <template #extra>
              <a-radio-group v-model:value="memifyTemplateMode" button-style="solid" size="small">
                <a-radio-button value="llm_generate">LLM自动生成</a-radio-button>
                <a-radio-button value="json_config">JSON手动配置</a-radio-button>
              </a-radio-group>
      </template>
      
            <div v-if="memifyTemplateMode === 'json_config'">
              <!-- 规则集合名称 -->
              <a-form-item label="规则集合名称" style="margin-bottom: 16px">
                <a-input 
                  v-model:value="memifyRulesNodesetName" 
                  placeholder="例如: default_rules, frontend_rules, backend_rules"
                  :disabled="executing"
                />
                <div style="font-size: 12px; color: #999; margin-top: 4px">
                  用于组织和分类规则，类似于文件夹名称
              </div>
              </a-form-item>

              <!-- 规则列表（手动配置） -->
              <a-form-item label="规则列表" style="margin-bottom: 16px">
                <a-textarea 
                  v-model:value="memifyRules" 
                  placeholder="每行一条规则，例如：&#10;所有接口必须使用类型注解&#10;数据库操作必须使用事务&#10;错误处理必须包含详细日志"
                  :rows="6"
                  :disabled="executing"
                  style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
                />
                <div style="font-size: 12px; color: #999; margin-top: 4px">
                  手动配置的规则列表（每行一条），留空则通过LLM自动提取
              </div>
              </a-form-item>
              
              <!-- 节点类型 -->
              <a-form-item label="节点类型" style="margin-bottom: 16px">
                <a-input 
                  v-model:value="memifyNodeTypes" 
                  placeholder="例如: DocumentChunk 或 DocumentChunk,Entity"
                  :disabled="executing"
                />
                <div style="font-size: 12px; color: #999; margin-top: 4px">
                  提取哪些类型的节点（逗号分隔），用于extraction阶段
                        </div>
              </a-form-item>

              <!-- 最大跳数 -->
              <a-form-item label="最大跳数" style="margin-bottom: 16px">
                <a-input-number 
                  v-model:value="memifyMaxHops" 
                  :min="1"
                  :max="10"
                  :disabled="executing"
                  style="width: 100%"
                />
                <div style="font-size: 12px; color: #999; margin-top: 4px">
                  图遍历的跳数，影响提取深度（1跳=直接关联，2跳=间接关联）
                            </div>
              </a-form-item>
                      
              <!-- 最大块数 -->
              <a-form-item label="最大块数" style="margin-bottom: 16px">
                <a-input-number 
                  v-model:value="memifyMaxChunks" 
                  :min="1"
                  :max="1000"
                  :disabled="executing"
                  style="width: 100%"
                />
                <div style="font-size: 12px; color: #999; margin-top: 4px">
                  最多处理多少个chunks，用于限制处理范围
                        </div>
              </a-form-item>
                                  </div>
            <div v-else>
              <!-- 模版类型选择 -->
              <a-form-item label="模版类型" style="margin-bottom: 16px">
                <a-select v-model:value="memifyTemplateType" style="width: 100%" :disabled="executing" @change="handleMemifyTemplateTypeChange">
                  <a-select-option value="default">默认模版</a-select-option>
                </a-select>
              </a-form-item>

              <!-- System Prompt -->
              <a-form-item style="margin-bottom: 16px">
                <template #label>
                  <div style="display: flex; justify-content: space-between; width: 100%">
                    <span>System Prompt</span>
                    <a-button type="link" size="small" @click="resetMemifySystemPrompt" style="padding: 0">恢复默认</a-button>
                    </div>
                  </template>
                <a-textarea 
                  v-model:value="memifySystemPrompt" 
                  :rows="4" 
                  placeholder="System Prompt（用于enrichment任务）"
                  :disabled="executing"
                  style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
                />
              </a-form-item>

              <!-- User Prompt 模板 -->
              <a-form-item style="margin-bottom: 16px">
                <template #label>
                  <div style="display: flex; justify-content: space-between; width: 100%">
                    <span>User Prompt</span>
                    <a-space>
                      <a-button type="link" size="small" @click="resetMemifyUserPrompt" style="padding: 0">恢复默认</a-button>
                      <a-button type="link" size="small" @click="previewMemifyFullPrompt" :disabled="!selectedDocumentId" style="padding: 0">预览完整</a-button>
                    </a-space>
                    </div>
                  </template>
                <a-textarea
                  v-model:value="memifyUserPromptTemplate" 
                  :rows="8" 
                  placeholder="User Prompt 模板（支持占位符: {document_name}, {section_title}, {section_content}等）"
                  :disabled="executing"
                  style="font-family: 'SFMono-Regular', Consolas, monospace; font-size: 13px"
                />
              </a-form-item>

              <!-- 规则列表生成区域 -->
              <div style="margin-top: 16px; border: 1px solid #d9d9d9; border-radius: 6px; overflow: hidden">
                <div style="background: #f5f5f5; padding: 8px 12px; border-bottom: 1px solid #d9d9d9; display: flex; justify-content: space-between; align-items: center">
                  <div style="font-size: 12px; color: #595959; font-weight: 500">
                    <CodeOutlined /> 规则列表
                    <span style="margin-left: 8px" :style="{ color: memifyGeneratedRules && memifyGeneratedRules.length > 0 ? '#52c41a' : '#999' }">
                      {{ memifyGeneratedRules && memifyGeneratedRules.length > 0 ? `● 已生成 (${memifyGeneratedRules.length}条)` : '○ 待生成' }}
                    </span>
              </div>
        <a-space>
                    <a-button type="primary" size="small" @click="handlePreviewMemifyRules" :loading="generatingMemifyRules" :disabled="!selectedDocumentId || executing || splitting || !selectedDoc?.chunks_path">
                      <ThunderboltOutlined /> LLM生成
          </a-button>
                    <a-button size="small" @click="handleResetMemifyRules" :disabled="!memifyGeneratedRules || memifyGeneratedRules.length === 0">重置</a-button>
                    <a-button size="small" @click="handleApplyMemifyRules" :disabled="!memifyGeneratedRules || memifyGeneratedRules.length === 0">应用到JSON配置</a-button>
        </a-space>
                </div>
                <a-textarea
                  v-model:value="memifyGeneratedRulesText"
                  placeholder="配置完成后点击「LLM生成」..."
                  :rows="6"
                  style="border: none; border-radius: 0; font-family: 'SFMono-Regular', Consolas, monospace; background: #fafafa; font-size: 13px"
                  :disabled="executing"
                />
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-form>

    <!-- 结果区域 -->
    <div v-if="executing" style="text-align: center; padding: 40px; background: white; border-radius: 8px; margin-bottom: 24px; border: 1px solid #f0f0f0">
      <a-spin size="large">
        <template #indicator>
          <LoadingOutlined style="font-size: 24px" spin />
        </template>
      </a-spin>
      <div style="margin-top: 12px; color: #999">
        {{ executionStatus }}
      </div>
    </div>

    <!-- 整合结果展示 -->
    <div v-if="executionResult || (graphData && graphData.nodes && graphData.nodes.length > 0) || (chunksData && chunksData.chunks)">
      
      <!-- 1. 执行结果摘要 -->
      <a-card v-if="executionResult" size="small" title="执行结果摘要" style="margin-bottom: 16px; border-radius: 8px">
        <a-descriptions :column="3" bordered size="small">
          <a-descriptions-item label="节点数量">
            <a-tag color="blue">{{ executionResult.node_count || 0 }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="关系数量">
            <a-tag color="cyan">{{ executionResult.relationship_count || 0 }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="执行状态">
            <a-tag color="green">成功</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="Dataset" :span="2">
            <span style="font-family: monospace; font-size: 12px">{{ executionResult.dataset_name || '-' }}</span>
          </a-descriptions-item>
          <a-descriptions-item label="Group ID">
            <span style="font-family: monospace; font-size: 12px">{{ executionResult.group_id || '-' }}</span>
          </a-descriptions-item>
        </a-descriptions>
      </a-card>

      <!-- 2. 结果 Tab 页签 -->
      <a-card size="small" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08)">
        <a-tabs default-active-key="graph" type="card">
          <!-- Tab 1: 知识图谱 -->
          <a-tab-pane key="graph" tab="知识图谱">
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
                <span>{{ loadingGraph ? '正在加载图谱数据...' : '暂无图谱数据，请先执行 Cognee 处理' }}</span>
              </div>
            </div>
          </a-tab-pane>

          <!-- Tab 2: 分块详情 -->
          <a-tab-pane key="chunks" tab="分块详情" v-if="chunksData && chunksData.chunks">
             <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
                <div>
                  <span style="font-weight: 500">共 {{ chunksData.chunks.length }} 个章节</span>
                  <a-divider type="vertical" />
                  <span style="color: #999">平均长度: {{ Math.round(chunksData.chunks.reduce((acc, cur) => acc + (cur.content?.length || 0), 0) / chunksData.chunks.length) }} 字符</span>
                </div>
                <a-space>
                  <a-button size="small" @click="chunksCollapseActiveKey = chunksData.chunks.map((_, idx) => `chunk_${idx}`)">展开全部</a-button>
                  <a-button size="small" @click="chunksCollapseActiveKey = []">收起全部</a-button>
                </a-space>
             </div>
             
             <a-spin :spinning="loadingChunks">
                <a-collapse v-model:activeKey="chunksCollapseActiveKey" :bordered="false" style="background: transparent">
                  <a-collapse-panel 
                    v-for="(chunk, idx) in chunksData.chunks" 
                    :key="`chunk_${idx}`"
                    :header="`${idx + 1}. ${chunk.title || `Chunk ${idx + 1}`}`"
                    style="background: #fff; margin-bottom: 8px; border: 1px solid #e8e8e8; border-radius: 4px"
                  >
                    <a-descriptions :column="2" size="small" bordered style="margin-bottom: 16px">
                      <a-descriptions-item label="Token数">{{ chunk.token_count || 0 }}</a-descriptions-item>
                      <a-descriptions-item label="长度">{{ chunk.content ? chunk.content.length : 0 }} 字符</a-descriptions-item>
                    </a-descriptions>
                    
                    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0">
                      <div style="font-size: 12px; font-weight: 500; margin-bottom: 8px; color: #1890ff">
                        <InfoCircleOutlined style="margin-right: 4px" /> Cognee 关联
                      </div>
                      
                      <div v-if="getChunkMapping(idx) && getChunkMapping(idx).actual">
                         <a-tag color="green">已关联</a-tag>
                         <span style="font-size: 12px; color: #666; margin-left: 8px">
                           关联到 Node: {{ getChunkMapping(idx).actual.text_document.name || 'Unknown' }}
                         </span>
                      </div>
                      <div v-else>
                         <a-tag color="blue">预期关联</a-tag>
                         <span style="font-size: 12px; color: #666; margin-left: 8px">将创建 TextDocument 节点存储此内容</span>
                      </div>
                    </div>

                    <div style="margin-top: 12px">
                      <div style="background: #fafafa; padding: 12px; border-radius: 4px; border: 1px solid #f0f0f0; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px">
                        {{ chunk.content }}
                      </div>
                    </div>
                  </a-collapse-panel>
                </a-collapse>
             </a-spin>
          </a-tab-pane>

          <!-- Tab 3: 处理步骤 -->
          <a-tab-pane key="steps" tab="处理步骤" v-if="executionResult && executionResult.processing_steps">
            <div style="padding: 24px">
        <a-timeline>
          <a-timeline-item 
            v-for="step in executionResult.processing_steps" 
            :key="step.step"
            :color="getStepColor(step.status)"
          >
            <template #dot>
              <CheckCircleOutlined v-if="step.status === 'completed'" style="font-size: 16px; color: #52c41a" />
              <CloseCircleOutlined v-else-if="step.status === 'failed'" style="font-size: 16px; color: #ff4d4f" />
              <MinusCircleOutlined v-else-if="step.status === 'skipped'" style="font-size: 16px; color: #999" />
              <LoadingOutlined v-else style="font-size: 16px; color: #1890ff" spin />
            </template>
                  <div style="margin-bottom: 4px; font-weight: 500">{{ step.name }}</div>
                  <div style="color: #666; font-size: 13px; margin-bottom: 8px">{{ step.message }}</div>
                  <a-collapse v-if="step.details" :bordered="false" style="background: #fafafa" size="small">
                    <a-collapse-panel key="1" header="详细信息">
                      <pre style="font-size: 11px; margin: 0">{{ JSON.stringify(step.details, null, 2) }}</pre>
                </a-collapse-panel>
              </a-collapse>
          </a-timeline-item>
        </a-timeline>
            </div>
          </a-tab-pane>

          <!-- Tab 4: 联动状态 -->
          <a-tab-pane key="linkage" tab="联动状态" v-if="executionResult && (executionResult.graphiti_reference || executionResult.graphiti_linkage)">
             <div style="padding: 16px">
        <a-alert 
          :type="getLinkageStatus().type"
          :message="getLinkageStatus().message"
          show-icon
          style="margin-bottom: 16px"
                />
                
                <a-descriptions :column="1" bordered size="small">
                  <a-descriptions-item label="联动关系类型">
                    (TextDocument)-[:RELATES_TO]->(Episode)
              </a-descriptions-item>
                  <a-descriptions-item label="关联 Episode UUID">
                    <span style="font-family: monospace">{{ getGraphitiLinkageData().episode_uuid || '-' }}</span>
              </a-descriptions-item>
                  <a-descriptions-item label="一致性检查">
                     <a-tag :color="getDataConsistency().doc_id_match ? 'green' : 'red'">Doc ID: {{ getDataConsistency().doc_id_match ? '匹配' : '不匹配' }}</a-tag>
                     <a-tag :color="getDataConsistency().group_id_match ? 'green' : 'red'">Group ID: {{ getDataConsistency().group_id_match ? '匹配' : '不匹配' }}</a-tag>
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </a-tab-pane>
          
          <!-- Tab 5: 三层结构 -->
          <a-tab-pane key="structure" tab="三层结构" v-if="executionResult && executionResult.cognee_structure">
             <div style="padding: 16px">
                <a-tree
                  :tree-data="[
                    {
                      title: `DataSet: ${executionResult.cognee_structure.dataset.name}`,
                      key: 'dataset',
                      children: [
                        {
                          title: `TextDocument (${executionResult.cognee_structure.text_documents.count} 个)`,
                          key: 'text_docs'
                        },
                        {
                          title: `DocumentChunk (${executionResult.cognee_structure.document_chunks.count} 个)`,
                          key: 'chunks'
                        }
                      ]
                    }
                  ]"
                  default-expand-all
                />
            </div>
          </a-tab-pane>
        </a-tabs>
      </a-card>
    </div>

    <!-- 空状态 -->
    <a-empty
      v-else
      description="请选择文档并点击执行按钮开始处理"
      style="margin: 60px 0"
    >
      <template #image>
        <InboxOutlined style="font-size: 64px; color: #d9d9d9" />
      </template>
    </a-empty>

    <!-- 详情展示 (抽屉) -->
    <a-drawer v-model:open="nodeDrawerVisible" title="节点属性" :width="400">
      <div v-if="selectedNode">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="名称">{{ selectedNode.properties?.name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="标签">
              <a-tag v-for="label in selectedNode.labels" :key="label">{{ label }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="属性">
            <pre style="font-size: 11px; overflow-x: auto">{{ JSON.stringify(selectedNode.properties, null, 2) }}</pre>
          </a-descriptions-item>
        </a-descriptions>
      </div>
    </a-drawer>

    <a-drawer v-model:open="edgeDrawerVisible" title="关系属性" :width="400">
      <div v-if="selectedEdge">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="类型">{{ selectedEdge.type }}</a-descriptions-item>
          <a-descriptions-item label="源节点">{{ selectedEdge.source }}</a-descriptions-item>
          <a-descriptions-item label="目标节点">{{ selectedEdge.target }}</a-descriptions-item>
          <a-descriptions-item label="属性">
            <pre style="font-size: 11px; overflow-x: auto">{{ JSON.stringify(selectedEdge.properties, null, 2) }}</pre>
          </a-descriptions-item>
        </a-descriptions>
      </div>
    </a-drawer>

    <!-- 图谱全屏 Modal -->
    <a-modal
      v-model:open="graphModalVisible"
      title="Cognee知识图谱 (全屏)"
      :width="1200"
      :footer="null"
      @cancel="handleGraphModalClose"
    >
      <div style="height: 700px; border: 1px solid #d9d9d9; border-radius: 4px">
        <GraphVisualization 
          v-if="viewGraphData"
          :data="viewGraphData"
          @nodeClick="handleNodeClick"
          @edgeClick="handleEdgeClick"
        />
      </div>
    </a-modal>

    <a-modal v-model:open="graphNotCreatedModalVisible" title="提示" :footer="null">
      <a-result status="warning" title="图谱未创建" sub-title="该文档尚未执行Cognee章节级处理，请先执行处理。">
          <template #extra>
          <a-button type="primary" @click="graphNotCreatedModalVisible = false">确定</a-button>
          </template>
        </a-result>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { 
  PlayCircleOutlined, 
  LoadingOutlined, 
  FileTextOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined, 
  MinusCircleOutlined, 
  InfoCircleOutlined,
  ShareAltOutlined,
  ThunderboltOutlined,
  CodeOutlined,
  InboxOutlined,
  DeleteOutlined
} from '@ant-design/icons-vue'
import GraphVisualization from '../GraphVisualization.vue'
import { getDocumentUploadList, splitDocument, getChunks } from '../../api/documentUpload'
import { step2CogneeBuild, getCogneeGraph, getChunksCogneeMapping, previewCognifyTemplate, previewMemifyPrompt, previewMemifyRules, deleteCogneeGraph } from '../../api/intelligentChat'

const documents = ref([])
const loadingDocuments = ref(false)
const selectedDocumentId = ref(null)
const provider = ref('qianwen')
const temperature = ref(0.7)
const executing = ref(false)
const executionStatus = ref('')
const executionResult = ref(null)
const graphData = ref(null)

// Chunks相关
const chunksData = ref(null)
const loadingChunks = ref(false)
const chunksCollapseActiveKey = ref([])
const chunksCogneeMapping = ref(null)
const loadingMapping = ref(false)

// 分块相关
const chunkingMode = ref('smart')
const chunkStrategy = ref('level_1')
const maxTokensPerSection = ref(8000)
const splitting = ref(false)
const splitResult = ref(null)

// 模板配置相关
const cognifyTemplateMode = ref('llm_generate')
const cognifyTemplateType = ref('default')
const cognifySystemPrompt = ref('')
const cognifyUserPromptTemplate = ref('')
const cognifyGeneratedJson = ref('')
const generatingCognifyTemplate = ref(false)
const cognifyTemplateConfigJson = ref('')
const cognifyJsonError = ref('')
const memifyTemplateMode = ref('llm_generate')
const memifyTemplateType = ref('default')
const memifySystemPrompt = ref('')
const memifyUserPromptTemplate = ref('')
const memifyTemplateConfigJson = ref('')
const memifyJsonError = ref('')

// Memify JSON配置模式的独立参数
const memifyRulesNodesetName = ref('default_rules')
const memifyRules = ref('') // 手动配置的规则列表（每行一条规则）
const memifyNodeTypes = ref('DocumentChunk') // 节点类型（逗号分隔）
const memifyMaxHops = ref(1)
const memifyMaxChunks = ref(100)

// Memify规则列表生成相关
const generatingMemifyRules = ref(false) // LLM生成规则列表的加载状态
const memifyGeneratedRules = ref([]) // LLM生成的规则列表（数组）
const memifyGeneratedRulesText = ref('') // LLM生成的规则列表（文本，每行一条）

// Cognify 默认提示词
const DEFAULT_COGNIFY_SYSTEM_PROMPT = '你是一个专业的知识图谱模板生成专家，擅长从章节内容中提取实体和关系结构，生成规范的模板配置。'

const DEFAULT_COGNIFY_USER_PROMPT_TEMPLATE = `你是一个知识图谱模板生成专家。请分析以下章节内容，生成适合的实体和关系模板配置。

章节标题：{section_title}

章节内容：
{section_content}

请根据章节内容，识别并生成：

1. **实体类型（entity_types）**：
   - 识别章节中的核心实体
   - 为每个实体类型定义：
     * **description**（必需）：实体类型的描述，说明这个实体类型代表什么（例如："角色实体，代表系统中的各种角色和岗位"）
     * **fields**：字段定义（字段类型、是否必需、描述）
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, name, group_id, labels, created_at, name_embedding, summary, attributes
   - 请使用其他字段名，例如：entity_name, title, description, status 等

2. **关系类型（edge_types）**：
   - 识别实体之间的关系类型
   - 为每个关系类型定义：
     * **description**（必需）：关系类型的描述，说明这个关系类型代表什么（例如："审批关系，表示一个实体对另一个实体的审批行为"）
     * **fields**：字段定义
   - ⚠️ **重要：以下字段是系统保留字段，不能使用**：
     - uuid, source_node_uuid, target_node_uuid, name, fact, attributes

3. **关系映射（edge_type_map）**：
   - 定义哪些实体之间可以使用哪些关系
   - 格式：{"SourceEntity -> TargetEntity": ["EdgeName1", "EdgeName2"]}

返回标准JSON格式：
{
  "entity_types": {
    "EntityName": {
      "description": "实体类型的描述",
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
      "description": "关系类型的描述",
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

const cognifyExampleTemplate = {
  entity_types: {
    "Person": "人物实体，包括姓名、职位、角色等信息",
    "Technology": "技术实体，包括技术名称、版本、描述等信息",
    "Concept": "概念实体，代表理论、方法、思想等"
  },
  edge_types: {
    "CREATED_BY": "创建关系，表示技术由人物创建",
    "USES": "使用关系，表示技术使用其他技术",
    "RELATED_TO": "相关关系，表示概念之间的关联"
  },
  edge_type_map: {
    "Person": ["CREATED_BY", "RELATED_TO"],
    "Technology": ["USES", "CREATED_BY", "RELATED_TO"],
    "Concept": ["RELATED_TO"]
  }
}

const memifyExampleTemplate = {
  extraction: {
    enabled: true,
    task: "extract_subgraph_chunks",
    node_types: ["DocumentChunk"],
    max_hops: 1,
    max_chunks: 100
  },
  enrichment: {
    enabled: true,
    task: "add_rule_associations",
    rules_nodeset_name: "default_rules",
    user_prompt_location: "coding_rule_association_agent_user.txt",
    system_prompt_location: "coding_rule_association_agent_system.txt"
  }
}

// Memify 默认提示词
const DEFAULT_MEMIFY_SYSTEM_PROMPT = '你是一个专业的规则关联专家，擅长从对话内容中提取和关联编码规则。'

const DEFAULT_MEMIFY_USER_PROMPT_TEMPLATE = `分析以下文档内容，提取编码规则和最佳实践。

文档名称：{document_name}

文档内容：
{document_content}

请从文档内容中提取编码规则和最佳实践，每条规则应该：
1. 清晰明确，具有可操作性
2. 基于文档中的实际内容
3. 适用于编码实践

返回规则列表，每条规则一行。`

const loadCognifyExample = () => {
  cognifyTemplateConfigJson.value = JSON.stringify(cognifyExampleTemplate, null, 2)
  cognifyJsonError.value = ''
  message.success('已加载Cognify示例模板')
}

const loadMemifyDefaults = () => {
  // 加载默认值
  memifyRulesNodesetName.value = 'default_rules'
  memifyRules.value = ''
  memifyNodeTypes.value = 'DocumentChunk'
  memifyMaxHops.value = 1
  memifyMaxChunks.value = 100
  message.success('已加载Memify默认配置')
}

const validateCognifyJson = () => {
  if (!cognifyTemplateConfigJson.value.trim()) {
    cognifyJsonError.value = 'JSON配置不能为空'
    return false
  }
  try {
    const config = JSON.parse(cognifyTemplateConfigJson.value.trim())
    if (!config.entity_types || typeof config.entity_types !== 'object') {
      cognifyJsonError.value = '缺少必需字段: entity_types'
      return false
    }
    if (!config.edge_types || typeof config.edge_types !== 'object') {
      cognifyJsonError.value = '缺少必需字段: edge_types'
      return false
    }
    if (!config.edge_type_map || typeof config.edge_type_map !== 'object') {
      cognifyJsonError.value = '缺少必需字段: edge_type_map'
      return false
    }
    cognifyJsonError.value = ''
    message.success('Cognify JSON格式验证通过')
    return true
  } catch (e) {
    cognifyJsonError.value = `JSON格式错误: ${e.message}`
    return false
  }
}

// Memify JSON配置模式的验证（现在使用独立参数，不需要JSON验证）
const validateMemifyConfig = () => {
  // 验证规则集合名称
  if (!memifyRulesNodesetName.value || !memifyRulesNodesetName.value.trim()) {
    message.warning('规则集合名称不能为空')
    return false
  }
  
  // 验证节点类型
  if (!memifyNodeTypes.value || !memifyNodeTypes.value.trim()) {
    message.warning('节点类型不能为空')
      return false
    }
  
  // 验证最大跳数
  if (memifyMaxHops.value < 1 || memifyMaxHops.value > 10) {
    message.warning('最大跳数必须在1-10之间')
      return false
    }
  
  // 验证最大块数
  if (memifyMaxChunks.value < 1 || memifyMaxChunks.value > 1000) {
    message.warning('最大块数必须在1-1000之间')
      return false
    }
  
    return true
}

const clearCognifyJson = () => {
  cognifyTemplateConfigJson.value = ''
  cognifyJsonError.value = ''
}

// Cognify 提示词相关方法
const resetCognifySystemPrompt = () => {
  cognifySystemPrompt.value = DEFAULT_COGNIFY_SYSTEM_PROMPT
  message.success('已恢复默认 System Prompt')
}

const resetCognifyUserPrompt = () => {
  cognifyUserPromptTemplate.value = DEFAULT_COGNIFY_USER_PROMPT_TEMPLATE
  message.success('已恢复默认 User Prompt')
}

const previewCognifyFullPrompt = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  
  if (!selectedDoc.value?.chunks_path) {
    message.warning('该文档尚未分块，请先完成文档分块')
    return
  }
  
  try {
    const response = await getChunks(selectedDocumentId.value)
    if (response && response.content && response.content.chunks && response.content.chunks.length > 0) {
      const firstChunk = response.content.chunks[0]
      const sectionTitle = firstChunk.title || '章节_1'
      const sectionContent = firstChunk.content || ''
      
      let previewPrompt = cognifyUserPromptTemplate.value || DEFAULT_COGNIFY_USER_PROMPT_TEMPLATE
      previewPrompt = previewPrompt.replace(/{section_title}/g, sectionTitle)
      previewPrompt = previewPrompt.replace(/{section_content}/g, sectionContent.substring(0, 1000) + '...')
      
      Modal.info({
        title: '完整 User Prompt 预览',
        width: 800,
        content: h('pre', {
          style: {
            maxHeight: '500px',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            fontFamily: 'monospace',
            fontSize: '12px',
            padding: '12px',
            background: '#f5f5f5',
            borderRadius: '4px'
          }
        }, previewPrompt)
      })
    } else {
      message.warning('无法获取章节内容')
    }
  } catch (error) {
    message.error(`预览失败: ${error.message || '未知错误'}`)
  }
}

const handlePreviewCognifyTemplate = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  
  if (!selectedDoc.value?.chunks_path) {
    message.warning('该文档尚未分块，请先完成文档分块')
    return
  }
  
  generatingCognifyTemplate.value = true
  try {
    const response = await previewCognifyTemplate({
      upload_id: selectedDocumentId.value,
      system_prompt: cognifySystemPrompt.value || undefined,
      user_prompt_template: cognifyUserPromptTemplate.value || undefined,
      template_type: cognifyTemplateType.value,
      provider: provider.value
    })
    
    if (response.success && response.template_json) {
      cognifyGeneratedJson.value = JSON.stringify(response.template_json, null, 2)
      message.success('模板生成成功')
    } else {
      message.error('模板生成失败')
    }
  } catch (error) {
    console.error('预览模板生成失败:', error)
    message.error(`模板生成失败: ${error.response?.data?.detail || error.message || '未知错误'}`)
  } finally {
    generatingCognifyTemplate.value = false
  }
}

const handleResetCognifyTemplate = () => {
  cognifyGeneratedJson.value = ''
  message.success('已重置模板 JSON')
}

// Memify 提示词相关方法
const resetMemifySystemPrompt = () => {
  memifySystemPrompt.value = DEFAULT_MEMIFY_SYSTEM_PROMPT
  message.success('已恢复默认 System Prompt')
}

const resetMemifyUserPrompt = () => {
  memifyUserPromptTemplate.value = DEFAULT_MEMIFY_USER_PROMPT_TEMPLATE
  message.success('已恢复默认 User Prompt')
}

// 处理模版类型变化
const handleMemifyTemplateTypeChange = (value) => {
  if (value === 'default') {
    // 选择默认模版时，自动填充默认提示词
    memifySystemPrompt.value = DEFAULT_MEMIFY_SYSTEM_PROMPT
    memifyUserPromptTemplate.value = DEFAULT_MEMIFY_USER_PROMPT_TEMPLATE
  }
}


// Memify规则列表生成相关函数
const handlePreviewMemifyRules = async () => {
  console.log('🔵 handlePreviewMemifyRules 被调用')
  console.log('🔵 selectedDocumentId:', selectedDocumentId.value)
  console.log('🔵 selectedDoc:', selectedDoc.value)
  console.log('🔵 chunks_path:', selectedDoc.value?.chunks_path)
  
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  
  if (!selectedDoc.value?.chunks_path) {
    message.warning('该文档尚未分块，请先完成文档分块')
    return
  }
  
  console.log('🔵 开始调用 previewMemifyRules API')
  generatingMemifyRules.value = true
  try {
    const requestParams = {
      upload_id: selectedDocumentId.value,
      system_prompt: memifySystemPrompt.value || undefined,
      user_prompt_template: memifyUserPromptTemplate.value || undefined,
      template_type: memifyTemplateType.value,
      provider: provider.value
    }
    console.log('🔵 请求参数:', requestParams)
    const response = await previewMemifyRules(requestParams)
    console.log('🔵 API 响应:', response)
    
    if (response.success && response.rules && Array.isArray(response.rules)) {
      memifyGeneratedRules.value = response.rules
      memifyGeneratedRulesText.value = response.rules.join('\n')
      message.success(`规则列表生成成功，共 ${response.rules.length} 条规则`)
  } else {
      message.error('规则列表生成失败')
    }
  } catch (error) {
    console.error('预览规则列表生成失败:', error)
    message.error(`规则列表生成失败: ${error.response?.data?.detail || error.message || '未知错误'}`)
  } finally {
    generatingMemifyRules.value = false
  }
}

const handleResetMemifyRules = () => {
  memifyGeneratedRules.value = []
  memifyGeneratedRulesText.value = ''
  message.success('已重置规则列表')
}

const handleApplyMemifyRules = () => {
  if (!memifyGeneratedRules.value || memifyGeneratedRules.value.length === 0) {
    message.warning('没有可应用的规则列表')
    return
  }
  
  // 切换到JSON配置模式
  memifyTemplateMode.value = 'json_config'
  
  // 填充规则列表
  memifyRules.value = memifyGeneratedRulesText.value
  
  message.success(`已应用 ${memifyGeneratedRules.value.length} 条规则到JSON配置`)
}

const handlePreviewCustomPrompt = () => {
  if (!cognifyGeneratedJson.value || !cognifyGeneratedJson.value.trim()) {
    message.warning('请先生成模板 JSON')
    return
  }
  
  try {
    const templateConfig = JSON.parse(cognifyGeneratedJson.value.trim())
    
    // 模拟 _template_to_custom_prompt 的转换逻辑
    const entityTypes = templateConfig.entity_types || {}
    const edgeTypes = templateConfig.edge_types || {}
    const edgeTypeMap = templateConfig.edge_type_map || {}
  
    // 构建实体类型描述
    const entityTypesDesc = []
    for (const [entityName, entityDef] of Object.entries(entityTypes)) {
      let entityDesc = `  - ${entityName}`
      if (typeof entityDef === 'object' && entityDef.description) {
        entityDesc += `：${entityDef.description}`
      }
      if (typeof entityDef === 'object' && entityDef.fields) {
        const fieldsDesc = []
        for (const [fieldName, fieldDef] of Object.entries(entityDef.fields)) {
          const fieldType = fieldDef.type || 'str'
          const required = fieldDef.required ? '必需' : '可选'
          const description = fieldDef.description || ''
          fieldsDesc.push(`    - ${fieldName} (${fieldType}, ${required}): ${description}`)
        }
        if (fieldsDesc.length > 0) {
          entityDesc += '\n' + fieldsDesc.join('\n')
        }
      }
      entityTypesDesc.push(entityDesc)
    }
    
    // 构建关系类型描述
    const edgeTypesDesc = []
    for (const [edgeName, edgeDef] of Object.entries(edgeTypes)) {
      let edgeDesc = `  - ${edgeName}`
      if (typeof edgeDef === 'object' && edgeDef.description) {
        edgeDesc += `：${edgeDef.description}`
      }
      if (typeof edgeDef === 'object' && edgeDef.fields) {
        const fieldsDesc = []
        for (const [fieldName, fieldDef] of Object.entries(edgeDef.fields)) {
          const fieldType = fieldDef.type || 'str'
          const required = fieldDef.required ? '必需' : '可选'
          const description = fieldDef.description || ''
          fieldsDesc.push(`    - ${fieldName} (${fieldType}, ${required}): ${description}`)
        }
        if (fieldsDesc.length > 0) {
          edgeDesc += '\n' + fieldsDesc.join('\n')
        }
      }
      edgeTypesDesc.push(edgeDesc)
    }
    
    // 构建关系映射描述
    const edgeMapDesc = []
    for (const [key, values] of Object.entries(edgeTypeMap)) {
      if (Array.isArray(values)) {
        edgeMapDesc.push(`  - ${key}: ${values.join(', ')}`)
  } else {
        edgeMapDesc.push(`  - ${key}: ${values}`)
      }
    }
    
    // 构建完整的 custom_prompt
    const customPrompt = `请根据以下实体和关系类型定义，从文本中提取知识图谱：

**实体类型定义**：
${entityTypesDesc.length > 0 ? entityTypesDesc.join('\n') : '  （无预定义实体类型，请根据内容自由识别）'}

**关系类型定义**：
${edgeTypesDesc.length > 0 ? edgeTypesDesc.join('\n') : '  （无预定义关系类型，请根据内容自由识别）'}

**关系映射规则**：
${edgeMapDesc.length > 0 ? edgeMapDesc.join('\n') : '  （无预定义关系映射，请根据内容自由识别）'}

**提取要求**：
1. 严格按照上述实体类型和关系类型定义进行提取
2. 实体必须符合定义的实体类型
3. 关系必须符合定义的关系类型和关系映射规则
4. 如果文本中没有符合定义的实体或关系，不要强制提取
5. 确保提取的实体和关系准确反映文本内容

请开始提取知识图谱。`
    
    Modal.info({
      title: 'Custom Prompt 预览',
      width: 900,
      content: h('pre', {
        style: {
          maxHeight: '600px',
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          fontFamily: 'monospace',
          fontSize: '13px',
          padding: '16px',
          background: '#f5f5f5',
          borderRadius: '4px',
          lineHeight: '1.6'
        }
      }, customPrompt)
    })
  } catch (error) {
    message.error(`预览失败: ${error.message || 'JSON格式错误'}`)
  }
}

const selectedDoc = computed(() => {
  return documents.value.find(d => d.id === selectedDocumentId.value)
})

const selectedNode = ref(null)
const selectedEdge = ref(null)
const nodeDrawerVisible = ref(false)
const edgeDrawerVisible = ref(false)
const graphModalVisible = ref(false)
const graphNotCreatedModalVisible = ref(false)
const viewGraphData = ref(null)
const loadingGraph = ref(false)

const loadDocuments = async () => {
  loadingDocuments.value = true
  try {
    const response = await getDocumentUploadList(1, 100, null, null)
    if (response && response.documents) {
      documents.value = response.documents.filter(doc => 
        doc.parsed_content_path || doc.chunks_path
      )
    }
  } catch (error) {
    message.error(`加载文档列表失败: ${error.message || '未知错误'}`)
  } finally {
    loadingDocuments.value = false
  }
}

const handleDocumentChange = async () => {
  executionResult.value = null
  graphData.value = null
  splitResult.value = null
  chunksData.value = null
  chunksCollapseActiveKey.value = []
  
  if (selectedDoc.value?.chunks_path && selectedDocumentId.value) {
    await loadChunks()
  }
}

const loadChunks = async () => {
  if (!selectedDocumentId.value) return
  loadingChunks.value = true
  try {
    const response = await getChunks(selectedDocumentId.value)
    if (response && response.content) {
      chunksData.value = response.content
      if (chunksData.value.chunks) {
        chunksCollapseActiveKey.value = chunksData.value.chunks.slice(0, 3).map((_, idx) => `chunk_${idx}`)
      }
        chunksCogneeMapping.value = { mappings: [] }
      }
    await loadChunksCogneeMapping()
  } catch (error) {
    message.warning(`加载分块失败: ${error.message || '未知错误'}`)
  } finally {
    loadingChunks.value = false
  }
}

const loadChunksCogneeMapping = async () => {
  if (!selectedDocumentId.value) return
  loadingMapping.value = true
  try {
    const response = await getChunksCogneeMapping(selectedDocumentId.value)
    if (response && response.mappings) {
      chunksCogneeMapping.value = response
    }
  } catch (error) {
    chunksCogneeMapping.value = { mappings: [] }
  } finally {
    loadingMapping.value = false
  }
}

const getChunkMapping = (chunkIndex) => {
  if (!chunksCogneeMapping.value?.mappings) return null
  return chunksCogneeMapping.value.mappings.find(m => m.chunk_index === chunkIndex) || null
}

const handleSplitDocument = async () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  splitting.value = true
  try {
    const strategy = chunkingMode.value === 'smart' ? 'auto' : chunkStrategy.value
    const response = await splitDocument(selectedDocumentId.value, strategy, maxTokensPerSection.value, true)
    splitResult.value = response
    message.success(`分块完成！共 ${response.statistics?.total_sections || 0} 个章节`)
    await loadDocuments()
      await loadChunks()
  } catch (error) {
    message.error(`分块失败: ${error.message || '未知错误'}`)
  } finally {
    splitting.value = false
  }
}

const handleExecute = async (skipConfirmation = false) => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }
  executing.value = true
  executionStatus.value = '正在分析文档并构建知识图谱...'
  try {
    let cognifyConfig = null
    let cognifySystemPromptValue = null
    let cognifyUserPromptTemplateValue = null
    
    if (cognifyTemplateMode.value === 'json_config') {
      if (!validateCognifyJson()) { executing.value = false; return; }
      cognifyConfig = JSON.parse(cognifyTemplateConfigJson.value)
    } else {
      // LLM生成模式：如果已有生成的 JSON，使用它；否则传递提示词让后端生成
      if (cognifyGeneratedJson.value && cognifyGeneratedJson.value.trim()) {
        try {
          cognifyConfig = JSON.parse(cognifyGeneratedJson.value.trim())
      } catch (e) {
          message.warning('已生成的 JSON 格式错误，将使用提示词重新生成')
          cognifyConfig = null
        }
      }
      
      // 如果没有已生成的 JSON，传递提示词
      if (!cognifyConfig) {
        cognifySystemPromptValue = cognifySystemPrompt.value || undefined
        cognifyUserPromptTemplateValue = cognifyUserPromptTemplate.value || undefined
      }
    }

    let memifyConfig = null
    let memifySystemPromptValue = null
    let memifyUserPromptTemplateValue = null
    
    if (memifyTemplateMode.value === 'json_config') {
      // JSON配置模式：验证配置
      if (!validateMemifyConfig()) { executing.value = false; return; }
      
      // 将独立参数组装成JSON格式
      const nodeTypesArray = memifyNodeTypes.value
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0)
      
      const rulesArray = memifyRules.value
        .split('\n')
        .map(r => r.trim())
        .filter(r => r.length > 0)
      
      memifyConfig = {
        extraction: {
          enabled: true,
          task: "extract_subgraph_chunks",
          node_types: nodeTypesArray.length > 0 ? nodeTypesArray : ["DocumentChunk"],
          max_hops: memifyMaxHops.value || 1,
          max_chunks: memifyMaxChunks.value || 100
        },
        enrichment: {
          enabled: true,
          task: "add_rule_associations",
          rules_nodeset_name: memifyRulesNodesetName.value || "default_rules",
          rules: rulesArray.length > 0 ? rulesArray : undefined, // 如果为空则不传，使用LLM自动提取
          mode: rulesArray.length > 0 ? "manual" : "llm_extract" // 手动配置或LLM提取
        }
      }
    } else {
      // LLM生成模式：传递提示词和已生成的规则列表（如果有）
      memifySystemPromptValue = memifySystemPrompt.value || undefined
      memifyUserPromptTemplateValue = memifyUserPromptTemplate.value || undefined
    }

    // LLM生成模式下，如果已生成规则列表，传递到后端
    const memifyRulesValue = memifyTemplateMode.value === 'llm_generate' && memifyGeneratedRules.value && memifyGeneratedRules.value.length > 0
      ? memifyGeneratedRules.value
      : undefined

    const result = await step2CogneeBuild({
      upload_id: selectedDocumentId.value,
      group_id: selectedDoc.value?.document_id || undefined,
      provider: provider.value,
      temperature: temperature.value,
      cognify_template_mode: cognifyTemplateMode.value,
      cognify_template_config_json: cognifyConfig,
      cognify_system_prompt: cognifySystemPromptValue,
      cognify_user_prompt_template: cognifyUserPromptTemplateValue,
      cognify_template_type: cognifyTemplateType.value,
      memify_template_mode: memifyTemplateMode.value,
      memify_template_config_json: memifyConfig,
      memify_system_prompt: memifySystemPromptValue,
      memify_user_prompt_template: memifyUserPromptTemplateValue,
      memify_template_type: memifyTemplateType.value,
      memify_rules: memifyRulesValue
    })

    // 优先检查是否需要确认删除已存在的Cognee知识图谱（即使success为false也要检查）
    // 但如果skipConfirmation为true，则跳过确认检查（用于删除后重新执行）
    console.log('Cognee API响应:', result)
    console.log('needs_confirmation:', result?.needs_confirmation, 'skipConfirmation:', skipConfirmation)
    if (!skipConfirmation && result && result.needs_confirmation === true) {
      console.log('检测到needs_confirmation=true，显示确认对话框')
      // 显示确认对话框
      Modal.confirm({
        title: '确认删除',
        content: `已存在Cognee知识图谱（dataset: ${result.dataset_name || '未知'}），是否删除后重建？`,
        okText: '确认删除并重建',
        cancelText: '取消',
        onOk: () => {
          // 立即关闭所有Modal
          Modal.destroyAll()
          
          // 然后执行删除和重建
          const executeDeleteAndRebuild = async () => {
            try {
              executing.value = true
              executionStatus.value = '正在删除旧的Cognee知识图谱...'
              // 删除已存在的Cognee知识图谱
              await deleteCogneeGraph(selectedDocumentId.value)
              message.success('已删除旧的Cognee知识图谱，开始重建...')

              // 重新执行，跳过确认检查
              await handleExecute(true)
            } catch (err) {
              message.error('删除失败: ' + (err.response?.data?.detail || err.message))
              executing.value = false
              executionStatus.value = ''
            }
          }
          
          // 异步执行，不阻塞
          executeDeleteAndRebuild()
          
          // 返回false，阻止Modal的默认关闭行为（因为我们已经手动关闭了）
          return false
        },
        onCancel: () => {
          executing.value = false
          executionStatus.value = ''
        }
      })
      // 重置状态，让按钮恢复可用
      executing.value = false
      executionStatus.value = ''
      return
    }

    // 如果success为false且不是needs_confirmation，说明是其他错误
    if (result && result.success === false && !result.needs_confirmation) {
      message.error(result.message || '执行失败')
      executing.value = false
      executionStatus.value = ''
      return
    }

    executionResult.value = result
    message.success('Cognee 处理完成')
    
    const groupId = result.group_id || selectedDoc.value?.document_id
    if (groupId) {
      const graphResult = await getCogneeGraph(groupId)
        graphData.value = graphResult
    }
    await loadChunksCogneeMapping()
  } catch (error) {
    message.error(`执行失败: ${error.message || '未知错误'}`)
  } finally {
    executing.value = false
    executionStatus.value = ''
  }
}

const handleClear = () => {
  executionResult.value = null
  graphData.value = null
  message.success('已清空结果')
}

const handleViewGraphModal = async () => {
  const groupId = selectedDoc.value?.document_id
  if (!groupId) return
  loadingGraph.value = true
  try {
    const graphResult = await getCogneeGraph(groupId)
    if (!graphResult.nodes?.length) {
      graphNotCreatedModalVisible.value = true
    } else {
      viewGraphData.value = graphResult
      graphModalVisible.value = true
    }
  } catch (error) {
    message.error(`获取图谱失败: ${error.message || '未知错误'}`)
  } finally {
    loadingGraph.value = false
  }
}

const handleGraphModalClose = () => {
  graphModalVisible.value = false
  viewGraphData.value = null
}

const handleDeleteGraph = () => {
  if (!selectedDocumentId.value) {
    message.warning('请先选择文档')
    return
  }

  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该文档的Cognee知识图谱和Milvus向量吗？此操作不可恢复。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteCogneeGraph(selectedDocumentId.value)
        message.success('Cognee知识图谱和Milvus向量已删除')
        
        // 清空相关数据
        executionResult.value = null
        graphData.value = null
        viewGraphData.value = null
        
        // 如果图谱Modal是打开的，关闭它
        if (graphModalVisible.value) {
          graphModalVisible.value = false
        }
      } catch (err) {
        message.error('删除失败: ' + (err.response?.data?.detail || err.message))
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

const getStepColor = (status) => {
  const map = { 'completed': 'green', 'failed': 'red', 'processing': 'blue' }
  return map[status] || 'gray'
}

const getLinkageStatus = () => {
  const linkage = executionResult.value?.graphiti_linkage || executionResult.value?.graphiti_reference
  if (!linkage) return { type: 'info', message: '尚未建立联动关系' }
  return linkage.linkage_established || linkage.established 
    ? { type: 'success', message: '✅ Cognee-Graphiti 联动已成功建立' }
    : { type: 'warning', message: '⚠️ 联动未建立，请先执行 Graphiti 处理' }
  }

const getGraphitiLinkageData = () => {
  const l = executionResult.value?.graphiti_linkage || executionResult.value?.graphiti_reference || {}
  return { episode_uuid: l.episode_uuid || null }
}

const getDataConsistency = () => {
  const l = executionResult.value?.graphiti_linkage || executionResult.value?.graphiti_reference
  return l?.data_consistency || { doc_id_match: l?.doc_id_match, group_id_match: l?.group_id_match }
}

onMounted(() => {
  loadDocuments()
  
  // 初始化时，如果模版类型是default，自动填充默认提示词
  if (memifyTemplateType.value === 'default') {
    // 如果当前提示词为空，则自动填充默认值
    if (!memifySystemPrompt.value || memifySystemPrompt.value.trim() === '') {
      memifySystemPrompt.value = DEFAULT_MEMIFY_SYSTEM_PROMPT
    }
    if (!memifyUserPromptTemplate.value || memifyUserPromptTemplate.value.trim() === '') {
      memifyUserPromptTemplate.value = DEFAULT_MEMIFY_USER_PROMPT_TEMPLATE
    }
  }
})
</script>

<style scoped>
.cognee-tab {
  padding: 8px 0;
}
.cognee-tab-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}
.cognee-tab-form :deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: #262626;
}
.error-border {
  border-color: #ff4d4f !important;
}
.base-config-section {
  background: #fbfbfb;
  padding: 24px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
</style>
