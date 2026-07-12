<script setup>
import { computed, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  result: { type: Object, required: true },
  queryCellId: { type: Number, default: null },
  maxPoints: { type: Number, default: 1200 },
})
const emit = defineEmits(['select-cell'])

const projection = ref(null)
const method = ref('umap')
const loading = ref(false)
const error = ref('')
const width = 720
const height = 390
const padding = 24

const neighborIds = computed(() => new Set(props.result.results.map(row => row.cell_id)))
const plottedPoints = computed(() => {
  const points = projection.value?.points || []
  if (!points.length) return []
  const xs = points.map(point => point.x)
  const ys = points.map(point => point.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  return points.map(point => ({
    ...point,
    sx: padding + ((point.x - minX) / spanX) * (width - padding * 2),
    sy: height - padding - ((point.y - minY) / spanY) * (height - padding * 2),
    role: point.cell_id === props.queryCellId
      ? 'query'
      : neighborIds.value.has(point.cell_id) ? 'neighbor' : 'context',
  }))
})

const palette = ['#94a3b8', '#a78bfa', '#2dd4bf', '#f59e0b', '#f472b6', '#84cc16']
function pointColor(point) {
  if (point.role === 'query') return '#dc2626'
  if (point.role === 'neighbor') return '#2563eb'
  const label = point.cell_type || 'unknown'
  let hash = 0
  for (const character of label) hash = (hash * 31 + character.charCodeAt(0)) >>> 0
  return palette[hash % palette.length]
}

function pointRadius(point) {
  if (point.role === 'query') return 7
  if (point.role === 'neighbor') return 5
  return 2.6
}

function selectPoint(point) {
  if (Number.isInteger(point.cell_id)) emit('select-cell', point.cell_id)
}

async function loadProjection() {
  if (!props.result?.results) return
  loading.value = true
  error.value = ''
  try {
    const ids = props.result.results.map(row => row.cell_id)
    if (Number.isInteger(props.queryCellId)) ids.unshift(props.queryCellId)
    const params = new URLSearchParams({
      method: method.value,
      max_points: String(Math.min(1200, Math.max(10, props.maxPoints))),
      include_ids: [...new Set(ids)].slice(0, 101).join(','),
    })
    projection.value = await apiRequest(`/api/visualization/embedding?${params}`)
  } catch (reason) {
    error.value = reason.message
    projection.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.result.query_id, props.result.dataset_fingerprint, method.value],
  loadProjection,
  { immediate: true },
)
</script>

<template>
  <article class="embedding-card" aria-labelledby="embedding-title" :aria-busy="loading">
    <div class="embedding-heading">
      <div>
        <h2 id="embedding-title">二维邻域分布</h2>
        <p>高亮查询细胞与 Top-K 结果；点击或按 Enter/空格可直接查询任意点。</p>
      </div>
      <label>
        <span class="sr-only">投影方法</span>
        <select v-model="method">
          <option value="umap">UMAP</option>
          <option value="pca">PCA</option>
        </select>
      </label>
    </div>
    <p v-if="loading" class="state">正在计算 {{ method.toUpperCase() }} 投影，首次运行可能稍慢…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="plottedPoints.length" class="plot-wrap">
      <svg :viewBox="`0 0 ${width} ${height}`" role="img" aria-labelledby="embedding-title embedding-desc">
        <desc id="embedding-desc">查询细胞为红色，近邻为蓝色，其他抽样细胞按类型着色。</desc>
        <rect width="100%" height="100%" rx="12" fill="#f8fafc" />
        <circle
          v-for="point in plottedPoints"
          :key="point.cell_id"
          :cx="point.sx"
          :cy="point.sy"
          :r="pointRadius(point)"
          :fill="pointColor(point)"
          :fill-opacity="point.role === 'context' ? 0.58 : 0.95"
          :stroke="point.role === 'context' ? 'none' : '#fff'"
          :stroke-width="point.role === 'context' ? 0 : 1.5"
          role="button"
          tabindex="0"
          :aria-label="`查询细胞 ${point.cell_name}，编号 ${point.cell_id}`"
          @click="selectPoint(point)"
          @keydown.enter.prevent="selectPoint(point)"
          @keydown.space.prevent="selectPoint(point)"
        >
          <title>{{ point.cell_name }} · {{ point.cell_type || '未标注' }} · {{ point.role }}</title>
        </circle>
      </svg>
      <div class="legend">
        <span v-if="Number.isInteger(queryCellId)"><i class="query"></i>查询细胞</span>
        <span><i class="neighbor"></i>Top-K 结果</span>
        <span><i class="context"></i>背景细胞</span>
        <small>{{ projection.method.toUpperCase() }} · {{ projection.returned }}/{{ projection.n_cells }} 点</small>
      </div>
    </div>
  </article>
</template>

<style scoped>
.embedding-card { margin: 14px 0; padding: 16px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; }
.embedding-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; font-size: 16px; } p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
select { padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; }
.state { padding: 28px 0; text-align: center; }.error { color: #b91c1c; }
.plot-wrap { margin-top: 12px; } svg { display: block; width: 100%; max-height: 440px; }
circle[role='button'] { cursor: pointer; outline: none; }
circle[role='button']:focus { stroke: #111827; stroke-width: 2.5; }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 10px; color: #475569; font-size: 12px; }
.legend span { display: inline-flex; gap: 5px; align-items: center; }.legend small { margin-left: auto; color: #94a3b8; }
.legend i { width: 9px; height: 9px; border-radius: 50%; }.legend .query { background: #dc2626; }.legend .neighbor { background: #2563eb; }.legend .context { background: #94a3b8; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 600px) { .legend small { width: 100%; margin-left: 0; } }
</style>
