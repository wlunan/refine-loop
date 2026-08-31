<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ClearOutlined, CodeOutlined, FileTextOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { useSSE } from '../composables/useSSE'
import ScoreChart from '../components/workbench/ScoreChart.vue'
import WorkspacePicker from '../components/workbench/WorkspacePicker.vue'

type RunMode = 'text' | 'files'

const { connect, disconnect, clearEvents } = useSSE()
const form = reactive({ task: '', domain: 'code', maxRounds: 5, threshold: 85, workspace: '' })
const runMode = ref<RunMode>('text')
const rounds = ref<any[]>([])
const tokens = ref('')
const toolEvents = ref<any[]>([])
const isRunning = ref(false)
const finalOutput = ref('')
const runId = ref('')
const statusMessage = ref('等待任务')
const elapsedSeconds = ref(0)
let timer: number | undefined

const quickTasks = [
  { label: '代码审查', domain: 'code', task: '审查以下代码的潜在问题，并给出可执行的修复建议。' },
  { label: '技术文档', domain: 'writing', task: '编写一份结构清晰的技术方案，包含目标、设计、风险与验收标准。' },
  { label: '方案拆解', domain: 'design', task: '将需求拆分为可执行任务，标明依赖关系和交付标准。' },
]

const finalScore = computed(() => rounds.value.length ? rounds.value[rounds.value.length - 1].score : null)
const toolCountLabel = computed(() => `${toolEvents.value.length} 次工具调用`)

function startTimer() {
  elapsedSeconds.value = 0
  if (timer !== undefined) window.clearInterval(timer)
  timer = window.setInterval(() => { elapsedSeconds.value += 1 }, 1000)
}

function stopTimer() {
  if (timer !== undefined) window.clearInterval(timer)
  timer = undefined
}

function applyQuickTask(item: typeof quickTasks[number]) {
  form.task = item.task
  form.domain = item.domain
}

function handleSubmit() {
  if (!form.task.trim()) {
    message.warning('请输入任务描述')
    return
  }
  if (runMode.value === 'files' && !form.workspace.trim()) {
    message.warning('文件模式需要选择工作区')
    return
  }

  rounds.value = []
  tokens.value = ''
  toolEvents.value = []
  finalOutput.value = ''
  runId.value = ''
  statusMessage.value = runMode.value === 'files' ? '正在连接文件工作区…' : '正在连接 Generator…'
  isRunning.value = true
  startTimer()
  clearEvents()

  const params = new URLSearchParams({
    task: form.task,
    domain: form.domain,
    max_rounds: String(form.maxRounds),
    threshold: String(form.threshold),
  })
  const endpoint = runMode.value === 'files' ? '/api/stream_files' : '/api/stream'
  if (runMode.value === 'files') params.set('workspace', form.workspace)
  connect(`${endpoint}?${params}`, handleEvent)
}

function handleEvent(data: any) {
  switch (data.type) {
    case 'run_id': runId.value = data.run_id; break
    case 'status': statusMessage.value = data.message; break
    case 'token': tokens.value += data.token; statusMessage.value = 'Generator 正在生成…'; break
    case 'tool': toolEvents.value.push(data); statusMessage.value = `正在执行 ${data.tool || '工具'}…`; break
    case 'critic':
      rounds.value.push({ round: data.round, score: data.score, acceptable: data.acceptable, issues: data.issues, suggestions: data.suggestions, summary: data.summary })
      statusMessage.value = `第 ${data.round} 轮审查完成`
      break
    case 'done':
      finalOutput.value = data.final_output
      statusMessage.value = data.convergence_reason || '迭代完成'
      finishRun('迭代完成')
      break
    case 'error':
      statusMessage.value = data.message || '运行失败'
      message.error(statusMessage.value)
      finishRun()
      break
    case 'end': if (isRunning.value) finishRun(); break
  }
}

function finishRun(successMessage?: string) {
  isRunning.value = false
  stopTimer()
  if (successMessage) message.success(successMessage)
}

async function handleStop() {
  if (runId.value) await fetch(`/api/stop?run_id=${encodeURIComponent(runId.value)}`, { method: 'POST' })
  disconnect()
  statusMessage.value = '已请求停止'
  finishRun('已停止迭代')
}

function handleClear() {
  rounds.value = []
  tokens.value = ''
  toolEvents.value = []
  finalOutput.value = ''
  statusMessage.value = '等待任务'
  clearEvents()
}

function sc(score: number) { return score >= 85 ? 'var(--c-success)' : score >= 70 ? 'var(--c-accent)' : 'var(--c-danger)' }
function sb(score: number) { return score >= 85 ? 'var(--c-success-soft)' : score >= 70 ? 'var(--c-accent-soft)' : 'var(--c-danger-soft)' }

onUnmounted(() => stopTimer())
</script>

<template>
  <div class="wb">
    <div class="hero">
      <div><span class="eyebrow">AGENT OPERATIONS</span><h1>生成 · 审查 · 验证</h1><p>以可观察的迭代过程，交付更可信的代码、文档与方案。</p></div>
      <div class="hero-stats"><div><strong>{{ rounds.length }}</strong><span>已完成轮次</span></div><div><strong>{{ finalScore ?? '—' }}</strong><span>最新评分</span></div><div><strong>{{ elapsedSeconds }}s</strong><span>运行时长</span></div></div>
    </div>

    <div class="mode-switch" role="tablist" aria-label="任务模式">
      <button :class="{ active: runMode === 'text' }" @click="runMode = 'text'"><FileTextOutlined /> 文本迭代 <small>适合文档与方案</small></button>
      <button :class="{ active: runMode === 'files' }" @click="runMode = 'files'"><CodeOutlined /> 文件工作区 <small>让 Agent 操作真实项目文件</small></button>
    </div>

    <div class="wg">
      <section class="panel">
        <header><span>任务配置</span></header>
        <div class="panel-body"><a-form :model="form" layout="vertical" @finish="handleSubmit">
          <div class="field"><label>任务描述</label><a-textarea v-model:value="form.task" :rows="6" placeholder="说明目标、输入、约束和预期结果" /></div>
          <div class="quick-tasks"><button v-for="item in quickTasks" :key="item.label" type="button" @click="applyQuickTask(item)">{{ item.label }}</button></div>
          <div class="field-row"><div class="field"><label>领域</label><a-select v-model:value="form.domain"><a-select-option value="code">代码开发</a-select-option><a-select-option value="writing">文案写作</a-select-option><a-select-option value="design">方案设计</a-select-option><a-select-option value="general">通用</a-select-option></a-select></div><div class="field"><label>最大轮数</label><a-input-number v-model:value="form.maxRounds" :min="1" :max="20" /></div></div>
          <div v-if="runMode === 'files'" class="workspace-box"><label>工作区</label><a-input v-model:value="form.workspace" placeholder="选择或输入本地项目目录" /><WorkspacePicker class="workspace-picker" @select="form.workspace = $event" /><p>文件模式会读取并修改该目录下的文件，请确认目录范围。</p></div>
          <div class="field"><label>收敛阈值 <small>{{ form.threshold }}</small></label><a-slider v-model:value="form.threshold" :min="60" :max="100" :marks="{ 60: '60', 85: '85', 100: '100' }" /></div>
          <div class="actions"><a-button type="primary" html-type="submit" :loading="isRunning" :disabled="isRunning" block><template #icon><PlayCircleOutlined /></template>{{ runMode === 'files' ? '启动文件任务' : '开始迭代' }}</a-button><a-button v-if="isRunning" danger @click="handleStop"><template #icon><StopOutlined /></template>停止</a-button><a-button :disabled="isRunning" @click="handleClear"><template #icon><ClearOutlined /></template>清空</a-button></div>
        </a-form></div>
      </section>

      <section class="panel process-panel">
        <header><span>迭代过程</span><span class="run-state" :class="{ running: isRunning }"><i></i>{{ statusMessage }}</span></header>
        <div class="panel-body process-body">
          <div v-if="rounds.length === 0 && !isRunning && !tokens" class="empty"><b>⌁</b><p>配置任务后，Agent 会在这里留下每次审查与改进的证据。</p></div>
          <div v-if="tokens" class="stream-box"><div><strong>实时生成</strong><small>{{ tokens.length.toLocaleString() }} 字符</small></div><pre>{{ tokens }}</pre></div>
          <a-spin :spinning="isRunning" tip="正在迭代…"><div v-if="rounds.length" class="timeline"><article v-for="round in rounds" :key="round.round" class="round"><div class="marker" :class="{ accepted: round.acceptable }"></div><div class="round-content"><div class="round-head"><strong>第 {{ round.round }} 轮</strong><span :style="{ color: sc(round.score), background: sb(round.score) }">{{ round.score }}</span><a-tag v-if="round.acceptable" color="success">已收敛</a-tag></div><a-progress :percent="round.score" :stroke-color="sc(round.score)" :show-info="false" size="small" /><div v-if="round.issues?.length" class="feedback issues"><label>发现的问题</label><ul><li v-for="(issue, index) in round.issues" :key="index">{{ issue }}</li></ul></div><div v-if="round.suggestions?.length" class="feedback suggestions"><label>下一步建议</label><ul><li v-for="(suggestion, index) in round.suggestions" :key="index">{{ suggestion }}</li></ul></div><p v-if="round.summary" class="summary">{{ round.summary }}</p></div></article></div></a-spin>
        </div>
      </section>

      <aside class="right-column">
        <section class="panel"><header><span>评分趋势</span></header><div class="panel-body"><ScoreChart :data="rounds" /></div></section>
        <section v-if="runMode === 'files'" class="panel"><header><span>工作区事件</span><small>{{ toolCountLabel }}</small></header><div class="panel-body tool-list"><p v-if="!toolEvents.length" class="tool-empty">文件操作会在这里显示</p><div v-for="(event, index) in toolEvents" :key="index" class="tool-item"><CodeOutlined /><div><strong>{{ event.tool || '工具调用' }}</strong><p>{{ event.subtype === 'tool_result' ? (event.result || '已完成') : JSON.stringify(event.arguments || {}) }}</p></div></div></div></section>
        <section v-if="finalOutput" class="panel"><header><span>最终产出</span></header><div class="panel-body"><pre class="output">{{ finalOutput }}</pre></div></section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.wb{max-width:1480px;margin:0 auto}.hero{display:flex;align-items:end;justify-content:space-between;gap:var(--sp-8);padding:var(--sp-6) 0 var(--sp-5)}.eyebrow{display:block;color:var(--c-accent);font-family:var(--font-mono);font-size:11px;font-weight:700;letter-spacing:1.4px;margin-bottom:var(--sp-2)}h1{font-size:32px;letter-spacing:-1.2px;line-height:1.1;font-weight:750;color:var(--c-text)}.hero p{font-size:var(--text-md);color:var(--c-text-2);margin-top:var(--sp-2)}.hero-stats{display:flex;gap:var(--sp-5);padding:var(--sp-3) var(--sp-4);border-left:1px solid var(--c-border)}.hero-stats div{display:flex;flex-direction:column;gap:2px;min-width:68px}.hero-stats strong{font-family:var(--font-mono);font-size:22px;line-height:1;color:var(--c-text)}.hero-stats span{font-size:var(--text-xs);color:var(--c-text-3);white-space:nowrap}
.mode-switch{display:flex;gap:var(--sp-2);border-bottom:1px solid var(--c-border);margin-bottom:var(--sp-5)}.mode-switch button{display:flex;align-items:center;gap:var(--sp-2);padding:10px 12px;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--c-text-3);cursor:pointer;font:inherit;font-size:var(--text-sm);font-weight:600}.mode-switch button small{font-weight:400}.mode-switch button.active{color:var(--c-accent);border-bottom-color:var(--c-accent)}
.wg{display:grid;grid-template-columns:320px minmax(420px,1fr) 340px;gap:var(--sp-5);align-items:start}.panel{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;box-shadow:var(--shadow-xs)}.panel header{display:flex;align-items:center;justify-content:space-between;padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border);font-size:var(--text-sm);font-weight:650;color:var(--c-text);letter-spacing:.5px;text-transform:uppercase}.panel header small{font-size:var(--text-xs);font-weight:400;color:var(--c-text-3);text-transform:none}.panel-body{padding:var(--sp-5)}.right-column{display:flex;flex-direction:column;gap:var(--sp-5)}
.field{margin-bottom:var(--sp-4)}.field label,.workspace-box>label{display:flex;justify-content:space-between;margin-bottom:var(--sp-2);font-size:var(--text-sm);font-weight:500;color:var(--c-text-2)}.field label small{font-size:var(--text-xs);color:var(--c-text-3);font-weight:400}.field :deep(.ant-select),.field :deep(.ant-input-number){width:100%}.field-row{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-3)}.quick-tasks{display:flex;flex-wrap:wrap;gap:6px;margin-top:calc(var(--sp-3) * -1);margin-bottom:var(--sp-4)}.quick-tasks button{border:1px solid var(--c-border);border-radius:99px;background:var(--c-surface);color:var(--c-text-2);font:inherit;font-size:var(--text-xs);padding:3px 8px;cursor:pointer}.quick-tasks button:hover{border-color:var(--c-accent);color:var(--c-accent)}.workspace-box{border:1px dashed var(--c-border-2);border-radius:var(--r-md);padding:var(--sp-3);margin-bottom:var(--sp-4);background:var(--c-surface-2)}.workspace-picker{margin-top:var(--sp-2)}.workspace-box p{font-size:var(--text-xs);line-height:1.5;color:var(--c-text-3);margin-top:var(--sp-2)}.actions{display:flex;gap:var(--sp-2);margin-top:var(--sp-5);padding-top:var(--sp-4);border-top:1px solid var(--c-border)}.actions :deep(.ant-btn-primary){flex:1}
.process-body{max-height:calc(100vh - 250px);overflow-y:auto}.run-state{display:flex;align-items:center;gap:6px;font-size:var(--text-xs);font-weight:400;color:var(--c-text-3);max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-transform:none;letter-spacing:0}.run-state i{width:7px;height:7px;border-radius:50%;background:var(--c-border-2)}.run-state.running{color:var(--c-accent)}.run-state.running i{background:var(--c-accent);box-shadow:0 0 0 4px var(--c-accent-soft);animation:pulse 1.5s infinite}.empty{text-align:center;padding:var(--sp-16) var(--sp-4)}.empty b{display:block;font-family:var(--font-mono);font-size:40px;color:var(--c-accent);margin-bottom:var(--sp-3)}.empty p{font-size:var(--text-sm);color:var(--c-text-3);line-height:1.7}.stream-box{border:1px solid var(--c-accent-muted);background:var(--c-accent-soft);border-radius:var(--r-md);padding:var(--sp-3);margin-bottom:var(--sp-4)}.stream-box>div{display:flex;justify-content:space-between;color:var(--c-accent);font-size:var(--text-xs);margin-bottom:var(--sp-2)}.stream-box small{font-weight:400}.stream-box pre{max-height:160px;overflow:auto;white-space:pre-wrap;margin:0;font:12px/1.7 var(--font-mono);color:var(--c-text-2)}
.timeline{display:flex;flex-direction:column}.round{display:flex;gap:var(--sp-4);position:relative;padding-bottom:var(--sp-5)}.round:not(:last-child)::before{content:'';position:absolute;left:7px;top:18px;bottom:0;width:1px;background:var(--c-border)}.marker{width:15px;height:15px;margin-top:2px;flex-shrink:0;border-radius:50%;border:2px solid var(--c-border-2);background:var(--c-surface)}.marker.accepted{border-color:var(--c-success);background:var(--c-success)}.round-content{flex:1;min-width:0}.round-head{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-2)}.round-head strong{font-size:var(--text-sm);color:var(--c-text)}.round-head>span{font-family:var(--font-mono);font-size:var(--text-xs);font-weight:700;padding:1px 8px;border-radius:var(--r-sm)}.feedback{margin-top:var(--sp-3)}.feedback label{display:block;font-size:var(--text-xs);font-weight:650;color:var(--c-text-3);margin-bottom:var(--sp-1)}.feedback ul{list-style:none;margin:0;padding:0}.feedback li{font-size:var(--text-sm);padding:var(--sp-1) 0 var(--sp-1) var(--sp-3);position:relative}.feedback li::before{content:'';position:absolute;left:0;top:11px;width:4px;height:4px;border-radius:50%}.issues li{color:var(--c-danger)}.issues li::before{background:var(--c-danger)}.suggestions li{color:var(--c-success)}.suggestions li::before{background:var(--c-success)}.summary{margin-top:var(--sp-2);font-size:var(--text-sm);color:var(--c-text-2)}
.tool-list{max-height:280px;overflow:auto}.tool-empty{font-size:var(--text-sm);color:var(--c-text-3);padding:var(--sp-3) 0;text-align:center}.tool-item{display:flex;gap:var(--sp-3);padding:var(--sp-3) 0;border-bottom:1px solid var(--c-border);color:var(--c-accent)}.tool-item:last-child{border-bottom:0}.tool-item div{min-width:0}.tool-item strong{display:block;color:var(--c-text);font-size:var(--text-xs)}.tool-item p{margin:2px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--c-text-3);font:11px var(--font-mono)}.output{background:var(--c-surface-2);padding:var(--sp-4);border-radius:var(--r-md);white-space:pre-wrap;font-family:var(--font-mono);font-size:var(--text-sm);max-height:400px;overflow-y:auto;color:var(--c-text);margin:0}
@keyframes pulse{50%{opacity:.45}}@media (max-width:1200px){.wg{grid-template-columns:300px 1fr}.right-column{grid-column:1 / -1;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.right-column .panel:last-child{grid-column:1/-1}}@media (max-width:760px){.hero{align-items:flex-start;flex-direction:column;gap:var(--sp-4)}.hero-stats{border-left:0;border-top:1px solid var(--c-border);padding-left:0;width:100%}.mode-switch{overflow:auto}.mode-switch button{white-space:nowrap}.mode-switch small{display:none}.wg,.right-column{display:flex;flex-direction:column}.wg>.panel,.right-column>.panel{width:100%}.process-body{max-height:none}}
</style>
