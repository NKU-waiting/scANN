import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, configureApi } from './api'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

describe('apiRequest', () => {
  it('adds the current bearer token and parses JSON', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    configureApi({ getToken: () => 'token-123', onUnauthorized: vi.fn() })

    const data = await apiRequest('/api/index/status')

    expect(data).toEqual({ status: 'ok' })
    const [, options] = globalThis.fetch.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer token-123')
  })

  it('does not force a JSON content type for multipart uploads', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 201 }))
    const body = new FormData()
    body.append('file', new File(['x'], 'cells.csv'))

    await apiRequest('/api/datasets/upload', { method: 'POST', body })

    const [, options] = globalThis.fetch.mock.calls[0]
    expect(options.headers['Content-Type']).toBeUndefined()
  })

  it('notifies the session owner and surfaces JSON errors on 401', async () => {
    const onUnauthorized = vi.fn()
    configureApi({ getToken: () => 'expired', onUnauthorized })
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'token 已过期' }), { status: 401 }),
    )

    await expect(apiRequest('/api/index/status')).rejects.toThrow('token 已过期')
    expect(onUnauthorized).toHaveBeenCalledWith('expired')
  })

  it('turns network failures into an actionable message', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('offline'))

    await expect(apiRequest('/api/health', {}, false)).rejects.toThrow('无法连接后端服务')
  })
})
