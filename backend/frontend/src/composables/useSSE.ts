import { ref, onUnmounted } from 'vue'

export function useSSE() {
  const eventSource = ref<EventSource | null>(null)
  const connected = ref(false)
  const events = ref<any[]>([])

  function connect(url: string, onEvent: (data: any) => void) {
    disconnect()

    eventSource.value = new EventSource(url)
    connected.value = true

    eventSource.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        events.value.push(data)
        onEvent(data)
      } catch (e) {
        console.error('SSE parse error:', e)
      }
    }

    eventSource.value.onerror = () => {
      connected.value = false
      disconnect()
    }
  }

  function disconnect() {
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
      connected.value = false
    }
  }

  function clearEvents() {
    events.value = []
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected,
    events,
    connect,
    disconnect,
    clearEvents,
  }
}
