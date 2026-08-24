<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { SendOutlined, ClearOutlined } from '@ant-design/icons-vue'
import { useSSE } from '../composables/useSSE'
import ScoreChart from '../components/workbench/ScoreChart.vue'

const { connected, events, connect, disconnect, clearEvents } = useSSE()

const form = reactive({
  task: '',
  domain: 'code',
  maxRounds: 5,
  threshold: 85,
})

const rounds = ref<any[]>([])
const currentRound = ref(0)
const isRunning = ref(false)
const finalOutput = ref('')

function handleSubmit() {
  if (!form.task.trim()) {
    message.warning('请输入任务描述')
    return
  }

  rounds.value = []
  currentRound.value = 0
  finalOutput.value = ''
  isRunning.value = true
  clearEvents()

  const params = new URLSearchParams({
    task: form.task,
    domain: form.domain,
    max_rounds: String(form.maxRounds),
    threshold: String(form.threshold),
  })

  connect(`/api/stream?${params}`, handleEvent)
}

function handleEvent(data: any) {
  switch (data.type) {
    case 'token':
      // 流式 token，可以实时显示
      break
    case 'critic':
      currentRound.value = data.round
      rounds.value.push({
        round: data.round,
        score: data.score,
        acceptable: data.acceptable,
        issues: data.issues,
        suggestions: data.suggestions,
        summary: data.summary,
      })
      break
    case 'done':
      finalOutput.value = data.final_output
      isRunning.value = false
      message.success('迭代完成！')
      break
    case 'error':
      message.error(data.message)
      isRunning.value = false
      break
    case 'end':
      isRunning.value = false
      break
  }
}

function handleStop() {
  disconnect()
  isRunning.value = false
  message.info('已停止')
}

function handleClear() {
  rounds.value = []
  currentRound.value = 0
  finalOutput.value = ''
  clearEvents()
}

const scoreData = ref([
  { round: 1, score: 65 },
  { round: 2, score: 78 },
  { round: 3, score: 88 },
])
</script>

<template>
  <div class="workbench">
    <a-row :gutter="24">
      <!-- 左侧：输入面板 -->
      <a-col :span="8">
        <a-card title="任务配置" class="config-card">
          <a-form
            :model="form"
            layout="vertical"
            @finish="handleSubmit"
          >
            <a-form-item label="任务描述" name="task">
              <a-textarea
                v-model:value="form.task"
                :rows="4"
                placeholder="描述你的任务，例如：写一篇关于人工智能的文章"
              />
            </a-form-item>

            <a-form-item label="领域" name="domain">
              <a-select v-model:value="form.domain">
                <a-select-option value="code">代码开发</a-select-option>
                <a-select-option value="writing">文案写作</a-select-option>
                <a-select-option value="design">方案设计</a-select-option>
                <a-select-option value="general">通用</a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="最大迭代轮数" name="maxRounds">
              <a-input-number
                v-model:value="form.maxRounds"
                :min="1"
                :max="20"
                style="width: 100%"
              />
            </a-form-item>

            <a-form-item label="收敛阈值" name="threshold">
              <a-slider
                v-model:value="form.threshold"
                :min="60"
                :max="100"
                :marks="{ 60: '60', 70: '70', 85: '85', 100: '100' }"
              />
            </a-form-item>

            <a-form-item>
              <a-space>
                <a-button
                  type="primary"
                  html-type="submit"
                  :loading="isRunning"
                  :disabled="isRunning"
                >
                  <template #icon><SendOutlined /></template>
                  开始迭代
                </a-button>
                <a-button
                  v-if="isRunning"
                  danger
                  @click="handleStop"
                >
                  停止
                </a-button>
                <a-button @click="handleClear">
                  <template #icon><ClearOutlined /></template>
                  清空
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>

        <!-- 评分趋势图 -->
        <a-card title="评分趋势" class="chart-card">
          <ScoreChart :data="rounds" />
        </a-card>
      </a-col>

      <!-- 右侧：结果面板 -->
      <a-col :span="16">
        <a-card title="迭代过程" class="result-card">
          <div v-if="rounds.length === 0 && !isRunning" class="empty-state">
            <a-empty description="暂无迭代记录，请输入任务开始" />
          </div>

          <a-spin :spinning="isRunning" tip="正在迭代中...">
            <a-timeline v-if="rounds.length > 0">
              <a-timeline-item
                v-for="round in rounds"
                :key="round.round"
                :color="round.acceptable ? 'green' : round.score >= 70 ? 'blue' : 'red'"
              >
                <template #dot>
                  <a-badge
                    :count="round.score"
                    :number-style="{
                      backgroundColor: round.acceptable ? '#52c41a' : round.score >= 70 ? '#1890ff' : '#ff4d4f',
                      fontSize: '12px',
                    }"
                  />
                </template>
                <a-card size="small" class="round-card">
                  <template #title>
                    <a-space>
                      <span>第 {{ round.round }} 轮</span>
                      <a-tag :color="round.acceptable ? 'success' : 'warning'">
                        {{ round.acceptable ? '已收敛' : '继续优化' }}
                      </a-tag>
                    </a-space>
                  </template>

                  <a-descriptions :column="1" size="small">
                    <a-descriptions-item label="评分">
                      <a-progress
                        :percent="round.score"
                        :stroke-color="round.score >= 85 ? '#52c41a' : round.score >= 70 ? '#1890ff' : '#ff4d4f'"
                        size="small"
                      />
                    </a-descriptions-item>
                    <a-descriptions-item v-if="round.issues?.length" label="问题">
                      <a-list size="small" :data-source="round.issues">
                        <template #renderItem="{ item }">
                          <a-list-item>
                            <a-typography-text type="danger">• {{ item }}</a-typography-text>
                          </a-list-item>
                        </template>
                      </a-list>
                    </a-descriptions-item>
                    <a-descriptions-item v-if="round.suggestions?.length" label="建议">
                      <a-list size="small" :data-source="round.suggestions">
                        <template #renderItem="{ item }">
                          <a-list-item>
                            <a-typography-text type="success">• {{ item }}</a-typography-text>
                          </a-list-item>
                        </template>
                      </a-list>
                    </a-descriptions-item>
                    <a-descriptions-item v-if="round.summary" label="总结">
                      {{ round.summary }}
                    </a-descriptions-item>
                  </a-descriptions>
                </a-card>
              </a-timeline-item>
            </a-timeline>
          </a-spin>
        </a-card>

        <!-- 最终产出 -->
        <a-card v-if="finalOutput" title="最终产出" class="output-card">
          <a-typography-paragraph>
            <pre class="output-content">{{ finalOutput }}</pre>
          </a-typography-paragraph>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.workbench {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card,
.chart-card,
.result-card,
.output-card {
  margin-bottom: 24px;
}

.round-card {
  margin-bottom: 0;
}

.empty-state {
  padding: 40px 0;
}

.output-content {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 500px;
  overflow-y: auto;
}
</style>
