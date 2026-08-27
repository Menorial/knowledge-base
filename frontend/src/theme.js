// 主题管理：亮色 / 暗色 / 跟随系统
const THEME_KEY = 'kb-theme'

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function getThemeMode() {
  return localStorage.getItem(THEME_KEY) || 'auto'
}

export function applyTheme(mode) {
  const dark = mode === 'dark' || (mode === 'auto' && systemPrefersDark())
  document.documentElement.classList.toggle('dark', dark)
}

export function initTheme() {
  applyTheme(getThemeMode())
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (getThemeMode() === 'auto') {
        document.documentElement.classList.toggle('dark', e.matches)
      }
    })
  }
}

export function setThemeMode(mode) {
  localStorage.setItem(THEME_KEY, mode)
  applyTheme(mode)
}
