<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { CodeOutlined, PlayCircleOutlined, UnorderedListOutlined } from '@ant-design/icons-vue'
import WorkspacePicker from '../components/workbench/WorkspacePicker.vue'
import { useTaskStore } from '../stores/task'

const router = useRouter()
const taskStore = useTaskStore()
const submitting = ref(false)
const form = reactive({
  requirement: '',
  workspace: '',
  maxRounds: 3,
  threshold: 85,
  verificationProfile: 'auto',
})
const detecting = ref(false)

const profileLabels: Record<string, string> = {
  none: '暂不执行确定性验证',
  python_pytest: 'Python · pytest',
  python_lint: 'Python · lint',
  node_build: 'Node · build',
}

async function detectWorkspace(workspace: string) {
  form.workspace = workspace
  if (!workspace.trim()) {
    taskStore.verificationDetection = null
    return
  }

  detecting.value = true
  try {
    await taskStore.detectVerification(workspace)
  } catch {
    // The form submission will show the actionable directory error.
    taskStore.verificationDetection = null
  } finally {
    detecting.value = false
  }
}

async function handleSubmit() {
  if (!form.requirement.trim()) {
    message.warning('请输入代码任务描述')
    return
  }
  if (!form.workspace.trim()) {
    message.warning('请选择工作区目录')
    return
  }

  submitting.value = true
  try {
    const task = await taskStore.createTask(
      form.requirement,
      form.workspace,
      'code',
      form.verificationProfile,
      form.maxRounds,
      form.threshold,
    )
    message.success('任务已创建，正在进入任务详情')
    await router.push(`/tasks/${task.task_id}`)
  } catch (error: any) {
    message.error(error.message || '创建任务失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="new-task-page">
    <section class="hero">
      <div>
        <span class="eyebrow">CODE AGENT</span>
        <h1>新建代码任务</h1>
        <p>任务创建后将进入任务详情页执行；运行日志、验证结果与暂停/恢复记录都会持久化。</p>
      </div>
      <a-button @click="router.push('/tasks')">
        <template #icon><UnorderedListOutlined /></template>
        前往任务中心
      </a-button>
    </section>

    <section class="panel form-panel">
      <header><CodeOutlined /> 任务配置</header>
      <div class="panel-body">
        <a-form :model="form" layout="vertical" @finish="handleSubmit">
          <a-form-item label="开发需求" required>
            <a-textarea v-model:value="form.requirement" :rows="7" placeholder="说明目标、涉及文件、约束和验收标准。例如：修复登录接口的空 token 异常，并补充回归测试。" />
          </a-form-item>
          <a-form-item label="工作区目录" required>
            <a-input v-model:value="form.workspace" placeholder="选择或输入本地 Git 项目根目录" @blur="detectWorkspace(form.workspace)" />
            <WorkspacePicker class="workspace-picker" @select="detectWorkspace($event)" />
            <p class="help">代码任务会在隔离 Git worktree 中修改和验证；仅在你审阅并应用 diff 后才会写回原项目。</p>
          </a-form-item>
          <a-form-item label="验证计划">
            <div class="detected-plan" :class="{ loading: detecting }">
              <a-spin :spinning="detecting" size="small">
                <template v-if="taskStore.verificationDetection">
                  <div class="plan-title">
                    自动识别 · {{ profileLabels[taskStore.verificationDetection.profile] }}
                  </div>
                  <p>{{ taskStore.verificationDetection.summary }}</p>
                  <code v-for="command in taskStore.verificationDetection.plan" :key="command">{{ command }}</code>
                  <p class="dependency-note">{{ taskStore.verificationDetection.dependency_note }}</p>
                </template>
                <span v-else>选择工作区后自动识别测试、构建或 lint 入口。</span>
              </a-spin>
            </div>
          </a-form-item>
          <a-collapse ghost class="advanced-settings">
            <a-collapse-panel key="advanced" header="高级设置（仅在自动识别不准确时调整）">
              <a-form-item label="验证方式">
                <a-select v-model:value="form.verificationProfile">
                  <a-select-option value="auto">自动识别（推荐）</a-select-option>
                  <a-select-option value="python_pytest">Python · pytest</a-select-option>
                  <a-select-option value="python_lint">Python · lint</a-select-option>
                  <a-select-option value="node_build">Node · build</a-select-option>
                  <a-select-option value="none">暂不验证</a-select-option>
                </a-select>
              </a-form-item>
              <div class="form-grid">
                <a-form-item label="最大修复轮数"><a-input-number v-model:value="form.maxRounds" :min="1" :max="20" /></a-form-item>
                <a-form-item label="Critic 收敛阈值"><a-input-number v-model:value="form.threshold" :min="60" :max="100" /></a-form-item>
              </div>
            </a-collapse-panel>
          </a-collapse>
          <div class="notice">配置验证后，只有测试、检查或构建通过，任务才会被标记为完成。</div>
          <a-button type="primary" html-type="submit" :loading="submitting" block size="large">
            <template #icon><PlayCircleOutlined /></template>
            创建并进入任务详情
          </a-button>
        </a-form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.new-task-page{max-width:900px;margin:0 auto}.hero{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--sp-6);padding:var(--sp-6) 0}.eyebrow{display:block;color:var(--c-accent);font:700 11px var(--font-mono);letter-spacing:1.4px;margin-bottom:var(--sp-2)}h1{font-size:32px;letter-spacing:-1.2px;line-height:1.1;font-weight:750;color:var(--c-text)}.hero p{margin-top:var(--sp-2);color:var(--c-text-2);line-height:1.6}.panel{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--r-lg);box-shadow:var(--shadow-xs);overflow:hidden}.panel header{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border);font-size:var(--text-sm);font-weight:650;color:var(--c-text);letter-spacing:.4px;text-transform:uppercase}.panel-body{padding:var(--sp-5)}.workspace-picker{margin-top:var(--sp-2)}.help{margin-top:var(--sp-2);font-size:var(--text-xs);line-height:1.5;color:var(--c-text-3)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-4)}.form-grid :deep(.ant-input-number),:deep(.ant-select){width:100%}.detected-plan{min-height:88px;padding:var(--sp-3);border:1px solid var(--c-border);border-radius:var(--r-md);background:var(--c-surface-2);color:var(--c-text-2);font-size:var(--text-sm);line-height:1.55}.detected-plan.loading{opacity:.72}.plan-title{font-weight:650;color:var(--c-text)}.detected-plan p{margin:var(--sp-1) 0}.detected-plan code{display:inline-block;margin-top:var(--sp-1);padding:2px 6px;border-radius:4px;background:var(--c-surface);font:12px var(--font-mono);color:var(--c-text)}.dependency-note{color:var(--c-text-3)}.advanced-settings{margin:calc(var(--sp-2) * -1) 0 var(--sp-4)}.notice{margin:-4px 0 var(--sp-5);padding:var(--sp-3);border-radius:var(--r-md);background:var(--c-accent-soft);color:var(--c-text-2);font-size:var(--text-sm);line-height:1.55}@media(max-width:640px){.hero{align-items:flex-start;flex-direction:column;gap:var(--sp-4);padding:var(--sp-4) 0}.hero h1{font-size:28px}.hero :deep(.ant-btn){width:100%;min-height:44px}.panel header{padding:var(--sp-4)}.panel-body{padding:var(--sp-4)}.form-grid{grid-template-columns:1fr}}
</style>
