<template>
  <div class="page-container">
    <div class="page-header">
      <h1>设置</h1>
      <div class="subtitle">配置 AI 接口、查看备份，修改即时生效无需重启</div>
    </div>

    <div class="card" style="padding: 24px; max-width: 720px;">
      <h3 style="margin-top: 0; font-size: 16px; margin-bottom: 16px;">AI 接口配置</h3>
      <el-form :model="config" label-width="140px" class="settings-form">
        <el-form-item label="API Key">
          <el-input
            v-model="config.apiKey"
            type="password"
            show-password
            :placeholder="config.apiKeySet ? '已配置：' + config.apiKeyMasked + '（留空保持不变）' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="config.baseUrl" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="聊天模型">
          <el-input v-model="config.model" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-form-item label="Embedding 模型">
          <el-input v-model="config.embeddingModel" placeholder="local / text-embedding-3-small" />
          <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">本地 BGE 模型填 <code>local</code>（免费）；API 型填模型名并确保有 Key</div>
        </el-form-item>

        <el-form-item label="预设模板">
          <el-radio-group :model-value="preset" @change="applyPreset">
            <el-radio-button label="deepseek">DeepSeek</el-radio-button>
            <el-radio-button label="openai">OpenAI</el-radio-button>
            <el-radio-button label="qwen">通义千问</el-radio-button>
            <el-radio-button label="custom">自定义</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="saveConfig" :loading="saving">保存并生效</el-button>
          <el-button @click="testConnection" :loading="testing">测试连接</el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <h3 style="font-size: 16px; margin-bottom: 16px;">💾 数据备份</h3>
      <div style="display: flex; gap: 12px; margin-bottom: 12px;">
        <el-button type="primary" plain :icon="Refresh" :loading="backingUp" @click="backupNow">立即备份</el-button>
        <el-button :icon="RefreshRight" :loading="loadingBackups" @click="loadBackups">刷新列表</el-button>
      </div>
      <div v-if="backups.length" class="backup-list">
        <div v-for="b in backups" :key="b.name" class="backup-item">
          <div class="backup-info">
            <div class="backup-name">📦 {{ b.name }}</div>
            <div class="backup-meta">{{ b.created_at }} · {{ formatSize(b.size_bytes) }}</div>
          </div>
          <el-button size="small" type="danger" plain @click="deleteBackup(b)">删除</el-button>
        </div>
      </div>
      <div v-else-if="!loadingBackups" style="color: #94a3b8; font-size: 13px;">暂无备份，点击「立即备份」创建第一份</div>

      <el-divider />

      <h3 style="font-size: 16px; margin-bottom: 16px;">系统信息</h3>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="版本">1.0.0</el-descriptions-item>
        <el-descriptions-item label="向量维度">{{ config.vectorDim || '-' }}</el-descriptions-item>
        <el-descriptions-item label="文件大小限制">{{ formatSize(config.maxFileSize) }}</el-descriptions-item>
        <el-descriptions-item label="支持格式">{{ config.allowedExtensions || '-' }}</el-descriptions-item>
        <el-descriptions-item label="备份保留天数">{{ config.backupKeepDays || '-' }} 天</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, RefreshRight } from '@element-plus/icons-vue'
import { systemApi } from '@/api'

const config = ref({
  apiKey: '',
  apiKeySet: false,
  apiKeyMasked: '',
  baseUrl: 'https://api.deepseek.com',
  model: 'deepseek-v4-flash',
  embeddingModel: 'local',
  vectorDim: 512,
  maxFileSize: 20 * 1024 * 1024,
  allowedExtensions: '',
  backupKeepDays: 7,
})
const preset = ref('custom')

const saving = ref(false)
const testing = ref(false)
const backingUp = ref(false)
const loadingBackups = ref(false)
const backups = ref([])

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadSettings() {
  try {
    const data = await systemApi.getSettings()
    config.value = {
      apiKey: '',
      apiKeySet: data.ai_api_key_set,
      apiKeyMasked: data.ai_api_key_masked,
      baseUrl: data.ai_base_url,
      model: data.ai_model,
      embeddingModel: data.ai_embedding_model,
      vectorDim: data.vector_dim,
      maxFileSize: data.max_file_size,
      allowedExtensions: data.allowed_extensions,
      backupKeepDays: data.backup_keep_days,
    }
    preset.value = detectPreset()
  } catch (e) { /* 后端未启动时静默 */ }
}

function detectPreset() {
  const url = config.value.baseUrl
  if (url.includes('deepseek')) return 'deepseek'
  if (url.includes('openai')) return 'openai'
  if (url.includes('dashscope')) return 'qwen'
  return 'custom'
}

function applyPreset(p) {
  preset.value = p
  const presets = {
    deepseek: {
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-v4-flash',
      embeddingModel: 'local',
    },
    openai: {
      baseUrl: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
      embeddingModel: 'text-embedding-3-small',
    },
    qwen: {
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      model: 'qwen-plus',
      embeddingModel: 'text-embedding-v3',
    },
  }
  if (presets[p]) {
    Object.assign(config.value, presets[p])
    const names = { deepseek: 'DeepSeek', openai: 'OpenAI', qwen: '通义千问' }
    ElMessage.success(`已套用 ${names[p]} 预设`)
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await systemApi.saveSettings({
      ai_base_url: config.value.baseUrl.trim(),
      ai_model: config.value.model.trim(),
      ai_embedding_model: config.value.embeddingModel.trim(),
      ai_api_key: config.value.apiKey ? config.value.apiKey.trim() : null,
    })
    ElMessage.success('配置已保存并即时生效')
    config.value.apiKey = ''
    await loadSettings()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    const data = await systemApi.testLlm()
    if (data.ok) {
      ElMessage.success('✅ AI 连接成功：' + (data.response_preview || '').slice(0, 50))
    } else {
      ElMessage.error('❌ AI 连接失败：' + (data.error || '未知错误'))
    }
  } catch (e) {
    ElMessage.error('无法连接后端，请检查后端是否已启动（http://localhost:8000）')
  } finally {
    testing.value = false
  }
}

async function backupNow() {
  backingUp.value = true
  try {
    const data = await systemApi.backupNow()
    ElMessage.success('备份完成：' + data.path)
    await loadBackups()
  } catch (e) {
    ElMessage.error(e.message || '备份失败')
  } finally {
    backingUp.value = false
  }
}

async function loadBackups() {
  loadingBackups.value = true
  try {
    const data = await systemApi.listBackups()
    backups.value = data.items || []
  } catch (e) {
    ElMessage.error('加载备份列表失败')
  } finally {
    loadingBackups.value = false
  }
}

async function deleteBackup(b) {
  try {
    await systemApi.deleteBackup(b.name)
    ElMessage.success('已删除备份：' + b.name)
    await loadBackups()
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

onMounted(() => {
  loadSettings()
  loadBackups()
})
</script>

<style scoped>
.quick-actions { display: flex; gap: 10px; }
.backup-list { display: flex; flex-direction: column; gap: 8px; }
.backup-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.backup-name { font-size: 13px; font-weight: 600; color: #0f172a; }
.backup-meta { font-size: 12px; color: #64748b; margin-top: 2px; }
</style>
