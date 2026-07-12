<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  datasets: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['busy'])

const selectedIds = ref([])
const question = ref('')
const embeddingSpace = ref('')
const confirmed = ref(false)
const topK = ref(5)
const metric = ref('auto')
const cellType = ref('')
const queryDatasetId = ref('')
const cellId = ref('')
const useAi = ref(true)
const providerStatus = ref(null)
const response = ref(null)
const loading = ref(false)
const error = ref('')
let requestGeneration = 0

const managedDatasets = computed(() => props.datasets.filter(dataset => dataset.id !== null))
const selectedDatasets = computed(() => managedDatasets.value.filter(
  dataset => selectedIds.value.includes(dataset.id),
))
const requiresSharedSpace = computed(() => selectedDatasets.value.length > 1)
const maxQuestionChars = computed(() => providerStatus.value?.limits?.max_question_chars || 2000)

function synchronizeSelection() {
  const available = new Set(managedDatasets.value.map(dataset => dataset.id))
  let next = selectedIds.value.filter(id => available.has(id))
  if (!next.length && managedDatasets.value.length) {
    const byDimension = new Map()
    for (const dataset of managedDatasets.value) {
      const group = byDimension.get(dataset.dim) || []
      group.push(dataset.id)
      byDimension.set(dataset.dim, group)
    }
    next = [...byDimension.values()].find(group => group.length >= 2)?.slice(0, 2)
      || [managedDatasets.value[0].id]
  }
  if (next.join(',') !== selectedIds.value.join(',')) selectedIds.value = next
  if (queryDatasetId.value !== '' && !next.includes(Number(queryDatasetId.value))) {
    queryDatasetId.value = ''
    cellId.value = ''
  }
}

async function loadStatus() {
  try {
    providerStatus.value = await apiRequest('/api/assistant/status')
  } catch (reason) {
    error.value = reason.message
  }
}

function buildPayload() {
  if (!question.value.trim()) throw new Error('请输入自然语言问题')
  if (!selectedDatasets.value.length) throw new Error('请至少选择一个受管理数据集')
  if (new Set(selectedDatasets.value.map(dataset => dataset.dim)).size !== 1) {
    throw new Error('所选数据集向量维度必须一致')
  }
  if (requiresSharedSpace.value && !embeddingSpace.value.trim()) {
    throw new Error('多数据集分析必须填写共享向量空间标识')
  }
  if (requiresSharedSpace.value && !confirmed.value) {
    throw new Error('请确认所选数据集已映射到同一向量空间')
  }
  const parsedTopK = Number(topK.value)
  if (!Number.isInteger(parsedTopK) || parsedTopK < 1) throw new Error('Top-K 必须是正整数')
  const payload = {
    question: question.value.trim(),
    dataset_ids: selectedIds.value,
    top_k: parsedTopK,
    use_ai: useAi.value,
  }
  if (requiresSharedSpace.value) {
    payload.embedding_space = embeddingSpace.value.trim()
    payload.confirm_shared_space = confirmed.value
  }
  if (metric.value !== 'auto') payload.metric = metric.value
  if (cellType.value.trim()) payload.cell_type = cellType.value.trim()
  const hasDataset = queryDatasetId.value !== ''
  const hasCell = cellId.value !== ''
  if (hasDataset !== hasCell) throw new Error('显式查询时，来源数据集和细胞编号必须同时填写')
  if (hasDataset) {
    const parsedCellId = Number(cellId.value)
    if (!Number.isInteger(parsedCellId) || parsedCellId < 0) {
      throw new Error('细胞编号必须是非负整数')
    }
    payload.query_dataset_id = Number(queryDatasetId.value)
    payload.cell_id = parsedCellId
  }
  return payload
}

async function ask() {
  const generation = ++requestGeneration
  loading.value = true
  error.value = ''
  response.value = null
  try {
    const data = await apiRequest('/api/assistant/query', {
      method: 'POST',
      body: JSON.stringify(buildPayload()),
    })
    if (generation === requestGeneration) response.value = data
  } catch (reason) {
    if (generation === requestGeneration) error.value = reason.message
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}

watch(() => props.datasets.map(dataset => `${dataset.id}:${dataset.fingerprint}`).join('|'), synchronizeSelection, { immediate: true })
watch(selectedIds, ids => {
  if (queryDatasetId.value !== '' && !ids.includes(Number(queryDatasetId.value))) {
    queryDatasetId.value = ''
    cellId.value = ''
  }
}, { deep: true })
watch(loading, value => emit('busy', value), { immediate: true })
onMounted(loadStatus)
onBeforeUnmount(() => { requestGeneration += 1 })
</script>

<template>
  <section class="assistant-card" aria-labelledby="assistant-title" :aria-busy="loading">
    <div class="heading">
      <div>
        <h2 id="assistant-title">RAG 单细胞分析助手</h2>
        <p>自然语言 → 受限检索计划 → 真实细胞证据 → 可追溯分析。</p>
      </div>
      <span class="provider" :class="{ online: providerStatus?.ai_configured }">
        {{ providerStatus?.ai_configured ? `AI · ${providerStatus.model}` : '本地证据模式' }}
      </span>
    </div>

    <div v-if="managedDatasets.length" class="dataset-options">
      <label v-for="dataset in managedDatasets" :key="dataset.id">
        <input v-model="selectedIds" type="checkbox" :value="dataset.id" :disabled="disabled || loading" />
        <span><b>{{ dataset.name }}</b><small>{{ dataset.n_cells }} × {{ dataset.dim }}</small></span>
      </label>
    </div>
    <p v-else class="empty">请先上传至少一个受管理数据集。</p>

    <label class="question">
      <span>自然语言问题</span>
      <textarea
        v-model="question"
        :maxlength="maxQuestionChars"
        :disabled="disabled || loading"
        placeholder="例如：请找出与 study-a/cell_0 最相似的 5 个细胞，并按证据总结类型与来源。"
      ></textarea>
      <small>{{ question.length }}/{{ maxQuestionChars }}</small>
    </label>

    <div class="controls">
      <label>
        <span>Top-K</span>
        <input v-model="topK" type="number" min="1" :disabled="disabled || loading" />
      </label>
      <label>
        <span>距离度量</span>
        <select v-model="metric" :disabled="disabled || loading">
          <option value="auto">从问题推断</option><option value="l2">L2</option>
          <option value="cosine">Cosine</option><option value="ip">IP</option>
        </select>
      </label>
      <label>
        <span>细胞类型（可选）</span>
        <input v-model.trim="cellType" :disabled="disabled || loading" placeholder="如 T cell" />
      </label>
      <label>
        <span>显式查询来源（可选）</span>
        <select v-model="queryDatasetId" :disabled="disabled || loading">
          <option value="">由问题解析</option>
          <option v-for="dataset in selectedDatasets" :key="dataset.id" :value="String(dataset.id)">{{ dataset.name }}</option>
        </select>
      </label>
      <label>
        <span>显式细胞编号（可选）</span>
        <input v-model="cellId" type="number" min="0" :disabled="disabled || loading" />
      </label>
    </div>

    <div v-if="requiresSharedSpace" class="shared-space">
      <label>
        <span>共享向量空间标识</span>
        <input v-model.trim="embeddingSpace" type="text" maxlength="100" :disabled="disabled || loading" placeholder="如 atlas-pca-v1" />
      </label>
      <label class="confirmation">
        <input v-model="confirmed" type="checkbox" :disabled="disabled || loading" />
        我确认这些数据集使用同一特征顺序或同一 embedding 模型。
      </label>
    </div>

    <div class="actions">
      <label class="ai-toggle">
        <input v-model="useAi" type="checkbox" :disabled="disabled || loading" />
        优先使用已配置 AI；未配置时返回本地证据摘要
      </label>
      <button :disabled="disabled || loading || !managedDatasets.length" @click="ask">
        {{ loading ? '检索与分析中…' : '提交自然语言分析' }}
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <article v-if="response" class="answer" aria-live="polite">
      <div class="answer-heading">
        <h3>证据约束回答</h3>
        <span>{{ response.generator.mode === 'openai_responses' ? `AI · ${response.generator.model}` : '本地摘要' }}</span>
      </div>
      <p v-if="response.warning" class="warning">{{ response.warning }}</p>
      <p class="answer-text">{{ response.answer }}</p>
      <div class="plan">
        <b>检索计划</b>
        <span>{{ response.plan.mode }} · {{ response.plan.metric }} · Top-{{ response.plan.top_k }}</span>
        <span v-if="response.plan.cell_type">类型：{{ response.plan.cell_type }}</span>
      </div>
      <div v-if="response.evidence.length" class="table-scroll">
        <table>
          <caption class="sr-only">RAG 检索证据</caption>
          <thead><tr><th>证据</th><th>来源</th><th>细胞</th><th>类型</th><th>距离/得分</th></tr></thead>
          <tbody>
            <tr v-for="row in response.evidence" :key="row.id">
              <td>[{{ row.id }}]</td><td>{{ row.dataset }}</td><td>{{ row.cell_name }} (#{{ row.cell_id }})</td>
              <td>{{ row.cell_type || '未标注' }}</td><td>{{ row.score }} <small>{{ row.score_kind }}</small></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="citations">
        <b>引用</b>
        <span v-for="citation in response.citations" :key="citation.id">
          [{{ citation.id }}] {{ citation.dataset }}<template v-if="citation.cell_name">/{{ citation.cell_name }}</template>
        </span>
      </div>
      <p class="disclaimer">回答仅基于所列检索证据，不是生物学定论、诊断或临床建议。</p>
    </article>
  </section>
</template>

<style scoped>
.assistant-card { margin-top: 16px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px #00000012; }
.heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
h2, h3 { margin: 0; } h2 { font-size: 17px; } h3 { font-size: 15px; }
p { margin: 4px 0 0; color: #64748b; font-size: 13px; }.provider { padding: 4px 9px; border-radius: 999px; background: #f1f5f9; color: #64748b; font-size: 12px; }
.provider.online { background: #ede9fe; color: #6d28d9; }.dataset-options { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.dataset-options label { flex-direction: row; align-items: center; padding: 7px 10px; border: 1px solid #e9d5ff; border-radius: 8px; background: #faf5ff; }
.dataset-options b, .dataset-options small { display: block; }.dataset-options small { color: #94a3b8; }
label { display: flex; flex-direction: column; gap: 5px; color: #64748b; font-size: 12px; }
input, select, textarea { padding: 8px 9px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; font: inherit; }
.question { position: relative; }.question textarea { min-height: 92px; resize: vertical; line-height: 1.5; }.question > small { align-self: flex-end; color: #94a3b8; }
.controls { display: grid; grid-template-columns: .65fr .9fr 1fr 1.2fr .8fr; gap: 10px; margin-top: 12px; }
.shared-space { display: grid; grid-template-columns: 1fr 1.6fr; gap: 12px; align-items: end; margin-top: 12px; padding: 11px; border-radius: 8px; background: #fffbeb; }
.confirmation, .ai-toggle { flex-direction: row; align-items: center; }.actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 14px; }
.actions button { padding: 9px 15px; border: 0; border-radius: 7px; background: #7c3aed; color: #fff; }.actions button:disabled { opacity: .55; }
.empty { padding: 12px; background: #f8fafc; border-radius: 8px; }.error { color: #b91c1c; }.warning { color: #92400e; }
.answer { margin-top: 14px; padding: 15px; border: 1px solid #ddd6fe; border-radius: 9px; background: #fafaff; }
.answer-heading { display: flex; justify-content: space-between; gap: 12px; }.answer-heading span { color: #6d28d9; font-size: 12px; }
.answer-text { margin: 12px 0; color: #1f2937; white-space: pre-wrap; line-height: 1.65; }.plan { display: flex; flex-wrap: wrap; gap: 10px; padding: 9px; border-radius: 7px; background: #fff; font-size: 12px; color: #475569; }
.citations { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; color: #475569; font-size: 12px; }.citations span { padding: 3px 7px; border-radius: 999px; background: #fff; }
.table-scroll { margin-top: 12px; overflow-x: auto; } table { width: 100%; border-collapse: collapse; background: #fff; font-size: 12px; }
th, td { padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: left; white-space: nowrap; } th { color: #64748b; } td small { display: block; color: #94a3b8; }
.disclaimer { margin-top: 10px; color: #9a3412; }.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 760px) { .heading, .actions { display: block; }.provider, .actions button { display: inline-block; margin-top: 9px; }.controls, .shared-space { grid-template-columns: 1fr; } }
</style>
