<template>
  <div class="page-container search-page">
    <div class="page-header">
      <h1>🔍 全文搜索</h1>
      <div class="subtitle">基于 SQLite FTS5 的中文全文检索</div>
    </div>

    <div class="search-box">
      <el-input
        v-model="query"
        size="large"
        placeholder="输入关键词，按回车搜索..."
        @keyup.enter="doSearch"
        clearable
      >
        <template #append>
          <el-button type="primary" @click="doSearch" :loading="loading">🔍 搜索</el-button>
        </template>
      </el-input>
    </div>

    <div v-if="results.length" class="result-info">
      找到 <strong>{{ total }}</strong> 个相关文档，耗时 {{ elapsed }}ms
    </div>
    <div v-else-if="hasSearched" class="empty">未找到相关内容，换个关键词试试吧</div>

    <div class="result-list">
      <div v-for="r in results" :key="r.id" class="result-card" @click="openDoc(r.id)">
        <div class="result-title">📄 {{ r.title }}</div>
        <div class="result-snippet" v-html="safeSnippet(r.snippet)"></div>
        <div v-if="r.rank" class="result-meta">相关度：{{ matchScore(r) }}%</div>
      </div>
    </div>

    <div v-if="total > pageSize" class="pager">
      <el-pagination
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { searchApi } from '@/api'

const query = ref('')
const results = ref([])
const total = ref(0)
const loading = ref(false)
const elapsed = ref(0)
const hasSearched = ref(false)
const page = ref(1)
const pageSize = 20
const router = useRouter()

// FTS5 的 bm25 rank 是负数（越小越相关），原公式 100 - rank*20 会恒大于 100%。
// 这里按本页最相关的那条归一化成 0-100%。
const bestRank = computed(() =>
  Math.max(...results.value.map((r) => Math.abs(r.rank || 0)), 1e-6)
)

function matchScore(r) {
  return Math.max(1, Math.round((Math.abs(r.rank || 0) / bestRank.value) * 100))
}

// snippet 来自 FTS 的 snippet()，内容是文档原文（可能含 HTML），
// 只保留高亮用的 <mark>，其余标签/属性全部去掉
const safeSnippet = (html) =>
  DOMPurify.sanitize(html || '', { ALLOWED_TAGS: ['mark'], ALLOWED_ATTR: [] })

async function doSearch(reset = true) {
  if (!query.value.trim()) return
  if (reset !== false) page.value = 1
  loading.value = true
  hasSearched.value = true
  const t0 = Date.now()
  try {
    const data = await searchApi.fulltext(query.value, page.value, pageSize)
    results.value = data.results
    total.value = data.total
    elapsed.value = Date.now() - t0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onPageChange(p) {
  page.value = p
  doSearch(false)
}

function openDoc(id) {
  router.push({ path: '/documents', query: { open: id } })
}
</script>

<style scoped>
.search-page { padding: 24px; }
.pager { display: flex; justify-content: center; margin-top: 16px; }
.search-box { max-width: 800px; margin: 0 auto 24px; }
.result-info { color: var(--text-2); font-size: 13px; margin-bottom: 16px; padding: 0 4px; }
.result-list { display: flex; flex-direction: column; gap: 12px; }
.result-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 18px 20px; cursor: pointer; transition: all 0.15s;
}
.result-card:hover { border-color: var(--accent); box-shadow: var(--shadow-2); transform: translateY(-1px); }
.result-title { font-size: 15px; font-weight: 600; color: var(--text-1); margin-bottom: 8px; }
.result-snippet { font-size: 13px; color: var(--text-2); line-height: 1.7; }
.result-snippet :deep(mark) { background: #fef08a; color: #854d0e; padding: 1px 3px; border-radius: 3px; }
.result-meta { font-size: 11px; color: var(--text-3); margin-top: 8px; }
.empty { text-align: center; color: var(--text-3); padding: 60px 20px; font-size: 14px; }
</style>
