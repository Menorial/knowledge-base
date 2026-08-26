<template>
  <div class="page-container">
    <div class="page-header">
      <h1>文档管理</h1>
      <div class="subtitle">上传、浏览和管理你的知识库文档</div>
    </div>

    <div class="card" style="padding: 20px 24px;">
      <div style="display: flex; gap: 12px; margin-bottom: 20px; align-items: center;">
        <el-input
          v-model="searchQuery"
          placeholder="搜索文档标题..."
          style="width: 300px;"
          :prefix-icon="Search"
          clearable
          @clear="loadList"
          @keyup.enter="loadList"
        />
        <el-button type="primary" :icon="Search" @click="loadList">搜索</el-button>
        <div style="flex: 1;"></div>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileSelect"
          accept=".md,.txt,.pdf,.docx,.html"
          multiple
        >
          <el-button type="primary" :icon="Upload">上传文档</el-button>
        </el-upload>
        <el-button :icon="EditPen" @click="openCreateDialog">📝 新建 Markdown</el-button>
        <el-button :icon="Refresh" :loading="reindexing" @click="reindexAll">一键重建全部索引</el-button>
      </div>

      <div class="upload-zone" :class="{ dragover: isDragging }"
        @click="triggerUpload"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop">
        <div class="icon">📤</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">
          点击或拖拽文件到此处上传
        </div>
        <div style="font-size: 12px; color: #6b7280;">
          支持 Markdown / PDF / Word / TXT / HTML，单个文件 ≤ 20MB
        </div>
        <input ref="fileInput" type="file" multiple hidden accept=".md,.txt,.pdf,.docx,.html"
          @change="handleFileSelect" />
      </div>
    </div>

    <div class="card" style="margin-top: 16px;">
      <div v-if="loading" style="padding: 60px; text-align: center; color: #6b7280;">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <div style="margin-top: 8px;">加载中...</div>
      </div>

      <div v-else-if="documents.length === 0" style="padding: 60px; text-align: center; color: #6b7280;">
        <div style="font-size: 48px; margin-bottom: 12px;">📄</div>
        <div>还没有文档，上传第一个吧</div>
      </div>

      <div v-else>
        <div v-for="doc in documents" :key="doc.id" class="doc-list-item" @click="openViewer(doc)">
          <div class="doc-icon" :class="doc.file_type || 'md'">
            {{ fileIcon(doc.file_type) }}
          </div>
          <div class="doc-info">
            <div class="doc-title">
              <template v-if="renamingId === doc.id">
                <input ref="renameInput" v-model="renameValue" class="doc-rename-input" @click.stop @blur="commitRename" @keyup.enter="commitRename" @keyup.esc="cancelRename" @mousedown.stop />
              </template>
              <template v-else>
                <span class="doc-title-text" @dblclick.stop="startRename(doc)" :title="'双击重命名：' + doc.title">{{ doc.title }}</span>
              </template>
              <el-icon class="doc-rename-icon" @click.stop="startRename(doc)" title="重命名"><Edit /></el-icon>
            </div>
            <div class="doc-meta">
              <span>{{ formatSize(doc.file_size) }}</span>
              <span>{{ formatTime(doc.created_at) }}</span>
              <span v-if="doc.tags && doc.tags.length" style="display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                <el-tag size="small" class="doc-tag" v-for="t in doc.tags" :key="t" closable @close="removeTag(doc, t)">{{ t }}</el-tag>
              </span>
              <span class="add-tag-btn" @click.stop="openAddTag(doc)" title="添加标签">+ 标签</span>
            </div>
          </div>
          <div class="doc-status">
            <span class="status-badge" :class="doc.parse_status">
              {{ statusLabel(doc.parse_status) }}
            </span>
          </div>
          <div class="doc-actions" @click.stop>
            <el-button link type="primary" size="small" @click="editDoc(doc)">编辑</el-button>
            <el-button link type="primary" size="small" @click="reparseDoc(doc)">重新解析</el-button>
            <el-button link type="warning" size="small" @click="reindexDoc(doc)">重建索引</el-button>
            <el-button link type="danger" size="small" @click="deleteDoc(doc)">删除</el-button>
          </div>
        </div>
      </div>

      <div v-if="total > pageSize" style="padding: 16px 20px; text-align: center; border-top: 1px solid #f3f4f6;">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next, page-size"
          background
          @size-change="loadList"
          @current-change="loadList"
        />
      </div>
    </div>

    <el-dialog v-model="createVisible" title="📝 新建 Markdown 文档" width="700px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="文档标题">
          <el-input v-model="createForm.title" placeholder="例如：学习笔记" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="createForm.content" type="textarea" :rows="12"
            style="font-family: 'Fira Code', Consolas, monospace; font-size: 14px;"
            placeholder="# 在这里写 Markdown..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="doCreate" :loading="creating">创建文档</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="viewerVisible" :title="viewerDoc?.title" width="80%" class="viewer-modal" :close-on-click-modal="false">
      <div class="viewer-content" v-loading="viewerLoading">
        <div style="display: flex; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">
          <el-button size="small" @click="viewerMode = 'md'" :type="viewerMode === 'md' ? 'primary' : 'default'">Markdown</el-button>
          <el-button size="small" @click="viewerMode = 'edit'" :type="viewerMode === 'edit' ? 'primary' : 'default'">编辑</el-button>
          <div style="flex: 1;"></div>
          <el-button size="small" @click="downloadRaw" :disabled="!viewerDoc?.file_path">下载原文件</el-button>
        </div>
        <div v-if="viewerMode === 'md'" class="markdown-body" v-html="renderedMd"></div>
        <div v-else-if="viewerMode === 'edit'" style="padding: 16px;">
          <el-input v-model="editContent" type="textarea" :rows="20" style="font-family: 'Fira Code', Consolas, monospace; font-size: 14px;" />
          <div style="margin-top: 12px; text-align: right;">
            <el-button @click="viewerMode = 'md'">取消</el-button>
            <el-button type="primary" @click="saveEdit">保存</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Upload, Loading, Refresh, EditPen, Edit } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import highlight from 'highlight.js'
import { documentsApi } from '@/api'

const md = new MarkdownIt({
  html: true,
  highlight(str, lang) {
    if (lang && highlight.getLanguage(lang)) {
      try {
        return highlight.highlight(str, { language: lang, ignoreIllegals: true }).value
      } catch (_) {}
    }
    return ''
  },
  breaks: true,
  linkify: true,
})

const documents = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')
const loading = ref(false)
const isDragging = ref(false)
const reindexing = ref(false)

const fileInput = ref(null)
const uploadDialogVisible = ref(false)

const viewerVisible = ref(false)
const viewerDoc = ref(null)
const viewerMode = ref('md')
const viewerLoading = ref(false)
const editContent = ref('')

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ title: '', content: '' })

const renamingId = ref(null)
const renameValue = ref('')
const renameInput = ref(null)

const renderedMd = computed(() => {
  return md.render(viewerDoc.value?.content_md || '')
})

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

function statusLabel(s) {
  const map = { success: '解析成功', partial: '部分解析', failed: '解析失败', processing: '解析中', pending: '待处理' }
  return map[s] || s
}

async function loadList() {
  loading.value = true
  try {
    const data = await documentsApi.list({
      page: page.value,
      page_size: pageSize.value,
      search: searchQuery.value || undefined,
    })
    documents.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleFileSelect(file) {
  if (!file) return
  await doUpload(file.raw)
}

async function handleDrop(e) {
  isDragging.value = false
  const files = Array.from(e.dataTransfer.files)
  for (const f of files) {
    await doUpload(f)
  }
}

async function doUpload(file) {
  try {
    const data = await documentsApi.upload(file)
    ElMessage.success(`已上传：${file.name}（${statusLabel(data.parse_status)}）`)
    loadList()
  } catch (err) {
    // error already handled in interceptor
  }
}

function openViewer(doc) {
  viewerDoc.value = doc
  viewerMode.value = 'md'
  viewerVisible.value = true
  loadPreview(doc.id)
}

async function loadPreview(id) {
  viewerLoading.value = true
  try {
    const data = await documentsApi.preview(id)
    viewerDoc.value = { ...viewerDoc.value, ...data }
    editContent.value = data.content_md || ''
  } finally {
    viewerLoading.value = false
  }
}

function downloadRaw() {
  if (!viewerDoc.value) return
  window.open(documentsApi.rawUrl(viewerDoc.value.id), '_blank')
}

async function saveEdit() {
  try {
    await documentsApi.update(viewerDoc.value.id, { content_md: editContent.value })
    ElMessage.success('保存成功')
    viewerMode.value = 'md'
    await loadPreview(viewerDoc.value.id)
    loadList()
  } catch (err) {}
}

function editDoc(doc) {
  viewerDoc.value = doc
  viewerMode.value = 'edit'
  viewerVisible.value = true
  loadPreview(doc.id)
}

async function reparseDoc(doc) {
  try {
    await ElMessageBox.confirm('确定重新解析该文档？这会覆盖现有的 Markdown 内容。', '确认')
    ElMessage.info('正在重新解析...')
    await documentsApi.reparse(doc.id)
    ElMessage.success('重新解析完成')
    loadList()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '操作失败')
  }
}

async function reindexDoc(doc) {
  try {
    ElMessage.info('正在重建索引（向量化），首次需加载本地模型...')
    const data = await documentsApi.reindex(doc.id)
    ElMessage.success(`完成，共 ${data.chunks} 个片段已向量化`)
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '重建失败')
  }
}

async function reindexAll() {
  try {
    await ElMessageBox.confirm('这会为所有文档重新构建向量索引，确定继续？', '批量重建', { type: 'warning' })
    reindexing.value = true
    ElMessage.info('正在批量重建索引，请稍候...')
    const data = await documentsApi.reindexAll()
    ElMessage.success(`完成！${data.documents} 个文档，共 ${data.chunks} 个片段`)
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '批量重建失败')
  } finally {
    reindexing.value = false
  }
}

async function deleteDoc(doc) {
  try {
    await ElMessageBox.confirm(`确定删除《${doc.title}》？`, '确认删除', { type: 'warning' })
    await documentsApi.delete(doc.id)
    ElMessage.success('已删除')
    loadList()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '删除失败')
  }
}

function startRename(doc) {
  renamingId.value = doc.id
  renameValue.value = doc.title
  setTimeout(() => {
    const el = renameInput.value
    if (el) { el.focus(); el.select() }
  }, 10)
}

async function commitRename() {
  const id = renamingId.value
  const newTitle = renameValue.value.trim()
  renamingId.value = null
  if (!id || !newTitle) return
  try {
    await documentsApi.update(id, { title: newTitle })
    ElMessage.success('重命名成功')
    loadList()
  } catch (e) {
    ElMessage.error('重命名失败')
  }
}

function cancelRename() { renamingId.value = null }

function openCreateDialog() {
  createForm.value = { title: '', content: '' }
  createVisible.value = true
}

async function doCreate() {
  if (!createForm.value.title.trim()) { ElMessage.warning('请输入标题'); return }
  creating.value = true
  try {
    const r = await fetch('/api/documents/create-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createForm.value),
    })
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || '创建失败') }
    ElMessage.success('创建成功！正在后台建立索引...')
    createVisible.value = false
    createForm.value = { title: '', content: '' }
    loadList()
  } catch (e) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creating.value = false
  }
}

function openAddTag(doc) {
  const name = prompt('输入标签名（空格分隔可添加多个）：')
  if (!name || !name.trim()) return
  const names = name.trim().split(/\s+/)
  addTagsToDoc(doc.id, names)
}

async function addTagsToDoc(docId, names) {
  try {
    const r = await fetch(`/api/tags/document/${docId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(names),
    })
    if (!r.ok) throw new Error('添加失败')
    ElMessage.success(`已添加 ${names.length} 个标签`)
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function removeTag(doc, tagName) {
  try {
    const tr = await fetch('/api/tags')
    const tags = await tr.json()
    const tag = tags.find(t => t.name === tagName)
    if (!tag) return
    const r = await fetch(`/api/tags/document/${doc.id}/${tag.id}`, { method: 'DELETE' })
    if (r.ok) loadList()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(loadList)
</script>

<style>
.doc-tag { cursor: pointer; }
.doc-tag:hover { opacity: 0.8; }
.add-tag-btn {
  display: inline-block;
  font-size: 11px;
  color: #3b82f6;
  padding: 0 6px;
  cursor: pointer;
  border: 1px dashed #93c5fd;
  border-radius: 4px;
  line-height: 1.4;
  transition: all 0.15s;
}
.add-tag-btn:hover {
  background: #eff6ff;
  border-color: #3b82f6;
}
.doc-title {
  display: flex;
  align-items: center;
  gap: 6px;
}
.doc-title-text {
  cursor: text;
}
.doc-title-text:hover {
  color: #3b82f6;
}
.doc-rename-icon {
  opacity: 0;
  font-size: 14px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s;
}
.doc-list-item:hover .doc-rename-icon {
  opacity: 1;
}
.doc-rename-icon:hover {
  color: #3b82f6;
}
.doc-rename-input {
  font-size: 14px;
  font-weight: 600;
  padding: 2px 8px;
  border: 1px solid #3b82f6;
  border-radius: 6px;
  outline: none;
  background: #fff;
  min-width: 120px;
}
</style>
