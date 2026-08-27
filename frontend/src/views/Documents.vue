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
        <el-button :icon="Link" @click="openClipDialog">🌐 网页剪藏</el-button>
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

    <el-dialog v-model="clipVisible" title="🌐 网页剪藏" width="620px">
      <el-form label-width="70px">
        <el-form-item label="网页地址" required>
          <el-input v-model="clipForm.url" placeholder="https://example.com/article" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="clipForm.title" placeholder="留空则自动取网页标题" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="clipForm.tagsText" placeholder="可选，空格分隔多个标签" />
        </el-form-item>
      </el-form>
      <div style="font-size: 12px; color: #94a3b8; line-height: 1.7; margin-bottom: 8px;">
        💡 后端会抓取网页正文并自动转为 Markdown 入库（支持搜索 / AI 问答 / 图谱）。
      </div>
      <el-alert type="warning" :closable="false">
        <div style="font-size: 12px; line-height: 1.8;">
          <div>⚠️ 如果网站拦截服务器抓取（如 CSDN 返回 521），请用<b>书签小工具</b>一键剪藏：</div>
          <ol style="margin: 4px 0 8px 18px; padding: 0;">
            <li>浏览器收藏夹新建书签，名称填「剪藏」</li>
            <li>把书签的网址替换为下方代码（点按钮复制）</li>
            <li>打开目标网页，点书签即可剪藏</li>
          </ol>
          <el-button size="small" type="warning" plain @click="copyBookmarklet">📋 复制书签代码</el-button>
        </div>
      </el-alert>
      <template #footer>
        <el-button @click="clipVisible = false">取消</el-button>
        <el-button type="primary" @click="doClip" :loading="clipping">剪藏</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="viewerVisible" :title="viewerDoc?.title" width="80%" class="viewer-modal" :close-on-click-modal="false">
      <div class="viewer-content" v-loading="viewerLoading">
        <div style="display: flex; gap: 8px; padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">
          <el-button size="small" @click="viewerMode = 'md'" :type="viewerMode === 'md' ? 'primary' : 'default'">Markdown</el-button>
          <el-button size="small" @click="viewerMode = 'edit'" :type="viewerMode === 'edit' ? 'primary' : 'default'">编辑</el-button>
          <el-button size="small" @click="openVersions" :icon="Clock">历史版本</el-button>
          <div style="flex: 1;"></div>
          <el-button size="small" @click="downloadRaw" :disabled="!viewerDoc?.file_path">下载原文件</el-button>
        </div>
        <div v-if="viewerDoc?.summary" class="doc-summary">
          <strong>📝 AI 摘要：</strong>{{ viewerDoc.summary }}
        </div>
        <div v-if="viewerDoc?.source_url" class="doc-source">
          <span>🌐 来源：</span>
          <a :href="viewerDoc.source_url" target="_blank" rel="noopener noreferrer">{{ viewerDoc.source_url }}</a>
        </div>
        <div v-if="links.outgoing.length || links.incoming.length" class="doc-links">
          <div v-if="links.outgoing.length" class="links-group">
            <span class="links-label">🔗 本文引用</span>
            <span v-for="l in links.outgoing" :key="'o' + l.id" class="link-chip"
              :class="l.source" @click="switchViewer(l.id)" :title="'打开《' + l.title + '》'">
              {{ l.title }}<el-icon class="link-open"><Right /></el-icon>
            </span>
          </div>
          <div v-if="links.incoming.length" class="links-group">
            <span class="links-label">🔙 被引用</span>
            <span v-for="l in links.incoming" :key="'i' + l.id" class="link-chip"
              :class="l.source" @click="switchViewer(l.id)" :title="'打开《' + l.title + '》'">
              {{ l.title }}<el-icon class="link-open"><Right /></el-icon>
            </span>
          </div>
          <div class="links-hint">🕸️ 链接由系统自动识别（正文出现其他文档标题），也可用 <code>[[文档标题]]</code> 显式指定</div>
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

    <el-dialog v-model="versionsVisible" title="📜 历史版本" width="640px">
      <div v-if="versionsLoading" style="padding: 40px; text-align: center; color: #6b7280;">加载中...</div>
      <div v-else-if="versions.length === 0" style="padding: 40px; text-align: center; color: #6b7280;">暂无历史版本</div>
      <div v-else class="version-list">
        <div v-for="v in versions" :key="v.id" class="version-item">
          <div class="version-main" @click="previewVersion(v)">
            <div class="version-title">
              <span class="version-badge">v{{ v.id }}</span>
              <span class="version-note">{{ v.version_note || '未命名版本' }}</span>
            </div>
            <div class="version-meta">
              {{ formatTime(v.created_at) }} · {{ v.word_count }} 字
              <span v-if="v.content_preview" class="version-preview">{{ v.content_preview }}</span>
            </div>
          </div>
          <el-button size="small" type="primary" plain @click="restoreVersion(v)">回滚</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="versionsVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Upload, Loading, Refresh, EditPen, Edit, Clock, Right, Link } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import highlight from 'highlight.js'
import DOMPurify from 'dompurify'
import { documentsApi, tagsApi, linksApi } from '@/api'

const route = useRoute()
const router = useRouter()

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

const renderSafe = (text) => DOMPurify.sanitize(md.render(text || ''))

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

const clipVisible = ref(false)
const clipping = ref(false)
const clipForm = ref({ url: '', title: '', tagsText: '' })

const BOOKMARKLET = "javascript:(function(){var u=location.href,t=document.title,h='<!DOCTYPE html>'+document.documentElement.outerHTML;fetch('http://localhost:8000/api/documents/clip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u,title:t,html:h})}).then(function(r){return r.json()}).then(function(d){if(d&&d.id){alert('✅ 已剪藏：《'+d.title+'》')}else{alert('❌ 剪藏失败：'+(d&&d.detail||'未知错误'))}}).catch(function(e){alert('❌ 连接知识库失败：'+e.message+'（请确认后端已启动 http://localhost:8000）')})})();"

async function copyBookmarklet() {
  try {
    await navigator.clipboard.writeText(BOOKMARKLET)
    ElMessage.success('书签代码已复制！粘贴到收藏夹书签的网址里即可')
  } catch (e) {
    ElMessage.error('复制失败，请从 README 复制')
  }
}

const renamingId = ref(null)
const renameValue = ref('')
const renameInput = ref(null)

const versionsVisible = ref(false)
const versionsLoading = ref(false)
const versions = ref([])

const links = ref({ outgoing: [], incoming: [] })

const renderedMd = computed(() => {
  return renderSafe(viewerDoc.value?.content_md || '')
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
  loadLinks(doc.id)
}

async function loadLinks(id) {
  try {
    links.value = await linksApi.docLinks(id)
  } catch (e) {
    links.value = { outgoing: [], incoming: [] }
  }
}

async function switchViewer(id) {
  try {
    const doc = await documentsApi.get(id)
    viewerDoc.value = doc
    viewerMode.value = 'md'
    loadPreview(doc.id)
    loadLinks(doc.id)
  } catch (e) {
    ElMessage.error('无法打开关联文档')
  }
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
    loadLinks(viewerDoc.value.id)
    loadList()
  } catch (err) {}
}

function editDoc(doc) {
  viewerDoc.value = doc
  viewerMode.value = 'edit'
  viewerVisible.value = true
  loadPreview(doc.id)
  loadLinks(doc.id)
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
    await documentsApi.createText(createForm.value)
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

function openClipDialog() {
  clipForm.value = { url: '', title: '', tagsText: '' }
  clipVisible.value = true
}

async function doClip() {
  const url = clipForm.value.url.trim()
  if (!url) { ElMessage.warning('请输入网页地址'); return }
  clipping.value = true
  try {
    const data = await documentsApi.clip({
      url,
      title: clipForm.value.title.trim() || undefined,
      tags: clipForm.value.tagsText.trim() ? clipForm.value.tagsText.trim().split(/\s+/) : [],
    })
    ElMessage.success(`剪藏成功：《${data.title}》`)
    clipVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error(e.message || '剪藏失败')
  } finally {
    clipping.value = false
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
    await tagsApi.addToDoc(docId, names)
    ElMessage.success(`已添加 ${names.length} 个标签`)
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function removeTag(doc, tagName) {
  try {
    const tags = await tagsApi.list()
    const tag = tags.find(t => t.name === tagName)
    if (!tag) return
    await tagsApi.removeFromDoc(doc.id, tag.id)
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function openVersions() {
  if (!viewerDoc.value) return
  versionsVisible.value = true
  versionsLoading.value = true
  versions.value = []
  try {
    versions.value = await documentsApi.versions(viewerDoc.value.id)
  } catch (e) {
    ElMessage.error('加载版本失败')
  } finally {
    versionsLoading.value = false
  }
}

async function previewVersion(v) {
  try {
    const data = await documentsApi.version(viewerDoc.value.id, v.id)
    ElMessageBox.alert(
      `<pre style="white-space:pre-wrap;font-size:12px;max-height:400px;overflow:auto;background:#f8fafc;padding:12px;border-radius:8px;margin:0">${escapeHtml(data.content_md || '')}</pre>`,
      `版本 v${v.id} 内容预览（${v.version_note || ''}）`,
      { dangerouslyUseHTMLString: true, customStyle: { width: '640px' } }
    )
  } catch (e) { ElMessage.error('加载版本内容失败') }
}

async function restoreVersion(v) {
  try {
    await ElMessageBox.confirm(`确定回滚到版本 v${v.id}？当前内容将保存为新版本。`, '确认回滚', { type: 'warning' })
    await documentsApi.restoreVersion(viewerDoc.value.id, v.id)
    ElMessage.success('已回滚')
    versionsVisible.value = false
    await loadPreview(viewerDoc.value.id)
    loadLinks(viewerDoc.value.id)
    loadList()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message || '回滚失败')
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// 从搜索页跳转：?open=<doc_id> 直接打开文档
watch(
  () => route.query.open,
  async (id) => {
    if (!id) return
    const docId = Number(id)
    router.replace({ query: {} })
    try {
      const doc = await documentsApi.get(docId)
      openViewer(doc)
    } catch (e) { /* 文档可能已删除 */ }
  }
)

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
.doc-summary {
  margin: 12px 16px;
  padding: 10px 14px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  font-size: 13px;
  color: #1e40af;
  line-height: 1.6;
}
.doc-source {
  margin: 0 16px 12px;
  font-size: 12px;
  color: #64748b;
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}
.doc-source a {
  color: #3b82f6;
  text-decoration: none;
  word-break: break-all;
}
.doc-source a:hover { text-decoration: underline; }
.version-list { display: flex; flex-direction: column; gap: 8px; }
.version-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}
.version-main { flex: 1; min-width: 0; cursor: pointer; }
.version-title { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.version-badge {
  background: #6366f1;
  color: #fff;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 8px;
  flex-shrink: 0;
}
.version-note { font-size: 14px; font-weight: 600; color: #0f172a; }
.version-meta { font-size: 12px; color: #64748b; display: flex; flex-direction: column; gap: 4px; }
.version-preview {
  color: #94a3b8;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 420px;
}
.version-item:hover { border-color: #a5b4fc; background: #eef2ff; }
.doc-links {
  margin: 12px 16px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.links-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.links-label { font-size: 12px; color: #64748b; font-weight: 600; flex-shrink: 0; }
.link-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.link-chip.auto { background: #eff6ff; color: #1e40af; border-color: #bfdbfe; }
.link-chip.syntax { background: #f0fdf4; color: #166534; border-color: #bbf7d0; }
.link-chip:hover { transform: translateY(-1px); box-shadow: 0 2px 8px rgba(59,130,246,0.15); }
.link-open { font-size: 10px; }
.links-hint { font-size: 11px; color: #94a3b8; }
.links-hint code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }
</style>
