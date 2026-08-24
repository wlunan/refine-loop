<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  DashboardOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()

const selectedKeys = computed(() => {
  if (route.path === '/') return ['workbench']
  if (route.path.startsWith('/tasks')) return ['tasks']
  return []
})

function handleMenuClick({ key }: { key: string }) {
  if (key === 'workbench') router.push('/')
  if (key === 'tasks') router.push('/tasks')
}
</script>

<template>
  <a-layout-sider
    width="200"
    class="app-sider"
    :style="{ background: '#fff' }"
  >
    <a-menu
      mode="inline"
      :selected-keys="selectedKeys"
      @click="handleMenuClick"
      class="sider-menu"
    >
      <a-menu-item key="workbench">
        <template #icon>
          <DashboardOutlined />
        </template>
        工作台
      </a-menu-item>
      <a-menu-item key="tasks">
        <template #icon>
          <UnorderedListOutlined />
        </template>
        任务管理
      </a-menu-item>
    </a-menu>
  </a-layout-sider>
</template>

<style scoped>
.app-sider {
  border-right: 1px solid #f0f0f0;
}

.sider-menu {
  border-inline-end: none;
  padding-top: 8px;
}
</style>
