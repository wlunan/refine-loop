<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  CloseCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons-vue'

interface SubTask {
  id: string
  title: string
  description: string
  status: string
  dependencies: string[]
  score: number | null
  iterations: number
  error: string | null
}

const props = defineProps<{
  subtasks: SubTask[]
}>()

function getStatusIcon(status: string) {
  switch (status) {
    case 'completed': return CheckCircleOutlined
    case 'running': return LoadingOutlined
    case 'failed': return CloseCircleOutlined
    case 'paused': return PauseCircleOutlined
    default: return ClockCircleOutlined
  }
}

function getStatusColor(status: string) {
  switch (status) {
    case 'completed': return '#52c41a'
    case 'running': return '#1890ff'
    case 'failed': return '#ff4d4f'
    case 'paused': return '#faad14'
    default: return '#d9d9d9'
  }
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
  <a-list :data-source="subtasks" item-layout="horizontal">
    <template #renderItem="{ item }">
      <a-list-item>
        <a-list-item-meta>
          <template #avatar>
            <a-avatar
              :style="{ backgroundColor: getStatusColor(item.status) }"
              size="small"
            >
              <template #icon>
                <component :is="getStatusIcon(item.status)" />
              </template>
            </a-avatar>
          </template>
          <template #title>
            <a-space>
              <span>{{ item.title }}</span>
              <a-tag :color="getStatusColor(item.status)" size="small">
                {{ getStatusText(item.status) }}
              </a-tag>
            </a-space>
          </template>
          <template #description>
            <div>
              <a-typography-paragraph
                :ellipsis="{ rows: 2 }"
                style="margin-bottom: 8px;"
              >
                {{ item.description }}
              </a-typography-paragraph>
              <a-space v-if="item.dependencies.length > 0" size="small">
                <span style="font-size: 12px; color: #888;">依赖:</span>
                <a-tag v-for="dep in item.dependencies" :key="dep" size="small">
                  {{ dep }}
                </a-tag>
              </a-space>
            </div>
          </template>
        </a-list-item-meta>
        <template #extra>
          <a-space direction="vertical" :size="4" style="text-align: right;">
            <a-statistic
              v-if="item.score !== null"
              title="评分"
              :value="item.score"
              :value-style="{
                fontSize: '16px',
                color: item.score >= 85 ? '#52c41a' : item.score >= 70 ? '#1890ff' : '#ff4d4f',
              }"
            />
            <div v-if="item.iterations > 0" style="font-size: 12px; color: #888;">
              迭代 {{ item.iterations }} 轮
            </div>
            <a-typography-text
              v-if="item.error"
              type="danger"
              style="font-size: 12px;"
            >
              {{ item.error }}
            </a-typography-text>
          </a-space>
        </template>
      </a-list-item>
    </template>
  </a-list>
</template>
