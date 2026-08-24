<script setup lang="ts">
import { onMounted } from 'vue'
import { useThemeStore } from './stores/theme'
import AppHeader from './components/layout/AppHeader.vue'
import AppSidebar from './components/layout/AppSidebar.vue'

const themeStore = useThemeStore()

onMounted(() => {
  themeStore.init()
})
</script>

<template>
  <a-config-provider
    :theme="{
      algorithm: themeStore.isDark
        ? undefined
        : undefined,
    }"
  >
    <a-layout class="app-layout">
      <AppHeader />
      <a-layout>
        <AppSidebar />
        <a-layout-content class="main-content">
          <router-view />
        </a-layout-content>
      </a-layout>
    </a-layout>
  </a-config-provider>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.main-content {
  padding: 24px;
  background: var(--bg-color, #f5f5f5);
  overflow-y: auto;
}
</style>
