// 标签自动配色：按标签名哈希稳定取色（同一标签全站颜色一致，亮暗模式自适应）
const TAG_COUNT = 8

function hashCode(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

/**
 * 返回标签的配色样式对象：{ background, color }
 * 使用 CSS 变量，暗色模式下自动切换对应变体
 */
export function tagStyle(name) {
  const idx = hashCode(String(name || '')) % TAG_COUNT
  return {
    background: `var(--tag-${idx}-bg)`,
    color: `var(--tag-${idx}-fg)`,
  }
}
