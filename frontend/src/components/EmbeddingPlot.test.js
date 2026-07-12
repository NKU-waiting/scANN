import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))
vi.mock('../api', () => ({ apiRequest: mocks.apiRequest }))

import EmbeddingPlot from './EmbeddingPlot.vue'

describe('EmbeddingPlot', () => {
  beforeEach(() => {
    mocks.apiRequest.mockResolvedValue({
      method: 'umap',
      returned: 3,
      n_cells: 100,
      points: [
        { cell_id: 0, cell_name: 'query', cell_type: 'a', x: 0, y: 0 },
        { cell_id: 1, cell_name: 'neighbor', cell_type: 'a', x: 1, y: 1 },
        { cell_id: 2, cell_name: 'context', cell_type: 'b', x: 2, y: -1 },
      ],
    })
  })

  it('highlights the query and Top-K neighbors in the SVG', async () => {
    const wrapper = mount(EmbeddingPlot, {
      props: {
        queryCellId: 0,
        maxPoints: 500,
        result: {
          query_id: 9,
          dataset_fingerprint: 'fingerprint',
          results: [{ cell_id: 1 }],
        },
      },
    })
    await flushPromises()

    const circles = wrapper.findAll('circle')
    expect(circles).toHaveLength(3)
    expect(circles[0].attributes('fill')).toBe('#dc2626')
    expect(circles[1].attributes('fill')).toBe('#2563eb')
    expect(mocks.apiRequest.mock.calls[0][0]).toContain('include_ids=0%2C1')
    expect(mocks.apiRequest.mock.calls[0][0]).toContain('max_points=500')
  })
})
