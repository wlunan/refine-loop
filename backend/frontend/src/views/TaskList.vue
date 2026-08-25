<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, PlayCircleOutlined, PauseCircleOutlined, StopOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useTaskStore } from '../stores/task'
const router = useRouter()
const taskStore = useTaskStore()
const showCreateModal = ref(false)
const createForm = ref({ requirement: '', workspaceDir: '', domain: 'code' })
const statusFilter = ref<string | undefined>(undefined)
onMounted(() => { taskStore.fetchTasks() })
function handleCreate() {
  if (!createForm.value.requirement.trim()) { message.warning('请输入需求描述'); return }
  if (!createForm.value.workspaceDir.trim()) { message.warning('请输入工作目录'); return }
  taskStore.createTask(createForm.value.requirement, createForm.value.workspaceDir, createForm.value.domain).then((r: any) => { message.success('任务已创建: ' + r.task_id); showCreateModal.value = false; createForm.value = { requirement: '', workspaceDir: '', domain: 'code' } }).catch((e: any) => { message.error(e.message) })
}
function handleStart(id: string) { Modal.confirm({ title: '确认启动', content: '确定要启动这个任务吗？', onOk: () => taskStore.startTask(id).then(() => message.success('任务已启动')) }) }
function handlePause(id: string) { taskStore.pauseTask(id).then(() => message.success('任务已暂停')) }
function handleResume(id: string) { taskStore.resumeTask(id).then(() => message.success('任务已恢复')) }
function handleCancel(id: string) { Modal.confirm({ title: '确认取消', content: '确定要取消这个任务吗？', okType: 'danger', onOk: () => taskStore.cancelTask(id).then(() => message.success('任务已取消')) }) }
function gsd(s: string) { const m: Record<string,string> = { pending:'var(--c-text-3)', planning:'var(--c-accent)', running:'var(--c-accent)', paused:'var(--c-warning)', completed:'var(--c-success)', failed:'var(--c-danger)', cancelled:'var(--c-text-3)' }; return m[s]||'var(--c-text-3)' }
function gst(s: string) { const t: Record<string,string> = { pending:'等待中', planning:'规划中', running:'运行中', paused:'已暂停', completed:'已完成', failed:'失败', cancelled:'已取消' }; return t[s]||s }
function handleFilterChange(v: string) { statusFilter.value = v || undefined; taskStore.fetchTasks(statusFilter.value) }
</script>
<template>
  <div class="tlp">
    <div class="ph"><div><h1 class="pt">任务管理</h1><p class="pd">创建和管理长时间运行的代码开发任务</p></div>
    <div class="ha"><a-select v-model:value="statusFilter" placeholder="全部状态" allow-clear style="width:120px" @change="handleFilterChange"><a-select-option value="">全部</a-select-option><a-select-option value="pending">等待中</a-select-option><a-select-option value="running">运行中</a-select-option><a-select-option value="paused">已暂停</a-select-option><a-select-option value="completed">已完成</a-select-option><a-select-option value="failed">失败</a-select-option></a-select><a-button @click="taskStore.fetchTasks(statusFilter)"><template #icon><ReloadOutlined /></template></a-button><a-button type="primary" @click="showCreateModal=true"><template #icon><PlusOutlined /></template>创建任务</a-button></div></div>
    <a-spin :spinning="taskStore.loading">
      <div v-if="taskStore.tasks.length===0" class="es"><div class="ei">&#9671;</div><p class="et">暂无任务，点击右上角创建</p></div>
      <div v-else class="tg">
        <div v-for="task in taskStore.tasks" :key="task.id" class="tc" @click="router.push('/tasks/'+task.id)">
          <div class="ct"><div class="cs"><span class="sd" :style="{background:gsd(task.status)}"></span><span class="st">{{ gst(task.status) }}</span></div><a-dropdown :trigger="['click']" @click.stop><button class="mb">&#8943;</button><template #overlay><a-menu><a-menu-item v-if="task.status==='pending'" @click.stop="handleStart(task.id)"><PlayCircleOutlined /> 启动</a-menu-item><a-menu-item v-if="task.status==='running'" @click.stop="handlePause(task.id)"><PauseCircleOutlined /> 暂停</a-menu-item><a-menu-item v-if="task.status==='paused'" @click.stop="handleResume(task.id)"><PlayCircleOutlined /> 恢复</a-menu-item><a-menu-item v-if="!['completed','cancelled'].includes(task.status)" @click.stop="handleCancel(task.id)" danger><StopOutlined /> 取消</a-menu-item></a-menu></template></a-dropdown></div>
          <h3 class="ct2">{{ task.title }}</h3>
          <div class="cp"><a-progress :percent="task.progress_percent" :status="task.status==='failed'?'exception':undefined" :show-info="false" size="small" /><span class="pl2">{{ task.progress_percent.toFixed(0) }}%</span></div>
          <div class="cm"><span>{{ task.completed_subtasks }}/{{ task.subtask_count }} 子任务</span><span>{{ new Date(task.created_at).toLocaleDateString() }}</span></div>
        </div>
      </div>
    </a-spin>
    <a-modal v-model:open="showCreateModal" title="创建新任务" @ok="handleCreate" ok-text="创建" cancel-text="取消" :width="520">
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="需求描述" required><a-textarea v-model:value="createForm.requirement" :rows="4" placeholder="详细描述你的开发需求" /></a-form-item>
        <a-form-item label="工作目录" required><a-input v-model:value="createForm.workspaceDir" placeholder="例如：E:\projects\my-app" /></a-form-item>
        <a-form-item label="任务领域"><a-select v-model:value="createForm.domain"><a-select-option value="code">代码开发</a-select-option><a-select-option value="writing">文案写作</a-select-option><a-select-option value="design">方案设计</a-select-option></a-select></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
<style scoped>
.tlp{max-width:1200px;margin:0 auto}.ph{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:var(--sp-6)}
.pt{font-size:var(--text-xl);font-weight:700;color:var(--c-text)}.pd{font-size:var(--text-sm);color:var(--c-text-3);margin-top:var(--sp-1)}
.ha{display:flex;gap:var(--sp-2);align-items:center}
.es{text-align:center;padding:var(--sp-16) 0}.ei{font-size:32px;color:var(--c-border-2);margin-bottom:var(--sp-3)}.et{font-size:var(--text-sm);color:var(--c-text-3)}
.tg{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:var(--sp-4)}
.tc{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);padding:var(--sp-5);cursor:pointer;transition:all .15s}.tc:hover{border-color:var(--c-border-2);box-shadow:var(--shadow-sm)}
.ct{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-3)}.cs{display:flex;align-items:center;gap:var(--sp-2)}.sd{width:8px;height:8px;border-radius:50%;flex-shrink:0}.st{font-size:var(--text-xs);font-weight:500;color:var(--c-text-2)}
.mb{background:none;border:none;cursor:pointer;color:var(--c-text-3);font-size:16px;padding:2px 6px;border-radius:var(--r-sm)}.mb:hover{background:var(--c-surface-2);color:var(--c-text)}
.ct2{font-size:var(--text-base);font-weight:600;color:var(--c-text);margin-bottom:var(--sp-3);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cp{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-3)}.cp :deep(.ant-progress){flex:1}.pl2{font-size:var(--text-xs);font-weight:600;color:var(--c-text-2);min-width:32px;text-align:right}
.cm{display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--c-text-3)}
</style>
