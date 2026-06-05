<script setup>
import { computed, ref, onMounted } from 'vue'

const status = ref(null)
const form = ref({
  cell_id: 0,
  top_k: 5,
  index_type: 'flat',
  compare_index_type: 'hnsw',
  metric: 'l2',
  cell_type: '',
  vector: '',
})
const queryMode = ref('cell') // 'cell' | 'vector'
const result = ref(null)
const buildInfo = ref(null)
const comparisonResults = ref([])
const loading = ref(false)
const building = ref(false)
const comparing = ref(false)
const error = ref('')

const indexLabels = {
  flat: 'Flat',
  faiss: 'FAISS-Flat',
  ivf: 'FAISS-IVF',
  hnsw: 'FAISS-HNSW',
  pq: 'FAISS-PQ',
}

const metadataFields = computed(() => status.value?.metadata_fields || [])

const datasetSummary = computed(() => [
  { label: '数据集', value: status.value?.dataset || '未加载' },
  { label: '细胞数', value: formatNumber(status.value?.n_cells || 0) },
  { label: '向量维度', value: formatNumber(status.value?.dim || 0) },
  { label: '当前索引', value: status.value?.index || '未构建' },
  { label: '距离度量', value: status.value?.metric === 'ip' ? 'IP（内积）' : 'L2（欧氏）' },
  { label: '元信息字段', value: metadataFields.value.length ? metadataFields.value.join('、') : '无' },
])

const resultRows = computed(() => result.value?.results || [])

const resultMetric = computed(() => {
  const metricMatch = result.value?.index?.match(/\(([^)]+)\)$/)
  return metricMatch?.[1] || form.value.metric
})

const valueLabel = computed(() => resultMetric.value === 'ip' ? '内积得分' : '距离')

const bestLabel = computed(() => resultMetric.value === 'ip' ? '最高得分' : '最近结果')

const worstLabel = computed(() => resultMetric.value === 'ip' ? '最低得分' : '最远结果')

const distanceStats = computed(() => {
  if (!resultRows.value.length) return null

  const distances = resultRows.value.map(row => Number(row.distance))
  const min = Math.min(...distances)
  const max = Math.max(...distances)
  const isInnerProduct = resultMetric.value === 'ip'
  return {
    min,
    max,
    best: isInnerProduct ? max : min,
    worst: isInnerProduct ? min : max,
    nearest: resultRows.value[0],
    farthest: resultRows.value[resultRows.value.length - 1],
  }
})

const distanceBars = computed(() => {
  if (!distanceStats.value) return []

  const span = distanceStats.value.max - distanceStats.value.min
  return resultRows.value.map((row, index) => {
    const distance = Number(row.distance)
    const normalized = span === 0 ? 1 : (distance - distanceStats.value.min) / span
    return {
      ...row,
      rank: index + 1,
      distance,
      width: Math.max(8, Math.round(normalized * 100)),
    }
  })
})

const typeDistribution = computed(() => {
  if (!resultRows.value.length) return []

  const counts = resultRows.value.reduce((acc, row) => {
    const label = row.cell_type || '未标注'
    acc[label] = (acc[label] || 0) + 1
    return acc
  }, {})

  return Object.entries(counts)
    .map(([label, count]) => ({
      label,
      count,
      percent: Math.round((count / resultRows.value.length) * 100),
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
})

function formatNumber(value) {
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function indexLabel(indexType) {
  return indexLabels[indexType] || indexType
}

function parseVectorInput() {
  const vec = form.value.vector.split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n))
  if (vec.length === 0) throw new Error('请输入有效的查询向量（逗号分隔）')
  return vec
}

function buildSearchPayload(indexType = form.value.index_type) {
  const payload = {
    top_k: Number(form.value.top_k),
    index_type: indexType,
    metric: form.value.metric,
  }
  if (queryMode.value === 'vector') {
    payload.vector = parseVectorInput()
  } else {
    payload.cell_id = Number(form.value.cell_id)
  }
  if (form.value.cell_type) payload.cell_type = form.value.cell_type
  return payload
}

async function requestSearch(indexType) {
  const r = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildSearchPayload(indexType)),
  })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || '检索失败')
  return data
}

async function fetchStatus() {
  const r = await fetch('/api/index/status')
  status.value = await r.json()
}

async function search() {
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await requestSearch(form.value.index_type)
    await fetchStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function buildIndex() {
  building.value = true
  error.value = ''
  try {
    const r = await fetch('/api/index/build', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index_type: form.value.index_type, metric: form.value.metric }),
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.error || '构建失败')
    buildInfo.value = data
    await fetchStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    building.value = false
  }
}

async function compareIndexes() {
  comparing.value = true
  error.value = ''
  comparisonResults.value = []
  const indexTypes = ['flat']
  if (form.value.compare_index_type !== 'flat') indexTypes.push(form.value.compare_index_type)

  try {
    for (const indexType of indexTypes) {
      try {
        const data = await requestSearch(indexType)
        const first = data.results?.[0]
        comparisonResults.value = [
          ...comparisonResults.value,
          {
            index_type: indexType,
            label: indexLabel(indexType),
            ok: true,
            index: data.index,
            query_ms: data.query_ms,
            returned: data.returned,
            first_cell: first?.cell_name || '-',
            first_distance: first?.distance ?? null,
          },
        ]
        result.value = data
      } catch (e) {
        comparisonResults.value = [
          ...comparisonResults.value,
          {
            index_type: indexType,
            label: indexLabel(indexType),
            ok: false,
            error: e.message,
          },
        ]
      }
    }
    await fetchStatus()
  } finally {
    comparing.value = false
  }
}

onMounted(fetchStatus)
</script>

<template>
  <div class="page">
    <header>
      <h1>scANN · 单细胞近似最近邻检索</h1>
      <p class="sub">输入查询细胞编号或向量，设置检索参数，获取 Top-K 相似细胞。</p>
    </header>

    <section class="dataset-card" v-if="status">
      <div class="section-heading">
        <h2>演示数据说明</h2>
        <span>{{ status.ready ? '索引就绪' : '索引未构建' }}</span>
      </div>
      <div class="dataset-grid">
        <div class="dataset-item" v-for="item in datasetSummary" :key="item.label">
          <span>{{ item.label }}</span>
          <b>{{ item.value }}</b>
        </div>
      </div>
    </section>

    <!-- 查询模式切换 -->
    <section class="mode-switch">
      <button :class="{ active: queryMode === 'cell' }" @click="queryMode = 'cell'">按细胞编号查询</button>
      <button :class="{ active: queryMode === 'vector' }" @click="queryMode = 'vector'">按向量查询</button>
    </section>

    <section class="panel">
      <div class="field" v-if="queryMode === 'cell'">
        <label>查询细胞编号</label>
        <input type="number" v-model="form.cell_id" min="0" />
      </div>
      <div class="field wide" v-if="queryMode === 'vector'">
        <label>查询向量（逗号分隔）</label>
        <input v-model="form.vector" placeholder="如 0.1, 0.5, -0.3, ..." />
      </div>
      <div class="field">
        <label>Top-K</label>
        <input type="number" v-model="form.top_k" min="1" max="50" />
      </div>
      <div class="field">
        <label>索引类型</label>
        <select v-model="form.index_type">
          <option value="flat">Flat（精确）</option>
          <option value="faiss">FAISS-Flat</option>
          <option value="ivf">FAISS-IVF</option>
          <option value="hnsw">FAISS-HNSW</option>
          <option value="pq">FAISS-PQ</option>
        </select>
      </div>
      <div class="field">
        <label>距离度量</label>
        <select v-model="form.metric">
          <option value="l2">L2（欧氏）</option>
          <option value="ip">IP（内积）</option>
        </select>
      </div>
      <div class="field">
        <label>限定细胞类型（可选）</label>
        <input v-model="form.cell_type" placeholder="如 type_1" />
      </div>
      <div class="field">
        <label>对比索引</label>
        <select v-model="form.compare_index_type">
          <option value="hnsw">FAISS-HNSW</option>
          <option value="ivf">FAISS-IVF</option>
          <option value="faiss">FAISS-Flat</option>
          <option value="pq">FAISS-PQ</option>
        </select>
      </div>
      <div class="btn-group">
        <button class="btn-primary" :disabled="loading" @click="search">{{ loading ? '检索中…' : '检索' }}</button>
        <button class="btn-build" :disabled="building" @click="buildIndex">{{ building ? '构建中…' : '构建索引' }}</button>
        <button class="btn-compare" :disabled="comparing" @click="compareIndexes">
          {{ comparing ? '对比中…' : '对比索引' }}
        </button>
      </div>
    </section>

    <section class="build-info" v-if="buildInfo">
      索引 <b>{{ buildInfo.index }}</b> 构建完成 · 耗时 <b class="highlight">{{ buildInfo.build_ms }} ms</b>
    </section>

    <p class="error" v-if="error">⚠ {{ error }}</p>

    <section class="comparison" v-if="comparisonResults.length">
      <div class="section-heading">
        <h2>索引对比</h2>
        <span>Flat vs {{ indexLabel(form.compare_index_type) }}</span>
      </div>
      <div class="comparison-table">
        <div class="comparison-row comparison-head">
          <span>索引</span>
          <span>查询耗时</span>
          <span>返回数</span>
          <span>首位结果</span>
          <span>{{ valueLabel }}</span>
        </div>
        <div class="comparison-row" v-for="item in comparisonResults" :key="item.index_type">
          <span>
            <b>{{ item.label }}</b>
            <small>{{ item.index || '未完成' }}</small>
          </span>
          <span>{{ item.ok ? `${item.query_ms} ms` : '失败' }}</span>
          <span>{{ item.ok ? item.returned : '-' }}</span>
          <span>{{ item.ok ? item.first_cell : item.error }}</span>
          <span>{{ item.ok && item.first_distance !== null ? formatNumber(item.first_distance) : '-' }}</span>
        </div>
      </div>
    </section>

    <section v-if="result" class="results">
      <div class="meta">
        返回 <b>{{ result.returned }}</b> 条 · 索引 <b>{{ result.index }}</b> ·
        查询耗时 <b>{{ result.query_ms }} ms</b>
      </div>
      <div v-if="resultRows.length" class="visual-grid">
        <article class="visual-card summary-card">
          <div class="visual-heading">
            <h2>查询摘要</h2>
            <span>{{ valueLabel }}</span>
          </div>
          <div class="summary-stats" v-if="distanceStats">
            <div>
              <span>{{ bestLabel }}</span>
              <b>{{ formatNumber(distanceStats.best) }}</b>
            </div>
            <div>
              <span>{{ worstLabel }}</span>
              <b>{{ formatNumber(distanceStats.worst) }}</b>
            </div>
            <div>
              <span>细胞类型</span>
              <b>{{ typeDistribution.length }}</b>
            </div>
          </div>
          <p class="summary-note" v-if="distanceStats">
            首位结果 {{ distanceStats.nearest.cell_name }}，编号 {{ distanceStats.nearest.cell_id }}。
          </p>
        </article>

        <article class="visual-card distance-card">
          <div class="visual-heading">
            <h2>{{ valueLabel }}条形图</h2>
            <span>Top {{ resultRows.length }}</span>
          </div>
          <div class="distance-list">
            <div class="distance-item" v-for="row in distanceBars" :key="`bar-${row.cell_id}`">
              <div class="distance-label">
                <span>#{{ row.rank }} {{ row.cell_name }}</span>
                <b>{{ formatNumber(row.distance) }}</b>
              </div>
              <div class="distance-track" :aria-label="`${row.cell_name} ${valueLabel} ${formatNumber(row.distance)}`">
                <span :style="{ width: `${row.width}%` }"></span>
              </div>
            </div>
          </div>
        </article>

        <article class="visual-card type-card">
          <div class="visual-heading">
            <h2>类型分布</h2>
            <span>{{ typeDistribution.length }} 类</span>
          </div>
          <div class="type-list">
            <div class="type-item" v-for="type in typeDistribution" :key="type.label">
              <div class="type-label">
                <span>{{ type.label }}</span>
                <b>{{ type.count }}</b>
              </div>
              <div class="type-track" :aria-label="`${type.label} 占比 ${type.percent}%`">
                <span :style="{ width: `${type.percent}%` }"></span>
              </div>
            </div>
          </div>
        </article>
      </div>
      <p v-else class="empty-state">未返回匹配结果，请调整 Top-K 或过滤条件后重试。</p>
      <table>
        <thead>
          <tr><th>#</th><th>细胞编号</th><th>名称</th><th>细胞类型</th><th>距离</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in result.results" :key="row.cell_id">
            <td>{{ i + 1 }}</td>
            <td>{{ row.cell_id }}</td>
            <td>{{ row.cell_name }}</td>
            <td>{{ row.cell_type }}</td>
            <td>{{ row.distance }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 880px; margin: 0 auto; padding: 32px 20px; }
header h1 { margin: 0 0 4px; font-size: 22px; }
.sub { color: #6b7280; margin: 0 0 20px; }
.dataset-card, .comparison { background: #fff; padding: 16px; border-radius: 8px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 12px; }
.section-heading h2 { margin: 0; font-size: 16px; color: #111827; }
.section-heading span { color: #0f766e; font-size: 12px; font-weight: 600; white-space: nowrap; }
.dataset-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.dataset-item { background: #f9fafb; border: 1px solid #edf0f3; border-radius: 7px; padding: 10px; min-width: 0; }
.dataset-item span { display: block; color: #6b7280; font-size: 12px; margin-bottom: 4px; }
.dataset-item b { color: #111827; display: block; font-size: 14px; overflow-wrap: anywhere; }
.panel { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end;
  background: #fff; padding: 18px 16px; border-radius: 10px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
/* 模式切换 */
.mode-switch { display: flex; gap: 0; margin-bottom: 12px; }
.mode-switch button { flex: 1; padding: 10px 0; border: 1px solid #d1d5db; background: #fff;
  font-size: 14px; color: #6b7280; cursor: pointer; transition: all .15s; }
.mode-switch button:first-child { border-radius: 8px 0 0 8px; }
.mode-switch button:last-child { border-radius: 0 8px 8px 0; border-left: none; }
.mode-switch button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field.wide { flex: 1 1 240px; }
.field label { font-size: 12px; color: #6b7280; }
.field input, .field select { padding: 7px 9px; border: 1px solid #d1d5db; border-radius: 7px; font-size: 14px; }
.btn-group { display: flex; gap: 8px; align-items: flex-end; }
.btn-primary { padding: 9px 22px; border: none; border-radius: 8px; background: #2563eb; color: #fff;
  font-size: 14px; }
.btn-build { padding: 9px 16px; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; color: #374151;
  font-size: 13px; }
.btn-compare { padding: 9px 16px; border: none; border-radius: 8px; background: #0f766e; color: #fff;
  font-size: 13px; }
button:disabled { opacity: .6; cursor: not-allowed; }
.build-info { background: #eff6ff; padding: 10px 16px; border-radius: 8px; margin-top: 12px;
  font-size: 14px; color: #1e40af; }
.highlight { color: #dc2626; font-weight: 700; }
.error { color: #dc2626; margin-top: 8px; }
.comparison-table { display: grid; gap: 1px; overflow: hidden; border: 1px solid #e5e7eb; border-radius: 8px;
  background: #e5e7eb; }
.comparison-row { display: grid; grid-template-columns: 1.1fr .85fr .6fr 1fr .75fr; gap: 10px;
  align-items: center; background: #fff; padding: 10px 12px; color: #374151; font-size: 13px; }
.comparison-row span { min-width: 0; overflow-wrap: anywhere; }
.comparison-row b { display: block; color: #111827; font-size: 13px; }
.comparison-row small { display: block; color: #6b7280; font-size: 12px; margin-top: 2px; }
.comparison-head { background: #f9fafb; color: #6b7280; font-weight: 600; }
.meta { margin: 20px 0 8px; font-size: 14px; color: #374151; }
.visual-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 1.35fr);
  gap: 12px; margin: 12px 0; }
.visual-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.summary-card { border-top: 3px solid #0f766e; }
.distance-card { grid-row: span 2; border-top: 3px solid #2563eb; }
.type-card { border-top: 3px solid #d97706; }
.visual-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-bottom: 12px; }
.visual-heading h2 { margin: 0; font-size: 15px; color: #111827; }
.visual-heading span { color: #6b7280; font-size: 12px; white-space: nowrap; }
.summary-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.summary-stats div { background: #f9fafb; border-radius: 7px; padding: 9px 10px; min-width: 0; }
.summary-stats span { display: block; color: #6b7280; font-size: 12px; margin-bottom: 3px; }
.summary-stats b { color: #111827; font-size: 16px; overflow-wrap: anywhere; }
.summary-note { margin: 12px 0 0; color: #4b5563; font-size: 13px; line-height: 1.5; }
.distance-list, .type-list { display: flex; flex-direction: column; gap: 10px; }
.distance-label, .type-label { display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 5px; color: #374151; font-size: 13px; }
.distance-label span, .type-label span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.distance-label b, .type-label b { color: #111827; font-variant-numeric: tabular-nums; white-space: nowrap; }
.distance-track, .type-track { height: 9px; overflow: hidden; border-radius: 999px; background: #edf2f7; }
.distance-track span, .type-track span { display: block; height: 100%; border-radius: inherit; }
.distance-track span { background: linear-gradient(90deg, #38bdf8, #2563eb); }
.type-track span { background: linear-gradient(90deg, #fbbf24, #d97706); }
.empty-state { background: #fff; border: 1px dashed #d1d5db; border-radius: 8px; color: #6b7280;
  padding: 14px; font-size: 14px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px;
  overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
th, td { padding: 9px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #f0f1f3; }
th { background: #f9fafb; color: #6b7280; font-weight: 600; }
@media (max-width: 760px) {
  .dataset-grid { grid-template-columns: 1fr; }
  .comparison-row { grid-template-columns: 1fr 1fr; }
  .comparison-head { display: none; }
  .visual-grid { grid-template-columns: 1fr; }
  .distance-card { grid-row: auto; }
  .summary-stats { grid-template-columns: 1fr; }
}
</style>
