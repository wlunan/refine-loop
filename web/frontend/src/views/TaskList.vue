<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { useTaskStore } from '../stores/task'

const router = useRouter()
const taskStore = useTaskStore()

const showCreateModal = ref(false)
const createForm = ref({
  requirement: '',
  workspaceDir: '',
  domain: 'code',
})

const statusFilter = ref<string | undefined>(undefined)

onMounted(() => {
  taskStore.fetchTasks()
})

function handleCreate() {
  if (!createForm.value.requirement.trim()) {
    message.warning('请输入需求描述')
    return
  }
  if (!createForm.value.workspaceDir.trim()) {
    message.warning('请输入工作目录')
    return
  }

  taskStore.createTask(
    createForm.value.requirement,
    createForm.value.workspaceDir,
    createForm.value.domain
  ).then((result) => {
    message.success(`任务已创建: ${result.task_id}`)
    showCreateModal.value = false
    createForm.value = { requirement: '', workspaceDir: '', domain: 'code' }
  }).catch((e) => {
    message.error(e.message)
  })
}

function handleStart(id: string) {
  Modal.confirm({
    title: '确认启动',
    content: '确定要启动这个任务吗？',
    onOk: () => {
      taskStore.startTask(id).then(() => {
        message.success('任务已启动')
      })
    },
  })
}

function handlePause(id: string) {
  taskStore.pauseTask(id).then(() => {
    message.success('任务已暂停')
  })
}

function handleResume(id: string) {
  taskStore.resumeTask(id).then(() => {
    message.success('任务已恢复')
  })
}

function handleCancel(id: string) {
  Modal.confirm({
    title: '确认取消',
    content: '确定要取消这个任务吗？此操作不可撤销。',
    okType: 'danger',
    onOk: () => {
      taskStore.cancelTask(id).then(() => {
        message.success('任务已取消')
      })
    },
  })
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

function handleFilterChange(value: string) {
  statusFilter.value = value || undefined
  taskStore.fetchTasks(statusFilter.value)
}
</script>

<template>
  <div class="task-list-page">
    <a-card>
      <template #title>
        <a-space>
          <span>任务管理</span>
          <a-button type="primary" @click="showCreateModal = true">
            <template #icon><PlusOutlined /></template>
            创建任务
          </a-button>
        </a-space>
      </template>
      <template #extra>
        <a-space>
          <a-select
            v-model:value="statusFilter"
            placeholder="筛选状态"
            allow-clear
            style="width: 120px"
            @change="handleFilterChange"
          >
            <a-select-option value="">全部</a-select-option>
            <a-select-option value="pending">等待中</a-select-option>
            <a-select-option value="running">运行中</a-select-option>
            <a-select-option value="paused">已暂停</a-select-option>
            <a-select-option value="completed">已完成</a-select-option>
            <a-select-option value="failed">失败</a-select-option>
          </a-select>
          <a-button @click="taskStore.fetchTasks(statusFilter)">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </a-space>
      </template>

      <a-spin :spinning="taskStore.loading">
        <a-empty v-if="taskStore.tasks.length === 0" description="暂无任务" />

        <a-row :gutter="[16, 16]" v-else>
          <a-col
            v-for="task in taskStore.tasks"
            :key="task.id"
            :xs="24"
            :sm="12"
            :lg="8"
          >
            <a-card
              hoverable
              class="task-card"
              @click="router.push(`/tasks/${task.id}`)"
            >
              <template #title>
                <a-space>
                  <a-tag :color="getStatusColor(task.status)">
                    {{ getStatusText(task.status) }}
                  </a-tag>
                  <span class="task-id">{{ task.id }}</span>
                </a-space>
              </template>
              <template #extra>
                <a-dropdown :trigger="['click']" @click.stop>
                  <a-button type="text" size="small">
                    操作
                  </a-button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item
                        v-if="task.status === 'pending'"
                        @click.stop="handleStart(task.id)"
                      >
                        <PlayCircleOutlined /> 启动
                      </a-menu-item>
                      <a-menu-item
                        v-if="task.status === 'running'"
                        @click.stop="handlePause(task.id)"
                      >
                        <PauseCircleOutlined /> 暂停
                      </a-menu-item>
                      <a-menu-item
                        v-if="task.status === 'paused'"
                        @click.stop="handleResume(task.id)"
                      >
                        <PlayCircleOutlined /> 恢复
                      </a-menu-item>
                      <a-menu-item
                        v-if="!['completed', 'cancelled'].includes(task.status)"
                        @click.stop="handleCancel(task.id)"
                        danger
                      >
                        <StopOutlined /> 取消
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </template>

              <a-typography-paragraph
                :ellipsis="{ rows: 2 }"
                class="task-title"
              >
                {{ task.title }}
              </a-typography-paragraph>

              <a-progress
                :percent="task.progress_percent"
                :status="task.status === 'failed' ? 'exception' : undefined"
                size="small"
              />

              <div class="task-meta">
                <span>子任务: {{ task.completed_subtasks }}/{{ task.subtask_count }}</span>
                <span>{{ new Date(task.created_at).toLocaleDateString() }}</span>
              </div>
            </a-card>
          </a-col>
        </a-row>
      </a-spin>
    </a-card>

    <!-- 创建任务弹窗 -->
    <a-modal
      v-model:open="showCreateModal"
      title="创建新任务"
      @ok="handleCreate"
      ok-text="创建"
      cancel-text="取消"
    >
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="需求描述" required>
          <a-textarea
            v-model:value="createForm.requirement"
            :rows="4"
            placeholder="详细描述你的开发需求"
          />
        </a-form-item>
        <a-form-item label="工作目录" required>
          <a-input
            v-model:value="createForm.workspaceDir"
            placeholder="例如：E:\projects\my-app"
          />
        </a-form-item>
        <a-form-item label="任务领域">
          <a-select v-model:value="createForm.domain">
            <a-select-option value="code">代码开发</a-select-option>
            <a-select-option value="writing">文案写作</a-select-option>
            <a-select-option value="design">方案设计</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.task-list-page {
  max-width: 1200px;
  margin: 0 auto;
}

.task-card {
  height: 100%;
}

.task-title {
  margin-bottom: 12px;
}

.task-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 12px;
  color: #888;
}

.task-id {
  font-size: 12px;
  color: #888;
}
</style>
