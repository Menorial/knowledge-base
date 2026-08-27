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
        <div class="result-snippet" v-html="r.snippet"></div>
        <div class="result-meta">匹配度：{{ (100 - Math.min(99, r.rank * 20)).toFixed(0) }}%</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { searchApi } from '@/api'

const query = ref('')
const results = ref([])
const total = ref(0)
const loading = ref(false)
const elapsed = ref(0)
const hasSearched = ref(false)
const router = useRouter()

async function doSearch() {
  if (!query.value.trim()) return
  loading.value = true
  hasSearched.value = true
  const t0 = Date.now()
  try {
    const data = await searchApi.fulltext(query.value)
    results.value = data.results
    total.value = data.total
    elapsed.value = Date.now() - t0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function openDoc(id) {
  router.push({ path: '/documents', query: { open: id } })
}
</script>

<style scoped>
.search-page { padding: 24px; }
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
