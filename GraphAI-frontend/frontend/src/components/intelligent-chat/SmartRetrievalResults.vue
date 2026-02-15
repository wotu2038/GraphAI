<template>
  <div class="smart-retrieval-results">
    <!-- 执行时间统计 -->
    <a-card title="执行统计" class="stats-card" size="small">
      <a-descriptions :column="3" bordered size="small">
        <a-descriptions-item label="阶段1耗时">
          <span class="time-value">{{ formatTime(result.summary?.stage1_time || 0) }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="阶段2耗时">
          <span class="time-value">{{ formatTime(result.summary?.stage2_time || 0) }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="总耗时">
          <span class="time-value total">{{ formatTime(result.summary?.total_time || 0) }}</span>
        </a-descriptions-item>
      </a-descriptions>
    </a-card>

    <!-- 检索策略版本 -->
    <a-alert
      v-if="result.summary"
      :message="`检索策略：v${result.summary.version || '4.0'}`"
      description="单路DocumentChunk检索 + 分数阈值过滤 + 批量Neo4j查询"
      type="info"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #icon>
        <RocketOutlined />
      </template>
    </a-alert>

    <!-- 阶段1结果：Chunk粒度检索 -->
    <a-card title="阶段1：DocumentChunk 检索结果" class="stage-card">
      <a-descriptions :column="3" bordered size="small" style="margin-bottom: 16px">
        <a-descriptions-item label="返回Chunk数">
          <span class="stat-value">{{ result.stage1?.summary?.total_chunks || 0 }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="涉及文档数">
          <span class="stat-value">{{ result.stage1?.summary?.total_documents || 0 }}</span>
        </a-descriptions-item>
        <a-descriptions-item label="分数范围">
          <a-tag color="blue">{{ formatScoreRange(result.stage1?.summary?.score_range) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="分数阈值">
          <a-tag color="green">{{ result.stage1?.summary?.threshold || 0 }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="Top K">
          <a-tag color="orange">{{ result.stage1?.summary?.top_k || 0 }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="满足阈值总数">
          <span class="stat-value">{{ result.stage1?.summary?.filtered_count || 0 }}</span>
        </a-descriptions-item>
      </a-descriptions>

      <a-list
        v-if="result.stage1?.chunk_results?.length > 0"
        :data-source="result.stage1.chunk_results"
        item-layout="vertical"
        :pagination="{ pageSize: 10 }"
      >
        <template #renderItem="{ item, index }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                <a-space>
                  <a-tag color="blue">Chunk {{ index + 1 }}</a-tag>
                  <a-tag color="orange">分数: {{ item.score?.toFixed(1) || 0 }}</a-tag>
                  <span style="font-weight: 600; font-size: 14px">{{ item.section_name }}</span>
                </a-space>
              </template>
              <template #description>
                <a-space direction="vertical" style="width: 100%">
                  <a-descriptions :column="3" size="small" bordered>
                    <a-descriptions-item label="文档名称">
                      {{ item.document_name || '未知文档' }}
                    </a-descriptions-item>
                    <a-descriptions-item label="章节">
                      {{ item.section_name || '未知章节' }}
                  </a-descriptions-item>
                    <a-descriptions-item label="Chunk索引">
                      {{ item.chunk_index }}
                  </a-descriptions-item>
                    <a-descriptions-item label="文档ID" :span="2">
                      <a-typography-text copyable>{{ item.group_id }}</a-typography-text>
                  </a-descriptions-item>
                    <a-descriptions-item label="来源">
                      <a-tag color="cyan">{{ item.metadata?.source || 'DocumentChunk_text' }}</a-tag>
                  </a-descriptions-item>
                </a-descriptions>
                  
                  <!-- Chunk内容预览 -->
                  <a-card size="small" title="内容预览" style="margin-top: 8px">
                    <div 
                      style="max-height: 120px; overflow-y: auto; background: #f5f5f5; padding: 12px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.6"
                    >
                      {{ item.content?.substring(0, 300) || '无内容' }}
                      <span v-if="item.content?.length > 300" style="color: #999">...</span>
                    </div>
                  </a-card>
                  
                  <!-- 操作按钮 -->
                  <a-space style="margin-top: 8px">
                    <a-button 
                      type="link" 
                      size="small" 
                      @click="viewChunkDetail(item)"
                    >
                      查看完整内容
                    </a-button>
                    <a-button 
                      type="link" 
                      size="small" 
                      @click="viewDocument(item)"
                    >
                      查看所属文档
                    </a-button>
                  </a-space>
                </a-space>
              </template>
            </a-list-item-meta>
          </a-list-item>
        </template>
      </a-list>
      <a-empty v-else description="没有找到匹配的chunk" />
    </a-card>

    <!-- 阶段2结果：Graphiti + Cognee 双路扩展 -->
    <a-card 
      v-if="result.stage2 || result.enable_refine" 
      class="stage-card"
      style="margin-top: 24px"
    >
      <template #title>
        <span>
          阶段2：知识图谱扩展（文档级 + 章节级）
          <a-tag 
            v-if="getStage2TotalEntityCount(result.stage2) > 0" 
            color="blue" 
            style="margin-left: 8px"
          >
            总计 {{ getStage2TotalEntityCount(result.stage2) }} 个Entity
              </a-tag>
            </span>
      </template>
      <!-- 调试信息：如果没有数据，显示调试信息 -->
      <div v-if="!hasGraphitiData(result.stage2) && !hasCogneeData(result.stage2)" style="padding: 16px; background: #f5f5f5; border-radius: 4px; margin-bottom: 16px;">
        <a-alert 
          message="阶段2数据为空" 
          description="Graphiti和Cognee都没有返回数据。请检查后端日志或确保已启用精细处理。"
          type="info" 
          show-icon
        />
        <div style="margin-top: 8px; font-size: 12px; color: #666;">
          <details>
            <summary style="cursor: pointer; color: #1890ff;">查看原始数据（调试用）</summary>
            <pre style="background: #fff; padding: 8px; border-radius: 4px; overflow: auto; max-height: 200px; margin-top: 8px;">{{ JSON.stringify(result.stage2, null, 2) }}</pre>
          </details>
        </div>
      </div>

      <!-- 主Tab：Graphiti / Cognee -->
      <a-tabs v-model:activeKey="stage2MainTab" type="card">
        <!-- Graphiti Tab（文档级） -->
        <a-tab-pane key="graphiti" tab="Graphiti（文档级业务结构化）">
          <template #tab>
            <span>
              Graphiti
              <a-badge 
                :count="result.stage2?.graphiti?.statistics?.entity_count || 0" 
                :number-style="{ backgroundColor: '#1890ff' }"
                style="margin-left: 8px"
              />
            </span>
          </template>
          
          <div v-if="hasGraphitiData(result.stage2)">
            <!-- Graphiti统计信息 -->
            <a-descriptions :column="4" bordered size="small" style="margin-bottom: 16px">
              <a-descriptions-item label="Entity数量">
                <span class="stat-value">{{ result.stage2?.graphiti?.statistics?.entity_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="关系数量">
                <span class="stat-value">{{ result.stage2?.graphiti?.statistics?.relationship_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="路径数量">
                <span class="stat-value">{{ result.stage2?.graphiti?.statistics?.path_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="节点数">
                <span class="stat-value">{{ result.stage2?.graphiti?.relationship_graph?.nodes?.length || 0 }}</span>
              </a-descriptions-item>
            </a-descriptions>

            <!-- Graphiti子Tab：知识图谱可视化 / Entity列表 -->
            <a-tabs v-model:activeKey="graphitiTab" type="card" style="margin-top: 16px">
              <!-- Graphiti知识图谱可视化 -->
              <a-tab-pane key="graph" tab="知识图谱可视化">
                <template #tab>
                  <span>
                    关系图
                    <a-badge 
                      :count="result.stage2?.graphiti?.relationship_graph?.edges?.length || 0" 
                      :number-style="{ backgroundColor: '#1890ff' }"
                      style="margin-left: 8px"
                    />
                  </span>
                </template>
                <div v-if="result.stage2?.graphiti?.relationship_graph?.nodes?.length > 0" style="height: 600px; border: 1px solid #f0f0f0; border-radius: 4px; background: #fff">
                  <GraphVisualization 
                    :data="formatGraphDataForVisualization(result.stage2.graphiti.relationship_graph)"
                  />
                </div>
                <a-empty v-else description="暂无关系图数据" />
              </a-tab-pane>

              <!-- Graphiti Entity列表 -->
              <a-tab-pane key="entities" tab="Entity列表">
                <template #tab>
                  <span>
                    Entity
                    <a-badge 
                      :count="result.stage2?.graphiti?.entities?.length || 0" 
                      :number-style="{ backgroundColor: '#52c41a' }"
                      style="margin-left: 8px"
                    />
                  </span>
                </template>
                <a-list
                  v-if="result.stage2?.graphiti?.entities?.length > 0"
                  :data-source="result.stage2.graphiti.entities"
            :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 个Entity` }"
            item-layout="vertical"
          >
            <template #renderItem="{ item, index }">
              <a-list-item>
                <a-list-item-meta>
                  <template #title>
                    <a-space>
                      <a-tag color="blue">Entity {{ index + 1 }}</a-tag>
                      <span style="font-weight: 600; font-size: 14px">{{ item.name }}</span>
                      <a-tag :color="getEntityTypeColor(item.type)">
                        {{ item.type || 'Entity' }}
                      </a-tag>
                      <a-tag color="orange">分数: {{ (item.score * 100).toFixed(1) }}</a-tag>
                    </a-space>
                  </template>
                  <template #description>
                    <a-space direction="vertical" style="width: 100%">
                      <!-- Entity基本信息 -->
                      <a-descriptions :column="3" size="small" bordered>
                        <a-descriptions-item label="UUID">
                          <a-typography-text copyable style="font-size: 11px">{{ item.uuid }}</a-typography-text>
                        </a-descriptions-item>
                        <a-descriptions-item label="类型">
                          {{ item.type || 'Entity' }}
                        </a-descriptions-item>
                        <a-descriptions-item label="分数">
                          {{ (item.score * 100).toFixed(1) }}
                        </a-descriptions-item>
                      </a-descriptions>

                      <!-- 关系列表 -->
                      <a-card v-if="item.relationships?.length > 0" size="small" title="关系" style="margin-top: 8px">
                        <a-list size="small" :data-source="item.relationships" :pagination="false">
                          <template #renderItem="{ item: rel }">
                            <a-list-item>
                              <a-space>
                                <a-tag color="cyan">{{ rel.type }}</a-tag>
                                <span style="font-weight: 500">{{ item.name || item.uuid || item.id }}</span>
                                <span style="color: #999">→</span>
                                <span style="font-weight: 500">{{ rel.target }}</span>
                                <a-tag size="small" color="default">{{ rel.target_type }}</a-tag>
                              </a-space>
                              <div v-if="rel.fact" style="margin-top: 4px; color: #666; font-size: 12px">
                                {{ rel.fact }}
                              </div>
                            </a-list-item>
                          </template>
                        </a-list>
                      </a-card>

                      <!-- 路径列表 -->
                      <a-card v-if="item.paths?.length > 0" size="small" title="关系路径" style="margin-top: 8px">
                        <a-list size="small" :data-source="item.paths" :pagination="false">
                          <template #renderItem="{ item: path }">
                            <a-list-item>
                              <a-space>
                                <span v-for="(entity, idx) in path.path" :key="idx">
                                  <a-tag color="blue">{{ entity }}</a-tag>
                                  <span v-if="idx < path.path.length - 1" style="color: #999; margin: 0 4px">
                                    {{ path.relationships[idx] || '→' }}
                                  </span>
                                </span>
                                <a-tag size="small" color="default">{{ path.depth }}跳</a-tag>
                              </a-space>
                            </a-list-item>
                          </template>
                        </a-list>
                      </a-card>

                      <!-- 关联Chunk -->
                      <a-card v-if="item.related_chunks?.length > 0" size="small" title="关联Chunk" style="margin-top: 8px">
                        <a-list size="small" :data-source="item.related_chunks" :pagination="false">
                          <template #renderItem="{ item: chunk }">
                            <a-list-item>
                              <a-space direction="vertical" style="width: 100%">
                                <a-space>
                                  <a-tag color="orange">分数: {{ chunk.score?.toFixed(1) || 0 }}</a-tag>
                                  <span>{{ chunk.section_name }}</span>
                                  <span style="color: #999">-</span>
                                  <span>{{ chunk.document_name }}</span>
                                </a-space>
                                <div style="color: #666; font-size: 12px; max-height: 60px; overflow: hidden">
                                  {{ chunk.content_preview }}
                                </div>
                              </a-space>
                            </a-list-item>
                          </template>
                        </a-list>
                      </a-card>
                    </a-space>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
                <a-empty v-else description="没有找到Entity" />
              </a-tab-pane>
            </a-tabs>
          </div>
          <a-empty v-else description="没有Graphiti数据" />
        </a-tab-pane>

        <!-- Cognee Tab（章节级） -->
        <a-tab-pane key="cognee" tab="Cognee（章节级通用语义）">
          <template #tab>
            <span>
              Cognee
              <a-badge 
                :count="result.stage2?.cognee?.statistics?.entity_count || 0" 
                :number-style="{ backgroundColor: '#52c41a' }"
                style="margin-left: 8px"
              />
            </span>
          </template>
          
          <div v-if="hasCogneeData(result.stage2)">
            <!-- Cognee统计信息 -->
            <a-descriptions :column="4" bordered size="small" style="margin-bottom: 16px">
              <a-descriptions-item label="Entity数量">
                <span class="stat-value">{{ result.stage2?.cognee?.statistics?.entity_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="关系数量">
                <span class="stat-value">{{ result.stage2?.cognee?.statistics?.relationship_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="路径数量">
                <span class="stat-value">{{ result.stage2?.cognee?.statistics?.path_count || 0 }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="节点数">
                <span class="stat-value">{{ result.stage2?.cognee?.relationship_graph?.nodes?.length || 0 }}</span>
              </a-descriptions-item>
            </a-descriptions>

            <!-- Cognee子Tab：知识图谱可视化 / Entity列表 -->
            <a-tabs v-model:activeKey="cogneeTab" type="card" style="margin-top: 16px">
              <!-- Cognee知识图谱可视化 -->
              <a-tab-pane key="graph" tab="知识图谱可视化">
                <template #tab>
                  <span>
                    关系图
                    <a-badge 
                      :count="result.stage2?.cognee?.relationship_graph?.edges?.length || 0" 
                      :number-style="{ backgroundColor: '#1890ff' }"
                      style="margin-left: 8px"
                    />
                  </span>
                </template>
                <div v-if="result.stage2?.cognee?.relationship_graph?.nodes?.length > 0" style="height: 600px; border: 1px solid #f0f0f0; border-radius: 4px; background: #fff">
                  <GraphVisualization 
                    :data="formatGraphDataForVisualization(result.stage2.cognee.relationship_graph)"
                  />
                </div>
                <a-empty v-else description="暂无关系图数据" />
              </a-tab-pane>

              <!-- Cognee Entity列表 -->
              <a-tab-pane key="entities" tab="Entity列表">
                <template #tab>
                  <span>
                    Entity
                    <a-badge 
                      :count="result.stage2?.cognee?.entities?.length || 0" 
                      :number-style="{ backgroundColor: '#52c41a' }"
                      style="margin-left: 8px"
                    />
                  </span>
                </template>
                <a-list
                  v-if="result.stage2?.cognee?.entities?.length > 0"
                  :data-source="result.stage2.cognee.entities"
                  :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 个Entity` }"
                  item-layout="vertical"
                >
                  <template #renderItem="{ item, index }">
                    <a-list-item>
                      <a-list-item-meta>
                        <template #title>
                          <a-space>
                            <a-tag color="green">Entity {{ index + 1 }}</a-tag>
                            <span style="font-weight: 600; font-size: 14px">{{ item.name }}</span>
                            <a-tag :color="getEntityTypeColor(item.type)">
                              {{ item.type || 'Entity' }}
                            </a-tag>
                            <a-tag color="orange">分数: {{ item.score?.toFixed(1) || 0 }}</a-tag>
                          </a-space>
                        </template>
                        <template #description>
                          <a-space direction="vertical" style="width: 100%">
                            <!-- Entity基本信息 -->
                            <a-descriptions :column="3" size="small" bordered>
                              <a-descriptions-item label="ID">
                                <a-typography-text copyable style="font-size: 11px">{{ item.id || item.uuid }}</a-typography-text>
                              </a-descriptions-item>
                              <a-descriptions-item label="类型">
                                {{ item.type || 'Entity' }}
                              </a-descriptions-item>
                              <a-descriptions-item label="分数">
                                {{ item.score?.toFixed(1) || 0 }}
                              </a-descriptions-item>
                            </a-descriptions>

                            <!-- 关系列表 -->
                            <a-card v-if="item.relationships?.length > 0" size="small" title="关系" style="margin-top: 8px">
                              <a-list size="small" :data-source="item.relationships" :pagination="false">
                                <template #renderItem="{ item: rel }">
                                  <a-list-item>
                                    <a-space>
                                      <a-tag color="cyan">{{ rel.type }}</a-tag>
                                      <span style="font-weight: 500">{{ item.name || item.id || item.uuid }}</span>
                                      <span style="color: #999">→</span>
                                      <span style="font-weight: 500">{{ rel.target }}</span>
                                      <a-tag size="small" color="default">{{ rel.target_type }}</a-tag>
                                    </a-space>
                                  </a-list-item>
                                </template>
                              </a-list>
                            </a-card>

                            <!-- 关联Chunk -->
                            <a-card v-if="item.related_chunks?.length > 0" size="small" title="关联Chunk" style="margin-top: 8px">
                              <a-list size="small" :data-source="item.related_chunks" :pagination="false">
                                <template #renderItem="{ item: chunk }">
                                  <a-list-item>
                                    <a-space direction="vertical" style="width: 100%">
                                      <a-space>
                                        <a-tag color="orange">分数: {{ chunk.score?.toFixed(1) || 0 }}</a-tag>
                                        <span>{{ chunk.section_name }}</span>
                                        <span style="color: #999">-</span>
                                        <span>{{ chunk.document_name }}</span>
                                      </a-space>
                                      <div style="color: #666; font-size: 12px; max-height: 60px; overflow: hidden">
                                        {{ chunk.content_preview }}
                                      </div>
                                    </a-space>
                                  </a-list-item>
                                </template>
                              </a-list>
                            </a-card>
                          </a-space>
                        </template>
                      </a-list-item-meta>
                    </a-list-item>
                  </template>
                </a-list>
                <a-empty v-else description="没有找到Entity" />
              </a-tab-pane>
            </a-tabs>
          </div>
          <a-empty v-else description="没有Cognee数据" />
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <!-- Chunk详情弹窗 -->
    <a-modal
      v-model:open="chunkDetailVisible"
      :title="`Chunk详情 - ${chunkDetailData?.section_name || ''}`"
      width="900px"
      :footer="null"
      :maskClosable="true"
    >
      <a-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
        <a-descriptions-item label="分数">
          <a-tag color="orange">{{ chunkDetailData?.score?.toFixed(1) || 0 }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="Chunk索引">
          {{ chunkDetailData?.chunk_index }}
        </a-descriptions-item>
        <a-descriptions-item label="章节名称">
          {{ chunkDetailData?.section_name || '未知章节' }}
        </a-descriptions-item>
        <a-descriptions-item label="文档名称">
          {{ chunkDetailData?.document_name || '未知文档' }}
        </a-descriptions-item>
        <a-descriptions-item label="文档ID" :span="2">
          <a-typography-text copyable>{{ chunkDetailData?.group_id }}</a-typography-text>
        </a-descriptions-item>
        <a-descriptions-item label="Chunk ID" :span="2">
          <a-typography-text copyable>{{ chunkDetailData?.uuid }}</a-typography-text>
        </a-descriptions-item>
      </a-descriptions>
      
      <a-card title="完整内容" size="small">
        <div 
          style="max-height: 60vh; overflow-y: auto; background: #f5f5f5; padding: 16px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; font-size: 14px; line-height: 1.8"
        >
          {{ chunkDetailData?.content || '无内容' }}
        </div>
      </a-card>
    </a-modal>

    <!-- 文档详情弹窗 -->
    <a-modal
      v-model:open="documentDetailVisible"
      :title="`查看文档详情 - ${documentDetailData?.group_id || documentDetailData?.document_id || ''}`"
      width="1000px"
      :footer="null"
      :maskClosable="true"
    >
      <a-spin :spinning="documentDetailLoading">
        <a-tabs v-model:activeKey="documentDetailTab" v-if="!documentDetailLoading">
          <!-- Tab 1: 原始文档 -->
          <a-tab-pane key="parsed" tab="原始文档">
            <div v-if="parsedContentText">
              <div 
                style="background: #f5f5f5; padding: 16px; border-radius: 4px; max-height: 70vh; overflow-y: auto; font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word;"
                v-html="formatMarkdown(parsedContentText)"
              ></div>
            </div>
            <a-empty v-else description="原始文档不可用" />
          </a-tab-pane>
          
          <!-- Tab 2: 摘要文档 -->
          <a-tab-pane key="summary" tab="摘要文档">
            <div v-if="summaryContentText">
              <div 
                style="background: #f5f5f5; padding: 16px; border-radius: 4px; max-height: 70vh; overflow-y: auto; font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word;"
                v-html="formatMarkdown(summaryContentText)"
              ></div>
            </div>
            <a-empty v-else description="摘要文档不可用" />
          </a-tab-pane>
          
          <!-- Tab 3: 结构化数据 -->
          <a-tab-pane key="structured" tab="结构化数据">
            <div v-if="structuredContentText">
              <pre 
                style="background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 4px; max-height: 70vh; overflow: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word;"
              >{{ structuredContentText }}</pre>
            </div>
            <a-empty v-else description="结构化数据不可用" />
          </a-tab-pane>
          
          <!-- Tab 4: 分块结果 -->
          <a-tab-pane key="chunks" tab="分块结果">
            <div v-if="chunksContentData">
              <!-- 分块统计信息 -->
              <a-descriptions title="分块信息" :column="4" bordered style="margin-bottom: 16px">
                <a-descriptions-item label="分块策略">
                  <a-tag color="blue">{{ getStrategyName(chunksContentData.strategy) }}</a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="总块数">
                  <a-tag color="green">{{ chunksContentData.total_chunks }}</a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="Max Tokens">
                  {{ chunksContentData.max_tokens }}
                </a-descriptions-item>
                <a-descriptions-item label="创建时间">
                  {{ chunksContentData.created_at ? new Date(chunksContentData.created_at).toLocaleString() : '-' }}
                </a-descriptions-item>
              </a-descriptions>
              
              <!-- 分块列表 -->
              <a-table
                :dataSource="chunksContentData.chunks || []"
                :columns="[
                  { title: '块ID', dataIndex: 'chunk_id', key: 'chunk_id', width: 100 },
                  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true }
                ]"
                :pagination="{ pageSize: 10 }"
                size="small"
                :scroll="{ y: 'calc(70vh - 200px)' }"
                rowKey="chunk_id"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'content'">
                    <a-tooltip :title="record.content">
                      <span style="max-width: 400px; display: inline-block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        {{ record.content?.substring(0, 100) }}{{ record.content?.length > 100 ? '...' : '' }}
                      </span>
                    </a-tooltip>
                  </template>
                </template>
              </a-table>
            </div>
            <a-empty v-else description="分块结果不可用（请先执行分块）" />
          </a-tab-pane>
        </a-tabs>
        <a-empty v-else description="正在加载文档详情..." />
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, h, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { RocketOutlined } from '@ant-design/icons-vue'
import RecallResultList from './RecallResultList.vue'
import Stage2ResultList from './Stage2ResultList.vue'
import GraphVisualization from '../GraphVisualization.vue'
import { getDocumentUploadList, getParsedContent, getSummaryContent, getStructuredContent, getChunks } from '../../api/documentUpload'

const props = defineProps({
  result: {
    type: Object,
    required: true
  }
})

// Tab状态管理
const stage2MainTab = ref('graphiti')
const graphitiTab = ref('graph')
const cogneeTab = ref('graph')

// 检查是否有Graphiti数据
const hasGraphitiData = (stage2) => {
  if (!stage2 || !stage2.graphiti) {
    console.log('❌ hasGraphitiData: stage2或graphiti不存在', { stage2 })
    return false
  }
  const hasEntities = stage2.graphiti.entities && stage2.graphiti.entities.length > 0
  const hasNodes = stage2.graphiti.relationship_graph && stage2.graphiti.relationship_graph.nodes && stage2.graphiti.relationship_graph.nodes.length > 0
  const result = hasEntities || hasNodes
  console.log('✅ hasGraphitiData:', { 
    hasEntities, 
    hasNodes, 
    result, 
    entityCount: stage2.graphiti.entities?.length || 0,
    nodeCount: stage2.graphiti.relationship_graph?.nodes?.length || 0,
    edgeCount: stage2.graphiti.relationship_graph?.edges?.length || 0,
    stage2: stage2.graphiti 
  })
  return result
}

// 检查是否有Cognee数据
const hasCogneeData = (stage2) => {
  if (!stage2 || !stage2.cognee) {
    console.log('❌ hasCogneeData: stage2或cognee不存在', { stage2 })
    return false
  }
  const hasEntities = stage2.cognee.entities && stage2.cognee.entities.length > 0
  const hasNodes = stage2.cognee.relationship_graph && stage2.cognee.relationship_graph.nodes && stage2.cognee.relationship_graph.nodes.length > 0
  const result = hasEntities || hasNodes
  console.log('✅ hasCogneeData:', { 
    hasEntities, 
    hasNodes, 
    result, 
    entityCount: stage2.cognee.entities?.length || 0,
    nodeCount: stage2.cognee.relationship_graph?.nodes?.length || 0,
    edgeCount: stage2.cognee.relationship_graph?.edges?.length || 0,
    stage2: stage2.cognee 
  })
  return result
}

// 获取阶段2总Entity数（Graphiti + Cognee）
const getStage2TotalEntityCount = (stage2) => {
  if (!stage2) return 0
  const graphitiCount = stage2.graphiti?.statistics?.entity_count || stage2.graphiti?.entities?.length || 0
  const cogneeCount = stage2.cognee?.statistics?.entity_count || stage2.cognee?.entities?.length || 0
  return graphitiCount + cogneeCount
}

// Chunk详情弹窗
const chunkDetailVisible = ref(false)
const chunkDetailData = ref(null)

// 查看Chunk详情
const viewChunkDetail = (chunk) => {
  chunkDetailData.value = chunk
  chunkDetailVisible.value = true
}

// 格式化分数范围
const formatScoreRange = (range) => {
  if (!range || !Array.isArray(range) || range.length < 2) {
    return 'N/A'
  }
  return `${range[0].toFixed(1)} - ${range[1].toFixed(1)}`
}

// 格式化关系图数据供GraphVisualization使用
const formatGraphDataForVisualization = (graphData) => {
  if (!graphData || !graphData.nodes || !graphData.edges) {
    return { nodes: [], edges: [] }
  }
  
  // 转换节点格式
  const nodes = graphData.nodes.map(node => ({
    id: node.id,
    labels: [node.type || 'Entity'],
    properties: {
      name: node.name,
      ...node.properties || {}
    }
  }))
  
  // 转换边格式
  const edges = graphData.edges.map(edge => ({
    source: edge.source,
    target: edge.target,
    type: edge.type,
    properties: {
      fact: edge.fact || ''
    }
  }))
  
  return { nodes, edges }
}

// 获取Entity类型颜色
const getEntityTypeColor = (type) => {
  const colorMap = {
    'Requirement': 'purple',
    'Feature': 'blue',
    'Module': 'cyan',
    'System': 'green',
    'Person': 'orange',
    'Entity': 'default'
  }
  return colorMap[type] || 'default'
}

const formatTime = (seconds) => {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`
  }
  return `${seconds.toFixed(2)}s`
}

// 调试：打印接收到的数据
onMounted(() => {
  console.log('SmartRetrievalResults 接收到的数据:', props.result)
  console.log('summary:', props.result?.summary)
  console.log('stage1:', props.result?.stage1)
  console.log('stage1 chunk_results:', props.result?.stage1?.chunk_results?.length)
})

// 文档详情相关
const documentDetailVisible = ref(false)
const documentDetailLoading = ref(false)
const documentDetailTab = ref('parsed')
const documentDetailData = ref(null)
const parsedContentText = ref('')
const summaryContentText = ref('')
const structuredContentText = ref('')
const chunksContentData = ref(null)

// 根据 group_id 查找 uploadId
const findUploadIdByGroupId = async (groupId) => {
  try {
    const response = await getDocumentUploadList(1, 100, null, null)
    const documents = response.documents || []
    // 查找匹配 group_id 的文档，优先选择最新的
    const matchedDocs = documents.filter(doc => doc.document_id === groupId)
    if (matchedDocs.length > 0) {
      // 按 id 降序排序，选择最新的
      matchedDocs.sort((a, b) => (b.id || 0) - (a.id || 0))
      return matchedDocs[0].id
    }
    return null
  } catch (error) {
    console.error('查找文档失败:', error)
    return null
  }
}

// 查看文档详情
const viewDocument = async (item) => {
  const groupId = item.group_id || item.document_id
  if (!groupId) {
    message.warning('该结果没有关联的文档')
    return
  }

  documentDetailVisible.value = true
  documentDetailData.value = item
  documentDetailTab.value = 'parsed'
  parsedContentText.value = ''
  summaryContentText.value = ''
  structuredContentText.value = ''
  chunksContentData.value = null
  documentDetailLoading.value = true

  try {
    // 根据 group_id 查找 uploadId
    const uploadId = await findUploadIdByGroupId(groupId)
    if (!uploadId) {
      throw new Error('未找到对应的文档，请确认文档已上传并处理')
    }

    // 并行加载三个内容
    const [parsedResponse, summaryResponse, structuredResponse] = await Promise.all([
      getParsedContent(uploadId),
      getSummaryContent(uploadId),
      getStructuredContent(uploadId)
    ])
    
    parsedContentText.value = parsedResponse.content || ''
    summaryContentText.value = summaryResponse.content || ''
    structuredContentText.value = structuredResponse.content 
      ? JSON.stringify(structuredResponse.content, null, 2)
      : ''
    
    // 单独加载 chunks（可能未分块，忽略错误）
    try {
      const chunksResponse = await getChunks(uploadId)
      chunksContentData.value = chunksResponse.content || null
    } catch (chunksError) {
      console.log('chunks 不可用（可能尚未分块）:', chunksError.message)
      chunksContentData.value = null
    }
  } catch (error) {
    console.error('加载文档详情失败:', error)
    message.error(`加载文档详情失败: ${error.message || '未知错误'}`)
    documentDetailVisible.value = false
  } finally {
    documentDetailLoading.value = false
  }
}

// 格式化 Markdown（简化版）
const formatMarkdown = (text) => {
  if (!text) return ''
  // 简单的 Markdown 格式化
  return text
    .replace(/\n/g, '<br>')
    .replace(/#{3}\s+(.+)/g, '<h3>$1</h3>')
    .replace(/#{2}\s+(.+)/g, '<h2>$1</h2>')
    .replace(/#{1}\s+(.+)/g, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

// 获取分块策略名称
const getStrategyName = (strategy) => {
  const strategyMap = {
    'level_1': '一级标题',
    'level_2': '二级标题',
    'fixed_token': '固定Token',
    'no_split': '不分块'
  }
  return strategyMap[strategy] || strategy
}
</script>

<style scoped>
.smart-retrieval-results {
  width: 100%;
}

.stats-card {
  margin-bottom: 24px;
}

.stage-card {
  margin-bottom: 24px;
}

.time-value {
  font-size: 14px;
  font-weight: 600;
  color: #1890ff;
}

.time-value.total {
  color: #52c41a;
  font-size: 16px;
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: #1890ff;
}
</style>

