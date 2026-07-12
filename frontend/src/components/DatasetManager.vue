<script setup>
import { onMounted, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  status: { type: Object, default: null },
  isAdmin: { type: Boolean, default: false },
})
const emit = defineEmits(['changed'])

const datasets = ref([])
const loading = ref(false)
const action = ref('')
const error = ref('')
const uploadName = ref('')
const useObsm = ref('X_pca')
const selectedFile = ref(null)
const fileInput = ref(null)

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiRequest('/api/datasets')
    datasets.value = data.datasets
  } catch (reason) {
    error.value = reason.message
  } finally {
    loading.value = false
  }
}

function pickFile(event) {
  selectedFile.value = event.target.files?.[0] || null
  if (selectedFile.value && !uploadName.value) {
    uploadName.value = selectedFile.value.name.replace(/\.(h5ad|npy|csv)$/i, '')
  }
}

async function upload() {
  if (!selectedFile.value) {
    error.value = '请选择 .h5ad、.npy 或 .csv 文件'
    return
  }
  action.value = 'upload'
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', selectedFile.value)
    body.append('name', uploadName.value)
    body.append('use_obsm', useObsm.value)
    body.append('activate', 'true')
    const data = await apiRequest('/api/datasets/upload', { method: 'POST', body })
    selectedFile.value = null
    uploadName.value = ''
    if (fileInput.value) fileInput.value.value = ''
    await reload()
    emit('changed', data.status)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

async function activate(dataset) {
  action.value = `activate-${dataset.id ?? 'demo'}`
  error.value = ''
  try {
    const path = dataset.id === null
      ? '/api/datasets/demo/activate'
      : `/api/datasets/${dataset.id}/activate`
    const data = await apiRequest(path, { method: 'POST' })
    await reload()
    emit('changed', data.status)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

async function remove(dataset) {
  if (!confirm(`确定删除数据集“${dataset.name}”及其关联索引？`)) return
  action.value = `delete-${dataset.id}`
  error.value = ''
  try {
    await apiRequest(`/api/datasets/${dataset.id}`, { method: 'DELETE' })
    await reload()
    emit('changed', null)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '系统生成'
}

watch(() => props.status?.dataset_fingerprint, reload)
onMounted(reload)
</script>

<template>
  <section class="resource-card" aria-labelledby="dataset-manager-title">
    <div class="resource-heading">
      <div>
        <h2 id="dataset-manager-title">数据集管理</h2>
        <p>上传、切换并管理经过校验的单细胞向量数据。</p>
      </div>
      <button class="secondary" :disabled="loading" @click="reload">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div class="upload-grid">
      <label>
        <span>数据文件</span>
        <input ref="fileInput" type="file" accept=".h5ad,.npy,.csv" @change="pickFile" />
      </label>
      <label>
        <span>数据集名称</span>
        <input v-model.trim="uploadName" maxlength="100" placeholder="默认使用文件名" />
      </label>
      <label>
        <span>AnnData 向量字段</span>
        <input v-model.trim="useObsm" maxlength="100" placeholder="X_pca；填 X 使用表达矩阵" />
      </label>
      <button class="primary" :disabled="Boolean(action)" @click="upload">
        {{ action === 'upload' ? '校验并上传中…' : '上传并激活' }}
      </button>
    </div>

    <p v-if="error" class="resource-error" role="alert">{{ error }}</p>
    <div class="table-scroll">
      <table>
        <caption class="sr-only">已管理的数据集</caption>
        <thead>
          <tr><th>名称</th><th>格式</th><th>规模</th><th>来源时间</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="dataset in datasets" :key="dataset.id ?? 'demo'">
            <td><b>{{ dataset.name }}</b><small>{{ dataset.original_filename || '可复现演示数据' }}</small></td>
            <td>{{ dataset.file_format.toUpperCase() }}</td>
            <td>{{ dataset.n_cells.toLocaleString() }} × {{ dataset.dim.toLocaleString() }}</td>
            <td>{{ formatDate(dataset.created_at) }}</td>
            <td><span class="badge" :class="{ active: dataset.active }">{{ dataset.active ? '当前' : '可用' }}</span></td>
            <td class="actions">
              <button
                class="secondary"
                :disabled="dataset.active || Boolean(action)"
                @click="activate(dataset)"
              >切换</button>
              <button
                v-if="isAdmin && dataset.id !== null"
                class="danger"
                :disabled="!dataset.deletable || Boolean(action)"
                @click="remove(dataset)"
              >删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.resource-card { margin-top: 16px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px #00000012; }
.resource-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
h2 { margin: 0; font-size: 17px; } p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
.upload-grid { display: grid; grid-template-columns: 1.2fr 1fr 1fr auto; gap: 10px; align-items: end; margin: 16px 0; }
label { display: flex; flex-direction: column; gap: 5px; color: #64748b; font-size: 12px; }
input { width: 100%; padding: 8px 9px; border: 1px solid #cbd5e1; border-radius: 7px; }
button { padding: 8px 12px; border-radius: 7px; font-size: 13px; }
.primary { border: 0; background: #2563eb; color: #fff; }
.secondary { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.danger { border: 1px solid #fecaca; background: #fff7f7; color: #b91c1c; }
button:disabled { opacity: .55; cursor: not-allowed; }
.resource-error { color: #b91c1c; margin: 8px 0; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; }
th { color: #64748b; font-size: 12px; } td small { display: block; max-width: 180px; overflow: hidden; text-overflow: ellipsis; color: #94a3b8; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #f1f5f9; color: #475569; }
.badge.active { background: #dcfce7; color: #166534; }
.actions { display: flex; gap: 6px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 760px) { .upload-grid { grid-template-columns: 1fr; } .resource-heading { align-items: center; } }
</style>
