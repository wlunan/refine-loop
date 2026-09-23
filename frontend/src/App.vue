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
  <a-config-provider>
    <a-layout class="app-layout">
      <AppHeader />
      <a-layout class="body-layout">
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
  background: var(--c-bg);
}

.body-layout {
  background: var(--c-bg);
}

.main-content {
  padding: var(--sp-6);
  background: var(--c-bg);
  overflow-y: auto;
  min-height: calc(100vh - var(--header-h));
  min-width: 0;
}

@media (max-width: 760px) {
  .body-layout {
    flex-direction: column;
  }

  .main-content {
    width: 100% !important;
    padding: var(--sp-3);
    min-height: calc(100vh - var(--header-h) - 56px);
  }
}
</style>
