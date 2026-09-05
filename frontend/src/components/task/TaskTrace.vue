<script setup lang="ts">
import { ref } from 'vue'
import { taskApi } from '../../api/task'
import type { TaskArtifactRef, TaskTraceEvent } from '../../stores/task'

interface TraceArtifact {
  id: string
  content_type: string
  content: unknown
}

const props = defineProps<{
  taskId: string
  events: TaskTraceEvent[]
}>()

const expandedEventId = ref<string | null>(null)
const artifactContents = ref<Record<string, TraceArtifact | null>>({})
const loadingArtifacts = ref<Set<string>>(new Set())

const categoryLabel: Record<string, string> = {
  llm: '模型',
  tool: '工具',
  verification: '验证',
  decision: '决策',
}

function eventKey(event: TaskTraceEvent, index: number) {
  return event.id || `${event.created_at}-${index}`
}

function formatContent(content: unknown) {
  return typeof content === 'string' ? content : JSON.stringify(content, null, 2)
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

async function toggleEvent(event: TaskTraceEvent, index: number) {
  const key = eventKey(event, index)
  expandedEventId.value = expandedEventId.value === key ? null : key
  if (expandedEventId.value !== key) return
  await Promise.all((event.artifacts || []).map(loadArtifact))
}

async function loadArtifact(artifact: TaskArtifactRef) {
  if (artifactContents.value[artifact.id] !== undefined || loadingArtifacts.value.has(artifact.id)) return
  loadingArtifacts.value.add(artifact.id)
  try {
    artifactContents.value[artifact.id] = await taskApi.getTraceArtifact(props.taskId, artifact.id)
  } catch {
    artifactContents.value[artifact.id] = null
  } finally {
    loadingArtifacts.value.delete(artifact.id)
  }
}
</script>

<template>
  <section class="trace-panel">
    <div class="trace-header">
      <span class="trace-title">执行 Trace</span>
      <span class="trace-count">{{ events.length }}</span>
    </div>
    <div class="trace-list">
      <div v-if="events.length === 0" class="trace-empty">暂无可回放事件</div>
      <article v-for="(event, index) in events" :key="eventKey(event, index)" class="trace-event">
        <button class="trace-row" type="button" :aria-expanded="expandedEventId === eventKey(event, index)" @click="toggleEvent(event, index)">
          <time>{{ formatTime(event.created_at) }}</time>
          <span class="trace-category">{{ categoryLabel[event.category || 'decision'] || event.category }}</span>
          <span class="trace-summary">{{ event.summary || event.type }}</span>
          <span v-if="event.round" class="trace-meta">第 {{ event.round }} 轮</span>
          <span v-if="event.subtask_id" class="trace-meta mono">{{ event.subtask_id }}</span>
        </button>
        <div v-if="expandedEventId === eventKey(event, index)" class="trace-detail">
          <pre v-if="Object.keys(event.data).length" class="trace-data">{{ formatContent(event.data) }}</pre>
          <div v-for="artifact in event.artifacts || []" :key="artifact.id" class="artifact">
            <div class="artifact-header"><span>{{ artifact.kind }}</span><span>{{ artifact.size }} B</span></div>
            <div v-if="loadingArtifacts.has(artifact.id)" class="artifact-state">正在读取完整内容…</div>
            <pre v-else-if="artifactContents[artifact.id]" class="artifact-content">{{ formatContent(artifactContents[artifact.id]?.content) }}</pre>
            <div v-else-if="artifactContents[artifact.id] === null" class="artifact-state">内容读取失败</div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.trace-panel{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden}.trace-header{display:flex;align-items:center;justify-content:space-between;padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border)}.trace-title{font-size:var(--text-sm);font-weight:600;color:var(--c-text);text-transform:uppercase;letter-spacing:.5px}.trace-count{font-size:var(--text-xs);color:var(--c-text-3);padding:1px 6px;background:var(--c-surface-2);border-radius:var(--r-sm)}.trace-list{max-height:620px;overflow:auto}.trace-empty{padding:var(--sp-8);color:var(--c-text-3);text-align:center}.trace-event{border-bottom:1px solid var(--c-border)}.trace-event:last-child{border-bottom:0}.trace-row{width:100%;display:grid;grid-template-columns:150px 48px minmax(0,1fr) auto auto;gap:var(--sp-3);align-items:center;padding:var(--sp-3) var(--sp-5);border:0;background:transparent;color:var(--c-text-2);font:inherit;text-align:left;cursor:pointer}.trace-row:hover{background:var(--c-surface-2)}.trace-row time,.trace-meta{font:var(--text-xs) var(--font-mono);color:var(--c-text-3)}.trace-category{font-size:11px;font-weight:600;color:var(--c-accent);text-transform:uppercase}.trace-summary{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--text-sm)}.trace-detail{padding:0 var(--sp-5) var(--sp-4);background:var(--c-surface-2)}.trace-data,.artifact-content{margin:0;padding:var(--sp-3);overflow:auto;white-space:pre-wrap;word-break:break-word;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface);font:11px/1.6 var(--font-mono);color:var(--c-text-2)}.artifact{margin-top:var(--sp-3)}.artifact-header{display:flex;justify-content:space-between;padding:var(--sp-2) 0;font:var(--text-xs) var(--font-mono);color:var(--c-text-3)}.artifact-state{padding:var(--sp-3);font-size:var(--text-xs);color:var(--c-text-3)}@media (max-width:760px){.trace-row{grid-template-columns:1fr auto;gap:var(--sp-2)}.trace-row time{grid-column:1/-1}.trace-category{grid-column:1}.trace-meta{display:none}}
</style>
