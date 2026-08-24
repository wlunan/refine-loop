import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)

  function toggle() {
    isDark.value = !isDark.value
  }

  function setDark(value: boolean) {
    isDark.value = value
  }

  // 持久化到 localStorage
  watch(isDark, (value) => {
    localStorage.setItem('theme', value ? 'dark' : 'light')
    document.documentElement.setAttribute('data-theme', value ? 'dark' : 'light')
  })

  // 初始化
  function init() {
    const saved = localStorage.getItem('theme')
    if (saved) {
      isDark.value = saved === 'dark'
    } else {
      isDark.value = window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
  }

  return {
    isDark,
    toggle,
    setDark,
    init,
  }
})
