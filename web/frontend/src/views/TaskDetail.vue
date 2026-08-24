<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, PlayCircleOutlined, PauseCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { useTaskStore } from '../stores/task'
import { useSSE } from '../composables/useSSE'
import SubTaskList from '../components/task/SubTaskList.vue'
import TaskProgress from '../components/task/TaskProgress.vue'
const route = useRoute(); const router = useRouter(); const taskStore = useTaskStore(); const { connect, disconnect } = useSSE()
const taskId = route.params.id as string; const logs = ref<string[]>([])
onMounted(async () => { await taskStore.fetchTask(taskId); if (taskStore.currentTask?.status === 'running') startSSE() })
onUnmounted(() => { disconnect() })
function startSSE() { connect('/api/tasks/' + taskId + '/events', handleEvent) }
function handleEvent(data: any) { const ts = new Date().toLocaleTimeString(); switch (data.type) {
  case 'task_started': logs.value.push('['+ts+'] 任务开始执行'); break
  case 'task_planning': logs.value.push('['+ts+'] 正在分析需求...'); break
  case 'task_planned': logs.value.push('['+ts+'] 任务分解完成: '+data.subtask_count+' 个子任务'); break
  case 'subtask_started': logs.value.push('['+ts+'] 子任务开始: '+data.title); break
  case 'subtask_progress': logs.value.push('['+ts+'] 第 '+data.round+' 轮完成，评分: '+data.score); break
  case 'file_operation': { const op=data.operation||''; const p=data.path||''; if(op.includes('write')||op.includes('create')) logs.value.push('['+ts+'] 写入文件: '+p); else if(op.includes('read')) logs.value.push('['+ts+'] 读取文件: '+p); else logs.value.push('['+ts+'] 文件操作: '+op+' '+p); break }
  case 'file_result': if(data.result) logs.value.push('['+ts+'] 操作完成: '+data.result); break
  case 'subtask_completed': logs.value.push('['+ts+'] 子任务完成，评分: '+data.score); taskStore.fetchTask(taskId); break
  case 'subtask_failed': logs.value.push('['+ts+'] 子任务失败: '+data.error); break
  case 'task_completed': logs.value.push('['+ts+'] 任务已完成'); taskStore.fetchTask(taskId); disconnect(); break
  case 'task_failed': logs.value.push('['+ts+'] 任务失败: '+data.error); taskStore.fetchTask(taskId); disconnect(); break
}; setTimeout(() => { const el=document.getElementById('log-container'); if(el) el.scrollTop=el.scrollHeight }, 50) }
async function handleStart() { await taskStore.startTask(taskId); message.success('任务已启动'); startSSE(); taskStore.fetchTask(taskId) }
async function handlePause() { await taskStore.pauseTask(taskId); message.success('任务已暂停'); disconnect(); taskStore.fetchTask(taskId) }
async function handleResume() { await taskStore.resumeTask(taskId); message.success('任务已恢复'); startSSE(); taskStore.fetchTask(taskId) }
async function handleCancel() { await taskStore.cancelTask(taskId); message.success('任务已取消'); disconnect(); taskStore.fetchTask(taskId) }
function gst(s: string) { const t: Record<string,string> = { pending:'等待中',planning:'规划中',running:'运行中',paused:'已暂停',completed:'已完成',failed:'失败',cancelled:'已取消' }; return t[s]||s }
function gsc(s: string) { const m: Record<string,string> = { pending:'var(--c-text-3)',planning:'var(--c-accent)',running:'var(--c-accent)',paused:'var(--c-warning)',completed:'var(--c-success)',failed:'var(--c-danger)',cancelled:'var(--c-text-3)' }; return m[s]||'var(--c-text-3)' }
</script>
<template>
  <div class="tdp"><a-spin :spinning="taskStore.loading"><template v-if="taskStore.currentTask">
    <div class="ph"><button class="bb" @click="router.push('/tasks')"><ArrowLeftOutlined /></button><div class="hi"><h1 class="pt">{{ taskStore.currentTask.title }}</h1><div class="hm"><span class="sb" :style="{color:gsc(taskStore.currentTask.status),background:gsc(taskStore.currentTask.status)+'1a'}">{{ gst(taskStore.currentTask.status) }}</span><span class="mi">{{ taskStore.currentTask.id }}</span><span class="mi">{{ taskStore.currentTask.domain }}</span></div></div><div class="ha"><a-button v-if="taskStore.currentTask.status==='pending'" type="primary" @click="handleStart"><template #icon><PlayCircleOutlined /></template>启动</a-button><a-button v-if="taskStore.currentTask.status==='running'" @click="handlePause"><template #icon><PauseCircleOutlined /></template>暂停</a-button><a-button v-if="taskStore.currentTask.status==='paused'" type="primary" @click="handleResume"><template #icon><PlayCircleOutlined /></template>恢复</a-button><a-button v-if="!['completed','cancelled'].includes(taskStore.currentTask.status)" danger @click="handleCancel"><template #icon><StopOutlined /></template>取消</a-button></div></div>
    <div class="dg"><div class="dl"><TaskProgress :task="taskStore.currentTask" /><div class="pn"><div class="nh"><span class="nt">子任务列表</span></div><div class="nb"><SubTaskList :subtasks="taskStore.currentTask.subtasks||[]" /></div></div></div>
    <div class="dr"><div class="pn"><div class="nh"><span class="nt">任务信息</span></div><div class="nb"><div class="ig"><div class="ii"><span class="il2">工作目录</span><code class="iv mono">{{ taskStore.currentTask.workspace_dir }}</code></div><div class="ii"><span class="il2">Token 消耗</span><span class="iv ivn">{{ taskStore.currentTask.total_tokens.toLocaleString() }}</span></div><div class="ii"><span class="il2">创建时间</span><span class="iv">{{ new Date(taskStore.currentTask.created_at).toLocaleString() }}</span></div><div v-if="taskStore.currentTask.error" class="ii"><span class="il2">错误信息</span><span class="iv" style="color:var(--c-danger)">{{ taskStore.currentTask.error }}</span></div></div></div></div>
    <div class="pn"><div class="nh"><span class="nt">实时日志</span><span v-if="logs.length" class="nm">{{ logs.length }}</span></div><div class="nb lb"><div id="log-container" class="lc"><div v-if="logs.length===0" class="le">暂无日志</div><div v-for="(log,i) in logs" :key="i" class="ll">{{ log }}</div></div></div></div></div>
  </div></template></a-spin></div>
</template>
<style scoped>
.tdp{max-width:1400px;margin:0 auto}.ph{display:flex;align-items:flex-start;gap:var(--sp-4);margin-bottom:var(--sp-6)}
.bb{width:36px;height:36px;border:1px solid var(--c-border);border-radius:var(--r-md);background:var(--c-surface);cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--c-text-2);flex-shrink:0;margin-top:2px;transition:all .15s}.bb:hover{border-color:var(--c-border-2);color:var(--c-text)}
.hi{flex:1;min-width:0}.pt{font-size:var(--text-xl);font-weight:700;color:var(--c-text)}.hm{display:flex;align-items:center;gap:var(--sp-3);margin-top:var(--sp-2)}
.sb{font-size:var(--text-xs);font-weight:600;padding:2px 8px;border-radius:var(--r-sm)}.mi{font-size:var(--text-xs);color:var(--c-text-3)}.ha{display:flex;gap:var(--sp-2);flex-shrink:0}
.dg{display:grid;grid-template-columns:1fr 360px;gap:var(--sp-5);align-items:start}.dl{display:flex;flex-direction:column;gap:var(--sp-5)}.dr{display:flex;flex-direction:column;gap:var(--sp-5)}
.pn{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden}
.nh{display:flex;align-items:center;justify-content:space-between;padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border)}.nt{font-size:var(--text-sm);font-weight:600;color:var(--c-text);text-transform:uppercase;letter-spacing:.5px}
.nm{font-size:var(--text-xs);color:var(--c-text-3);padding:1px 6px;background:var(--c-surface-2);border-radius:var(--r-sm)}.nb{padding:var(--sp-5)}
.ig{display:flex;flex-direction:column;gap:var(--sp-4)}.ii{display:flex;flex-direction:column;gap:var(--sp-1)}
.il2{font-size:var(--text-xs);font-weight:500;color:var(--c-text-3);text-transform:uppercase;letter-spacing:.3px}.iv{font-size:var(--text-sm);color:var(--c-text);word-break:break-all}.ivn{font-size:var(--text-lg);font-weight:700;font-variant-numeric:tabular-nums}
.lb{padding:0}.lc{background:var(--c-surface-2);padding:var(--sp-4);max-height:400px;overflow-y:auto;font-family:var(--font-mono);font-size:var(--text-xs);line-height:1.7}
.le{color:var(--c-text-3);text-align:center;padding:var(--sp-8) 0}.ll{color:var(--c-text-2);padding:1px 0;border-bottom:1px solid var(--c-border)}.ll:last-child{border-bottom:none}
</style>
