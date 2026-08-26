<template>
  <div class="page-container">
    <div class="page-header">
      <h1>设置</h1>
      <div class="subtitle">配置 AI 接口和知识库选项</div>
    </div>

    <div class="card" style="padding: 24px; max-width: 720px;">
      <h3 style="margin-top: 0; font-size: 16px; margin-bottom: 16px;">AI 接口配置</h3>
      <el-form :model="config" label-width="140px" class="settings-form">
        <el-form-item label="API Key">
          <el-input v-model="config.apiKey" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="config.baseUrl" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="聊天模型">
          <el-input v-model="config.model" placeholder="gpt-4o-mini" />
        </el-form-item>
        <el-form-item label="Embedding 模型">
          <el-input v-model="config.embeddingModel" placeholder="text-embedding-3-small" />
        </el-form-item>

        <el-form-item label="预设模板">
          <el-radio-group @change="applyPreset">
            <el-radio-button label="openai">OpenAI</el-radio-button>
            <el-radio-button label="qwen">通义千问</el-radio-button>
            <el-radio-button label="deepseek">DeepSeek</el-radio-button>
            <el-radio-button label="custom">自定义</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="saveConfig" :loading="saving">保存配置</el-button>
          <el-button @click="testConnection" :loading="testing">测试连接</el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <h3 style="font-size: 16px; margin-bottom: 16px;">系统信息</h3>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="版本">1.0.0</el-descriptions-item>
        <el-descriptions-item label="前端地址">http://localhost:5173</el-descriptions-item>
        <el-descriptions-item label="后端地址">http://localhost:8000</el-descriptions-item>
        <el-descriptions-item label="支持格式">Markdown / PDF / Word / TXT / HTML</el-descriptions-item>
      </el-descriptions>

      <el-divider />

      <h3 style="font-size: 16px; margin-bottom: 16px;">🛠️ 快捷操作</h3>
      <div class="quick-actions">
        <el-button @click="go('/dashboard')">📊 仪表盘</el-button>
        <el-button @click="go('/search')">🔍 全文搜索</el-button>
        <el-button @click="go('/chat')">💬 开始对话</el-button>
      </div>
    </div>

    <div style="margin-top: 16px; padding: 16px; background: #fef3c7; border-radius: 8px; font-size: 13px; color: #92400e;">
      <strong>提示：</strong> 修改 AI 配置需要在后端目录的 <code>.env</code> 文件中进行，修改后重启后端服务生效。<br/>
      后端支持 OpenAI 兼容接口，通义千问、DeepSeek 等国产模型均可使用。
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()
function go(path) { router.push(path) }

const config = ref({
  apiKey: '',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  embeddingModel: 'text-embedding-3-small',
  preset: 'custom',
})

const saving = ref(false)
const testing = ref(false)

function applyPreset(preset) {
  const presets = {
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
    deepseek: {
      baseUrl: 'https://api.deepseek.com',
      model: 'deepseek-v4-flash',
      embeddingModel: 'local (BGE-small)',
    },
  }
  if (presets[preset]) {
    Object.assign(config.value, presets[preset])
    ElMessage.success(`已切换到 ${preset === 'openai' ? 'OpenAI' : preset === 'qwen' ? '通义千问' : 'DeepSeek'} 预设`)
  }
}

function saveConfig() {
  ElMessage.info('请在后端 .env 文件中配置 API Key 和模型参数，然后重启后端服务')
}

async function testConnection() {
  testing.value = true
  try {
    const r = await fetch('/api/stats/test-llm', { method: 'POST' })
    const data = await r.json()
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
</script>

<style scoped>
.quick-actions { display: flex; gap: 10px; }
</style>
