const API_BASE = '/api'

export const taskApi = {
  async listTasks(status?: string) {
    const url = status
      ? `${API_BASE}/tasks?status=${status}`
      : `${API_BASE}/tasks`
    const response = await fetch(url)
    if (!response.ok) throw new Error('获取任务列表失败')
    return response.json()
  },

  async getTask(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}`)
    if (!response.ok) throw new Error('获取任务详情失败')
    return response.json()
  },

  async createTask(
    requirement: string,
    workspaceDir: string,
    domain: string,
    verificationProfile = 'none',
    maxRounds = 3,
    threshold = 85,
  ) {
    const response = await fetch(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requirement,
        workspace_dir: workspaceDir,
        domain,
        verification_profile: verificationProfile,
        max_rounds: maxRounds,
        threshold,
      }),
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '创建任务失败')
    }
    return response.json()
  },

  async startTask(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/start`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('启动任务失败')
    return response.json()
  },

  async pauseTask(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/pause`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('暂停任务失败')
    return response.json()
  },

  async resumeTask(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/resume`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('恢复任务失败')
    return response.json()
  },

  async cancelTask(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/cancel`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('取消任务失败')
    return response.json()
  },

  async approveChangeset(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/changeset/approve`, { method: 'POST' })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '应用变更失败')
    }
    return response.json()
  },

  async discardChangeset(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/changeset/discard`, { method: 'POST' })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '丢弃变更失败')
    }
    return response.json()
  },

  async getProgress(id: string) {
    const response = await fetch(`${API_BASE}/tasks/${id}/progress`)
    if (!response.ok) throw new Error('获取进度失败')
    return response.json()
  },

  async getSubtaskRounds(taskId: string, subtaskId: string) {
    const response = await fetch(
      `${API_BASE}/tasks/${taskId}/subtasks/${subtaskId}/rounds`
    )
    if (!response.ok) throw new Error('获取子任务迭代记录失败')
    return response.json()
  },
}
