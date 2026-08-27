<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-logo">
        <span class="logo-icon">📚</span>
        <div class="logo-text">
          <div class="logo-title">个人知识库</div>
          <div class="logo-sub">Knowledge Base</div>
        </div>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/dashboard" class="nav-item"><span class="nav-icon">📊</span><span>仪表盘</span></router-link>
        <router-link to="/documents" class="nav-item"><span class="nav-icon">📄</span><span>文档管理</span></router-link>
        <router-link to="/chat" class="nav-item"><span class="nav-icon">💬</span><span>AI 对话</span></router-link>
        <router-link to="/search" class="nav-item"><span class="nav-icon">🔍</span><span>全文搜索</span></router-link>
        <router-link to="/graph" class="nav-item"><span class="nav-icon">🕸️</span><span>知识图谱</span></router-link>
        <router-link to="/trash" class="nav-item"><span class="nav-icon">🗑️</span><span>回收站</span></router-link>
        <router-link to="/settings" class="nav-item"><span class="nav-icon">⚙️</span><span>设置</span></router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="theme-btn" :title="'当前模式：' + themeLabel" @click="cycleTheme">
          <span class="theme-icon">{{ themeIcon }}</span>
          <span>{{ themeLabel }}</span>
        </button>
      </div>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { getThemeMode, setThemeMode } from './theme'

const mode = ref(getThemeMode())

const THEMES = ['light', 'dark', 'auto']
const LABELS = { light: '亮色', dark: '暗色', auto: '跟随系统' }
const ICONS = { light: '☀️', dark: '🌙', auto: '🖥️' }

const themeLabel = computed(() => LABELS[mode.value] || '跟随系统')
const themeIcon = computed(() => ICONS[mode.value] || '🖥️')

function cycleTheme() {
  const idx = THEMES.indexOf(mode.value) === -1 ? 0 : THEMES.indexOf(mode.value)
  mode.value = THEMES[(idx + 1) % THEMES.length]
  setThemeMode(mode.value)
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: var(--bg-page);
}
.sidebar {
  width: 216px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: background-color 0.25s ease;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 18px 18px;
  border-bottom: 1px solid var(--border);
}
.logo-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--accent-weak);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.logo-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: 0.01em;
}
.logo-sub {
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-top: 2px;
}
.sidebar-nav {
  flex: 1;
  padding: 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  color: var(--text-2);
  text-decoration: none;
  font-size: 13.5px;
  border-radius: var(--radius-sm);
  transition: all 0.15s;
  position: relative;
}
.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-1);
}
.nav-item.router-link-active {
  background: var(--accent-weak);
  color: var(--accent-text);
  font-weight: 600;
}
.nav-item.router-link-active::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 20%;
  height: 60%;
  width: 3px;
  border-radius: 2px;
  background: var(--accent);
}
.nav-icon { font-size: 15px; width: 20px; text-align: center; }
.sidebar-footer {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}
.theme-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.15s;
}
.theme-btn:hover {
  border-color: var(--accent);
  color: var(--accent-text);
  background: var(--accent-weak);
}
.theme-icon { font-size: 14px; }
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-page);
  transition: background-color 0.25s ease;
}
</style>
