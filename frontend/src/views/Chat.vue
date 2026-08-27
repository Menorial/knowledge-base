<template>
  <div class="page-container chat-page" style="padding: 0;">
    <div class="chat-layout">
      <!-- 左侧会话列表 -->
      <aside class="chat-sidebar">
        <div class="sidebar-header">
          <el-button type="primary" class="new-conv-btn" @click="createNewConversation">
            <el-icon><Plus /></el-icon>
            新建对话
          </el-button>
        </div>
        <div class="chat-sessions">
          <div v-for="conv in conversations" :key="conv.id"
            class="chat-session-item"
            :class="{ active: conv.id === currentConvId }"
            @click="selectConversation(conv.id)">
            <span class="conv-mode-badge" :class="conv.mode || 'rag'">
              {{ modeIcon(conv.mode) }}
            </span>
            <template v-if="renamingId === conv.id">
              <input
                ref="renameInput"
                v-model="renameValue"
                class="conv-rename-input"
                @click.stop
                @blur="commitRename"
                @keyup.enter="commitRename"
                @keyup.esc="cancelRename"
                @mousedown.stop
              />
            </template>
            <template v-else>
              <span class="conv-title" @dblclick.stop="startRename(conv)" :title="conv.title">{{ conv.title || '新对话' }}</span>
            </template>
            <el-icon class="conv-export" @click.stop="exportConv(conv.id)" title="导出为 Markdown"><Download /></el-icon>
            <el-icon class="conv-delete" @click.stop="deleteConv(conv.id)"><Delete /></el-icon>
          </div>
          <div v-if="conversations.length === 0" class="empty-tip">
            <div style="font-size: 32px; margin-bottom: 8px;">💬</div>
            <div>还没有对话，点上面按钮开始吧</div>
          </div>
        </div>
      </aside>

      <!-- 主聊天区 -->
      <div class="chat-main">
        <!-- 无会话时的欢迎页 -->
        <div v-if="!currentConv" class="chat-welcome">
          <div class="welcome-icon">🧠</div>
          <h1>你好，我是你的知识库助手</h1>
          <p class="welcome-sub">三种模式，想怎么聊就怎么聊</p>
          <div class="mode-cards">
            <div class="mode-card" @click="quickStart('rag')">
              <div class="mode-icon rag">📚</div>
              <div class="mode-name">知识库问答</div>
              <div class="mode-desc">基于你上传的文档，精准检索回答</div>
            </div>
            <div class="mode-card" @click="quickStart('direct')">
              <div class="mode-icon direct">✨</div>
              <div class="mode-name">纯 AI 对话</div>
              <div class="mode-desc">直接和 AI 聊天，不限知识库内容</div>
            </div>
            <div class="mode-card" @click="selectDocAndStart">
              <div class="mode-icon doc">📄</div>
              <div class="mode-name">指定文档</div>
              <div class="mode-desc">围绕某篇文档深入讨论</div>
            </div>
          </div>
        </div>

        <!-- 有会话时的消息区 -->
        <div v-else class="chat-messages" ref="messagesRef">
          <div v-for="msg in currentConv.messages" :key="msg.id"
            class="chat-message" :class="msg.role">
            <div class="avatar" :class="msg.role">
              {{ msg.role === 'user' ? '👤' : '🤖' }}
            </div>
            <div class="bubble">
              <div v-html="renderMsg(msg.content)"></div>
              <div v-if="msg.sources && msg.sources.length" class="sources-list">
                <div class="sources-header" @click="toggleSources(msg.id)">
                  <span>📎 引用来源 ({{ msg.sources.length }})</span>
                  <el-icon class="expand-icon" :class="{ expanded: expandedSources[msg.id] }"><ArrowDown /></el-icon>
                </div>
                <div v-show="expandedSources[msg.id] !== false" class="sources-body">
                  <div v-for="(s, i) in msg.sources" :key="i" class="source-card">
                    <div class="source-title">📄 {{ s.title }}</div>
                    <div v-if="s.section_path" class="source-section">＞ {{ s.section_path }}</div>
                    <div v-if="s.snippet" class="source-snippet">{{ s.snippet }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="msg.role === 'assistant'" class="msg-actions">
              <span class="msg-action" @click="regenerateMsg(msg.id)" title="重新生成">🔄 重新生成</span>
              <span class="msg-action" @click="copyMsg(msg.content)" title="复制">📋 复制</span>
            </div>
          </div>

          <div v-if="streaming" class="chat-message assistant">
            <div class="avatar">🤖</div>
            <div class="bubble">
              <div v-html="renderMsg(streamingContent)"></div>
              <span class="cursor">▌</span>
              <div v-if="streamingSources.length" class="sources-list">
                <div class="sources-header"><span>📎 检索到 {{ streamingSources.length }} 个来源</span></div>
                <div class="sources-body">
                  <div v-for="(s, i) in streamingSources" :key="i" class="source-card compact">
                    📄 {{ s.title }}{{ s.section_path ? ` ＞ ${s.section_path}` : '' }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div v-if="currentConv" class="chat-input-area">
          <div class="mode-switch">
            <button class="mode-btn" :class="{ active: chatMode === 'rag' }" @click="setMode('rag')" :title="'基于知识库检索回答'">
              <span>📚</span><span>知识库</span>
            </button>
            <button class="mode-btn" :class="{ active: chatMode === 'direct' }" @click="setMode('direct')" :title="'直接和 AI 对话'">
              <span>✨</span><span>纯 AI</span>
            </button>
            <button class="mode-btn" :class="{ active: chatMode === 'doc' }" @click="setMode('doc')" :title="'围绕某篇文档回答'">
              <span>📄</span><span>指定文档</span>
            </button>
            <el-select v-if="chatMode === 'doc'" v-model="selectedDocId" placeholder="选一篇文档"
              filterable size="small" style="width: 220px; margin-left: 8px;">
              <el-option v-for="d in docList" :key="d.id" :label="d.title" :value="d.id" />
            </el-select>
          </div>
          <div class="input-row">
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="输入你的问题... (Enter 发送，Shift+Enter 换行)"
              :disabled="streaming"
              @keydown.enter.exact.prevent="sendMessage"
              resize="none"
            />
            <el-button type="primary" class="send-btn" :icon="Promotion" :loading="streaming"
              @click="sendMessage">
              发送
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, Delete, Plus, ArrowDown, Download } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import highlight from 'highlight.js'
import DOMPurify from 'dompurify'
import { chatApi, documentsApi } from '@/api'

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

const conversations = ref([])
const currentConvId = ref(null)
const currentConv = ref(null)
const inputText = ref('')
const streaming = ref(false)
const streamingContent = ref('')
const streamingSources = ref([])
const messagesRef = ref(null)

const chatMode = ref('rag')
const selectedDocId = ref(null)
const docList = ref([])

const renamingId = ref(null)
const renameValue = ref('')
const renameInput = ref(null)

const expandedSources = reactive({})

const renderMsg = (text) => DOMPurify.sanitize(md.render(text || ''))

function addCodeCopyButtons() {
  document.querySelectorAll('.chat-main pre:not(.copy-ready)').forEach(pre => {
    pre.classList.add('copy-ready')
    const btn = document.createElement('button')
    btn.textContent = '📋 复制'
    btn.style.cssText = 'position:absolute;top:8px;right:8px;background:rgba(255,255,255,0.15);color:var(--border);border:none;border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;z-index:20;transition:background 0.15s'
    btn.onmouseenter = () => btn.style.background = 'rgba(255,255,255,0.3)'
    btn.onmouseleave = () => btn.style.background = 'rgba(255,255,255,0.15)'
    btn.onclick = async () => {
      const code = pre.querySelector('code')?.textContent || pre.textContent
      try {
        await navigator.clipboard.writeText(code)
        btn.textContent = '✅ 已复制'
        setTimeout(() => btn.textContent = '📋 复制', 1500)
      } catch {
        btn.textContent = '❌ 失败'
        setTimeout(() => btn.textContent = '📋 复制', 1500)
      }
    }
    pre.style.position = 'relative'
    pre.appendChild(btn)
  })
}

function modeIcon(mode) {
  const map = { rag: '📚', direct: '✨', doc: '📄' }
  return map[mode] || '💬'
}

function toggleSources(id) {
  expandedSources[id] = expandedSources[id] === false ? true : false
}

async function loadConversations() {
  try {
    conversations.value = await chatApi.listConversations()
  } catch (e) {}
}

async function loadCurrentConversation() {
  if (!currentConvId.value) {
    currentConv.value = null
    return
  }
  try {
    currentConv.value = await chatApi.getConversation(currentConvId.value)
    // 根据会话的 mode 设置前端的 chatMode
    if (currentConv.value.mode) {
      chatMode.value = currentConv.value.mode
      if (chatMode.value === 'doc') {
        selectedDocId.value = currentConv.value.document_id || null
      }
    }
    scrollToBottom()
    nextTick(() => addCodeCopyButtons())
  } catch (e) {
    currentConv.value = null
  }
}

async function loadDocList() {
  try {
    const data = await documentsApi.list({ page: 1, page_size: 100 })
    docList.value = data.items || []
  } catch (e) {}
}

async function quickStart(mode) {
  chatMode.value = mode
  await createNewConversation()
}

async function selectDocAndStart() {
  await loadDocList()
  if (!docList.value.length) {
    ElMessage.warning('先去文档管理页面上传文档吧')
    return
  }
  chatMode.value = 'doc'
  selectedDocId.value = docList.value[0].id
  await createNewConversation()
}

async function createNewConversation() {
  let docId = null
  let mode = chatMode.value
  if (mode === 'doc') {
    docId = selectedDocId.value
    if (!docId) {
      ElMessage.warning('请先选一篇文档')
      return
    }
  }
  try {
    const conv = await chatApi.createConversation({
      title: '新对话',
      mode: mode,
      document_id: docId,
    })
    await loadConversations()
    currentConvId.value = conv.id
    await loadCurrentConversation()
    inputText.value = ''
  } catch (e) {
    ElMessage.error('创建对话失败')
  }
}

async function selectConversation(id) {
  currentConvId.value = id
  await loadCurrentConversation()
}

async function deleteConv(id) {
  try {
    await chatApi.deleteConversation(id)
    if (currentConvId.value === id) {
      currentConvId.value = null
      currentConv.value = null
    }
    await loadConversations()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function regenerateMsg(msgId) {
  if (!currentConvId.value) return
  if (!confirm('确定要重新生成这条 AI 回答吗？该消息之后的对话将被删除。')) return
  streaming.value = true
  streamingContent.value = ''
  try {
    const resp = await fetch(`/api/conversations/${currentConvId.value}/regenerate/${msgId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    if (!resp.ok || !resp.body) { ElMessage.error('重新生成失败'); return }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const d = JSON.parse(line.slice(6))
            if (d.content) { streamingContent.value += d.content; scrollToBottom() }
          } catch {}
        }
      }
    }
  } catch (e) {
    ElMessage.error('重新生成出错：' + e.message)
  } finally {
    streaming.value = false
    if (currentConvId.value) {
      await loadCurrentConversation()
      await loadConversations()
    }
  }
}

async function copyMsg(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

function exportConv(convId) {
  window.open(chatApi.exportUrl(convId), '_blank')
}

function startRename(conv) {
  renamingId.value = conv.id
  renameValue.value = conv.title || ''
  nextTick(() => {
    const el = renameInput.value
    if (el) { el.focus(); el.select() }
  })
}

async function commitRename() {
  const id = renamingId.value
  const newTitle = renameValue.value.trim()
  renamingId.value = null
  if (!id || !newTitle) return
  try {
    await chatApi.updateConversation(id, { title: newTitle })
    await loadConversations()
  } catch (e) {
    ElMessage.error('重命名失败')
  }
}

function cancelRename() { renamingId.value = null }

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function setMode(mode) {
  if (streaming.value) return
  chatMode.value = mode
  if (mode === 'rag') selectedDocId.value = null
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  // 文档模式校验
  if (chatMode.value === 'doc' && !selectedDocId.value) {
    ElMessage.warning('请先选一篇文档')
    return
  }

  let convId = currentConvId.value
  if (!convId) {
    try {
      const conv = await chatApi.createConversation({
        title: text.slice(0, 20),
        mode: chatMode.value,
        document_id: chatMode.value === 'doc' ? selectedDocId.value : null,
      })
      convId = conv.id
      currentConvId.value = conv.id
      conversations.value.unshift(conv)
    } catch (e) {
      return
    }
  }

  streaming.value = true
  streamingContent.value = ''
  streamingSources.value = []
  inputText.value = ''
  scrollToBottom()
  nextTick(() => addCodeCopyButtons())

  // 同步更新会话 mode
  if (currentConv.value && currentConv.value.mode !== chatMode.value) {
    currentConv.value.mode = chatMode.value
  }

  try {
    let url, body
    if (chatMode.value === 'rag') {
      url = '/api/chat/rag'
      body = { conversation_id: convId, message: text, top_k: 5 }
    } else if (chatMode.value === 'direct') {
      url = '/api/chat/direct'
      body = { conversation_id: convId, message: text }
    } else {
      url = '/api/chat/stream'
      body = { conversation_id: convId, document_id: selectedDocId.value, message: text }
    }

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!resp.ok || !resp.body) {
      ElMessage.error('请求失败，请检查 AI 配置')
      streaming.value = false
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') continue
          try {
            const parsed = JSON.parse(data)
            if (parsed.content) {
              streamingContent.value += parsed.content
              scrollToBottom()
            }
            if (parsed.sources) {
              streamingSources.value = parsed.sources.map(s => ({
                title: s.title,
                section_path: s.section_path,
                snippet: s.snippet || '',
              }))
            }
          } catch (_) {}
        }
      }
    }
  } catch (e) {
    ElMessage.error('AI 响应失败：' + e.message)
  } finally {
    streaming.value = false
    streamingSources.value = []
    if (currentConvId.value) {
      await loadCurrentConversation()
      await loadConversations()
    }
  }
}

watch(chatMode, () => {
  if (chatMode.value !== 'doc') {
    selectedDocId.value = null
  }
})

onMounted(async () => {
  await Promise.all([loadConversations(), loadDocList()])
})
</script>

<style scoped>
.chat-page {
  height: 100%;
  overflow: hidden;
}

.chat-layout {
  display: flex;
  height: 100%;
  background: var(--bg-inset);
}

.chat-sidebar {
  width: 260px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--bg-hover);
}

.new-conv-btn {
  width: 100%;
  height: 40px;
  border-radius: 10px;
  font-weight: 500;
}

.chat-sessions {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.empty-tip {
  padding: 40px 16px;
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
}

.chat-session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 2px;
  transition: all 0.15s;
  white-space: nowrap;
  overflow: hidden;
}

.chat-session-item:hover {
  background: var(--bg-hover);
}

.chat-session-item.active {
  background: linear-gradient(135deg, var(--accent-weak), var(--accent-weak));
  color: var(--accent-text);
  font-weight: 500;
}

.conv-mode-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  background: var(--bg-hover);
  margin-right: 8px;
  flex-shrink: 0;
}
.conv-mode-badge.rag { background: var(--blue-weak); }
.conv-mode-badge.direct { background: var(--amber-weak); }
.conv-mode-badge.doc { background: var(--green-weak); }

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.conv-rename-input {
  flex: 1;
  font-size: 13px;
  padding: 4px 8px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  outline: none;
  background: var(--bg-card);
  margin-right: 8px;
}

.conv-delete {
  opacity: 0;
  color: var(--text-3);
  font-size: 14px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.chat-session-item:hover .conv-delete { opacity: 1; }
.conv-delete:hover { color: var(--red); }

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

/* ===== 欢迎页 ===== */
.chat-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.welcome-icon {
  font-size: 72px;
  margin-bottom: 16px;
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.chat-welcome h1 {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 600;
  color: #0f172a;
}

.welcome-sub {
  margin: 0 0 40px;
  color: var(--text-2);
  font-size: 15px;
}

.mode-cards {
  display: flex;
  gap: 16px;
  max-width: 720px;
  flex-wrap: wrap;
  justify-content: center;
}

.mode-card {
  width: 200px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.mode-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.08);
  border-color: var(--accent);
}

.mode-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin: 0 auto 12px;
}
.mode-icon.rag { background: var(--blue-weak); }
.mode-icon.direct { background: var(--amber-weak); }
.mode-icon.doc { background: var(--green-weak); }

.mode-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: 4px;
}

.mode-desc {
  font-size: 12px;
  color: var(--text-3);
}

/* ===== 消息区 ===== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

.chat-message {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  animation: fadeInUp 0.3s ease;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.chat-message.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.avatar.assistant {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
  box-shadow: 0 4px 12px rgba(59,130,246,0.3);
}
.avatar.user {
  background: linear-gradient(135deg, var(--bg-hover) 0%, var(--border) 100%);
  color: var(--text-2);
}

.bubble {
  max-width: 70%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px 18px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-1);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.chat-message.user .bubble {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(59,130,246,0.3);
}

.cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent);
  font-weight: bold;
}
@keyframes blink { 50% { opacity: 0; } }

/* ===== 引用来源 ===== */
.sources-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}
.sources-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
}
.expand-icon {
  transition: transform 0.2s;
  font-size: 12px;
}
.expand-icon.expanded { transform: rotate(180deg); }
.sources-body {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.source-card {
  background: var(--bg-inset);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
}
.source-card.compact {
  padding: 6px 10px;
}
.source-title {
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 2px;
}
.source-section {
  color: var(--text-2);
  font-size: 11px;
  margin-bottom: 4px;
}
.source-snippet {
  color: var(--text-3);
  font-size: 11px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ===== 输入区 ===== */
.chat-input-area {
  padding: 16px 32px 24px;
  background: var(--bg-card);
  border-top: 1px solid var(--border);
}

.mode-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--bg-inset);
  font-size: 12px;
  color: var(--text-2);
  cursor: pointer;
  transition: all 0.15s;
}
.mode-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.mode-btn.active {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 4px 10px rgba(59,130,246,0.3);
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-row :deep(.el-textarea__inner) {
  border-radius: 12px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  font-size: 14px;
  line-height: 1.6;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.input-row :deep(.el-textarea__inner:focus) {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(59,130,246,0.1);
}

.send-btn {
  height: 40px;
  border-radius: 10px;
  padding: 0 20px;
  flex-shrink: 0;
}

/* Markdown 样式覆盖 */
.bubble :deep(h1),
.bubble :deep(h2),
.bubble :deep(h3) {
  margin: 0.8em 0 0.4em;
  font-weight: 600;
}
.bubble :deep(h1) { font-size: 1.3em; }
.bubble :deep(h2) { font-size: 1.2em; }
.bubble :deep(h3) { font-size: 1.1em; }
.bubble :deep(code) {
  background: rgba(59,130,246,0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Fira Code', Consolas, monospace;
}
.bubble :deep(pre) {
  background: var(--text-1);
  color: var(--border);
  padding: 14px 16px;
  border-radius: 10px;
  overflow-x: auto;
  margin: 0.8em 0;
}
.bubble :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}
.bubble :deep(blockquote) {
  border-left: 4px solid var(--accent);
  background: var(--accent-weak);
  padding: 8px 14px;
  margin: 0.8em 0;
  border-radius: 0 8px 8px 0;
  color: var(--accent-text);
}
.bubble :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
}
.bubble :deep(th), .bubble :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
  font-size: 13px;
}
.bubble :deep(th) { background: var(--bg-inset); font-weight: 600; }

.chat-message.user .bubble :deep(code) {
  background: rgba(255,255,255,0.2);
}
.chat-message.user .bubble :deep(pre) {
  background: rgba(0,0,0,0.2);
}
.chat-message.user .bubble :deep(blockquote) {
  background: rgba(255,255,255,0.15);
  border-left-color: rgba(255,255,255,0.5);
  color: #fff;
}

.msg-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  padding-left: 52px;
}
.msg-action {
  font-size: 12px;
  color: var(--text-3);
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.15s;
}
.msg-action:hover {
  color: var(--accent);
  background: var(--accent-weak);
}
.conv-export {
  opacity: 0;
  color: var(--text-3);
  font-size: 14px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.chat-session-item:hover .conv-export { opacity: 1; }
.conv-export:hover { color: var(--green); }
</style>
