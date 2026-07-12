<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiRequest } from '../api'

const props = defineProps({
  status: { type: Object, default: null },
  isAdmin: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['changed', 'busy'])

const artifacts = ref([])
const name = ref('')
const loading = ref(false)
const action = ref('')
const error = ref('')
const localBusy = computed(() => loading.value || Boolean(action.value))

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiRequest('/api/index/artifacts')
    artifacts.value = data.artifacts
  } catch (reason) {
    error.value = reason.message
  } finally {
    loading.value = false
  }
}

async function save() {
  action.value = 'save'
  error.value = ''
  try {
    const data = await apiRequest('/api/index/save', {
      method: 'POST',
      body: JSON.stringify({ name: name.value || undefined }),
    })
    name.value = ''
    await reload()
    emit('changed', data.status)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

async function load(artifact) {
  action.value = `load-${artifact.id}`
  error.value = ''
  try {
    const data = await apiRequest('/api/index/load', {
      method: 'POST',
      body: JSON.stringify({ index_id: artifact.id }),
    })
    await reload()
    emit('changed', data.status)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

async function remove(artifact) {
  if (!confirm(`确定删除持久化索引“${artifact.name}”？`)) return
  action.value = `delete-${artifact.id}`
  error.value = ''
  try {
    await apiRequest(`/api/index/artifacts/${artifact.id}`, { method: 'DELETE' })
    await reload()
    emit('changed', null)
  } catch (reason) {
    error.value = reason.message
  } finally {
    action.value = ''
  }
}

function formatDate(value) {
  return new Date(value).toLocaleString('zh-CN')
}

watch(
  () => [props.status?.dataset_fingerprint, props.status?.index_record_id],
  reload,
)
watch(localBusy, value => emit('busy', value), { immediate: true })
onMounted(reload)
</script>

<template>
  <section class="resource-card" aria-labelledby="index-manager-title">
    <div class="resource-heading">
      <div>
        <h2 id="index-manager-title">索引持久化</h2>
        <p>索引与数据集指纹绑定；只有兼容当前数据集的索引可以加载。</p>
      </div>
      <button class="secondary" :disabled="disabled || localBusy" @click="reload">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>
    <div class="save-row">
      <label>
        <span>索引名称（可选）</span>
        <input v-model.trim="name" maxlength="100" :disabled="disabled || localBusy" placeholder="自动生成名称" />
      </label>
      <button class="primary" :disabled="disabled || !status?.ready || localBusy" @click="save">
        {{ action === 'save' ? '保存中…' : '保存当前索引' }}
      </button>
      <span v-if="status?.persisted" class="persisted">当前已保存 · #{{ status.index_record_id }}</span>
    </div>

    <p v-if="error" class="resource-error" role="alert">{{ error }}</p>
    <div class="table-scroll">
      <table>
        <caption class="sr-only">持久化索引列表</caption>
        <thead><tr><th>名称</th><th>数据集</th><th>算法 / 度量</th><th>规模</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="artifact in artifacts" :key="artifact.id">
            <td><b>{{ artifact.name }}</b><small>{{ formatDate(artifact.created_at) }}</small></td>
            <td>{{ artifact.dataset_name }}</td>
            <td>{{ artifact.index_type }} / {{ artifact.metric }}</td>
            <td>{{ artifact.n_items.toLocaleString() }} × {{ artifact.dim }}</td>
            <td>
              <span class="badge" :class="{ active: artifact.active, incompatible: !artifact.compatible }">
                {{ artifact.active ? '当前' : artifact.compatible ? '兼容' : '其他数据集' }}
              </span>
            </td>
            <td class="actions">
              <button
                class="secondary"
                :disabled="disabled || artifact.active || !artifact.compatible || localBusy"
                @click="load(artifact)"
              >加载</button>
              <button
                v-if="isAdmin"
                class="danger"
                :disabled="disabled || !artifact.deletable || localBusy"
                @click="remove(artifact)"
              >删除</button>
            </td>
          </tr>
          <tr v-if="!artifacts.length && !loading"><td colspan="6" class="empty">尚无持久化索引。</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.resource-card { margin-top: 16px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px #00000012; }
.resource-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
h2 { margin: 0; font-size: 17px; } p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
.save-row { display: flex; align-items: end; gap: 10px; margin: 16px 0; }
label { display: flex; flex: 0 1 320px; flex-direction: column; gap: 5px; color: #64748b; font-size: 12px; }
input { padding: 8px 9px; border: 1px solid #cbd5e1; border-radius: 7px; }
button { padding: 8px 12px; border-radius: 7px; font-size: 13px; }
.primary { border: 0; background: #0f766e; color: #fff; }
.secondary { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.danger { border: 1px solid #fecaca; background: #fff7f7; color: #b91c1c; }
button:disabled { opacity: .55; cursor: not-allowed; }
.persisted { color: #166534; font-size: 12px; padding-bottom: 8px; }
.resource-error { color: #b91c1c; margin: 8px 0; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; white-space: nowrap; }
th { color: #64748b; font-size: 12px; } td small { display: block; color: #94a3b8; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #dcfce7; color: #166534; }
.badge.active { background: #dbeafe; color: #1d4ed8; } .badge.incompatible { background: #f1f5f9; color: #64748b; }
.actions { display: flex; gap: 6px; }.empty { color: #94a3b8; text-align: center; padding: 18px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 760px) { .save-row { align-items: stretch; flex-direction: column; } label { flex-basis: auto; width: 100%; } }
</style>
