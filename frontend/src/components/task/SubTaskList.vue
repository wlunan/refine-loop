<script setup lang="ts">
import { ref } from 'vue'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  CloseCircleOutlined,
  PauseCircleOutlined,
  DownOutlined,
  RightOutlined,
} from '@ant-design/icons-vue'
import { taskApi } from '../../api/task'

interface SubTask {
  id: string
  title: string
  description: string
  status: string
  dependencies: string[]
  score: number | null
  iterations: number
  error: string | null
}

interface RoundRecord {
  round: number
  draft: string
  score: number | null
  acceptable: boolean | null
  issues: string[]
  suggestions: string[]
  summary: string | null
  tokens_used: number
}

const props = defineProps<{ taskId: string; subtasks: SubTask[] }>()

// 展开状态：subtaskId -> boolean
const expanded = ref<Record<string, boolean>>({})
// 每轮记录缓存：subtaskId -> RoundRecord[]
const roundsCache = ref<Record<string, RoundRecord[]>>({})
// 加载状态：subtaskId -> boolean
const loading = ref<Record<string, boolean>>({})

function gi(s: string) {
  switch (s) {
    case 'completed': return CheckCircleOutlined
    case 'running': return LoadingOutlined
    case 'failed': return CloseCircleOutlined
    case 'paused': return PauseCircleOutlined
    default: return ClockCircleOutlined
  }
}
function gc(s: string) {
  switch (s) {
    case 'completed': return 'var(--c-success)'
    case 'running': return 'var(--c-accent)'
    case 'failed': return 'var(--c-danger)'
    case 'paused': return 'var(--c-warning)'
    default: return 'var(--c-text-3)'
  }
}
function gt(s: string) {
  const t: Record<string, string> = {
    pending: '等待中', planning: '规划中', running: '运行中', paused: '已暂停',
    completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return t[s] || s
}
function sc(s: number) {
  return s >= 85 ? 'var(--c-success)' : s >= 70 ? 'var(--c-accent)' : 'var(--c-danger)'
}

async function toggle(subtask: SubTask) {
  if (!expanded.value[subtask.id]) {
    expanded.value[subtask.id] = true
    // 首次展开时加载每轮记录
    if (!roundsCache.value[subtask.id]) {
      loading.value[subtask.id] = true
      try {
        roundsCache.value[subtask.id] = await taskApi.getSubtaskRounds(
          props.taskId,
          subtask.id
        )
      } catch (e: any) {
        roundsCache.value[subtask.id] = []
        // 静默失败：无记录时展示空态
      } finally {
        loading.value[subtask.id] = false
      }
    }
  } else {
    expanded.value[subtask.id] = false
  }
}
</script>
<template>
  <div class="sl3">
    <div v-if="subtasks.length===0" class="em">暂无子任务</div>
    <div v-for="item in subtasks" :key="item.id" class="si">
      <div class="si-main" role="button" :tabindex="0" @click="toggle(item)" @keydown.enter="toggle(item)" @keydown.space.prevent="toggle(item)">
        <div class="il"><div class="is" :style="{color:gc(item.status)}"><component :is="gi(item.status)" /></div></div>
        <div class="ib">
          <div class="ih">
            <span class="it">{{ item.title }}</span>
            <span class="ib2" :style="{color:gc(item.status),background:gc(item.status)+'1a'}">{{ gt(item.status) }}</span>
            <span v-if="expanded[item.id]" class="arrow"><DownOutlined /></span>
            <span v-else class="arrow"><RightOutlined /></span>
          </div>
          <p class="id">{{ item.description }}</p>
          <div v-if="item.dependencies.length>0" class="deps"><span class="dl">依赖</span><span v-for="dep in item.dependencies" :key="dep" class="dt">{{ dep }}</span></div>
        </div>
        <div class="ir">
          <div v-if="item.score!==null" class="isc" :style="{color:sc(item.score!)}">{{ item.score }}</div>
          <span v-if="item.iterations>0" class="iter">{{ item.iterations }} 轮</span>
          <span v-if="item.error" class="ie">{{ item.error }}</span>
        </div>
      </div>

      <!-- 展开：每轮迭代详情 -->
      <div v-if="expanded[item.id]" class="sd">
        <div v-if="loading[item.id]" class="ld"><LoadingOutlined spin /> 加载中...</div>
        <div v-else-if="(roundsCache[item.id]||[]).length===0" class="em2">暂无迭代记录（任务可能尚未执行完成）</div>
        <div v-else class="rounds">
          <div v-for="r in roundsCache[item.id]" :key="r.round" class="rd">
            <div class="rh">
              <span class="rt">第 {{ r.round }} 轮</span>
              <span v-if="r.score!==null" class="rsc" :style="{color:sc(r.score)}">{{ r.score }} 分</span>
              <span v-if="r.acceptable!==null" class="rb" :style="r.acceptable ? {color:'var(--c-success)',background:'rgba(16,185,129,.12)'} : {color:'var(--c-danger)',background:'rgba(239,68,68,.1)'}">{{ r.acceptable ? '可接受' : '需修改' }}</span>
              <span v-if="r.tokens_used" class="rtk">{{ r.tokens_used }} tokens</span>
            </div>
            <div class="rg">
              <span class="rl">生成内容</span>
              <pre class="rc gen">{{ r.draft || '（空）' }}</pre>
            </div>
            <div v-if="(r.issues||[]).length" class="rg">
              <span class="rl">问题</span>
              <ul class="rlist"><li v-for="(iss,i) in r.issues" :key="i">{{ iss }}</li></ul>
            </div>
            <div v-if="(r.suggestions||[]).length" class="rg">
              <span class="rl">建议</span>
              <ul class="rlist"><li v-for="(sug,i) in r.suggestions" :key="i">{{ sug }}</li></ul>
            </div>
            <div v-if="r.summary" class="rg">
              <span class="rl">总结</span>
              <p class="rs">{{ r.summary }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.sl3{display:flex;flex-direction:column}
.em{text-align:center;padding:var(--sp-8) 0;color:var(--c-text-3);font-size:var(--text-sm)}
.si{display:flex;flex-direction:column;border-bottom:1px solid var(--c-border)}.si:last-child{border-bottom:none}
.si-main{display:flex;gap:var(--sp-3);padding:var(--sp-4) 0;cursor:pointer;transition:background .12s;border-radius:var(--r-sm)}
.si-main:hover{background:var(--c-surface-2)}
.si-main:focus-visible{outline:2px solid var(--c-accent);outline-offset:-2px}
.il{flex-shrink:0;padding-top:2px}.is{font-size:16px}
.ib{flex:1;min-width:0}
.ih{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-1)}
.it{font-size:var(--text-sm);font-weight:600;color:var(--c-text)}
.arrow{font-size:var(--text-xs);color:var(--c-text-3)}
.ib2{font-size:var(--text-xs);font-weight:500;padding:1px 6px;border-radius:var(--r-sm)}
.id{font-size:var(--text-sm);color:var(--c-text-2);line-height:var(--leading);margin-bottom:var(--sp-2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.deps{display:flex;align-items:center;gap:var(--sp-1);flex-wrap:wrap}
.dl{font-size:var(--text-xs);color:var(--c-text-3)}.dt{font-size:var(--text-xs);color:var(--c-text-2);background:var(--c-surface-2);padding:0 4px;border-radius:var(--r-sm)}
.ir{flex-shrink:0;text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:var(--sp-1)}
.isc{font-size:var(--text-lg);font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.iter{font-size:var(--text-xs);color:var(--c-text-3)}
.ie{font-size:var(--text-xs);color:var(--c-danger);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* 展开区域 */
.sd{padding:0 0 var(--sp-4) calc(var(--sp-3) + 20px);border-left:2px solid var(--c-border);margin-left:20px}
.ld{display:flex;align-items:center;gap:var(--sp-2);color:var(--c-text-3);font-size:var(--text-sm);padding:var(--sp-2) 0}
.em2{color:var(--c-text-3);font-size:var(--text-sm);padding:var(--sp-2) 0}
.rounds{display:flex;flex-direction:column;gap:var(--sp-4)}
.rd{background:var(--c-surface-2);border:1px solid var(--c-border);border-radius:var(--r-md);padding:var(--sp-3) var(--sp-4)}
.rh{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap;margin-bottom:var(--sp-2)}
.rt{font-size:var(--text-xs);font-weight:700;color:var(--c-text);text-transform:uppercase;letter-spacing:.5px}
.rsc{font-size:var(--text-sm);font-weight:700}
.rb{font-size:var(--text-xs);font-weight:600;padding:1px 6px;border-radius:var(--r-sm)}
.rtk{font-size:var(--text-xs);color:var(--c-text-3);margin-left:auto}
.rg{display:flex;flex-direction:column;gap:var(--sp-1);margin-top:var(--sp-2)}
.rl{font-size:var(--text-xs);font-weight:600;color:var(--c-text-3)}
.rc{white-space:pre-wrap;word-break:break-word;font-family:var(--font-mono);font-size:var(--text-xs);line-height:1.7;background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-sm);padding:var(--sp-3);margin:0;max-height:280px;overflow-y:auto}
.rlist{margin:0;padding-left:var(--sp-4);display:flex;flex-direction:column;gap:2px}
.rlist li{font-size:var(--text-xs);color:var(--c-text-2)}
.rs{font-size:var(--text-xs);color:var(--c-text-2);margin:0}
</style>
