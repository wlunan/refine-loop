<script setup lang="ts">
/**
 * 验证驱动修复闭环面板
 *
 * 把任务执行时间线里的「文件改动 → 验证证据 → 失败回注 → 复跑」整理成
 * 逐轮闭环卡片，让用户一眼看到：每一轮改了哪些文件、验证命令与退出码、
 * 哪几轮失败、最终第几轮通过或达到最大轮数仍未通过——而不是只看到
 * Critic 分数，或在原始事件日志里翻 JSON。
 *
 * 数据来自 SSE / timeline 的 verification_completed / file_operation /
 * subtask_progress 事件；完整 stdout/stderr 证据在 verification_results
 * artifact 中按需加载。
 */
import { computed, ref } from 'vue'
import { taskApi } from '../../api/task'
import type { RunConfigInfo, TaskArtifactRef, TaskTraceEvent } from '../../stores/task'

interface VerificationStepInfo {
  step_id: string
  label: string
  required: boolean
  passed: boolean
  exit_code: number | null
  timed_out: boolean
  duration_seconds?: number
}

interface FileOp {
  operation: string
  path: string
}

interface LoopRound {
  key: string
  subtaskId: string | null
  round: number
  createdAt: string
  passed: boolean
  profile: string
  steps: VerificationStepInfo[]
  files: FileOp[]
  criticScore: number | null
  artifactRef: TaskArtifactRef | null
}

const props = defineProps<{
  taskId: string
  events: TaskTraceEvent[]
  runConfig: RunConfigInfo | null
  taskStatus?: string
}>()

const profileLabels: Record<string, string> = {
  python_pytest: 'Python · pytest',
  python_lint: 'Python · lint',
  node_build: 'Node · build',
}

// 校验命令文本：优先取 RunConfig 里声明的命令，缺失时回退到 label。
const commandMap = computed(
  () => new Map((props.runConfig?.verification_steps || []).map((s) => [s.id, s.command])),
)
const profile = computed(() => props.runConfig?.verification_profile)
const maxRounds = computed(() => props.runConfig?.max_rounds ?? 3)

const expandedEvidence = ref<Set<string>>(new Set())
const evidencePayload = ref<Record<string, unknown>>({})

/** 把时间线事件按「子任务 × 轮次」聚合成一轮轮闭环。 */
const rounds = computed<LoopRound[]>(() => {
  const byKey = new Map<string, LoopRound>()
  const order: string[] = []
  const ensure = (subtaskId: string | null, round: number): LoopRound => {
    const key = `${subtaskId ?? ''}|${round}`
    let r = byKey.get(key)
    if (!r) {
      r = {
        key,
        subtaskId,
        round,
        createdAt: '',
        passed: false,
        profile: '',
        steps: [],
        files: [],
        criticScore: null,
        artifactRef: null,
      }
      byKey.set(key, r)
      order.push(key)
    }
    return r
  }

  for (const ev of props.events) {
    const subtaskId = (ev.subtask_id as string | null) ?? null
    const data: any = ev.data || {}
    const round = typeof ev.round === 'number'
      ? ev.round
      : typeof data.round === 'number' ? data.round : 0

    if (ev.type === 'verification_completed') {
      const r = ensure(subtaskId, round)
      r.createdAt = r.createdAt || ev.created_at
      r.passed = Boolean(data.passed)
      r.profile = data.profile || ''
      r.steps = Array.isArray(data.steps) ? (data.steps as VerificationStepInfo[]) : []
      r.artifactRef = (ev.artifacts || []).find((a) => a.kind === 'verification_results') ?? null
    } else if (ev.type === 'file_operation') {
      const r = ensure(subtaskId, round)
      r.createdAt = r.createdAt || ev.created_at
      const operation = String(data.operation || '')
      const path = String(data.path || '')
      if (operation && path && !r.files.some((f) => f.operation === operation && f.path === path)) {
        r.files.push({ operation, path })
      }
    } else if (ev.type === 'subtask_progress') {
      const r = ensure(subtaskId, round)
      r.createdAt = r.createdAt || ev.created_at
      if (typeof data.score === 'number') r.criticScore = data.score
    }
  }

  return order
    .map((key) => byKey.get(key)!)
    .sort((a, b) => a.round - b.round || a.createdAt.localeCompare(b.createdAt))
})

const failedRounds = computed(() => rounds.value.filter((r) => !r.passed))
const lastRound = computed(() => rounds.value[rounds.value.length - 1] ?? null)

/** 闭环结论：通过 / 达到最大轮数未通过 / 进行中。 */
const conclusion = computed(() => {
  if (!lastRound.value) return null
  if (lastRound.value.passed) {
    return { kind: 'success' as const, text: `验证通过 · 在第 ${lastRound.value.round} 轮收敛` }
  }
  if (lastRound.value.round >= maxRounds.value) {
    return {
      kind: 'failed' as const,
      text: `达到最大修复轮数（${maxRounds.value}），验证仍未通过`,
    }
  }
  return {
    kind: 'running' as const,
    text: `第 ${lastRound.value.round} 轮验证失败，已携带失败证据进入下一轮修复`,
  }
})

const runningNow = computed(() => props.taskStatus === 'running' || props.taskStatus === 'awaiting_approval')

function commandOf(step: VerificationStepInfo): string {
  return commandMap.value.get(step.step_id) || step.label
}

function formatTime(value: string) {
  return value ? new Date(value).toLocaleString() : ''
}

function shortId(value: string | null) {
  return value && value.length > 8 ? `${value.slice(0, 8)}…` : (value || '')
}

async function toggleEvidence(round: LoopRound) {
  if (!round.artifactRef) return
  if (expandedEvidence.value.has(round.key)) {
    expandedEvidence.value.delete(round.key)
    return
  }
  if (evidencePayload.value[round.key] === undefined) {
    try {
      const artifact = await taskApi.getTraceArtifact(props.taskId, round.artifactRef.id)
      evidencePayload.value[round.key] = (artifact as any)?.content ?? null
    } catch {
      evidencePayload.value[round.key] = null
    }
  }
  expandedEvidence.value.add(round.key)
}

function evidenceText(payload: unknown): string {
  if (!Array.isArray(payload)) {
    return payload == null ? '' : JSON.stringify(payload, null, 2)
  }
  const parts = payload.map((r: any) => {
    const header = `${r.label || r.step_id} · ${r.passed ? '通过' : '失败'}` +
      (typeof r.exit_code === 'number' ? ` · 退出码 ${r.exit_code}` : '')
    const body = [r.stdout, r.stderr].filter(Boolean).join('\n')
    return `${header}\n${body}`
  })
  return parts.join('\n\n')
}
</script>

<template>
  <section class="rlp">
    <header class="rlp-head">
      <div>
        <span class="rlp-title">验证驱动修复闭环</span>
        <span v-if="profile && profile !== 'none'" class="rlp-profile">{{ profileLabels[profile] || profile }}</span>
      </div>
      <span v-if="rounds.length" class="rlp-count">{{ rounds.length }} 轮验证</span>
    </header>

    <template v-if="conclusion">
      <div class="rlp-conclusion" :class="`kind-${conclusion.kind}`">
        <span class="dot" />
        <span>{{ conclusion.text }}</span>
        <span v-if="failedRounds.length" class="rlp-meta">{{ failedRounds.length }} 轮失败后修复</span>
      </div>

      <div class="rlp-list">
        <article v-for="round in rounds" :key="round.key" class="rlp-round" :class="{ failed: !round.passed }">
          <header class="round-head">
            <span class="round-no">第 {{ round.round }} 轮</span>
            <span v-if="round.subtaskId" class="round-sub mono">{{ shortId(round.subtaskId) }}</span>
            <span v-if="round.criticScore !== null" class="round-score">Critic {{ round.criticScore }}</span>
            <span class="round-time">{{ formatTime(round.createdAt) }}</span>
            <span class="round-badge" :class="round.passed ? 'ok' : 'bad'">
              {{ round.passed ? '验证通过' : '验证失败' }}
            </span>
          </header>

          <div class="round-body">
            <div v-if="round.files.length" class="round-files">
              <span v-for="(file, i) in round.files" :key="`${file.operation}:${file.path}:${i}`" class="file-chip">
                {{ file.operation }} · {{ file.path }}
              </span>
            </div>
            <div v-else class="round-files empty">本轮未产生文件改动</div>

            <div v-if="round.steps.length" class="round-steps">
              <div v-for="step in round.steps" :key="step.step_id" class="step-row">
                <span class="step-icon" :class="step.passed ? 'ok' : 'bad'">{{ step.passed ? '✓' : '✗' }}</span>
                <span class="step-label">{{ step.label }}</span>
                <code class="step-cmd">{{ commandOf(step) }}</code>
                <span class="step-exit" :class="step.passed ? 'ok' : 'bad'">
                  exit {{ step.exit_code ?? '-' }}{{ step.timed_out ? '（超时）' : '' }}
                </span>
              </div>
            </div>
            <div v-else class="round-steps empty">未执行验证步骤</div>

            <button v-if="!round.passed && round.artifactRef" type="button" class="evidence-toggle" @click="toggleEvidence(round)">
              {{ expandedEvidence.has(round.key) ? '收起失败证据' : '查看失败证据（stdout/stderr）' }}
            </button>
            <pre v-if="!round.passed && expandedEvidence.has(round.key)" class="evidence-box">
{{ evidenceText(evidencePayload[round.key]) || '（暂无证据内容）' }}</pre>
          </div>
        </article>
      </div>
    </template>

    <div v-else-if="profile && profile !== 'none' && runningNow" class="rlp-empty">
      {{ '等待首次验证…（每一轮修复后都会运行 ' + (profileLabels[profile] || profile) + '）' }}
    </div>
    <div v-else class="rlp-empty">
      该任务未产生确定性验证记录。配置 pytest / lint / build 后，只有验证通过任务才会完成。
    </div>
  </section>
</template>

<style scoped>
.rlp{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden}
.rlp-head{display:flex;align-items:center;justify-content:space-between;padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border)}
.rlp-title{font-size:var(--text-sm);font-weight:600;color:var(--c-text);text-transform:uppercase;letter-spacing:.5px}
.rlp-profile{margin-left:var(--sp-3);padding:1px 6px;border-radius:var(--r-sm);background:var(--c-surface-2);color:var(--c-text-3);font:var(--text-xs) var(--font-mono)}
.rlp-count{font-size:var(--text-xs);color:var(--c-text-3)}
.rlp-conclusion{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-3) var(--sp-5);font-size:var(--text-sm);font-weight:600;border-left:3px solid;background:var(--c-surface-2)}
.rlp-conclusion .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:currentColor}
.rlp-conclusion.kind-success{color:var(--c-success);border-color:var(--c-success)}
.rlp-conclusion.kind-failed{color:var(--c-danger);border-color:var(--c-danger)}
.rlp-conclusion.kind-running{color:var(--c-warning);border-color:var(--c-warning)}
.rlp-meta{margin-left:auto;font-size:var(--text-xs);font-weight:400;opacity:.85}
.rlp-list{max-height:560px;overflow:auto}
.rlp-empty{padding:var(--sp-6) var(--sp-5);color:var(--c-text-3);font-size:var(--text-sm);text-align:center}
.rlp-round{border-bottom:1px solid var(--c-border)}
.rlp-round:last-child{border-bottom:0}
.round-head{display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-3) var(--sp-5)}
.round-no{font-weight:650;color:var(--c-text);font-size:var(--text-sm)}
.round-sub{color:var(--c-text-3);font-size:var(--text-xs)}
.round-score{color:var(--c-text-3);font-size:var(--text-xs)}
.round-time{margin-left:auto;color:var(--c-text-3);font:var(--text-xs) var(--font-mono)}
.round-badge{font-size:var(--text-xs);font-weight:600;padding:1px 8px;border-radius:var(--r-sm)}
.round-badge.ok{color:var(--c-success);border:1px solid var(--c-success);background:transparent}
.round-badge.bad{color:var(--c-danger);border:1px solid var(--c-danger);background:transparent}
.round-body{padding:0 var(--sp-5) var(--sp-4)}
.round-files{display:flex;flex-wrap:wrap;gap:var(--sp-2);margin-bottom:var(--sp-3)}
.file-chip{font:var(--text-xs) var(--font-mono);color:var(--c-text-2);background:var(--c-surface-2);padding:2px 8px;border-radius:var(--r-sm)}
.round-files.empty,.round-steps.empty{color:var(--c-text-3);font-size:var(--text-xs)}
.round-steps{display:flex;flex-direction:column;gap:var(--sp-2);margin-bottom:var(--sp-3)}
.step-row{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-2) var(--sp-3);border:1px solid var(--c-border);border-radius:var(--r-sm);font-size:var(--text-xs)}
.step-icon{font-weight:700}
.step-icon.ok{color:var(--c-success)}.step-icon.bad{color:var(--c-danger)}
.step-label{font-weight:600;color:var(--c-text);flex-shrink:0}
.step-cmd{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:var(--text-xs) var(--font-mono);color:var(--c-text-3)}
.step-exit{flex-shrink:0;font:var(--text-xs) var(--font-mono)}
.step-exit.ok{color:var(--c-success)}.step-exit.bad{color:var(--c-danger)}
.evidence-toggle{font-size:var(--text-xs);color:var(--c-accent);background:transparent;border:0;cursor:pointer;padding:0}
.evidence-toggle:hover{text-decoration:underline}
.evidence-box{margin:var(--sp-3) 0 0;padding:var(--sp-3);overflow:auto;white-space:pre-wrap;word-break:break-word;border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-surface-2);font:11px/1.6 var(--font-mono);color:var(--c-text-2);max-height:320px}
</style>
