<script setup lang="ts">
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined, LeftOutlined, ReloadOutlined } from '@ant-design/icons-vue'

interface BrowseResult {
  path: string
  parent: string | null
  exists: boolean
  dirs: string[]
}

const emit = defineEmits<{ select: [path: string] }>()
const open = ref(false)
const loading = ref(false)
const current = ref<BrowseResult>({ path: '', parent: null, exists: true, dirs: [] })

async function browse(path = '') {
  loading.value = true
  try {
    const response = await fetch(`/api/browse_dir?path=${encodeURIComponent(path)}`)
    if (!response.ok) throw new Error('目录读取失败')
    current.value = await response.json()
  } catch (error: any) {
    message.error(error.message || '无法读取目录')
  } finally {
    loading.value = false
  }
}

function show() {
  open.value = true
  browse()
}

function openDir(name: string) {
  if (!current.value.path) {
    browse(name)
    return
  }
  const separator = current.value.path.includes('\\') ? '\\' : '/'
  browse(`${current.value.path}${separator}${name}`)
}

function selectCurrent() {
  if (!current.value.path) {
    message.warning('请先进入一个目录')
    return
  }
  emit('select', current.value.path)
  open.value = false
}
</script>

<template>
  <a-button block @click="show">
    <template #icon><FolderOpenOutlined /></template>
    浏览工作区
  </a-button>
  <a-modal v-model:open="open" title="选择工作区" :footer="null" :width="620">
    <div class="toolbar">
      <a-button :disabled="!current.parent" @click="browse(current.parent || '')"><template #icon><LeftOutlined /></template>上一级</a-button>
      <a-button @click="browse(current.path)"><template #icon><ReloadOutlined /></template>刷新</a-button>
      <code>{{ current.path || '请选择磁盘' }}</code>
    </div>
    <a-spin :spinning="loading"><div class="directory-list">
      <button v-for="directory in current.dirs" :key="directory" class="directory-row" @click="openDir(directory)"><FolderOpenOutlined /><span>{{ directory }}</span></button>
      <a-empty v-if="!loading && current.dirs.length === 0" description="此目录为空" />
    </div></a-spin>
    <div class="footer"><span>Agent 的文件操作将限定在此目录内。</span><a-button type="primary" :disabled="!current.path" @click="selectCurrent">使用此目录</a-button></div>
  </a-modal>
</template>

<style scoped>
.toolbar{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-4)}.toolbar code{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--c-text-2);background:var(--c-surface-2);border:1px solid var(--c-border);border-radius:var(--r-sm);padding:6px 8px;font-size:var(--text-xs)}
.directory-list{min-height:280px;max-height:420px;overflow:auto;border:1px solid var(--c-border);border-radius:var(--r-md);padding:var(--sp-2);background:var(--c-surface-2)}.directory-row{display:flex;align-items:center;gap:var(--sp-3);width:100%;padding:10px 12px;border:0;border-radius:var(--r-sm);background:transparent;color:var(--c-text);font:inherit;text-align:left;cursor:pointer}.directory-row:hover{background:var(--c-accent-soft);color:var(--c-accent)}
.footer{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-4);padding-top:var(--sp-4);font-size:var(--text-xs);color:var(--c-text-3)}
</style>
