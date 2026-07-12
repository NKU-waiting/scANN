import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))
vi.mock('../api', () => ({ apiRequest: mocks.apiRequest }))

import DatasetManager from './DatasetManager.vue'

const resources = [
  {
    id: null,
    name: 'demo',
    original_filename: null,
    file_format: 'demo',
    n_cells: 100,
    dim: 8,
    active: true,
    deletable: false,
    created_at: null,
  },
  {
    id: 7,
    name: 'uploaded',
    original_filename: 'cells.npy',
    file_format: 'npy',
    n_cells: 20,
    dim: 4,
    active: false,
    deletable: true,
    created_at: '2026-01-01T00:00:00Z',
  },
]

describe('DatasetManager', () => {
  beforeEach(() => {
    mocks.apiRequest.mockImplementation(async path => {
      if (path === '/api/datasets') return { datasets: resources }
      if (path === '/api/datasets/7/activate') return { status: { dataset: 'uploaded' } }
      throw new Error(`unexpected path: ${path}`)
    })
  })

  it('renders managed resources and activates a compatible dataset', async () => {
    const wrapper = mount(DatasetManager, {
      props: { status: { dataset_fingerprint: 'demo' }, isAdmin: true },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('uploaded')
    expect(wrapper.emitted('resources')?.[0]).toEqual([resources])
    const switchButtons = wrapper.findAll('button').filter(button => button.text() === '切换')
    await switchButtons.at(-1).trigger('click')
    await flushPromises()

    expect(mocks.apiRequest).toHaveBeenCalledWith(
      '/api/datasets/7/activate',
      { method: 'POST' },
    )
    expect(wrapper.emitted('changed')?.[0]).toEqual([{ dataset: 'uploaded' }])
  })

  it('rejects an empty upload before making a request', async () => {
    const wrapper = mount(DatasetManager, { props: { status: null, isAdmin: false } })
    await flushPromises()
    mocks.apiRequest.mockClear()

    const uploadButton = wrapper.findAll('button').find(button => button.text() === '上传并激活')
    await uploadButton.trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('请选择')
    expect(mocks.apiRequest).not.toHaveBeenCalled()
  })

  it('disables lifecycle actions while another workspace operation is active', async () => {
    const wrapper = mount(DatasetManager, {
      props: { status: { dataset_fingerprint: 'demo' }, isAdmin: true, disabled: true },
    })
    await flushPromises()

    const uploadButton = wrapper.findAll('button').find(button => button.text() === '上传并激活')
    const switchButton = wrapper.findAll('button').find(button => button.text() === '切换')
    expect(uploadButton.attributes('disabled')).toBeDefined()
    expect(switchButton.attributes('disabled')).toBeDefined()
  })
})
