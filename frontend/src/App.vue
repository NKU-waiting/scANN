<script setup>
import { computed, ref, onMounted } from 'vue'
import DatasetManager from './components/DatasetManager.vue'
import EmbeddingPlot from './components/EmbeddingPlot.vue'
import FederatedSearch from './components/FederatedSearch.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import IndexManager from './components/IndexManager.vue'
import { apiRequest, configureApi } from './api'

// ── 认证状态 ──────────────────────────────────────────────
function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('scann_user') || 'null')
  } catch {
    localStorage.removeItem('scann_user')
    localStorage.removeItem('scann_token')
    return null
  }
}

const token = ref(localStorage.getItem('scann_token') || '')
const currentUser = ref(readStoredUser())
const authReady = ref(false)
const authMode = ref('login')
const authForm = ref({ username: '', password: '' })
const authLoading = ref(false)
const authError = ref('')
const sessionGeneration = ref(0)
const workspaceGeneration = ref(0)

configureApi({
  getToken: () => token.value,
  onUnauthorized: failedToken => {
    if (failedToken === token.value) doLogout()
  },
})

// ── 管理员用户管理 ────────────────────────────────────────
const userList = ref([])
const userListLoading = ref(false)
const userListError = ref('')

async function doLogin() {
  const attemptGeneration = sessionGeneration.value
  let authenticatedGeneration = null
  authLoading.value = true
  authError.value = ''
  try {
    const data = await apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: authForm.value.username, password: authForm.value.password }),
    }, false)
    if (attemptGeneration !== sessionGeneration.value) return
    sessionGeneration.value += 1
    authenticatedGeneration = sessionGeneration.value
    workspaceGeneration.value += 1
    resetWorkspaceState()
    token.value = data.token
    currentUser.value = data.user
    localStorage.setItem('scann_token', data.token)
    localStorage.setItem('scann_user', JSON.stringify(data.user))
    authForm.value = { username: '', password: '' }
    const snapshot = captureWorkspace()
    await fetchStatus(snapshot)
    if (data.user.role === 'admin' && isWorkspaceCurrent(snapshot)) await loadUsers()
  } catch (e) {
    const ownsSession = authenticatedGeneration === null
      ? attemptGeneration === sessionGeneration.value
      : authenticatedGeneration === sessionGeneration.value
    if (ownsSession) {
      if (authenticatedGeneration === null) authError.value = e.message
      else error.value = e.message
    }
  } finally {
    const ownsSession = authenticatedGeneration === null
      ? attemptGeneration === sessionGeneration.value
      : authenticatedGeneration === sessionGeneration.value
    if (ownsSession) authLoading.value = false
  }
}

async function doRegister() {
  authLoading.value = true
  authError.value = ''
  try {
    await apiRequest('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username: authForm.value.username, password: authForm.value.password }),
    }, false)
    authMode.value = 'login'
    authError.value = '注册成功，请登录'
    authForm.value.password = ''
  } catch (e) {
    authError.value = e.message
  } finally {
    authLoading.value = false
  }
}

function doLogout() {
  sessionGeneration.value += 1
  workspaceGeneration.value += 1
  token.value = ''
  currentUser.value = null
  resetWorkspaceState()
  authLoading.value = false
  authError.value = ''
  authForm.value = { username: '', password: '' }
  localStorage.removeItem('scann_token')
  localStorage.removeItem('scann_user')
}

async function loadUsers() {
  const generation = sessionGeneration.value
  userListLoading.value = true
  userListError.value = ''
  try {
    const data = await apiRequest('/api/auth/users')
    if (generation === sessionGeneration.value) userList.value = data.users
  } catch (e) {
    if (generation === sessionGeneration.value) userListError.value = e.message
  } finally {
    if (generation === sessionGeneration.value) userListLoading.value = false
  }
}

async function removeUser(userId) {
  if (!confirm('确定删除该用户？')) return
  const generation = sessionGeneration.value
  try {
    await apiRequest(`/api/auth/users/${userId}`, {
      method: 'DELETE',
    })
    if (generation === sessionGeneration.value) await loadUsers()
  } catch (e) {
    if (generation === sessionGeneration.value) userListError.value = e.message
  }
}

function defaultSearchForm() {
  return {
    cell_id: 0,
    top_k: 5,
    index_type: 'flat',
    compare_index_type: 'hnsw',
    metric: 'l2',
    cell_type: '',
    vector: '',
  }
}

function defaultEvalForm() {
  return {
    index_types: ['flat', 'hnsw'],
    top_k: 10,
    n_queries: 100,
    metric: 'l2',
  }
}

const status = ref(null)
const form = ref(defaultSearchForm())
const queryMode = ref('cell') // 'cell' | 'vector'
const result = ref(null)
const buildInfo = ref(null)
const comparisonResults = ref([])
const comparisonMeta = ref(null)
const loading = ref(false)
const building = ref(false)
const comparing = ref(false)
const error = ref('')

const evalForm = ref(defaultEvalForm())
const evalResults = ref([])
const annImprovement = ref(null)
const evalLoading = ref(false)
const evalError = ref('')
const historyRefreshKey = ref(0)
const datasetManagerBusy = ref(false)
const indexManagerBusy = ref(false)
const federatedBusy = ref(false)
const resourceSyncing = ref(false)
const datasetResources = ref([])

function resetWorkspaceState() {
  userList.value = []
  userListLoading.value = false
  userListError.value = ''
  status.value = null
  form.value = defaultSearchForm()
  queryMode.value = 'cell'
  result.value = null
  buildInfo.value = null
  comparisonResults.value = []
  comparisonMeta.value = null
  loading.value = false
  building.value = false
  comparing.value = false
  error.value = ''
  evalForm.value = defaultEvalForm()
  evalResults.value = []
  annImprovement.value = null
  evalLoading.value = false
  evalError.value = ''
  historyRefreshKey.value = 0
  datasetManagerBusy.value = false
  indexManagerBusy.value = false
  federatedBusy.value = false
  resourceSyncing.value = false
  datasetResources.value = []
}

function captureWorkspace() {
  return {
    session: sessionGeneration.value,
    workspace: workspaceGeneration.value,
    token: token.value,
  }
}

function isWorkspaceCurrent(snapshot) {
  return snapshot.session === sessionGeneration.value
    && snapshot.workspace === workspaceGeneration.value
    && snapshot.token === token.value
    && Boolean(currentUser.value)
}

function applyStatus(nextStatus) {
  status.value = nextStatus
  if (nextStatus?.index_type) form.value.index_type = nextStatus.index_type
  if (nextStatus?.metric) form.value.metric = nextStatus.metric
}

const indexLabels = {
  flat: 'Flat',
  faiss: 'FAISS-Flat',
  ivf: 'FAISS-IVF',
  hnsw: 'FAISS-HNSW',
  pq: 'FAISS-PQ',
  pq_rerank: 'PQ + 精确重排',
}

const metadataFields = computed(() => status.value?.metadata_fields || [])
const maxTopK = computed(() => status.value?.limits?.max_top_k || 50)
const maxEvalQueries = computed(() => status.value?.limits?.max_eval_queries || 500)
const maxVisualizationPoints = computed(
  () => status.value?.limits?.max_visualization_points || 1200,
)
const busy = computed(() => (
  loading.value
  || building.value
  || comparing.value
  || evalLoading.value
  || datasetManagerBusy.value
  || indexManagerBusy.value
  || federatedBusy.value
  || resourceSyncing.value
))

const datasetSummary = computed(() => [
  { label: '数据集', value: status.value?.dataset || '未加载' },
  { label: '细胞数', value: formatNumber(status.value?.n_cells || 0) },
  { label: '向量维度', value: formatNumber(status.value?.dim || 0) },
  { label: '当前索引', value: status.value?.index || '未构建' },
  {
    label: '距离度量',
    value: status.value?.metric === 'cosine'
      ? 'Cosine（余弦）'
      : status.value?.metric === 'ip' ? 'IP（内积）' : 'L2（平方欧氏）',
  },
  { label: '元信息字段', value: metadataFields.value.length ? metadataFields.value.join('、') : '无' },
])

const resultRows = computed(() => result.value?.results || [])

const resultMetric = computed(() => {
  return result.value?.metric || form.value.metric
})

const valueLabel = computed(() => {
  return metricValueLabel(resultMetric.value)
})

const comparisonValueLabel = computed(() => (
  metricValueLabel(comparisonMeta.value?.metric || resultMetric.value)
))

const evalEffectiveTopK = computed(() => (
  evalResults.value[0]?.effective_top_k ?? evalResults.value[0]?.top_k ?? null
))

const evalRequestedTopK = computed(() => evalResults.value[0]?.top_k ?? null)

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

function formatBytes(value) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes)) return '-'
  const absolute = Math.abs(bytes)
  if (absolute < 1024) return `${bytes} B`
  if (absolute < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

function indexLabel(indexType) {
  return indexLabels[indexType] || indexType
}

function metricValueLabel(metric) {
  if (metric === 'ip') return '内积得分'
  if (metric === 'cosine') return '余弦距离'
  return '平方 L2 距离'
}

function parseVectorInput() {
  const parts = form.value.vector.split(',').map(value => value.trim())
  if (!parts.length || parts.some(value => value === '')) {
    throw new Error('查询向量必须是完整的逗号分隔数值')
  }
  const vec = parts.map(Number)
  if (vec.some(value => !Number.isFinite(value))) {
    throw new Error('查询向量只能包含有限数值')
  }
  if (status.value?.dim && vec.length !== status.value.dim) {
    throw new Error(`查询向量维度应为 ${status.value.dim}，当前为 ${vec.length}`)
  }
  return vec
}

function buildSearchPayload(indexType = form.value.index_type) {
  const topK = Number(form.value.top_k)
  if (!Number.isInteger(topK) || topK < 1 || topK > maxTopK.value) {
    throw new Error(`Top-K 必须是 1 到 ${maxTopK.value} 的整数`)
  }
  const payload = {
    top_k: topK,
    index_type: indexType,
    metric: form.value.metric,
  }
  if (queryMode.value === 'vector') {
    payload.vector = parseVectorInput()
  } else {
    const cellId = Number(form.value.cell_id)
    if (!Number.isInteger(cellId) || cellId < 0 || cellId >= (status.value?.n_cells || 0)) {
      throw new Error(`细胞编号必须是 0 到 ${(status.value?.n_cells || 1) - 1} 的整数`)
    }
    payload.cell_id = cellId
  }
  if (form.value.cell_type.trim()) payload.cell_type = form.value.cell_type.trim()
  return payload
}

async function requestSearch(indexType, basePayload = null) {
  const payload = basePayload
    ? { ...basePayload, index_type: indexType }
    : buildSearchPayload(indexType)
  return apiRequest('/api/search', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

async function fetchStatus(snapshot = captureWorkspace()) {
  const nextStatus = await apiRequest('/api/index/status')
  if (isWorkspaceCurrent(snapshot)) applyStatus(nextStatus)
  return nextStatus
}

async function search() {
  const snapshot = captureWorkspace()
  loading.value = true
  error.value = ''
  result.value = null
  comparisonResults.value = []
  comparisonMeta.value = null
  try {
    const data = await requestSearch(form.value.index_type)
    if (!isWorkspaceCurrent(snapshot)) return
    result.value = data
    historyRefreshKey.value += 1
    await fetchStatus(snapshot)
  } catch (e) {
    if (isWorkspaceCurrent(snapshot)) error.value = e.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) loading.value = false
  }
}

async function searchFromPlot(cellId) {
  if (busy.value || !Number.isInteger(cellId)) return
  queryMode.value = 'cell'
  form.value.cell_id = cellId
  await search()
}

async function buildIndex() {
  const snapshot = captureWorkspace()
  building.value = true
  error.value = ''
  comparisonResults.value = []
  comparisonMeta.value = null
  try {
    const data = await apiRequest('/api/index/build', {
      method: 'POST',
      body: JSON.stringify({ index_type: form.value.index_type, metric: form.value.metric }),
    })
    if (!isWorkspaceCurrent(snapshot)) return
    buildInfo.value = data
    await fetchStatus(snapshot)
  } catch (e) {
    if (isWorkspaceCurrent(snapshot)) error.value = e.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) building.value = false
  }
}

async function compareIndexes() {
  const snapshot = captureWorkspace()
  comparing.value = true
  error.value = ''
  comparisonResults.value = []
  comparisonMeta.value = null
  const indexTypes = ['flat']
  if (form.value.compare_index_type !== 'flat') indexTypes.push(form.value.compare_index_type)

  try {
    const payloadSnapshot = buildSearchPayload()
    comparisonMeta.value = {
      target: form.value.compare_index_type,
      metric: payloadSnapshot.metric,
      topK: payloadSnapshot.top_k,
    }
    for (const indexType of indexTypes) {
      try {
        const data = await requestSearch(indexType, payloadSnapshot)
        if (!isWorkspaceCurrent(snapshot)) return
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
        if (!isWorkspaceCurrent(snapshot)) return
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
    historyRefreshKey.value += 1
    await fetchStatus(snapshot)
  } catch (e) {
    if (isWorkspaceCurrent(snapshot)) error.value = e.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) comparing.value = false
  }
}

async function runEval() {
  const snapshot = captureWorkspace()
  evalLoading.value = true
  evalError.value = ''
  evalResults.value = []
  annImprovement.value = null
  try {
    const topK = Number(evalForm.value.top_k)
    const nQueries = Number(evalForm.value.n_queries)
    if (!Number.isInteger(topK) || topK < 1 || topK > maxTopK.value) {
      throw new Error(`评测 Top-K 必须是 1 到 ${maxTopK.value} 的整数`)
    }
    if (!Number.isInteger(nQueries) || nQueries < 1 || nQueries > maxEvalQueries.value) {
      throw new Error(`查询样本数必须是 1 到 ${maxEvalQueries.value} 的整数`)
    }
    const data = await apiRequest('/api/eval', {
      method: 'POST',
      body: JSON.stringify({
        index_types: evalForm.value.index_types,
        top_k: topK,
        n_queries: nQueries,
        metric: evalForm.value.metric,
      }),
    })
    if (!isWorkspaceCurrent(snapshot)) return
    evalResults.value = data.results
    annImprovement.value = data.ann_improvement || null
    historyRefreshKey.value += 1
  } catch (e) {
    if (isWorkspaceCurrent(snapshot)) evalError.value = e.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) evalLoading.value = false
  }
}

async function handleDatasetChanged(nextStatus) {
  workspaceGeneration.value += 1
  const snapshot = captureWorkspace()
  resourceSyncing.value = true
  try {
    const resolvedStatus = nextStatus || await apiRequest('/api/index/status')
    if (!isWorkspaceCurrent(snapshot)) return
    applyStatus(resolvedStatus)
    result.value = null
    buildInfo.value = null
    comparisonResults.value = []
    comparisonMeta.value = null
    evalResults.value = []
    annImprovement.value = null
    evalError.value = ''
    error.value = ''
    historyRefreshKey.value += 1
  } catch (reason) {
    if (isWorkspaceCurrent(snapshot)) error.value = reason.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) resourceSyncing.value = false
  }
}

async function handleIndexChanged(nextStatus) {
  workspaceGeneration.value += 1
  const snapshot = captureWorkspace()
  resourceSyncing.value = true
  try {
    const resolvedStatus = nextStatus || await apiRequest('/api/index/status')
    if (!isWorkspaceCurrent(snapshot)) return
    applyStatus(resolvedStatus)
    result.value = null
    buildInfo.value = null
    comparisonResults.value = []
    comparisonMeta.value = null
    error.value = ''
  } catch (reason) {
    if (isWorkspaceCurrent(snapshot)) error.value = reason.message
  } finally {
    if (isWorkspaceCurrent(snapshot)) resourceSyncing.value = false
  }
}

const queryCellForPlot = computed(() => (
  Number.isInteger(result.value?.query_cell_id) ? result.value.query_cell_id : null
))

onMounted(async () => {
  const initialGeneration = sessionGeneration.value
  const initialToken = token.value
  if (initialToken) {
    try {
      const data = await apiRequest('/api/auth/me')
      if (initialGeneration === sessionGeneration.value && initialToken === token.value) {
        currentUser.value = data.user
        localStorage.setItem('scann_user', JSON.stringify(data.user))
      }
    } catch {
      if (initialGeneration === sessionGeneration.value && initialToken === token.value) {
        doLogout()
      }
    }
  } else {
    currentUser.value = null
  }
  authReady.value = true
  if (currentUser.value) {
    const snapshot = captureWorkspace()
    try {
      await fetchStatus(snapshot)
      if (isWorkspaceCurrent(snapshot) && currentUser.value.role === 'admin') {
        await loadUsers()
      }
    } catch (e) {
      if (isWorkspaceCurrent(snapshot)) error.value = e.message
    }
  }
})
</script>

<template>
  <div class="page">
    <header>
      <div class="header-row">
        <div>
          <h1>scANN · 单细胞近似最近邻检索</h1>
          <p class="sub">输入查询细胞编号或向量，设置检索参数，获取 Top-K 相似细胞。</p>
        </div>
        <div v-if="authReady && currentUser" class="user-badge">
          <span class="user-name">{{ currentUser.username }}</span>
          <span class="user-role" :class="currentUser.role">{{ currentUser.role }}</span>
          <button class="btn-logout" @click="doLogout">退出</button>
        </div>
      </div>
    </header>

    <!-- 登录 / 注册面板 -->
    <section v-if="!authReady" class="auth-panel" aria-live="polite">
      正在验证登录状态…
    </section>

    <section v-else-if="!currentUser" class="auth-panel">
      <div class="auth-tabs">
        <button :class="{ active: authMode === 'login' }" @click="authMode = 'login'; authError = ''">登录</button>
        <button :class="{ active: authMode === 'register' }" @click="authMode = 'register'; authError = ''">注册</button>
      </div>
      <div class="auth-form">
        <div class="field">
          <label>用户名</label>
          <input v-model="authForm.username" placeholder="请输入用户名" @keyup.enter="authMode === 'login' ? doLogin() : doRegister()" />
        </div>
        <div class="field">
          <label>密码</label>
          <input type="password" v-model="authForm.password" placeholder="请输入密码" @keyup.enter="authMode === 'login' ? doLogin() : doRegister()" />
        </div>
        <button class="btn-auth" :disabled="authLoading" @click="authMode === 'login' ? doLogin() : doRegister()">
          {{ authLoading ? '处理中…' : (authMode === 'login' ? '登录' : '注册') }}
        </button>
      </div>
      <p class="auth-msg" :class="{ 'auth-ok': authError.startsWith('注册成功') }">{{ authError }}</p>
    </section>

    <template v-if="authReady && currentUser">
    <!-- 管理员用户管理 -->
    <section v-if="currentUser?.role === 'admin'" class="user-mgmt">
      <div class="section-heading">
        <h2>用户管理</h2>
        <button class="btn-refresh" @click="loadUsers" :disabled="userListLoading">{{ userListLoading ? '加载中…' : '刷新' }}</button>
      </div>
      <p class="error" v-if="userListError">⚠ {{ userListError }}</p>
      <table v-if="userList.length" class="user-table">
        <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="u in userList" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td><span class="user-role" :class="u.role">{{ u.role }}</span></td>
            <td>{{ u.created_at.replace('T', ' ').slice(0, 19) }}</td>
            <td>
              <button class="btn-del" :disabled="u.username === currentUser.username" @click="removeUser(u.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!userListLoading" class="empty-state">暂无用户数据。</p>
    </section>

    <DatasetManager
      :status="status"
      :is-admin="currentUser.role === 'admin'"
      :disabled="busy"
      @changed="handleDatasetChanged"
      @busy="datasetManagerBusy = $event"
      @resources="datasetResources = $event"
    />

    <IndexManager
      :status="status"
      :is-admin="currentUser.role === 'admin'"
      :disabled="busy"
      @changed="handleIndexChanged"
      @busy="indexManagerBusy = $event"
    />

    <FederatedSearch
      :datasets="datasetResources"
      :disabled="busy"
      @busy="federatedBusy = $event"
    />

    <section class="dataset-card" v-if="status">
      <div class="section-heading">
        <h2>当前数据与索引</h2>
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
    <section class="mode-switch" role="tablist" aria-label="查询模式">
      <button :aria-pressed="queryMode === 'cell'" :disabled="busy" :class="{ active: queryMode === 'cell' }" @click="queryMode = 'cell'">按细胞编号查询</button>
      <button :aria-pressed="queryMode === 'vector'" :disabled="busy" :class="{ active: queryMode === 'vector' }" @click="queryMode = 'vector'">按向量查询</button>
    </section>

    <section class="panel">
      <div class="field" v-if="queryMode === 'cell'">
        <label>查询细胞编号</label>
        <input type="number" v-model="form.cell_id" min="0" :disabled="busy" />
      </div>
      <div class="field wide" v-if="queryMode === 'vector'">
        <label>查询向量（逗号分隔）</label>
        <input v-model="form.vector" :disabled="busy" placeholder="如 0.1, 0.5, -0.3, ..." />
      </div>
      <div class="field">
        <label>Top-K</label>
        <input type="number" v-model="form.top_k" min="1" :max="maxTopK" :disabled="busy" />
      </div>
      <div class="field">
        <label>索引类型</label>
        <select v-model="form.index_type" :disabled="busy">
          <option value="flat">Flat（精确）</option>
          <option value="faiss">FAISS-Flat</option>
          <option value="ivf">FAISS-IVF</option>
          <option value="hnsw">FAISS-HNSW</option>
          <option value="pq">FAISS-PQ</option>
          <option value="pq_rerank">PQ + 精确候选重排</option>
        </select>
      </div>
      <div class="field">
        <label>距离度量</label>
        <select v-model="form.metric" :disabled="busy">
          <option value="l2">L2（平方欧氏）</option>
          <option value="cosine">Cosine（余弦距离）</option>
          <option value="ip">IP（内积）</option>
        </select>
      </div>
      <div class="field">
        <label>限定细胞类型（可选）</label>
        <input v-model="form.cell_type" :disabled="busy" placeholder="如 type_1" />
      </div>
      <div class="field">
        <label>对比索引</label>
        <select v-model="form.compare_index_type" :disabled="busy">
          <option value="hnsw">FAISS-HNSW</option>
          <option value="ivf">FAISS-IVF</option>
          <option value="faiss">FAISS-Flat</option>
          <option value="pq">FAISS-PQ</option>
          <option value="pq_rerank">PQ + 精确候选重排</option>
        </select>
      </div>
      <div class="btn-group">
        <button class="btn-primary" :disabled="busy" @click="search">{{ loading ? '检索中…' : '检索' }}</button>
        <button class="btn-build" :disabled="busy" @click="buildIndex">{{ building ? '构建中…' : '构建索引' }}</button>
        <button class="btn-compare" :disabled="busy" @click="compareIndexes">
          {{ comparing ? '对比中…' : '对比索引' }}
        </button>
      </div>
    </section>

    <section class="build-info" v-if="buildInfo">
      索引 <b>{{ buildInfo.index }}</b> 构建完成 · 耗时 <b class="highlight">{{ buildInfo.build_ms }} ms</b>
    </section>

    <p class="error" v-if="error" role="alert">⚠ {{ error }}</p>

    <section class="comparison" v-if="comparisonResults.length">
      <div class="section-heading">
        <h2>索引对比</h2>
        <span>Flat vs {{ indexLabel(comparisonMeta?.target) }} · {{ comparisonMeta?.metric }}</span>
      </div>
      <div class="comparison-table">
        <div class="comparison-row comparison-head">
          <span>索引</span>
          <span>查询耗时</span>
          <span>返回数</span>
          <span>首位结果</span>
          <span>{{ comparisonValueLabel }}</span>
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

    <section class="eval-panel">
      <div class="section-heading">
        <h2>性能评测</h2>
        <span>Recall@K · 查询耗时 · 构建耗时 · 索引字节</span>
      </div>
      <div class="eval-form">
        <div class="eval-checkboxes">
          <label v-for="type in ['flat','faiss','ivf','hnsw','pq','pq_rerank']" :key="type">
            <input type="checkbox" :value="type" v-model="evalForm.index_types" :disabled="busy" />
            {{ indexLabel(type) }}
          </label>
        </div>
        <div class="eval-fields">
          <div class="field">
            <label>Top-K</label>
            <input type="number" v-model="evalForm.top_k" min="1" :max="maxTopK" :disabled="busy" />
          </div>
          <div class="field">
            <label>查询样本数</label>
            <input type="number" v-model="evalForm.n_queries" min="1" :max="maxEvalQueries" :disabled="busy" />
          </div>
          <div class="field">
            <label>距离度量</label>
            <select v-model="evalForm.metric" :disabled="busy">
              <option value="l2">L2（平方欧氏）</option>
              <option value="cosine">Cosine（余弦距离）</option>
              <option value="ip">IP（内积）</option>
            </select>
          </div>
          <button class="btn-eval" :disabled="busy || evalForm.index_types.length === 0" @click="runEval">
            {{ evalLoading ? '评测中…' : '性能评测' }}
          </button>
        </div>
      </div>
      <p class="error" v-if="evalError">⚠ {{ evalError }}</p>
      <div class="eval-results" v-if="evalResults.length">
        <table class="eval-table">
          <thead>
            <tr>
              <th>索引</th>
              <th>
                Recall@{{ evalEffectiveTopK }}
                <small v-if="evalEffectiveTopK !== evalRequestedTopK">请求 K={{ evalRequestedTopK }}</small>
              </th>
              <th>平均查询耗时</th>
              <th>构建耗时</th>
              <th>序列化索引</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in evalResults" :key="row.index_type">
              <td><b>{{ indexLabel(row.index_type) }}</b></td>
              <td class="recall-cell">{{ (row.recall_at_k * 100).toFixed(1) }}%</td>
              <td>{{ row.avg_query_ms }} ms</td>
              <td>{{ row.build_ms }} ms</td>
              <td>{{ formatBytes(row.index_bytes) }}<small v-if="row.bytes_per_vector != null">{{ row.bytes_per_vector }} B/细胞</small></td>
            </tr>
          </tbody>
        </table>
        <article v-if="annImprovement" class="improvement-summary">
          <div>
            <b>PQ 候选精确重排</b>
            <span>同一查询集 · 候选扩大 {{ evalResults.find(row => row.index_type === 'pq_rerank')?.parameters?.rerank_factor || '-' }}×</span>
          </div>
          <dl>
            <div><dt>Recall 变化</dt><dd>{{ annImprovement.recall_delta >= 0 ? '+' : '' }}{{ (annImprovement.recall_delta * 100).toFixed(1) }} 个百分点</dd></div>
            <div><dt>查询耗时变化</dt><dd>{{ annImprovement.avg_query_ms_delta >= 0 ? '+' : '' }}{{ annImprovement.avg_query_ms_delta }} ms</dd></div>
            <div><dt>索引字节变化</dt><dd>{{ annImprovement.index_bytes_delta >= 0 ? '+' : '' }}{{ formatBytes(annImprovement.index_bytes_delta) }}</dd></div>
          </dl>
          <p>重排复用已加载的原始数据向量；索引字节不含数据集本体。耗时是精度提升的显式权衡。</p>
        </article>
        <div class="eval-chart">
          <div class="eval-chart-heading">
            Recall@{{ evalEffectiveTopK }} 对比
            <small v-if="evalEffectiveTopK !== evalRequestedTopK">（请求 K={{ evalRequestedTopK }}）</small>
          </div>
          <div class="eval-bar-list">
            <div class="eval-bar-item" v-for="row in evalResults" :key="`bar-${row.index_type}`">
              <span class="eval-bar-label">{{ indexLabel(row.index_type) }}</span>
              <div class="eval-bar-track">
                <span :style="{ width: `${row.recall_at_k * 100}%` }"></span>
              </div>
              <span class="eval-bar-value">{{ (row.recall_at_k * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="result" class="results">
      <div class="meta">
        返回 <b>{{ result.returned }}</b> 条 · 索引 <b>{{ result.index }}</b> ·
        查询耗时 <b>{{ result.query_ms }} ms</b>
      </div>
      <EmbeddingPlot
        v-if="resultRows.length"
        :result="result"
        :query-cell-id="queryCellForPlot"
        :max-points="maxVisualizationPoints"
        @select-cell="searchFromPlot"
      />
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
      <div v-if="resultRows.length" class="table-scroll">
      <table>
        <caption class="sr-only">Top-K 相似细胞结果</caption>
        <thead>
          <tr><th>#</th><th>细胞编号</th><th>名称</th><th>细胞类型</th><th>{{ valueLabel }}</th></tr>
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
      </div>
    </section>

    <HistoryPanel :refresh-key="historyRefreshKey" :is-admin="currentUser.role === 'admin'" />
    </template>
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
.table-scroll { overflow-x: auto; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
th, td { padding: 9px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #f0f1f3; }
th { background: #f9fafb; color: #6b7280; font-weight: 600; }
.eval-panel { background: #fff; padding: 16px; border-radius: 8px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.eval-form { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.eval-checkboxes { display: flex; gap: 16px; flex-wrap: wrap; }
.eval-checkboxes label { display: flex; align-items: center; gap: 6px; font-size: 14px;
  color: #374151; cursor: pointer; user-select: none; }
.eval-fields { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.btn-eval { padding: 9px 22px; border: none; border-radius: 8px; background: #7c3aed; color: #fff;
  font-size: 14px; cursor: pointer; }
.eval-results { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 12px; }
.eval-table { width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb; border-radius: 8px;
  overflow: hidden; }
.eval-table th, .eval-table td { padding: 9px 12px; text-align: left; font-size: 14px;
  border-bottom: 1px solid #f0f1f3; }
.eval-table th { background: #f9fafb; color: #6b7280; font-weight: 600; }
.recall-cell { color: #0f766e; font-weight: 700; }
.eval-table td small { display: block; color: #94a3b8; font-size: 11px; margin-top: 2px; }
.improvement-summary { grid-column: 1 / -1; grid-row: 1; margin: 0; padding: 14px; border: 1px solid #a7f3d0; border-radius: 9px; background: #f0fdfa; }
.improvement-summary > div { display: flex; justify-content: space-between; gap: 12px; color: #115e59; }
.improvement-summary > div span { font-size: 12px; }.improvement-summary dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
.improvement-summary dl div { padding: 8px; border-radius: 7px; background: #fff; }.improvement-summary dt { color: #64748b; font-size: 11px; }
.improvement-summary dd { margin: 3px 0 0; color: #0f766e; font-weight: 700; }.improvement-summary p { color: #475569; }
.eval-chart { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }
.eval-chart-heading { font-size: 14px; font-weight: 600; color: #374151; margin-bottom: 14px; }
.eval-bar-list { display: flex; flex-direction: column; gap: 12px; }
.eval-bar-item { display: grid; grid-template-columns: 90px 1fr 46px; align-items: center; gap: 10px; }
.eval-bar-label { font-size: 13px; color: #374151; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.eval-bar-track { height: 10px; overflow: hidden; border-radius: 999px; background: #e5e7eb; }
.eval-bar-track span { display: block; height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, #a78bfa, #7c3aed); transition: width .4s ease; }
.eval-bar-value { font-size: 13px; color: #4b5563; text-align: right;
  font-variant-numeric: tabular-nums; }
/* auth */
.header-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.user-badge { display: flex; align-items: center; gap: 8px; flex-shrink: 0; padding-top: 4px; }
.user-name { font-size: 14px; color: #111827; font-weight: 600; }
.user-role { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 99px; }
.user-role.admin { background: #fef3c7; color: #b45309; }
.user-role.user { background: #dbeafe; color: #1d4ed8; }
.btn-logout { padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff;
  font-size: 13px; color: #6b7280; cursor: pointer; }
.btn-logout:hover { background: #f9fafb; }
.auth-panel { background: #fff; padding: 20px; border-radius: 10px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); max-width: 400px; }
.auth-tabs { display: flex; gap: 0; margin-bottom: 16px; }
.auth-tabs button { flex: 1; padding: 8px 0; border: 1px solid #d1d5db; background: #fff;
  font-size: 14px; color: #6b7280; cursor: pointer; }
.auth-tabs button:first-child { border-radius: 7px 0 0 7px; }
.auth-tabs button:last-child { border-radius: 0 7px 7px 0; border-left: none; }
.auth-tabs button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.auth-form { display: flex; flex-direction: column; gap: 12px; }
.btn-auth { padding: 9px; border: none; border-radius: 8px; background: #2563eb; color: #fff;
  font-size: 14px; cursor: pointer; margin-top: 4px; }
.btn-auth:disabled { opacity: .6; cursor: not-allowed; }
.auth-msg { margin: 10px 0 0; font-size: 13px; color: #dc2626; min-height: 18px; }
.auth-msg.auth-ok { color: #0f766e; }
.user-mgmt { background: #fff; padding: 16px; border-radius: 8px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow-x: auto; }
.btn-refresh { padding: 5px 14px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb;
  font-size: 13px; color: #374151; cursor: pointer; }
.user-table { width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb; border-radius: 8px;
  overflow: hidden; margin-top: 12px; }
.user-table th, .user-table td { padding: 9px 12px; text-align: left; font-size: 14px;
  border-bottom: 1px solid #f0f1f3; }
.user-table th { background: #f9fafb; color: #6b7280; font-weight: 600; }
.btn-del { padding: 4px 10px; border: 1px solid #fca5a5; border-radius: 5px; background: #fff5f5;
  color: #dc2626; font-size: 12px; cursor: pointer; }
.btn-del:disabled { opacity: .4; cursor: not-allowed; }
@media (max-width: 760px) {
  .dataset-grid { grid-template-columns: 1fr; }
  .comparison-row { grid-template-columns: 1fr 1fr; }
  .comparison-head { display: none; }
  .visual-grid { grid-template-columns: 1fr; }
  .distance-card { grid-row: auto; }
  .summary-stats { grid-template-columns: 1fr; }
  .eval-results { grid-template-columns: 1fr; }
  .header-row { flex-direction: column; gap: 8px; }
}
</style>
