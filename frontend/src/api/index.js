import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export const documentsApi = {
  upload: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request.post('/documents/upload', fd)
  },
  list: (params) => request.get('/documents', { params }),
  get: (id) => request.get(`/documents/${id}`),
  preview: (id) => request.get(`/documents/${id}/preview`),
  update: (id, data) => request.put(`/documents/${id}`, data),
  delete: (id) => request.delete(`/documents/${id}`),
  batchDelete: (ids) => request.post('/documents/batch-delete', { ids }),
  restore: (id) => request.post(`/documents/${id}/restore`),
  reparse: (id) => request.post(`/documents/${id}/reparse`),
  reindex: (id) => request.post(`/documents/${id}/reindex`),
  reindexAll: () => request.post('/documents/reindex-all'),
  createText: (data) => request.post('/documents/create-text', data),
  clip: (data) => request.post('/documents/clip', data),
  versions: (id) => request.get(`/documents/${id}/versions`),
  version: (id, versionId) => request.get(`/documents/${id}/versions/${versionId}`),
  restoreVersion: (id, versionId) => request.post(`/documents/${id}/versions/${versionId}/restore`),
  rawUrl: (id) => `/api/documents/${id}/raw`,
}

export const trashApi = {
  list: () => request.get('/trash'),
  restore: (id) => request.post(`/trash/${id}/restore`),
  purge: (id) => request.delete(`/trash/${id}`),
}

export const searchApi = {
  fulltext: (q, page = 1, page_size = 20) =>
    request.get('/search', { params: { q, page, page_size } }),
}

export const tagsApi = {
  list: () => request.get('/tags'),
  create: (data) => request.post('/tags', data),
  update: (id, data) => request.put(`/tags/${id}`, data),
  delete: (id) => request.delete(`/tags/${id}`),
  addToDoc: (docId, tagNames) => request.post(`/tags/document/${docId}`, tagNames),
  removeFromDoc: (docId, tagId) => request.delete(`/tags/document/${docId}/${tagId}`),
}

export const chatApi = {
  listConversations: () => request.get('/conversations'),
  createConversation: (data) => request.post('/conversations', data),
  getConversation: (id) => request.get(`/conversations/${id}`),
  deleteConversation: (id) => request.delete(`/conversations/${id}`),
  updateConversation: (id, data) => request.put(`/conversations/${id}`, data),
  regenerate: (convId, msgId) =>
    request.post(`/conversations/${convId}/regenerate/${msgId}`),
  exportUrl: (convId) => `/api/conversations/${convId}/export`,
}

export const systemApi = {
  getSettings: () => request.get('/settings'),
  saveSettings: (data) => request.put('/settings', data),
  backupNow: () => request.post('/backup'),
  listBackups: () => request.get('/backups'),
  deleteBackup: (name) => request.delete(`/backups/${encodeURIComponent(name)}`),
  testLlm: () => request.post('/stats/test-llm'),
}

export const linksApi = {
  docLinks: (id) => request.get(`/documents/${id}/links`),
  graph: () => request.get('/graph'),
}
