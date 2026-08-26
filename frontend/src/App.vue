<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-logo">📚 个人知识库</div>
      <nav class="sidebar-nav">
        <router-link to="/dashboard" class="nav-item"><span class="nav-icon">📊</span><span>仪表盘</span></router-link>
        <router-link to="/documents" class="nav-item"><span class="nav-icon">📄</span><span>文档管理</span></router-link>
        <router-link to="/chat" class="nav-item"><span class="nav-icon">💬</span><span>AI 对话</span></router-link>
        <router-link to="/search" class="nav-item"><span class="nav-icon">🔍</span><span>全文搜索</span></router-link>
        <router-link to="/trash" class="nav-item"><span class="nav-icon">🗑️</span><span>回收站</span></router-link>
        <router-link to="/graph" class="nav-item"><span class="nav-icon">🕸️</span><span>知识图谱</span></router-link>
        <router-link to="/settings" class="nav-item"><span class="nav-icon">⚙️</span><span>设置</span></router-link>
      </nav>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: #f8fafc;
}
.sidebar {
  width: 200px; background: #fff; border-right: 1px solid #e2e8f0;
  display: flex; flex-direction: column; flex-shrink: 0;
}
.sidebar-logo {
  padding: 20px 16px; font-size: 15px; font-weight: 700; color: #0f172a;
  border-bottom: 1px solid #f1f5f9;
}
.sidebar-nav { padding: 12px 8px; display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  color: #475569; text-decoration: none; font-size: 14px;
  border-radius: 8px; transition: all 0.15s;
}
.nav-item:hover { background: #f1f5f9; color: #0f172a; }
.nav-item.router-link-active {
  background: linear-gradient(135deg, #eff6ff, #e0e7ff);
  color: #1e40af; font-weight: 500;
}
.nav-icon { font-size: 16px; }
.main-content {
  flex: 1; overflow-y: auto; background: #f8fafc;
}
</style>
