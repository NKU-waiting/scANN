<script setup>
import { onMounted, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  refreshKey: { type: Number, default: 0 },
  isAdmin: { type: Boolean, default: false },
})

const tab = ref('queries')
const queries = ref([])
const evaluations = ref([])
const loading = ref(false)
const error = ref('')

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const [queryData, evaluationData] = await Promise.all([
      apiRequest('/api/history/queries?limit=20'),
      apiRequest('/api/history/evaluations?limit=10'),
    ])
    queries.value = queryData.queries
    evaluations.value = evaluationData.evaluations
  } catch (reason) {
    error.value = reason.message
  } finally {
    loading.value = false
  }
}

function formatDate(value) {
  return new Date(value).toLocaleString('zh-CN')
}

function formatIndexes(record) {
  return record.index_types.join(' / ')
}

function effectiveTopK(record) {
  return record.results[0]?.effective_top_k ?? record.top_k
}

function topKLabel(record) {
  const effective = effectiveTopK(record)
  return effective === record.top_k ? `K=${effective}` : `K=${effective}（请求 ${record.top_k}）`
}

watch(() => props.refreshKey, reload)
onMounted(reload)
</script>

<template>
  <section class="history-card" aria-labelledby="history-title">
    <div class="history-heading">
      <div>
        <h2 id="history-title">运行历史</h2>
        <p>普通用户查看自己的记录，管理员可查看全局记录。</p>
      </div>
      <button :disabled="loading" @click="reload">{{ loading ? '刷新中…' : '刷新' }}</button>
    </div>
    <div class="tabs" role="tablist" aria-label="历史类型">
      <button :aria-selected="tab === 'queries'" :class="{ active: tab === 'queries' }" @click="tab = 'queries'">查询记录</button>
      <button :aria-selected="tab === 'evaluations'" :class="{ active: tab === 'evaluations' }" @click="tab = 'evaluations'">评测记录</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="table-scroll">
      <table v-if="tab === 'queries'">
        <caption class="sr-only">最近查询记录</caption>
        <thead><tr><th>时间</th><th v-if="isAdmin">用户 ID</th><th>数据集</th><th>查询</th><th>索引 / 度量</th><th>Top-K</th><th>耗时</th></tr></thead>
        <tbody>
          <tr v-for="record in queries" :key="record.id">
            <td>{{ formatDate(record.created_at) }}</td>
            <td v-if="isAdmin">#{{ record.user_id }}</td>
            <td>{{ record.dataset_name }}</td>
            <td>{{ record.query_mode === 'cell' ? `细胞 #${record.query_cell_id}` : '向量（未留存）' }}</td>
            <td>{{ record.index_type }} / {{ record.metric }}</td>
            <td>{{ record.returned }}/{{ record.top_k }}</td>
            <td>{{ record.query_ms }} ms</td>
          </tr>
          <tr v-if="!queries.length"><td :colspan="isAdmin ? 7 : 6" class="empty">暂无查询记录。</td></tr>
        </tbody>
      </table>
      <table v-else>
        <caption class="sr-only">最近评测记录</caption>
        <thead><tr><th>时间</th><th v-if="isAdmin">用户 ID</th><th>数据集</th><th>索引</th><th>参数</th><th>最佳召回率</th></tr></thead>
        <tbody>
          <tr v-for="record in evaluations" :key="record.id">
            <td>{{ formatDate(record.created_at) }}</td>
            <td v-if="isAdmin">#{{ record.user_id }}</td>
            <td>{{ record.dataset_name }}</td>
            <td>{{ formatIndexes(record) }}</td>
            <td>{{ topKLabel(record) }} · {{ record.n_queries }} 查询 · {{ record.metric }}</td>
            <td>{{ (Math.max(...record.results.map(row => row.recall_at_k)) * 100).toFixed(1) }}%</td>
          </tr>
          <tr v-if="!evaluations.length"><td :colspan="isAdmin ? 6 : 5" class="empty">暂无评测记录。</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.history-card { margin-top: 16px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px #00000012; }
.history-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; font-size: 17px; } p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
.history-heading button { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; }
.tabs { display: flex; margin: 16px 0 10px; border-bottom: 1px solid #e2e8f0; }
.tabs button { padding: 8px 14px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: #64748b; }
.tabs button.active { border-color: #2563eb; color: #1d4ed8; font-weight: 600; }
.error { color: #b91c1c; }.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; }
th { color: #64748b; font-size: 12px; }.empty { color: #94a3b8; text-align: center; padding: 18px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
</style>
