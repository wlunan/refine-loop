<script setup lang="ts">
import { BulbOutlined, BulbFilled } from '@ant-design/icons-vue'
import { useThemeStore } from '../../stores/theme'

const themeStore = useThemeStore()
</script>

<template>
  <a-layout-header class="app-header">
    <div class="header-left">
      <div class="logo">
        <span class="logo-icon">⚡</span>
        <span class="logo-text">Generator-Critic</span>
      </div>
    </div>
    <div class="header-right">
      <a-space>
        <a-tag color="processing">多 Agent 工作台</a-tag>
        <a-button
          type="text"
          @click="themeStore.toggle()"
          class="theme-toggle"
        >
          <template #icon>
            <BulbFilled v-if="themeStore.isDark" style="color: #fadb14" />
            <BulbOutlined v-else />
          </template>
        </a-button>
      </a-space>
    </div>
  </a-layout-header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: linear-gradient(135deg, #17152e 0%, #2b2563 55%, #4f46e5 130%);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.14);
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 24px;
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  align-items: center;
}

.theme-toggle {
  color: rgba(255, 255, 255, 0.85);
  font-size: 18px;
}

.theme-toggle:hover {
  color: #fff;
}
</style>
