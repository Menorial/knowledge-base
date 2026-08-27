<template>
  <div class="page-container graph-page">
    <div class="page-header">
      <h1>🕸️ 知识图谱</h1>
      <div class="subtitle">文档关联网络 —— 正文提到其他文档标题自动连接，或写 [[标题]] 显式指定</div>
      <div v-if="loaded" class="graph-stats">
        <span>📄 {{ nodes.length }} 篇文档</span>
        <span>🔗 {{ edges.length }} 条连接</span>
        <span v-if="isolated > 0">🧊 {{ isolated }} 篇孤立</span>
      </div>
    </div>

    <div class="graph-card" ref="cardRef">
      <div v-if="!loaded" class="graph-empty">加载中...</div>
      <div v-else-if="nodes.length === 0" class="graph-empty">还没有文档，先去「文档管理」上传吧</div>
      <div v-else-if="edges.length === 0" class="graph-empty">
        <div style="font-size: 44px; margin-bottom: 12px;">🕸️</div>
        <div>还没有连接 —— 在文档正文中提及另一篇文档的标题，或写 <code>[[文档标题]]</code>，保存后就会自动建立关联</div>
      </div>
      <svg v-else ref="svgRef" class="graph-svg" :viewBox="`0 0 ${W} ${H}`" @click="svgClick">
        <g ref="zoomRef"></g>
      </svg>
      <div v-if="loaded && nodes.length" class="graph-legend">
        <span><i class="dot auto"></i>自动链接</span>
        <span><i class="dot syntax"></i>[[语法]] 链接</span>
        <span class="legend-hint">拖拽节点移动 · 滚轮缩放 · 空白处拖动平移 · 点击节点打开文档</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { drag } from 'd3-drag'
import { zoom, zoomIdentity } from 'd3-zoom'
import { select } from 'd3-selection'
import { linksApi } from '@/api'

const W = 1200
const H = 720

const router = useRouter()
const cardRef = ref(null)
const svgRef = ref(null)
const zoomRef = ref(null)

const nodes = ref([])
const edges = ref([])
const loaded = ref(false)
const isolated = ref(0)

let simulation = null

onMounted(async () => {
  try {
    const data = await linksApi.graph()
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    const degree = new Map()
    edges.value.forEach((e) => {
      degree.set(e.source, (degree.get(e.source) || 0) + 1)
      degree.set(e.target, (degree.get(e.target) || 0) + 1)
    })
    isolated.value = nodes.value.filter((n) => !degree.has(n.id)).length
    if (nodes.value.length && edges.value.length) {
      buildGraph()
    }
  } catch (e) {
    // 后端未就绪时静默
  } finally {
    loaded.value = true
  }
})

onBeforeUnmount(() => {
  if (simulation) simulation.stop()
})

function buildGraph() {
  const svg = select(svgRef.value)
  const g = select(zoomRef.value)

  const edgeColor = (source) => (source === 'syntax' ? 'var(--green)' : 'var(--blue)')

  // 节点数据：id、标题、度数（决定半径）
  const degree = new Map()
  edges.value.forEach((e) => {
    degree.set(e.source, (degree.get(e.source) || 0) + 1)
    degree.set(e.target, (degree.get(e.target) || 0) + 1)
  })
  const nodeData = nodes.value.map((n) => ({
    id: n.id,
    title: n.title,
    degree: degree.get(n.id) || 0,
  }))
  const edgeData = edges.value.map((e) => ({
    source: typeof e.source === 'object' ? e.source.id : e.source,
    target: typeof e.target === 'object' ? e.target.id : e.target,
    sourceType: e.sourceType || 'auto',
  }))

  // 边
  const line = g
    .append('g')
    .attr('class', 'links')
    .selectAll('line')
    .data(edgeData)
    .join('line')
    .attr('stroke', (d) => edgeColor(d.sourceType))
    .attr('stroke-width', 1.2)
    .attr('stroke-opacity', 0.7)

  // 节点组：圆 + 标签
  const node = g
    .append('g')
    .attr('class', 'nodes')
    .selectAll('g')
    .data(nodeData)
    .join('g')
    .attr('class', 'graph-node')
    .call(
      drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.25).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      router.push({ path: '/documents', query: { open: d.id } })
    })
    .on('dblclick', (event, d) => {
      event.stopPropagation()
    })

  node
    .append('circle')
    .attr('r', (d) => 14 + Math.min(10, d.degree * 2))
    .attr('fill', (d) => (d.degree > 0 ? 'var(--accent)' : 'var(--border-strong)'))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)

  node
    .append('text')
    .attr('dy', (d) => 28 + Math.min(10, d.degree * 2))
    .attr('text-anchor', 'middle')
    .attr('class', 'node-label')
    .text((d) => (d.title.length > 14 ? d.title.slice(0, 13) + '…' : d.title))

  // 悬停提示
  node
    .append('title')
    .text((d) => `${d.title}\n连接数：${d.degree}`)

  // 力导向模拟
  simulation = forceSimulation(nodeData)
    .force(
      'link',
      forceLink(edgeData).id((d) => d.id).distance(110).strength(0.6)
    )
    .force('charge', forceManyBody().strength(-320))
    .force('center', forceCenter(W / 2, H / 2))
    .force('collide', forceCollide(40))
    .on('tick', () => {
      line
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)
      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

  // 缩放 + 平移
  const zoomBehavior = zoom()
    .scaleExtent([0.3, 3])
    .on('zoom', (event) => {
      g.attr('transform', event.transform)
    })
  svg.call(zoomBehavior)

  // 空白处点击清除节点选中态（暂无选中逻辑，仅占位防冒泡）
  svg.on('click', () => {})
}

function svgClick() {
  // 点击空白处不做跳转（节点点击已 stopPropagation）
}
</script>

<style scoped>
.graph-page { padding: 24px; }
.graph-stats { display: flex; gap: 16px; margin-top: 8px; font-size: 13px; color: var(--text-2); }
.graph-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  height: calc(100vh - 170px);
  min-height: 480px;
  overflow: hidden;
}
.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
}
.graph-svg:active { cursor: grabbing; }
.graph-node { cursor: pointer; }
.node-label {
  font-size: 11px;
  fill: var(--text-2);
  pointer-events: none;
  user-select: none;
}
.graph-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 14px;
  padding: 40px;
  text-align: center;
  gap: 8px;
}
.graph-empty code {
  background: var(--bg-hover);
  padding: 1px 6px;
  border-radius: 4px;
}
.graph-legend {
  position: absolute;
  left: 14px;
  bottom: 12px;
  display: flex;
  gap: 14px;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--text-2);
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.dot.auto { background: var(--blue); }
.dot.syntax { background: var(--green); }
.legend-hint { color: var(--text-3); }
</style>
