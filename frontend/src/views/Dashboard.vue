<template>
  <div class="page-container dashboard">
    <div class="page-header">
      <h1>📊 知识库概览</h1>
      <div class="subtitle">你的知识资产一览</div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg,#dbeafe,#bfdbfe);">📄</div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.documents || 0 }}</div>
          <div class="stat-label">文档总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg,#fef3c7,#fde68a);">💬</div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.conversations || 0 }}</div>
          <div class="stat-label">AI 对话</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg,#dcfce7,#bbf7d0);">✉️</div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.messages || 0 }}</div>
          <div class="stat-label">消息总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg,#fce7f3,#fbcfe8);">🏷️</div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.tags || 0 }}</div>
          <div class="stat-label">标签数量</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg,#ede9fe,#ddd6fe);">🧩</div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.chunks || 0 }}</div>
          <div class="stat-label">文本分块</div>
        </div>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="card">
        <h3>📈 近 7 日上传趋势</h3>
        <div class="trend-chart">
          <div v-for="(v, i) in stats.upload_trend_7d" :key="i" class="trend-bar-wrap">
            <div class="trend-bar" :style="{ height: barHeight(v) + '%' }" :title="v + ' 篇'"></div>
            <div class="trend-label">{{ dayLabel(i) }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>🏆 Top 标签</h3>
        <div class="tag-list">
          <div v-if="!stats.top_tags?.length" class="empty">暂无标签</div>
          <div v-for="t in stats.top_tags" :key="t.name" class="tag-item">
            <span class="tag-name">{{ t.name }}</span>
            <span class="tag-count">{{ t.count }}</span>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>⚙️ 解析状态</h3>
        <div class="status-list">
          <div v-for="(cnt, status) in stats.parse_status" :key="status" class="status-item">
            <span class="status-dot" :class="status"></span>
            <span class="status-name">{{ statusLabel(status) }}</span>
            <span class="status-count">{{ cnt }}</span>
          </div>
          <div v-if="!Object.keys(stats.parse_status || {}).length" class="empty">暂无数据</div>
        </div>
      </div>

      <div class="card">
        <h3>🔗 快速入口</h3>
        <div class="quick-links">
          <router-link to="/documents" class="quick-link">📄 文档管理</router-link>
          <router-link to="/chat" class="quick-link">💬 AI 对话</router-link>
          <router-link to="/search" class="quick-link">🔍 全文搜索</router-link>
          <router-link to="/settings" class="quick-link">⚙️ 系统设置</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const stats = ref({})

async function load() {
  try {
    const r = await fetch('/api/stats/overview')
    stats.value = await r.json()
  } catch (e) {
    console.error(e)
  }
}

function barHeight(v) {
  const trend = stats.value.upload_trend_7d || []
  const max = Math.max(1, ...trend)
  return Math.round((v / max) * 100)
}

function dayLabel(i) {
  const d = new Date()
  d.setDate(d.getDate() - (6 - i))
  return (d.getMonth() + 1) + '/' + d.getDate()
}

function statusLabel(s) {
  return { success: '✅ 已解析', failed: '❌ 解析失败', partial: '⚠️ 部分解析', pending: '⏳ 解析中' }[s] || s
}

onMounted(load)
</script>

<style scoped>
.dashboard { padding: 24px; }
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.06); }
.stat-icon {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; flex-shrink: 0;
}
.stat-value { font-size: 26px; font-weight: 700; color: #0f172a; }
.stat-label { font-size: 13px; color: #94a3b8; }
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}
.dashboard-grid .card { padding: 20px; }
.dashboard-grid h3 { margin: 0 0 14px; font-size: 15px; color: #334155; }
.trend-chart {
  display: flex; align-items: flex-end; gap: 8px; height: 160px; padding-top: 10px;
}
.trend-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
.trend-bar {
  width: 100%; max-width: 28px;
  background: linear-gradient(180deg, #3b82f6 0%, #6366f1 100%);
  border-radius: 6px 6px 0 0; min-height: 4px; transition: height 0.4s;
}
.trend-label { font-size: 11px; color: #94a3b8; margin-top: 6px; }
.tag-list { display: flex; flex-direction: column; gap: 8px; }
.tag-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #f8fafc; border-radius: 8px; font-size: 13px; }
.tag-count { background: #3b82f6; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.status-list { display: flex; flex-direction: column; gap: 8px; }
.status-item { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 8px 12px; background: #f8fafc; border-radius: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.success { background: #22c55e; }
.status-dot.failed { background: #ef4444; }
.status-dot.partial { background: #f59e0b; }
.status-dot.pending { background: #3b82f6; }
.status-name { flex: 1; }
.status-count { font-weight: 600; color: #334155; }
.empty { text-align: center; color: #94a3b8; font-size: 13px; padding: 20px; }
.quick-links { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.quick-link { display: block; padding: 14px; background: #f8fafc; border-radius: 10px; text-align: center; color: #334155; text-decoration: none; font-size: 14px; transition: all 0.15s; }
.quick-link:hover { background: #3b82f6; color: #fff; transform: translateY(-2px); }
</style>
