<script setup>
import { ref, onMounted } from 'vue'

const status = ref(null)
const form = ref({ cell_id: 0, top_k: 5, index_type: 'flat', metric: 'l2', cell_type: '' })
const result = ref(null)
const loading = ref(false)
const error = ref('')

async function fetchStatus() {
  const r = await fetch('/api/index/status')
  status.value = await r.json()
}

async function search() {
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const payload = {
      cell_id: Number(form.value.cell_id),
      top_k: Number(form.value.top_k),
      index_type: form.value.index_type,
      metric: form.value.metric,
    }
    if (form.value.cell_type) payload.cell_type = form.value.cell_type
    const r = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.error || '检索失败')
    result.value = data
    await fetchStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchStatus)
</script>

<template>
  <div class="page">
    <header>
      <h1>scANN · 单细胞近似最近邻检索</h1>
      <p class="sub">输入查询细胞编号，设置检索参数，获取 Top-K 相似细胞。</p>
    </header>

    <section class="status" v-if="status">
      <span>数据集：<b>{{ status.dataset }}</b></span>
      <span>细胞数：<b>{{ status.n_cells }}</b></span>
      <span>维度：<b>{{ status.dim }}</b></span>
      <span>当前索引：<b>{{ status.index || '未构建' }}</b></span>
    </section>

    <section class="panel">
      <div class="field">
        <label>查询细胞编号</label>
        <input type="number" v-model="form.cell_id" min="0" />
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
      <button :disabled="loading" @click="search">{{ loading ? '检索中…' : '检索' }}</button>
    </section>

    <p class="error" v-if="error">⚠ {{ error }}</p>

    <section v-if="result">
      <div class="meta">
        返回 <b>{{ result.returned }}</b> 条 · 索引 <b>{{ result.index }}</b> ·
        查询耗时 <b>{{ result.query_ms }} ms</b>
      </div>
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
.status { display: flex; gap: 18px; flex-wrap: wrap; background: #fff; padding: 12px 16px;
  border-radius: 10px; font-size: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.panel { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end;
  background: #fff; padding: 18px 16px; border-radius: 10px; margin-top: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: #6b7280; }
.field input, .field select { padding: 7px 9px; border: 1px solid #d1d5db; border-radius: 7px; }
button { padding: 9px 22px; border: none; border-radius: 8px; background: #2563eb; color: #fff;
  font-size: 14px; }
button:disabled { opacity: .6; }
.error { color: #dc2626; }
.meta { margin: 20px 0 8px; font-size: 14px; color: #374151; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px;
  overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
th, td { padding: 9px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #f0f1f3; }
th { background: #f9fafb; color: #6b7280; font-weight: 600; }
</style>
