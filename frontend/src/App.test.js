import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  configureApi: vi.fn(),
}))
vi.mock('./api', () => mocks)

import App from './App.vue'

describe('App authentication gate', () => {
  beforeEach(() => {
    mocks.apiRequest.mockImplementation(async path => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/index/status') {
        return {
          dataset: 'demo',
          n_cells: 100,
          dim: 8,
          ready: true,
          index_type: 'flat',
          metric: 'l2',
          metadata_fields: ['cell_type'],
          limits: {
            max_top_k: 1000,
            max_eval_queries: 1000,
            max_visualization_points: 500,
          },
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
  })

  it('keeps the workspace hidden for anonymous visitors', async () => {
    const wrapper = shallowMount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('登录')
    expect(wrapper.findComponent({ name: 'DatasetManager' }).exists()).toBe(false)
  })

  it('restores a verified session before exposing resource managers', async () => {
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))

    const wrapper = shallowMount(App)
    await flushPromises()

    expect(mocks.apiRequest).toHaveBeenCalledWith('/api/auth/me')
    expect(wrapper.findComponent({ name: 'DatasetManager' }).exists()).toBe(true)
    expect(wrapper.text()).toContain('当前数据与索引')
  })

  it('surfaces comparison validation errors instead of rejecting silently', async () => {
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    const numericInputs = wrapper.findAll('.panel input[type="number"]')
    await numericInputs[1].setValue('0')
    await wrapper.get('.btn-compare').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Top-K 必须是 1 到 1000 的整数')
  })

  it('synchronizes the query form after a persisted index is loaded', async () => {
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    wrapper.findComponent({ name: 'IndexManager' }).vm.$emit('changed', {
      dataset: 'demo',
      n_cells: 100,
      dim: 8,
      ready: true,
      index_type: 'hnsw',
      metric: 'cosine',
      metadata_fields: ['cell_type'],
      limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
    })
    await flushPromises()

    const selects = wrapper.findAll('.panel select')
    expect(selects[0].element.value).toBe('hnsw')
    expect(selects[1].element.value).toBe('cosine')
  })

  it('clears private inputs and ignores an old evaluation after logout and relogin', async () => {
    let resolveEvaluation
    const evaluation = new Promise(resolve => { resolveEvaluation = resolve })
    mocks.apiRequest.mockImplementation(async (path) => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/auth/login') {
        return { token: 'bob-token', user: { id: 2, username: 'bob', role: 'user' } }
      }
      if (path === '/api/index/status') {
        return {
          dataset: 'demo', n_cells: 100, dim: 8, ready: true, index_type: 'flat', metric: 'l2',
          metadata_fields: ['cell_type'],
          limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
        }
      }
      if (path === '/api/eval') return evaluation
      throw new Error(`unexpected path: ${path}`)
    })
    localStorage.setItem('scann_token', 'alice-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    await wrapper.findAll('.mode-switch button')[1].trigger('click')
    await wrapper.get('.field.wide input').setValue('1,2,3,4,5,6,7,8')
    await wrapper.get('.btn-eval').trigger('click')
    await wrapper.get('.btn-logout').trigger('click')

    const authInputs = wrapper.findAll('.auth-form input')
    await authInputs[0].setValue('bob')
    await authInputs[1].setValue('pass123')
    await wrapper.get('.btn-auth').trigger('click')
    await flushPromises()
    await wrapper.findAll('.mode-switch button')[1].trigger('click')

    expect(wrapper.get('.field.wide input').element.value).toBe('')
    resolveEvaluation({
      results: [{ index_type: 'flat', top_k: 10, effective_top_k: 10, recall_at_k: 1 }],
    })
    await flushPromises()
    expect(wrapper.find('.eval-results').exists()).toBe(false)
  })

  it('labels evaluation recall with the backend effective K', async () => {
    mocks.apiRequest.mockImplementation(async (path) => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/index/status') {
        return {
          dataset: 'small', n_cells: 5, dim: 8, ready: true, index_type: 'flat', metric: 'l2',
          metadata_fields: [],
          limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
        }
      }
      if (path === '/api/eval') {
        return {
          results: [{
            index_type: 'flat', top_k: 10, effective_top_k: 4,
            recall_at_k: 1, avg_query_ms: 0.1, build_ms: 0.2,
          }],
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    await wrapper.get('.btn-eval').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Recall@4')
    expect(wrapper.text()).toContain('请求 K=10')
  })

  it('shows the paired PQ rerank recall, latency, and index-size tradeoff', async () => {
    mocks.apiRequest.mockImplementation(async (path) => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/index/status') {
        return {
          dataset: 'demo', n_cells: 640, dim: 16, ready: true, index_type: 'flat', metric: 'l2',
          metadata_fields: [],
          limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
        }
      }
      if (path === '/api/eval') {
        return {
          results: [
            {
              index_type: 'pq', top_k: 10, effective_top_k: 10, recall_at_k: 0.6,
              avg_query_ms: 0.2, build_ms: 1, index_bytes: 400, bytes_per_vector: 0.63,
              parameters: { m: 8, nbits: 4 },
            },
            {
              index_type: 'pq_rerank', top_k: 10, effective_top_k: 10, recall_at_k: 0.9,
              avg_query_ms: 0.3, build_ms: 1, index_bytes: 400, bytes_per_vector: 0.63,
              parameters: { m: 8, nbits: 4, rerank_factor: 4 },
            },
          ],
          ann_improvement: {
            recall_delta: 0.3,
            avg_query_ms_delta: 0.1,
            index_bytes_delta: 0,
          },
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    const checkboxes = wrapper.findAll('.eval-checkboxes input')
    await checkboxes[0].setValue(false)
    await checkboxes[3].setValue(false)
    await checkboxes[4].setValue(true)
    await checkboxes[5].setValue(true)
    await wrapper.get('.btn-eval').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('PQ 候选精确重排')
    expect(wrapper.text()).toContain('+30.0 个百分点')
    expect(wrapper.text()).toContain('+0.1 ms')
    expect(wrapper.text()).toContain('+0 B')
    expect(wrapper.text()).toContain('0.63 B/细胞')
  })

  it('runs a cell-id search selected from the embedding plot', async () => {
    mocks.apiRequest.mockImplementation(async (path, options) => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/index/status') {
        return {
          dataset: 'demo', n_cells: 100, dim: 8, ready: true, index_type: 'flat', metric: 'l2',
          metadata_fields: [],
          limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
        }
      }
      if (path === '/api/search') {
        const payload = JSON.parse(options.body)
        return {
          query_id: payload.cell_id + 1,
          query_cell_id: payload.cell_id,
          dataset_fingerprint: 'demo-fingerprint',
          index: 'flat(l2)',
          metric: 'l2',
          query_ms: 0.1,
          returned: 1,
          results: [{ cell_id: payload.cell_id + 1, cell_name: 'neighbor', distance: 1 }],
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
    localStorage.setItem('scann_token', 'valid-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'EmbeddingPlot' }).vm.$emit('select-cell', 7)
    await flushPromises()

    const searchCalls = mocks.apiRequest.mock.calls.filter(([path]) => path === '/api/search')
    expect(searchCalls).toHaveLength(2)
    expect(JSON.parse(searchCalls[1][1].body).cell_id).toBe(7)
    expect(wrapper.findAll('.mode-switch button')[0].attributes('aria-pressed')).toBe('true')
  })

  it('does not write an initial-session status failure into a new login', async () => {
    let rejectInitialStatus
    const initialStatus = new Promise((resolve, reject) => {
      rejectInitialStatus = reject
    })
    let statusCalls = 0
    const readyStatus = {
      dataset: 'demo', n_cells: 100, dim: 8, ready: true, index_type: 'flat', metric: 'l2',
      metadata_fields: [],
      limits: { max_top_k: 1000, max_eval_queries: 1000, max_visualization_points: 500 },
    }
    mocks.apiRequest.mockImplementation(async (path) => {
      if (path === '/api/auth/me') return { user: { id: 1, username: 'alice', role: 'user' } }
      if (path === '/api/auth/login') {
        return { token: 'bob-token', user: { id: 2, username: 'bob', role: 'user' } }
      }
      if (path === '/api/index/status') {
        statusCalls += 1
        return statusCalls === 1 ? initialStatus : readyStatus
      }
      throw new Error(`unexpected path: ${path}`)
    })
    localStorage.setItem('scann_token', 'alice-token')
    localStorage.setItem('scann_user', JSON.stringify({ id: 1, username: 'alice', role: 'user' }))
    const wrapper = shallowMount(App)
    await flushPromises()

    await wrapper.get('.btn-logout').trigger('click')
    const authInputs = wrapper.findAll('.auth-form input')
    await authInputs[0].setValue('bob')
    await authInputs[1].setValue('pass123')
    await wrapper.get('.btn-auth').trigger('click')
    await flushPromises()

    rejectInitialStatus(new Error('old session failure'))
    await flushPromises()

    expect(wrapper.text()).toContain('bob')
    expect(wrapper.text()).not.toContain('old session failure')
  })
})
