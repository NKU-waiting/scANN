import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))
vi.mock('../api', () => ({ apiRequest: mocks.apiRequest }))

import CellAssistant from './CellAssistant.vue'

const datasets = [
  { id: null, name: 'demo', n_cells: 100, dim: 8, fingerprint: 'demo' },
  { id: 1, name: 'study-a', n_cells: 10, dim: 4, fingerprint: 'a' },
  { id: 2, name: 'study-b', n_cells: 20, dim: 4, fingerprint: 'b' },
]

describe('CellAssistant', () => {
  beforeEach(() => {
    mocks.apiRequest.mockImplementation(async (path, options) => {
      if (path === '/api/assistant/status') {
        return {
          ai_configured: false,
          model: null,
          local_fallback: true,
          limits: { max_question_chars: 500, max_evidence: 10, max_cells: 100 },
        }
      }
      if (path === '/api/assistant/query') {
        const payload = JSON.parse(options.body)
        return {
          answer: 'study-b/b0 是首位证据 [E1]。',
          warning: '未配置 OpenAI provider，已返回本地证据摘要',
          generator: { mode: 'local_grounded', model: null },
          plan: {
            mode: 'similar_to_cell', metric: 'l2', top_k: payload.top_k,
            dataset_ids: payload.dataset_ids, cell_type: null,
          },
          evidence: [{
            id: 'E1', dataset: 'study-b', dataset_id: 2, cell_id: 0,
            cell_name: 'b0', cell_type: 'B', score: 0.01, score_kind: 'squared_l2_distance',
          }],
          citations: [{ id: 'E1', kind: 'cell', dataset: 'study-b', cell_name: 'b0' }],
          grounding: { raw_vectors_exposed: false },
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
  })

  it('submits a bounded shared-space question and renders grounded evidence', async () => {
    const wrapper = mount(CellAssistant, { props: { datasets } })
    await flushPromises()

    expect(wrapper.text()).toContain('本地证据模式')
    expect(wrapper.findAll('.dataset-options input:checked')).toHaveLength(2)
    await wrapper.get('textarea').setValue('请找出与 study-a/a0 最相似的细胞。')
    await wrapper.get('.shared-space input[type="text"]').setValue('atlas-pca-v1')
    await wrapper.get('.confirmation input').setValue(true)
    await wrapper.get('.actions button').trigger('click')
    await flushPromises()

    const call = mocks.apiRequest.mock.calls.find(([path]) => path === '/api/assistant/query')
    expect(JSON.parse(call[1].body)).toMatchObject({
      question: '请找出与 study-a/a0 最相似的细胞。',
      dataset_ids: [1, 2],
      top_k: 5,
      embedding_space: 'atlas-pca-v1',
      confirm_shared_space: true,
      use_ai: true,
    })
    expect(wrapper.text()).toContain('证据约束回答')
    expect(wrapper.text()).toContain('study-b/b0 是首位证据 [E1]')
    expect(wrapper.text()).toContain('squared_l2_distance')
    expect(wrapper.text()).toContain('不是生物学定论')
  })

  it('rejects an unconfirmed multi-dataset request before calling the API', async () => {
    const wrapper = mount(CellAssistant, { props: { datasets } })
    await flushPromises()
    await wrapper.get('textarea').setValue('总结数据集')
    await wrapper.get('.shared-space input[type="text"]').setValue('atlas-pca-v1')
    await wrapper.get('.actions button').trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('确认')
    expect(mocks.apiRequest.mock.calls.filter(([path]) => path === '/api/assistant/query')).toHaveLength(0)
  })
})
