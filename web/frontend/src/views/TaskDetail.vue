<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { useTaskStore } from '../stores/task'
import { useSSE } from '../composables/useSSE'
import SubTaskList from '../components/task/SubTaskList.vue'
import TaskProgress from '../components/task/TaskProgress.vue'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const { connected, events, connect, disconnect } = useSSE()

const taskId = route.params.id as string
const logs = ref<string[]>([])

onMounted(async () => {
  await taskStore.fetchTask(taskId)

  if (taskStore.currentTask?.status === 'running') {
    startSSE()
  }
})

onUnmounted(() => {
  disconnect()
})

function startSSE() {
  connect(`/api/tasks/${taskId}/events`, handleEvent)
}

function handleEvent(data: any) {
  const timestamp = new Date().toLocaleTimeString()

  switch (data.type) {
    case 'task_started':
      logs.value.push(`[${timestamp}] 任务开始执行`)
      break
    case 'task_planning':
      logs.value.push(`[${timestamp}] 正在分析需求...`)
      break
    case 'task_planned':
      logs.value.push(`[${timestamp}] 任务分解完成: ${data.subtask_count} 个子任务`)
      break
    case 'subtask_started':
      logs.value.push(`[${timestamp}] 子任务开始: ${data.title}`)
      break
    case 'subtask_progress':
      logs.value.push(`[${timestamp}] 第 ${data.round} 轮完成，评分: ${data.score}`)
      break
    case 'subtask_completed':
      logs.value.push(`[${timestamp}] 子任务完成，评分: ${data.score}`)
      taskStore.fetchTask(taskId)
      break
    case 'subtask_failed':
      logs.value.push(`[${timestamp}] 子任务失败: ${data.error}`)
      break
    case 'task_completed':
      logs.value.push(`[${timestamp}] 任务已完成！`)
      taskStore.fetchTask(taskId)
      disconnect()
      break
    case 'task_failed':
      logs.value.push(`[${timestamp}] 任务失败: ${data.error}`)
      taskStore.fetchTask(taskId)
      disconnect()
      break
  }

  // 自动滚动到底部
  setTimeout(() => {
    const container = document.getElementById('log-container')
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, 100)
}

async function handleStart() {
  await taskStore.startTask(taskId)
  message.success('任务已启动')
  startSSE()
  taskStore.fetchTask(taskId)
}

async function handlePause() {
  await taskStore.pauseTask(taskId)
  message.success('任务已暂停')
  disconnect()
  taskStore.fetchTask(taskId)
}

async function handleResume() {
  await taskStore.resumeTask(taskId)
  message.success('任务已恢复')
  startSSE()
  taskStore.fetchTask(taskId)
}

async function handleCancel() {
  await taskStore.cancelTask(taskId)
  message.success('任务已取消')
  disconnect()
  taskStore.fetchTask(taskId)
}

function getStatusColor(status: string) {
  const colors: Record<string, string> = {
    pending: 'default',
    planning: 'processing',
    running: 'processing',
    paused: 'warning',
    completed: 'success',
    failed: 'error',
    cancelled: 'default',
  }
  return colors[status] || 'default'
}

function getStatusText(status: string) {
  const texts: Record<string, string> = {
    pending: '等待中',
    planning: '规划中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return texts[status] || status
}
</script>

<template>
  <div class="task-detail-page">
    <a-spin :spinning="taskStore.loading">
      <template v-if="taskStore.currentTask">
        <a-page-header
          :title="taskStore.currentTask.title"
          @back="router.push('/tasks')"
        >
          <template #extra>
            <a-space>
              <a-tag :color="getStatusColor(taskStore.currentTask.status)">
                {{ getStatusText(taskStore.currentTask.status) }}
              </a-tag>
              <a-button
                v-if="taskStore.currentTask.status === 'pending'"
                type="primary"
                @click="handleStart"
              >
                <template #icon><PlayCircleOutlined /></template>
                启动
              </a-button>
              <a-button
                v-if="taskStore.currentTask.status === 'running'"
                @click="handlePause"
              >
                <template #icon><PauseCircleOutlined /></template>
                暂停
              </a-button>
              <a-button
                v-if="taskStore.currentTask.status === 'paused'"
                type="primary"
                @click="handleResume"
              >
                <template #icon><PlayCircleOutlined /></template>
                恢复
              </a-button>
              <a-button
                v-if="!['completed', 'cancelled'].includes(taskStore.currentTask.status)"
                danger
                @click="handleCancel"
              >
                <template #icon><StopOutlined /></template>
                取消
              </a-button>
            </a-space>
          </template>
        </a-page-header>

        <a-row :gutter="24">
          <!-- 左侧：进度和子任务 -->
          <a-col :span="16">
            <!-- 进度卡片 -->
            <TaskProgress :task="taskStore.currentTask" />

            <!-- 子任务列表 -->
            <a-card title="子任务列表" class="section-card">
              <SubTaskList :subtasks="taskStore.currentTask.subtasks || []" />
            </a-card>
          </a-col>

          <!-- 右侧：任务信息和日志 -->
          <a-col :span="8">
            <!-- 任务信息 -->
            <a-card title="任务信息" class="section-card">
              <a-descriptions :column="1" size="small">
                <a-descriptions-item label="任务 ID">
                  {{ taskStore.currentTask.id }}
                </a-descriptions-item>
                <a-descriptions-item label="工作目录">
                  <a-typography-text code>
                    {{ taskStore.currentTask.workspace_dir }}
                  </a-typography-text>
                </a-descriptions-item>
                <a-descriptions-item label="领域">
                  <a-tag>{{ taskStore.currentTask.domain }}</a-tag>
                </a-descriptions-item>
                <a-descriptions-item label="Token 消耗">
                  <a-statistic
                    :value="taskStore.currentTask.total_tokens"
                    :value-style="{ fontSize: '16px' }"
                  />
                </a-descriptions-item>
                <a-descriptions-item label="创建时间">
                  {{ new Date(taskStore.currentTask.created_at).toLocaleString() }}
                </a-descriptions-item>
                <a-descriptions-item
                  v-if="taskStore.currentTask.error"
                  label="错误信息"
                >
                  <a-typography-text type="danger">
                    {{ taskStore.currentTask.error }}
                  </a-typography-text>
                </a-descriptions-item>
              </a-descriptions>
            </a-card>

            <!-- 实时日志 -->
            <a-card title="实时日志" class="section-card">
              <div id="log-container" class="log-container">
                <div v-if="logs.length === 0" class="log-empty">
                  暂无日志
                </div>
                <div
                  v-for="(log, index) in logs"
                  :key="index"
                  class="log-entry"
                >
                  {{ log }}
                </div>
              </div>
            </a-card>
          </a-col>
        </a-row>
      </template>
    </a-spin>
  </div>
</template>

<style scoped>
.task-detail-page {
  max-width: 1400px;
  margin: 0 auto;
}

.section-card {
  margin-bottom: 24px;
}

.log-container {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  max-height: 400px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-empty {
  color: #666;
  text-align: center;
  padding: 20px;
}

.log-entry {
  padding: 2px 0;
  border-bottom: 1px solid #333;
}

.log-entry:last-child {
  border-bottom: none;
}
</style>
