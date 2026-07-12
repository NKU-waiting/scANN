<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  datasets: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['busy'])

const selectedIds = ref([])
const embeddingSpace = ref('')
const confirmed = ref(false)
const indexType = ref('hnsw')
const metric = ref('l2')
const queryDatasetId = ref(null)
const cellId = ref(0)
const topK = ref(5)
const cellType = ref('')
const status = ref(null)
const results = ref([])
const building = ref(false)
const searching = ref(false)
const error = ref('')

const managedDatasets = computed(() => props.datasets.filter(dataset => dataset.id !== null))
const localBusy = computed(() => building.value || searching.value)
const selectedDatasets = computed(() => managedDatasets.value.filter(
  dataset => selectedIds.value.includes(dataset.id),
))

function synchronizeSelection() {
  const availableIds = new Set(managedDatasets.value.map(dataset => dataset.id))
  let nextIds = selectedIds.value.filter(id => availableIds.has(id))
  if (nextIds.length < 2) {
    const byDimension = new Map()
    for (const dataset of managedDatasets.value) {
      const group = byDimension.get(dataset.dim) || []
      group.push(dataset.id)
      byDimension.set(dataset.dim, group)
    }
    const compatible = [...byDimension.values()].find(group => group.length >= 2)
    if (compatible) nextIds = compatible.slice(0, 2)
  }
  if (nextIds.join(',') !== selectedIds.value.join(',')) selectedIds.value = nextIds
  if (!nextIds.includes(queryDatasetId.value)) {
    queryDatasetId.value = nextIds[0] ?? null
  }
}

async function loadStatus() {
  try {
    status.value = await apiRequest('/api/federated/index/status')
    if (status.value.ready) {
      selectedIds.value = [...status.value.dataset_ids]
      queryDatasetId.value = status.value.dataset_ids[0] ?? null
      embeddingSpace.value = status.value.embedding_space || ''
      indexType.value = status.value.index_type || indexType.value
      metric.value = status.value.metric || metric.value
    }
  } catch (reason) {
    error.value = reason.message
  }
}

function validateBuild() {
  if (selectedDatasets.value.length < 2) throw new Error('请至少选择两个受管理数据集')
  if (new Set(selectedDatasets.value.map(dataset => dataset.dim)).size !== 1) {
    throw new Error('所选数据集向量维度必须一致')
  }
  if (!embeddingSpace.value.trim()) throw new Error('请填写共享向量空间标识')
  if (!confirmed.value) throw new Error('请确认所选数据集已映射到同一向量空间')
}

async function buildJointIndex() {
  building.value = true
  error.value = ''
  results.value = []
  try {
    validateBuild()
    status.value = await apiRequest('/api/federated/index', {
      method: 'POST',
      body: JSON.stringify({
        dataset_ids: selectedIds.value,
        embedding_space: embeddingSpace.value.trim(),
        confirm_shared_space: confirmed.value,
        index_type: indexType.value,
        metric: metric.value,
      }),
    })
    selectedIds.value = [...status.value.dataset_ids]
    queryDatasetId.value = status.value.dataset_ids[0]
  } catch (reason) {
    error.value = reason.message
  } finally {
    building.value = false
  }
}

async function searchJointIndex() {
  searching.value = true
  error.value = ''
  results.value = []
  try {
    if (!status.value?.ready) throw new Error('请先构建联合索引')
    const parsedCellId = Number(cellId.value)
    const parsedTopK = Number(topK.value)
    if (!Number.isInteger(parsedCellId) || parsedCellId < 0) {
      throw new Error('细胞编号必须是非负整数')
    }
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1) {
      throw new Error('Top-K 必须是正整数')
    }
    const payload = {
      query_dataset_id: Number(queryDatasetId.value),
      cell_id: parsedCellId,
      top_k: parsedTopK,
    }
    if (cellType.value.trim()) payload.cell_type = cellType.value.trim()
    const data = await apiRequest('/api/federated/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    results.value = data.results
  } catch (reason) {
    error.value = reason.message
  } finally {
    searching.value = false
  }
}

watch(() => props.datasets.map(dataset => `${dataset.id}:${dataset.fingerprint}`).join('|'), () => {
  synchronizeSelection()
  const availableIds = new Set(managedDatasets.value.map(dataset => dataset.id))
  if (status.value?.ready && status.value.dataset_ids.some(id => !availableIds.has(id))) {
    status.value = { ready: false, dataset_ids: [], datasets: [] }
    results.value = []
  }
}, { immediate: true })
watch(selectedIds, ids => {
  if (!ids.includes(queryDatasetId.value)) queryDatasetId.value = ids[0] ?? null
}, { deep: true })
watch(localBusy, value => emit('busy', value), { immediate: true })
onMounted(loadStatus)
</script>

<template>
  <section class="federated-card" aria-labelledby="federated-title" :aria-busy="localBusy">
    <div class="heading">
      <div>
        <h2 id="federated-title">多数据集联合检索</h2>
        <p>将已对齐到同一向量空间的数据集联合建索引，并保留每个结果的来源身份。</p>
      </div>
      <span class="state" :class="{ ready: status?.ready }">
        {{ status?.ready ? `${status.datasets.length} 个数据集 · ${status.n_cells} 个细胞` : '尚未构建' }}
      </span>
    </div>

    <div v-if="managedDatasets.length >= 2" class="dataset-options">
      <label v-for="dataset in managedDatasets" :key="dataset.id">
        <input v-model="selectedIds" type="checkbox" :value="dataset.id" :disabled="disabled || localBusy" />
        <span><b>{{ dataset.name }}</b><small>{{ dataset.n_cells }} × {{ dataset.dim }}</small></span>
      </label>
    </div>
    <p v-else class="empty">请先上传至少两个受管理数据集；演示数据不参与联合索引。</p>

    <div class="build-grid">
      <label>
        <span>共享向量空间标识</span>
        <input v-model.trim="embeddingSpace" maxlength="100" placeholder="如 atlas-pca-v1" :disabled="disabled || localBusy" />
      </label>
      <label>
        <span>联合索引</span>
        <select v-model="indexType" :disabled="disabled || localBusy">
          <option value="flat">Flat（精确）</option>
          <option value="ivf">FAISS-IVF</option>
          <option value="hnsw">FAISS-HNSW</option>
          <option value="pq">FAISS-PQ</option>
          <option value="pq_rerank">PQ + 精确候选重排</option>
        </select>
      </label>
      <label>
        <span>距离度量</span>
        <select v-model="metric" :disabled="disabled || localBusy">
          <option value="l2">L2</option>
          <option value="cosine">Cosine</option>
          <option value="ip">IP</option>
        </select>
      </label>
      <button class="build" :disabled="disabled || localBusy || managedDatasets.length < 2" @click="buildJointIndex">
        {{ building ? '构建中…' : '构建联合索引' }}
      </button>
    </div>
    <label class="confirmation">
      <input v-model="confirmed" type="checkbox" :disabled="disabled || localBusy" />
      我确认这些向量由同一特征顺序或同一 embedding 模型产生；系统不会自动对齐不同 PCA 基底。
    </label>

    <div class="query-grid">
      <label>
        <span>查询来源数据集</span>
        <select v-model.number="queryDatasetId" :disabled="disabled || localBusy || !status?.ready">
          <option v-for="dataset in selectedDatasets" :key="dataset.id" :value="dataset.id">{{ dataset.name }}</option>
        </select>
      </label>
      <label>
        <span>本地细胞编号</span>
        <input v-model="cellId" type="number" min="0" :disabled="disabled || localBusy || !status?.ready" />
      </label>
      <label>
        <span>Top-K</span>
        <input v-model="topK" type="number" min="1" :disabled="disabled || localBusy || !status?.ready" />
      </label>
      <label>
        <span>细胞类型（可选）</span>
        <input v-model.trim="cellType" :disabled="disabled || localBusy || !status?.ready" />
      </label>
      <button class="search" :disabled="disabled || localBusy || !status?.ready" @click="searchJointIndex">
        {{ searching ? '检索中…' : '跨数据集检索' }}
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="results.length" class="table-scroll">
      <table>
        <caption class="sr-only">跨数据集相似细胞结果</caption>
        <thead><tr><th>#</th><th>来源数据集</th><th>本地 ID</th><th>细胞名称</th><th>类型</th><th>距离/得分</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in results" :key="row.composite_id">
            <td>{{ index + 1 }}</td><td><b>{{ row.dataset }}</b></td><td>{{ row.cell_id }}</td>
            <td>{{ row.cell_name }}</td><td>{{ row.cell_type || '未标注' }}</td><td>{{ row.distance }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.federated-card { margin-top: 16px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px #00000012; }
.heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h2 { margin: 0; font-size: 17px; } p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
.state { padding: 4px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; font-size: 12px; white-space: nowrap; }
.state.ready { background: #dcfce7; color: #166534; }
.dataset-options { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.dataset-options label { flex-direction: row; align-items: center; padding: 7px 10px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fbff; }
.dataset-options b, .dataset-options small { display: block; }.dataset-options small { color: #94a3b8; }
.build-grid, .query-grid { display: grid; grid-template-columns: 1.4fr 1fr 1fr auto; gap: 10px; align-items: end; margin-top: 12px; }
.query-grid { grid-template-columns: 1.3fr .8fr .7fr 1fr auto; padding-top: 12px; border-top: 1px solid #e2e8f0; }
label { display: flex; flex-direction: column; gap: 5px; color: #64748b; font-size: 12px; }
input, select { min-width: 0; padding: 8px 9px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; }
button { padding: 9px 13px; border: 0; border-radius: 7px; color: #fff; }
.build { background: #0f766e; }.search { background: #2563eb; } button:disabled { opacity: .55; cursor: not-allowed; }
.confirmation { flex-direction: row; align-items: flex-start; margin: 10px 0 14px; color: #475569; }
.confirmation input { margin-top: 2px; }.empty { padding: 12px; background: #f8fafc; border-radius: 8px; }.error { color: #b91c1c; }
.table-scroll { margin-top: 14px; overflow-x: auto; } table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; } th { color: #64748b; font-size: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 760px) { .heading { display: block; } .state { display: inline-block; margin-top: 8px; } .build-grid, .query-grid { grid-template-columns: 1fr; } }
</style>
