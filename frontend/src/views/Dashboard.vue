<template>
  <div class="page-container dashboard">
    <div class="page-header">
      <h1>📊 知识库概览</h1>
      <div class="subtitle">你的知识资产一览</div>
    </div>

    <div class="stat-grid">
      <div v-for="s in statCards" :key="s.label" class="stat-card" :style="{ '--card-deg': s.deg }">
        <div class="stat-icon">{{ s.icon }}</div>
        <div class="stat-body">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="card chart-card">
        <h3>📈 近 7 日上传趋势</h3>
        <div ref="trendRef" class="chart"></div>
      </div>

      <div class="card chart-card">
        <h3>⚙️ 解析状态分布</h3>
        <div ref="statusRef" class="chart"></div>
      </div>

      <div class="card chart-card wide">
        <h3>🏆 Top 标签</h3>
        <div v-if="!stats.top_tags?.length" class="empty">暂无标签，去给文档打几个标签吧</div>
        <div v-else ref="tagsRef" class="chart"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const stats = ref({})
const trendRef = ref(null)
const statusRef = ref(null)
const tagsRef = ref(null)
let charts = []

function textColor() {
  return getComputedStyle(document.documentElement).getPropertyValue('--text-2').trim() || '#5c6068'
}
function axisColor() {
  return getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#e5e3dc'
}

const statCards = computed(() => [
  { icon: '📄', label: '文档总数', value: stats.value.documents || 0, deg: '135deg,#dbe6ff,#eef1fe' },
  { icon: '💬', label: 'AI 对话', value: stats.value.conversations || 0, deg: '135deg,#fdf3e0,#fff8ec' },
  { icon: '✉️', label: '消息总数', value: stats.value.messages || 0, deg: '135deg,#e4f5ed,#f2faf6' },
  { icon: '🏷️', label: '标签数量', value: stats.value.tags || 0, deg: '135deg,#f1ebfe,#faf7ff' },
  { icon: '🧩', label: '文本分块', value: stats.value.chunks || 0, deg: '135deg,#e8f0fc,#f3f8ff' },
])

function dayLabel(i) {
  const d = new Date()
  d.setDate(d.getDate() - (6 - i))
  return (d.getMonth() + 1) + '/' + d.getDate()
}

function buildCharts() {
  charts.forEach((c) => c && c.dispose())
  charts = []
  const textC = textColor()
  const axisC = axisColor()

  // 1. 趋势面积图
  const trend = stats.value.upload_trend_7d || []
  const tChart = echarts.init(trendRef.value)
  tChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 32, right: 16, top: 20, bottom: 28 },
    xAxis: {
      type: 'category',
      data: trend.map((_, i) => dayLabel(i)),
      axisLine: { lineStyle: { color: axisC } },
      axisLabel: { color: textC },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: axisC, type: 'dashed' } },
      axisLabel: { color: textC },
    },
    series: [{
      type: 'line',
      data: trend,
      smooth: true,
      symbol: 'circle',
      symbolSize: 7,
      lineStyle: { width: 3, color: '#4b66f0' },
      itemStyle: { color: '#4b66f0', borderColor: '#fff', borderWidth: 1.5 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(75,102,240,0.28)' },
          { offset: 1, color: 'rgba(75,102,240,0.02)' },
        ]),
      },
    }],
  })
  charts.push(tChart)

  // 2. 解析状态环形图
  const statusData = Object.entries(stats.value.parse_status || {}).map(([k, v]) => ({
    name: { success: '解析成功', failed: '解析失败', partial: '部分解析', pending: '解析中' }[k] || k,
    value: v,
  }))
  const sChart = echarts.init(statusRef.value)
  sChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: textC } },
    color: ['#22a06b', '#d64343', '#e8a23d', '#3d74dd'],
    series: [{
      type: 'pie',
      radius: ['52%', '72%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, formatter: '{b}\n{c}', color: textC, fontSize: 11 },
      data: statusData,
    }],
  })
  charts.push(sChart)

  // 3. 标签条形图
  const tags = (stats.value.top_tags || []).slice(0, 8)
  const tagChart = echarts.init(tagsRef.value)
  tagChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: axisC, type: 'dashed' } },
      axisLabel: { color: textC },
    },
    yAxis: {
      type: 'category',
      data: tags.map((t) => t.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: textC, fontSize: 12 },
    },
    series: [{
      type: 'bar',
      data: tags.map((t) => t.count),
      barWidth: 16,
      itemStyle: {
        borderRadius: [0, 8, 8, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#8ea2ff' },
          { offset: 1, color: '#4b66f0' },
        ]),
      },
    }],
  })
  charts.push(tagChart)
}

async function load() {
  try {
    const r = await fetch('/api/stats/overview')
    stats.value = await r.json()
    await new Promise((resolve) => setTimeout(resolve, 0))
    buildCharts()
  } catch (e) {
    console.error(e)
  }
}

function handleResize() {
  charts.forEach((c) => c && c.resize())
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  charts.forEach((c) => c && c.dispose())
  charts = []
})
</script>

<style scoped>
.dashboard { padding: 28px 32px; max-width: 1280px; margin: 0 auto; }
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow-1);
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-2); }
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
  background: linear-gradient(var(--card-deg));
}
.stat-value { font-size: 26px; font-weight: 700; color: var(--text-1); letter-spacing: -0.02em; }
.stat-label { font-size: 13px; color: var(--text-3); }
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.dashboard-grid .card { padding: 18px 20px; }
.dashboard-grid h3 { margin: 0 0 8px; font-size: 15px; color: var(--text-1); font-weight: 650; }
.chart { width: 100%; height: 240px; }
.chart-card.wide { grid-column: 1 / -1; }
.empty { text-align: center; color: var(--text-3); font-size: 13px; padding: 40px 20px; }
</style>
