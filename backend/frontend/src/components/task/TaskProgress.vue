<script setup lang="ts">
import { computed } from 'vue'
interface Task { id: string; status: string; progress_percent: number; total_tokens: number; error: string | null }
const props = defineProps<{ task: Task }>()
const statusColor = computed(() => {
  switch (props.task.status) { case 'running': return 'var(--c-accent)'; case 'completed': return 'var(--c-success)'; case 'failed': return 'var(--c-danger)'; case 'paused': return 'var(--c-warning)'; default: return 'var(--c-text-3)' }
})
const statusText = computed(() => {
  const t: Record<string,string> = { pending:'等待中', planning:'规划中', running:'运行中', paused:'已暂停', completed:'已完成', failed:'失败', cancelled:'已取消' }
  return t[props.task.status] || props.task.status
})
</script>
<template>
  <div class="pp">
    <div class="pm">
      <div class="pl">
        <div class="pv" :style="{color:statusColor}">{{ task.progress_percent.toFixed(1) }}%</div>
        <span class="ps" :style="{color:statusColor}">{{ statusText }}</span>
      </div>
      <div class="pr"><div class="st"><span class="sl2">Token</span><span class="sv">{{ task.total_tokens.toLocaleString() }}</span></div></div>
    </div>
    <a-progress :percent="task.progress_percent" :stroke-color="statusColor" :status="task.status==='failed'?'exception':undefined" :show-info="false" />
    <a-alert v-if="task.error" :message="task.error" type="error" show-icon style="margin-top:var(--sp-3);" />
  </div>
</template>
<style scoped>
.pp{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);padding:var(--sp-5)}
.pm{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:var(--sp-4)}
.pl{display:flex;align-items:baseline;gap:var(--sp-3)}.pv{font-size:32px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
.ps{font-size:var(--text-sm);font-weight:500}.pr{display:flex;gap:var(--sp-6)}
.st{display:flex;flex-direction:column;align-items:flex-end;gap:2px}.sl2{font-size:var(--text-xs);color:var(--c-text-3);text-transform:uppercase;letter-spacing:.3px}
.sv{font-size:var(--text-md);font-weight:600;color:var(--c-text);font-variant-numeric:tabular-nums}
</style>
