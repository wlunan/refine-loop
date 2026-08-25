<script setup lang="ts">
import { BulbOutlined, BulbFilled } from '@ant-design/icons-vue'
import { useThemeStore } from '../../stores/theme'

const themeStore = useThemeStore()
</script>

<template>
  <a-layout-header class="header">
    <div class="header-brand">
      <div class="brand-mark">G</div>
      <span class="brand-name">Generator-Critic</span>
      <span class="brand-tag">Workbench</span>
    </div>
    <div class="header-actions">
      <a-button
        type="text"
        size="small"
        @click="themeStore.toggle()"
        class="theme-btn"
      >
        <template #icon>
          <BulbFilled v-if="themeStore.isDark" />
          <BulbOutlined v-else />
        </template>
      </a-button>
    </div>
  </a-layout-header>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-h);
  padding: 0 var(--sp-6);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  box-shadow: var(--shadow-xs);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  background: var(--c-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: var(--text-sm);
  letter-spacing: -0.5px;
}

.brand-name {
  font-weight: 600;
  font-size: var(--text-md);
  color: var(--c-text);
}

.brand-tag {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  padding: 1px 6px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  line-height: 1.4;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.theme-btn {
  color: var(--c-text-3);
  width: 32px;
  height: 32px;
}

.theme-btn:hover {
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
</style>
