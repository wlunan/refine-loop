<script setup lang="ts">
import { CheckCircleOutlined, ClockCircleOutlined, LoadingOutlined, CloseCircleOutlined, PauseCircleOutlined } from '@ant-design/icons-vue'
interface SubTask { id: string; title: string; description: string; status: string; dependencies: string[]; score: number | null; iterations: number; error: string | null }
defineProps<{ subtasks: SubTask[] }>()
function gi(s: string) { switch(s) { case 'completed': return CheckCircleOutlined; case 'running': return LoadingOutlined; case 'failed': return CloseCircleOutlined; case 'paused': return PauseCircleOutlined; default: return ClockCircleOutlined } }
function gc(s: string) { switch(s) { case 'completed': return 'var(--c-success)'; case 'running': return 'var(--c-accent)'; case 'failed': return 'var(--c-danger)'; case 'paused': return 'var(--c-warning)'; default: return 'var(--c-text-3)' } }
function gt(s: string) { const t: Record<string,string> = { pending:'等待中', planning:'规划中', running:'运行中', paused:'已暂停', completed:'已完成', failed:'失败', cancelled:'已取消' }; return t[s] || s }
function sc(s: number) { return s >= 85 ? 'var(--c-success)' : s >= 70 ? 'var(--c-accent)' : 'var(--c-danger)' }
</script>
<template>
  <div class="sl3">
    <div v-if="subtasks.length===0" class="em">暂无子任务</div>
    <div v-for="item in subtasks" :key="item.id" class="si">
      <div class="il"><div class="is" :style="{color:gc(item.status)}"><component :is="gi(item.status)" /></div></div>
      <div class="ib"><div class="ih"><span class="it">{{ item.title }}</span><span class="ib2" :style="{color:gc(item.status),background:gc(item.status)+'1a'}">{{ gt(item.status) }}</span></div><p class="id">{{ item.description }}</p><div v-if="item.dependencies.length>0" class="deps"><span class="dl">依赖</span><span v-for="dep in item.dependencies" :key="dep" class="dt">{{ dep }}</span></div></div>
      <div class="ir"><div v-if="item.score!==null" class="isc" :style="{color:sc(item.score!)}">{{ item.score }}</div><span v-if="item.iterations>0" class="iter">{{ item.iterations }} 轮</span><span v-if="item.error" class="ie">{{ item.error }}</span></div>
    </div>
  </div>
</template>
<style scoped>
.sl3{display:flex;flex-direction:column}.em{text-align:center;padding:var(--sp-8) 0;color:var(--c-text-3);font-size:var(--text-sm)}
.si{display:flex;gap:var(--sp-3);padding:var(--sp-4) 0;border-bottom:1px solid var(--c-border)}.si:last-child{border-bottom:none}
.il{flex-shrink:0;padding-top:2px}.is{font-size:16px}.ib{flex:1;min-width:0}
.ih{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-1)}.it{font-size:var(--text-sm);font-weight:600;color:var(--c-text)}
.ib2{font-size:var(--text-xs);font-weight:500;padding:1px 6px;border-radius:var(--r-sm)}
.id{font-size:var(--text-sm);color:var(--c-text-2);line-height:var(--leading);margin-bottom:var(--sp-2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.deps{display:flex;align-items:center;gap:var(--sp-1);flex-wrap:wrap}.dl{font-size:var(--text-xs);color:var(--c-text-3)}.dt{font-size:var(--text-xs);color:var(--c-text-2);background:var(--c-surface-2);padding:0 4px;border-radius:var(--r-sm)}
.ir{flex-shrink:0;text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:var(--sp-1)}
.isc{font-size:var(--text-lg);font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.iter{font-size:var(--text-xs);color:var(--c-text-3)}.ie{font-size:var(--text-xs);color:var(--c-danger);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
