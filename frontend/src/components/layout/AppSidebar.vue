<script setup lang="ts">
import { computed } from 'vue'
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

const menuItems = [
  { key: 'workbench', icon: DashboardOutlined, label: '新建任务', path: '/' },
  { key: 'tasks', icon: UnorderedListOutlined, label: '任务中心', path: '/tasks' },
]

function navigate(key: string) {
  const item = menuItems.find((m) => m.key === key)
  if (item) router.push(item.path)
}
</script>

<template>
  <a-layout-sider :width="220" class="sidebar">
    <nav class="sidebar-nav">
      <button
        v-for="item in menuItems"
        :key="item.key"
        class="nav-item"
        :class="{ active: selectedKeys.includes(item.key) }"
        @click="navigate(item.key)"
      >
        <component :is="item.icon" class="nav-icon" />
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </nav>
    <div class="sidebar-footer">
      <div class="footer-hint">
        <span class="hint-dot"></span>
        <span class="hint-text">多 Agent 协作</span>
      </div>
    </div>
  </a-layout-sider>
</template>

<style scoped>
.sidebar {
  background: var(--c-surface) !important;
  border-right: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: calc(100vh - var(--header-h));
  position: sticky;
  top: var(--header-h);
}

.sidebar-nav {
  padding: var(--sp-4) var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border: none;
  background: transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  color: var(--c-text-2);
  font-size: var(--text-base);
  font-family: inherit;
  transition: all 0.15s ease;
  text-align: left;
}

.nav-item:hover {
  background: var(--c-surface-2);
  color: var(--c-text);
}

.nav-item.active {
  background: var(--c-accent-soft);
  color: var(--c-accent);
  font-weight: 500;
}

.nav-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.nav-label {
  line-height: 1;
}

.sidebar-footer {
  padding: var(--sp-4) var(--sp-6);
  border-top: 1px solid var(--c-border);
}

.footer-hint {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--text-xs);
  color: var(--c-text-3);
}

.hint-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-success);
  flex-shrink: 0;
}

.hint-text {
  line-height: 1;
}

@media (max-width: 760px) {
  .sidebar {
    width: 100% !important;
    min-width: 100% !important;
    max-width: 100% !important;
    flex: 0 0 56px !important;
    height: 56px;
    position: sticky;
    top: var(--header-h);
    z-index: 90;
    border-right: 0;
    border-bottom: 1px solid var(--c-border);
  }

  .sidebar-nav {
    height: 100%;
    padding: 6px var(--sp-3);
    flex-direction: row;
    gap: var(--sp-2);
  }

  .nav-item {
    min-height: 44px;
    justify-content: center;
    padding: var(--sp-2) var(--sp-3);
    text-align: center;
  }

  .sidebar-footer {
    display: none;
  }
}
</style>
