<script setup lang="ts">
import { computed } from 'vue'

interface Task {
  id: string
  status: string
  progress_percent: number
  total_tokens: number
  error: string | null
}

const props = defineProps<{
  task: Task
}>()

const statusColor = computed(() => {
  switch (props.task.status) {
    case 'running': return '#1890ff'
    case 'completed': return '#52c41a'
    case 'failed': return '#ff4d4f'
    case 'paused': return '#faad14'
    default: return '#d9d9d9'
  }
})

const statusText = computed(() => {
  const texts: Record<string, string> = {
    pending: '等待中',
    planning: '规划中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return texts[props.task.status] || props.task.status
})
</script>

<template>
  <a-card class="progress-card" :bordered="false">
    <a-row :gutter="24" align="middle">
      <a-col :span="16">
        <a-progress
          :percent="task.progress_percent"
          :stroke-color="statusColor"
          :status="task.status === 'failed' ? 'exception' : undefined"
        >
          <template #format="{ percent }">
            <span style="font-size: 24px; font-weight: 600;">
              {{ percent?.toFixed(1) }}%
            </span>
          </template>
        </a-progress>
      </a-col>
      <a-col :span="8" style="text-align: right;">
        <a-space direction="vertical" :size="4">
          <a-tag :color="statusColor" style="font-size: 14px;">
            {{ statusText }}
          </a-tag>
          <a-statistic
            title="Token 消耗"
            :value="task.total_tokens"
            :value-style="{ fontSize: '16px' }"
          />
        </a-space>
      </a-col>
    </a-row>
    <a-alert
      v-if="task.error"
      :message="task.error"
      type="error"
      show-icon
      style="margin-top: 16px;"
    />
  </a-card>
</template>

<style scoped>
.progress-card {
  margin-bottom: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
}
</style>
