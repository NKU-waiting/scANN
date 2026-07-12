import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))
vi.mock('../api', () => ({ apiRequest: mocks.apiRequest }))

import FederatedSearch from './FederatedSearch.vue'

const datasets = [
  { id: null, name: 'demo', n_cells: 100, dim: 8, fingerprint: 'demo' },
  { id: 1, name: 'study-a', n_cells: 10, dim: 4, fingerprint: 'a' },
  { id: 2, name: 'study-b', n_cells: 20, dim: 4, fingerprint: 'b' },
]

describe('FederatedSearch', () => {
  beforeEach(() => {
    mocks.apiRequest.mockImplementation(async (path, options) => {
      if (path === '/api/federated/index/status') return { ready: false, dataset_ids: [] }
      if (path === '/api/federated/index') {
        const payload = JSON.parse(options.body)
        return {
          ready: true,
          dataset_ids: [...payload.dataset_ids].sort(),
          datasets: [{ name: 'study-a' }, { name: 'study-b' }],
          n_cells: 30,
          embedding_space: payload.embedding_space,
          index_type: payload.index_type,
          metric: payload.metric,
        }
      }
      if (path === '/api/federated/search') {
        return {
          results: [{
            composite_id: '2:0', dataset_id: 2, dataset: 'study-b', cell_id: 0,
            cell_name: 'b0', cell_type: 'B', distance: 0.01,
          }],
        }
      }
      throw new Error(`unexpected path: ${path}`)
    })
  })

  it('builds a declared shared-space index and renders source provenance', async () => {
    const wrapper = mount(FederatedSearch, { props: { datasets } })
    await flushPromises()

    expect(wrapper.findAll('.dataset-options input:checked')).toHaveLength(2)
    await wrapper.get('.build-grid input').setValue('atlas-pca-v1')
    await wrapper.get('.confirmation input').setValue(true)
    await wrapper.get('button.build').trigger('click')
    await flushPromises()

    const buildCall = mocks.apiRequest.mock.calls.find(([path]) => path === '/api/federated/index')
    expect(JSON.parse(buildCall[1].body)).toMatchObject({
      dataset_ids: [1, 2],
      embedding_space: 'atlas-pca-v1',
      confirm_shared_space: true,
    })

    await wrapper.get('button.search').trigger('click')
    await flushPromises()
    const searchCall = mocks.apiRequest.mock.calls.find(([path]) => path === '/api/federated/search')
    expect(JSON.parse(searchCall[1].body)).toMatchObject({
      query_dataset_id: 1,
      cell_id: 0,
      top_k: 5,
    })
    expect(wrapper.text()).toContain('study-b')
    expect(wrapper.text()).toContain('b0')
  })

  it('rejects dimension-incompatible selections before calling the build API', async () => {
    const incompatible = [
      ...datasets,
      { id: 3, name: 'wrong-dim', n_cells: 5, dim: 3, fingerprint: 'c' },
    ]
    const wrapper = mount(FederatedSearch, { props: { datasets: incompatible } })
    await flushPromises()
    await wrapper.get('.build-grid input').setValue('atlas-pca-v1')
    await wrapper.get('.confirmation input').setValue(true)
    const options = wrapper.findAll('.dataset-options input')
    await options[1].setValue(false)
    await options[2].setValue(true)
    await wrapper.get('button.build').trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('维度必须一致')
    expect(mocks.apiRequest.mock.calls.filter(([path]) => path === '/api/federated/index')).toHaveLength(0)
  })
})
