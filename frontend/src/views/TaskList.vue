<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { DeleteOutlined, PlayCircleOutlined, PauseCircleOutlined, StopOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { useTaskStore } from '../stores/task'
import { taskApi, type SystemMetricsSnapshot } from '../api/task'
import { formatTokenCount } from '../utils/format'

const router = useRouter()
const taskStore = useTaskStore()
const statusFilter = ref<string | undefined>(undefined)

// 系统级可观测统计（来自 GET /api/system/metrics 进程内指标聚合）
const systemMetrics = ref<SystemMetricsSnapshot | null>(null)

function counterSum(name: string, pred?: (labels: Record<string, string>) => boolean) {
  if (!systemMetrics.value) return 0
  return systemMetrics.value.counters
    .filter((c) => c.name === name && (!pred || pred(c.labels)))
    .reduce((sum, c) => sum + c.value, 0)
}

async function loadMetrics() {
  try {
    systemMetrics.value = await taskApi.getSystemMetrics()
  } catch {
    systemMetrics.value = null
  }
}

const stat = computed(() => {
  if (!systemMetrics.value) return null
  return {
    active: systemMetrics.value.gauges?.active_tasks ?? 0,
    created: Math.round(counterSum('tasks_created_total')),
    finishedOk: Math.round(counterSum('tasks_finished_total', (l) => l.status === 'completed')),
    calls: Math.round(counterSum('llm_calls_total')),
    tokens: Math.round(
      counterSum('llm_prompt_tokens_total') + counterSum('llm_completion_tokens_total'),
    ),
  }
})

async function refresh() {
  await Promise.all([taskStore.fetchTasks(statusFilter.value), loadMetrics()])
}

onMounted(() => { refresh() })

function handleStart(id: string) { Modal.confirm({ title: '确认启动', content: '确定要启动这个任务吗？', onOk: () => taskStore.startTask(id).then(() => { message.success('任务已启动'); refresh() }) }) }
function handlePause(id: string) { taskStore.pauseTask(id).then(() => { message.success('任务已暂停'); refresh() }) }
function handleResume(id: string) { taskStore.resumeTask(id).then(() => { message.success('任务已恢复'); refresh() }) }
function handleCancel(id: string) { Modal.confirm({ title: '确认取消', content: '确定要取消这个任务吗？', okType: 'danger', onOk: () => taskStore.cancelTask(id).then(() => { message.success('任务已取消'); refresh() }) }) }
function handleDelete(id: string, status: string) { const discardsDiff = status === 'awaiting_approval'; Modal.confirm({ title: '确认删除任务', content: discardsDiff ? '删除后将丢弃尚未应用的变更、运行记录和检查点，无法恢复。' : '删除后将清除任务记录、运行日志和检查点，无法恢复。', okText: '删除', okType: 'danger', onOk: () => taskStore.deleteTask(id).then(() => { message.success('任务已删除'); refresh() }) }) }
function gsd(s: string) { const m: Record<string,string> = { pending:'var(--c-text-3)', planning:'var(--c-accent)', running:'var(--c-accent)', paused:'var(--c-warning)', awaiting_approval:'var(--c-warning)', completed:'var(--c-success)', failed:'var(--c-danger)', cancelled:'var(--c-text-3)' }; return m[s]||'var(--c-text-3)' }
function gst(s: string) { const t: Record<string,string> = { pending:'等待中', planning:'规划中', running:'运行中', paused:'已暂停', awaiting_approval:'等待确认', completed:'已完成', failed:'失败', cancelled:'已取消' }; return t[s]||s }
function handleFilterChange(v: string) { statusFilter.value = v || undefined; taskStore.fetchTasks(statusFilter.value) }
</script>
<template>
  <div class="tlp">
    <div class="ph"><div><h1 class="pt">任务中心</h1><p class="pd">集中查看进行中、已完成和失败的代码任务；每个任务都有独立的执行记录。</p></div>
    <div class="ha"><a-select v-model:value="statusFilter" placeholder="全部状态" allow-clear style="width:120px" @change="handleFilterChange"><a-select-option value="">全部</a-select-option><a-select-option value="pending">等待中</a-select-option><a-select-option value="running">运行中</a-select-option><a-select-option value="paused">已暂停</a-select-option><a-select-option value="awaiting_approval">等待确认</a-select-option><a-select-option value="completed">已完成</a-select-option><a-select-option value="failed">失败</a-select-option></a-select><a-button @click="refresh"><template #icon><ReloadOutlined /></template></a-button><a-button type="primary" @click="router.push('/')"><template #icon><PlusOutlined /></template>新建任务</a-button></div></div>

    <div v-if="stat" class="stats">
      <div class="stat"><span class="sl">运行中任务</span><b>{{ stat.active }}</b></div>
      <div class="stat"><span class="sl">已完成任务</span><b>{{ stat.finishedOk }}</b><small>共创建 {{ stat.created }}</small></div>
      <div class="stat"><span class="sl">LLM 调用</span><b>{{ stat.calls }}</b></div>
      <div class="stat"><span class="sl">Token 消耗</span><b>{{ formatTokenCount(stat.tokens) }}</b></div>
    </div>

    <a-spin :spinning="taskStore.loading">
      <div v-if="taskStore.tasks.length===0" class="es"><div class="ei">&#9671;</div><p class="et">暂无任务，点击右上角新建代码任务</p></div>
      <div v-else class="tg">
        <div v-for="task in taskStore.tasks" :key="task.id" class="tc" @click="router.push('/tasks/'+task.id)">
          <div class="ct"><div class="cs"><span class="sd" :style="{background:gsd(task.status)}"></span><span class="st">{{ gst(task.status) }}</span></div><a-dropdown :trigger="['click']" @click.stop><button class="mb">&#8943;</button><template #overlay><a-menu><a-menu-item v-if="task.status==='pending'" @click.stop="handleStart(task.id)"><PlayCircleOutlined /> 启动</a-menu-item><a-menu-item v-if="task.status==='running'" @click.stop="handlePause(task.id)"><PauseCircleOutlined /> 暂停</a-menu-item><a-menu-item v-if="task.status==='paused'" @click.stop="handleResume(task.id)"><PlayCircleOutlined /> 恢复</a-menu-item><a-menu-item v-if="!['completed','cancelled'].includes(task.status)" @click.stop="handleCancel(task.id)" danger><StopOutlined /> 取消</a-menu-item><a-menu-divider v-if="['awaiting_approval','completed','failed','cancelled'].includes(task.status)" /><a-menu-item v-if="['awaiting_approval','completed','failed','cancelled'].includes(task.status)" @click.stop="handleDelete(task.id, task.status)" danger><DeleteOutlined /> 删除</a-menu-item></a-menu></template></a-dropdown></div>
          <h3 class="ct2">{{ task.title }}</h3>
          <div class="cp"><a-progress :percent="task.progress_percent" :status="task.status==='failed'?'exception':undefined" :show-info="false" size="small" /><span class="pl2">{{ task.progress_percent.toFixed(0) }}%</span></div>
          <div class="cm"><span>{{ task.completed_subtasks }}/{{ task.subtask_count }} 子任务</span><span>{{ new Date(task.created_at).toLocaleDateString() }}</span></div>
        </div>
      </div>
    </a-spin>
  </div>
</template>
<style scoped>
.tlp{max-width:1200px;margin:0 auto}.ph{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:var(--sp-4)}
.pt{font-size:var(--text-xl);font-weight:700;color:var(--c-text)}.pd{font-size:var(--text-sm);color:var(--c-text-3);margin-top:var(--sp-1)}
.ha{display:flex;gap:var(--sp-2);align-items:center}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--sp-4);margin-bottom:var(--sp-5)}
.stat{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);padding:var(--sp-4) var(--sp-5);display:flex;flex-direction:column;gap:2px}
.stat b{font-size:24px;font-weight:750;color:var(--c-text);line-height:1.1;font-variant-numeric:tabular-nums}
.stat .sl{font-size:var(--text-xs);color:var(--c-text-3);text-transform:uppercase;letter-spacing:.3px}
.stat small{font-size:var(--text-xs);color:var(--c-text-3)}
.es{text-align:center;padding:var(--sp-16) 0}.ei{font-size:32px;color:var(--c-border-2);margin-bottom:var(--sp-3)}.et{font-size:var(--text-sm);color:var(--c-text-3)}
.tg{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:var(--sp-4)}
.tc{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);padding:var(--sp-5);cursor:pointer;transition:all .15s}.tc:hover{border-color:var(--c-border-2);box-shadow:var(--shadow-sm)}
.ct{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-3)}.cs{display:flex;align-items:center;gap:var(--sp-2)}.sd{width:8px;height:8px;border-radius:50%;flex-shrink:0}.st{font-size:var(--text-xs);font-weight:500;color:var(--c-text-2)}
.mb{background:none;border:none;cursor:pointer;color:var(--c-text-3);font-size:16px;padding:2px 6px;border-radius:var(--r-sm)}.mb:hover{background:var(--c-surface-2);color:var(--c-text)}
.ct2{font-size:var(--text-base);font-weight:600;color:var(--c-text);margin-bottom:var(--sp-3);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cp{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-3)}.cp :deep(.ant-progress){flex:1}.pl2{font-size:var(--text-xs);font-weight:600;color:var(--c-text-2);min-width:32px;text-align:right}
.cm{display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--c-text-3)}
@media(max-width:760px){.ph{flex-direction:column;gap:var(--sp-4)}.ha{width:100%}.ha :deep(.ant-select){flex:1;width:auto!important;min-width:0}.ha :deep(.ant-btn){min-width:44px;min-height:44px}.stats{grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--sp-3)}.stat{padding:var(--sp-4)}.tg{grid-template-columns:minmax(0,1fr);gap:var(--sp-3)}.tc{padding:var(--sp-4)}}
</style>
