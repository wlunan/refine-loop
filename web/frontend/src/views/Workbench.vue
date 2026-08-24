<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import { SendOutlined, ClearOutlined, StopOutlined } from '@ant-design/icons-vue'
import { useSSE } from '../composables/useSSE'
import ScoreChart from '../components/workbench/ScoreChart.vue'
const { connect, disconnect, clearEvents } = useSSE()
const form = reactive({ task: '', domain: 'code', maxRounds: 5, threshold: 85 })
const rounds = ref<any[]>([])
const isRunning = ref(false)
const finalOutput = ref('')
function handleSubmit() { if (!form.task.trim()) { message.warning('请输入任务描述'); return }; rounds.value = []; finalOutput.value = ''; isRunning.value = true; clearEvents(); const p = new URLSearchParams({ task: form.task, domain: form.domain, max_rounds: String(form.maxRounds), threshold: String(form.threshold) }); connect('/api/stream?' + p, handleEvent) }
function handleEvent(data: any) { switch (data.type) { case 'critic': rounds.value.push({ round: data.round, score: data.score, acceptable: data.acceptable, issues: data.issues, suggestions: data.suggestions, summary: data.summary }); break; case 'done': finalOutput.value = data.final_output; isRunning.value = false; message.success('迭代完成'); break; case 'error': message.error(data.message); isRunning.value = false; break; case 'end': isRunning.value = false; break } }
function handleStop() { disconnect(); isRunning.value = false; message.info('已停止') }
function handleClear() { rounds.value = []; finalOutput.value = ''; clearEvents() }
function sc(s: number) { return s >= 85 ? 'var(--c-success)' : s >= 70 ? 'var(--c-accent)' : 'var(--c-danger)' }
function sb(s: number) { return s >= 85 ? 'var(--c-success-soft)' : s >= 70 ? 'var(--c-accent-soft)' : 'var(--c-danger-soft)' }
</script>
<template>
  <div class="wb"><div class="ph"><h1 class="pt">工作台</h1><p class="pd">输入任务，让 Generator 和 Critic 自动迭代优化</p></div>
  <div class="wg">
    <div class="pn"><div class="nh"><span class="nt">任务配置</span></div><div class="nb">
      <a-form :model="form" layout="vertical" @finish="handleSubmit">
        <div class="ff"><label class="fl">任务描述</label><a-textarea v-model:value="form.task" :rows="4" placeholder="描述你的任务" /></div>
        <div class="fr"><div class="ff"><label class="fl">领域</label><a-select v-model:value="form.domain" style="width:100%"><a-select-option value="code">代码开发</a-select-option><a-select-option value="writing">文案写作</a-select-option><a-select-option value="design">方案设计</a-select-option><a-select-option value="general">通用</a-select-option></a-select></div><div class="ff"><label class="fl">最大轮数</label><a-input-number v-model:value="form.maxRounds" :min="1" :max="20" style="width:100%" /></div></div>
        <div class="ff"><label class="fl">收敛阈值 <span class="fh">{{ form.threshold }}</span></label><a-slider v-model:value="form.threshold" :min="60" :max="100" :marks="{60:'60',85:'85',100:'100'}" /></div>
        <div class="fa"><a-button type="primary" html-type="submit" :loading="isRunning" :disabled="isRunning" style="flex:1"><template #icon><SendOutlined /></template>开始迭代</a-button><a-button v-if="isRunning" danger @click="handleStop"><template #icon><StopOutlined /></template>停止</a-button><a-button @click="handleClear" :disabled="isRunning"><template #icon><ClearOutlined /></template>清空</a-button></div>
      </a-form>
    </div></div>
    <div class="pn"><div class="nh"><span class="nt">迭代过程</span><span v-if="rounds.length" class="nm">{{ rounds.length }} 轮</span></div><div class="nb ns">
      <div v-if="rounds.length===0 && !isRunning" class="es"><div class="ei">&#9671;</div><p class="et">输入任务开始迭代</p></div>
      <a-spin :spinning="isRunning" tip="正在迭代..."><div v-if="rounds.length>0" class="tl"><div v-for="r in rounds" :key="r.round" class="ti"><div class="tm"><div class="md" :class="{ac:r.acceptable}"></div></div><div class="tc"><div class="rh"><span class="rn">第 {{ r.round }} 轮</span><span class="rs" :style="{color:sc(r.score),background:sb(r.score)}">{{ r.score }}</span><a-tag v-if="r.acceptable" color="success" size="small">已收敛</a-tag></div><a-progress :percent="r.score" :stroke-color="sc(r.score)" :show-info="false" size="small" /><div v-if="r.issues?.length" class="rs2"><div class="sl">问题</div><ul class="il"><li v-for="(issue,i) in r.issues" :key="i" class="ii">{{ issue }}</li></ul></div><div v-if="r.suggestions?.length" class="rs2"><div class="sl">建议</div><ul class="sgl"><li v-for="(sug,i) in r.suggestions" :key="i" class="sgi">{{ sug }}</li></ul></div><p v-if="r.summary" class="rsm">{{ r.summary }}</p></div></div></div></a-spin>
    </div></div>
    <div class="pg"><div class="pn"><div class="nh"><span class="nt">评分趋势</span></div><div class="nb"><ScoreChart :data="rounds" /></div></div><div v-if="finalOutput" class="pn"><div class="nh"><span class="nt">最终产出</span></div><div class="nb"><pre class="oc">{{ finalOutput }}</pre></div></div></div>
  </div></div>
</template>
<style scoped>
.wb{max-width:1440px;margin:0 auto}.ph{margin-bottom:var(--sp-6)}.pt{font-size:var(--text-xl);font-weight:700;color:var(--c-text)}.pd{font-size:var(--text-sm);color:var(--c-text-3);margin-top:var(--sp-1)}
.wg{display:grid;grid-template-columns:300px 1fr 320px;gap:var(--sp-5);align-items:start}.pn{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden}
.nh{display:flex;align-items:center;justify-content:space-between;padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border)}.nt{font-size:var(--text-sm);font-weight:600;color:var(--c-text);text-transform:uppercase;letter-spacing:.5px}
.nm{font-size:var(--text-xs);color:var(--c-text-3);padding:1px 6px;background:var(--c-surface-2);border-radius:var(--r-sm)}.nb{padding:var(--sp-5)}.ns{max-height:calc(100vh - 200px);overflow-y:auto}.pg{display:flex;flex-direction:column;gap:var(--sp-5)}
.ff{margin-bottom:var(--sp-4)}.fl{display:flex;align-items:center;justify-content:space-between;font-size:var(--text-sm);font-weight:500;color:var(--c-text-2);margin-bottom:var(--sp-2)}.fh{font-weight:400;color:var(--c-text-3);font-size:var(--text-xs)}.fr{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-3)}
.fa{display:flex;gap:var(--sp-2);margin-top:var(--sp-5);padding-top:var(--sp-4);border-top:1px solid var(--c-border)}
.es{text-align:center;padding:var(--sp-16) 0}.ei{font-size:32px;color:var(--c-border-2);margin-bottom:var(--sp-3)}.et{font-size:var(--text-sm);color:var(--c-text-3)}
.tl{display:flex;flex-direction:column}.ti{display:flex;gap:var(--sp-4);position:relative;padding-bottom:var(--sp-5)}.ti:not(:last-child)::before{content:'';position:absolute;left:7px;top:18px;bottom:0;width:1px;background:var(--c-border)}
.tm{flex-shrink:0;padding-top:2px}.md{width:15px;height:15px;border-radius:50%;border:2px solid var(--c-border-2);background:var(--c-surface)}.md.ac{border-color:var(--c-success);background:var(--c-success)}
.tc{flex:1;min-width:0}.rh{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-2)}.rn{font-weight:600;font-size:var(--text-sm);color:var(--c-text)}
.rs{font-size:var(--text-xs);font-weight:600;padding:1px 8px;border-radius:var(--r-sm)}.rs2{margin-top:var(--sp-3)}
.sl{font-size:var(--text-xs);font-weight:600;color:var(--c-text-3);text-transform:uppercase;letter-spacing:.3px;margin-bottom:var(--sp-1)}
.il,.sgl{list-style:none;padding:0;margin:0}.ii{font-size:var(--text-sm);color:var(--c-danger);padding:var(--sp-1) 0;padding-left:var(--sp-3);position:relative}
.ii::before{content:'';position:absolute;left:0;top:10px;width:4px;height:4px;border-radius:50%;background:var(--c-danger)}
.sgi{font-size:var(--text-sm);color:var(--c-success);padding:var(--sp-1) 0;padding-left:var(--sp-3);position:relative}
.sgi::before{content:'';position:absolute;left:0;top:10px;width:4px;height:4px;border-radius:50%;background:var(--c-success)}
.rsm{margin-top:var(--sp-2);font-size:var(--text-sm);color:var(--c-text-2)}.oc{background:var(--c-surface-2);padding:var(--sp-4);border-radius:var(--r-md);white-space:pre-wrap;font-family:var(--font-mono);font-size:var(--text-sm);max-height:400px;overflow-y:auto;color:var(--c-text);margin:0}
</style>
