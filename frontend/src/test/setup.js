import { afterEach, vi } from 'vitest'

afterEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})
