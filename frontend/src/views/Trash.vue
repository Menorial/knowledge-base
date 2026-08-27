<template>
  <div class="page-container">
    <div class="page-header">
      <h1>🗑️ 回收站</h1>
      <div class="subtitle">误删的文档可以在这里恢复，或彻底删除释放空间</div>
    </div>

    <div class="card">
      <div v-if="selectedIds.length" class="batch-bar">
        <el-checkbox :model-value="allSelected" @change="toggleSelectAll">全选</el-checkbox>
        <span class="batch-count">已选 {{ selectedIds.length }} 篇</span>
        <div style="flex: 1;"></div>
        <el-button size="small" @click="selectedIds = []">取消选择</el-button>
        <el-button size="small" type="primary" plain @click="batchRestore" :loading="restoring">批量恢复</el-button>
        <el-button size="small" type="danger" @click="openBatchPurge">批量彻底删除</el-button>
      </div>

      <div v-if="loading" style="padding: 60px; text-align: center; color: var(--text-3);">加载中...</div>

      <div v-else-if="items.length === 0" style="padding: 60px; text-align: center; color: var(--text-3);">
        <div style="font-size: 48px; margin-bottom: 12px;">🗑️</div>
        <div>回收站是空的</div>
      </div>

      <div v-else>
        <div v-for="doc in items" :key="doc.id" class="trash-item" :class="{ selected: isSelected(doc.id) }">
          <el-checkbox class="trash-check" :model-value="isSelected(doc.id)" @change="toggleSelect(doc.id)" />
          <div class="doc-icon" :class="doc.file_type || 'md'">{{ fileIcon(doc.file_type) }}</div>
          <div class="trash-info">
            <div class="trash-title">{{ doc.title }}</div>
            <div class="trash-meta">
              <span>{{ formatSize(doc.file_size) }}</span>
              <span>{{ doc.word_count }} 字</span>
              <span>删除于 {{ formatTime(doc.deleted_at) }}</span>
            </div>
          </div>
          <div class="trash-actions">
            <el-button size="small" type="primary" plain @click="restoreDoc(doc)">恢复</el-button>
            <el-button size="small" type="danger" plain @click="purgeDoc(doc)">彻底删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="purgeVisible" title="⚠️ 确认彻底删除" width="540px">
      <div style="font-size: 13px; color: var(--red); margin-bottom: 12px; line-height: 1.7;">
        彻底删除<strong>不可恢复</strong>！将同时删除原始文件、版本历史、向量索引与关联数据。
        即将删除以下 {{ selectedDocs.length }} 篇文档：
      </div>
      <div class="batch-delete-list">
        <div v-for="doc in selectedDocs" :key="doc.id" class="batch-delete-item">
          <span class="batch-delete-icon">{{ fileIcon(doc.file_type) }}</span>
          <span class="batch-delete-title" :title="doc.title">{{ doc.title }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="purgeVisible = false">取消</el-button>
        <el-button type="danger" :loading="purging" @click="doBatchPurge">
          确认彻底删除 {{ selectedIds.length }} 篇
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { trashApi } from '@/api'

const items = ref([])
const loading = ref(false)
const selectedIds = ref([])
const purgeVisible = ref(false)
const purging = ref(false)
const restoring = ref(false)

const selectedDocs = computed(() => items.value.filter((d) => selectedIds.value.includes(d.id)))
const allSelected = computed(() => items.value.length > 0 && selectedIds.value.length === items.value.length)

function fileIcon(type) {
  const icons = { pdf: '📕', docx: '📘', md: '📗', txt: '📙', html: '🌐', clip: '🌐' }
  return icons[type] || '📄'
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function isSelected(id) {
  return selectedIds.value.includes(id)
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx === -1) selectedIds.value.push(id)
  else selectedIds.value.splice(idx, 1)
}

function toggleSelectAll(val) {
  selectedIds.value = val ? items.value.map((d) => d.id) : []
}

async function load() {
  loading.value = true
  try {
    items.value = await trashApi.list()
    // 清理已不存在的选中项
    const valid = new Set(items.value.map((d) => d.id))
    selectedIds.value = selectedIds.value.filter((id) => valid.has(id))
  } catch (e) {
  } finally {
    loading.value = false
  }
}

async function restoreDoc(doc) {
  try {
    await trashApi.restore(doc.id)
    ElMessage.success(`已恢复《${doc.title}》`)
    load()
  } catch (e) {
    ElMessage.error(e.message || '恢复失败')
  }
}

async function purgeDoc(doc) {
  try {
    await ElMessageBox.confirm(
      `彻底删除《${doc.title}》？该操作不可恢复，将同时删除原始文件、版本历史和向量索引。`,
      '确认彻底删除',
      { type: 'warning', confirmButtonText: '彻底删除', confirmButtonClass: 'el-button--danger' }
    )
    await trashApi.purge(doc.id)
    ElMessage.success('已彻底删除')
    load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '删除失败')
  }
}

async function batchRestore() {
  if (!selectedIds.value.length) return
  restoring.value = true
  try {
    const data = await trashApi.batchRestore(selectedIds.value)
    ElMessage.success(`已恢复 ${data.restored} 篇文档`)
    selectedIds.value = []
    load()
  } catch (e) {
    ElMessage.error(e.message || '批量恢复失败')
  } finally {
    restoring.value = false
  }
}

function openBatchPurge() {
  if (!selectedIds.value.length) {
    ElMessage.warning('请先勾选要删除的文档')
    return
  }
  purgeVisible.value = true
}

async function doBatchPurge() {
  purging.value = true
  try {
    const data = await trashApi.batchPurge(selectedIds.value)
    ElMessage.success(`已彻底删除 ${data.purged} 篇文档`)
    purgeVisible.value = false
    selectedIds.value = []
    load()
  } catch (e) {
    ElMessage.error(e.message || '批量删除失败')
  } finally {
    purging.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  background: var(--accent-weak);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  animation: fadeIn 0.2s ease;
}
.batch-count { color: var(--accent-text); font-weight: 600; }
.trash-check { margin-right: 6px; flex-shrink: 0; }
.trash-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}
.trash-item:hover { background: var(--bg-hover); }
.trash-item.selected { background: var(--accent-weak); }
.trash-item:last-child { border-bottom: none; }
.doc-icon {
  width: 40px; height: 40px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.doc-icon.pdf { background: var(--red-weak); color: var(--red); }
.doc-icon.docx { background: var(--blue-weak); color: var(--blue); }
.doc-icon.md { background: var(--green-weak); color: var(--green); }
.doc-icon.txt { background: var(--amber-weak); color: var(--amber); }
.doc-icon.html { background: var(--purple-weak); color: var(--purple); }
.doc-icon.clip { background: var(--accent-weak); color: var(--accent); }
.trash-info { flex: 1; min-width: 0; }
.trash-title { font-size: 14px; font-weight: 500; color: var(--text-1); }
.trash-meta { font-size: 12px; color: var(--text-3); margin-top: 4px; display: flex; gap: 12px; }
.trash-actions { flex-shrink: 0; }
.batch-delete-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-inset);
}
.batch-delete-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.batch-delete-item:last-child { border-bottom: none; }
.batch-delete-icon { font-size: 15px; flex-shrink: 0; }
.batch-delete-title {
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
