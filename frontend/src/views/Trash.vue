<template>
  <div class="page-container">
    <div class="page-header">
      <h1>🗑️ 回收站</h1>
      <div class="subtitle">误删的文档可以在这里恢复，或彻底删除释放空间</div>
    </div>

    <div class="card">
      <div v-if="loading" style="padding: 60px; text-align: center; color: #6b7280;">加载中...</div>

      <div v-else-if="items.length === 0" style="padding: 60px; text-align: center; color: #6b7280;">
        <div style="font-size: 48px; margin-bottom: 12px;">🗑️</div>
        <div>回收站是空的</div>
      </div>

      <div v-else>
        <div v-for="doc in items" :key="doc.id" class="trash-item">
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { trashApi } from '@/api'

const items = ref([])
const loading = ref(false)

function fileIcon(type) {
  const icons = { pdf: '📕', docx: '📘', md: '📗', txt: '📙', html: '🌐' }
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

async function load() {
  loading.value = true
  try {
    items.value = await trashApi.list()
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

onMounted(load)
</script>

<style scoped>
.trash-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border-bottom: 1px solid #f3f4f6;
}
.trash-item:last-child { border-bottom: none; }
.doc-icon {
  width: 40px; height: 40px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.doc-icon.pdf { background: #fef2f2; color: #ef4444; }
.doc-icon.docx { background: #eff6ff; color: #3b82f6; }
.doc-icon.md { background: #f0fdf4; color: #22c55e; }
.doc-icon.txt { background: #fefce8; color: #eab308; }
.doc-icon.html { background: #fdf4ff; color: #a855f7; }
.trash-info { flex: 1; min-width: 0; }
.trash-title { font-size: 14px; font-weight: 500; color: #1f2937; }
.trash-meta { font-size: 12px; color: #6b7280; margin-top: 4px; display: flex; gap: 12px; }
.trash-actions { flex-shrink: 0; }
</style>
