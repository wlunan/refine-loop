import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskApi } from '../api/task'

export interface SubTask {
  id: string
  title: string
  description: string
  status: string
  dependencies: string[]
  score: number | null
  iterations: number
  error: string | null
}

export interface Task {
  id: string
  title: string
  description: string
  status: string
  progress_percent: number
  workspace_dir: string
  domain: string
  error: string | null
  total_tokens: number
  created_at: string
  updated_at: string
  completed_at: string | null
  subtasks: SubTask[]
}

export interface TaskProgress {
  task_id: string
  status: string
  progress_percent: number
  current_subtask: string | null
  completed_subtasks: number
  total_subtasks: number
  total_tokens: number
  message: string
}

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const runningTasks = computed(() =>
    tasks.value.filter((t) => t.status === 'running')
  )

  const completedTasks = computed(() =>
    tasks.value.filter((t) => t.status === 'completed')
  )

  async function fetchTasks(status?: string) {
    loading.value = true
    error.value = null
    try {
      tasks.value = await taskApi.listTasks(status)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchTask(id: string) {
    loading.value = true
    error.value = null
    try {
      currentTask.value = await taskApi.getTask(id)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function createTask(requirement: string, workspaceDir: string, domain: string) {
    loading.value = true
    error.value = null
    try {
      const result = await taskApi.createTask(requirement, workspaceDir, domain)
      await fetchTasks()
      return result
    } catch (e: any) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function startTask(id: string) {
    try {
      await taskApi.startTask(id)
      await fetchTask(id)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function pauseTask(id: string) {
    try {
      await taskApi.pauseTask(id)
      await fetchTask(id)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function resumeTask(id: string) {
    try {
      await taskApi.resumeTask(id)
      await fetchTask(id)
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function cancelTask(id: string) {
    try {
      await taskApi.cancelTask(id)
      await fetchTask(id)
    } catch (e: any) {
      error.value = e.message
    }
  }

  function updateTaskProgress(progress: TaskProgress) {
    const index = tasks.value.findIndex((t) => t.id === progress.task_id)
    if (index !== -1) {
      tasks.value[index].progress_percent = progress.progress_percent
      tasks.value[index].status = progress.status
      tasks.value[index].total_tokens = progress.total_tokens
    }
    if (currentTask.value?.id === progress.task_id) {
      currentTask.value.progress_percent = progress.progress_percent
      currentTask.value.status = progress.status
      currentTask.value.total_tokens = progress.total_tokens
    }
  }

  return {
    tasks,
    currentTask,
    loading,
    error,
    runningTasks,
    completedTasks,
    fetchTasks,
    fetchTask,
    createTask,
    startTask,
    pauseTask,
    resumeTask,
    cancelTask,
    updateTaskProgress,
  }
})
