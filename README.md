# 📚 个人知识库

一个面向个人的本地知识库系统，支持文档存储、双版本管理、AI 调用文档问答和 RAG 跨库检索。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📥 文档上传 | 支持 Markdown / PDF / Word / TXT / HTML，拖拽上传 |
| 💾 双版本存储 | 原始文件保留保真 + Markdown 版本供 AI/搜索使用 |
| 🔍 全文搜索 | SQLite FTS5 trigram 分词，中文子串匹配 + 结果高亮 |
| 🤖 AI 对话 | 指定文档问答 + 知识库 RAG 跨库检索 |
| 💬 流式输出 | SSE 逐字返回，体验丝滑 |
| 🏷️ 标签管理 | 多标签分类 |
| 📝 手动编辑 | 解析错了？直接手动修正 Markdown |
| 🔄 版本历史 | 每次修改自动存档，可预览、可回滚 |
| 🗑️ 回收站 | 软删除 + 恢复 + 彻底清除 |
| 📝 AI 自动摘要 | 上传后后台自动生成文档摘要 |
| 💾 自动备份 | 启动时自动备份数据库+文件，保留 N 天，可手动触发 |
| ⚙️ 设置热更新 | 在网页改 AI 配置即时生效，无需重启 |
| 🔌 多模型兼容 | OpenAI / 通义千问 / DeepSeek 等 |

## 🛠️ 技术栈

- **后端**：Python 3.11+ / FastAPI / SQLAlchemy / SQLite + FTS5 + sqlite-vec
- **前端**：Vue 3 / Vite / Element Plus / markdown-it
- **AI**：OpenAI 兼容接口（GPT / 通义 / DeepSeek）

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+

### 第一步：克隆项目

```bash
git clone <your-repo>
cd 知识库
```

### 第二步：配置 AI 接口

```bash
# 复制模板
cp .env.example .env

# 编辑 .env，填入你的 API Key
```

```env
# DeepSeek（推荐，Embedding 用本地 BGE 模型，免费）
AI_API_KEY=sk-xxx
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-v4-flash
AI_EMBEDDING_MODEL=local   # 本地 BGE-small 模型，无需 API Key
VECTOR_DIM=512

# OpenAI
# AI_BASE_URL=https://api.openai.com/v1
# AI_MODEL=gpt-4o-mini
# AI_EMBEDDING_MODEL=text-embedding-3-small
# VECTOR_DIM=1536

# 通义千问
# AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# AI_MODEL=qwen-plus
# AI_EMBEDDING_MODEL=text-embedding-v3
# VECTOR_DIM=1024
```

> 💡 配置也可以在网页「设置」页修改，保存后即时生效，无需重启后端。

### 第三步：启动后端

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

后端启动后自动创建数据库，访问 `http://localhost:8000/docs` 查看 API 文档。

### 第四步：启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用。

### 一键启动（Windows PowerShell）

```powershell
# 首次使用（自动建 venv + 装依赖 + 启动前后端）
.\start.ps1

# 之后日常启动
.\start.ps1 -SkipInstall
```

也可以手动分两个终端启动：

```powershell
# 终端 1 — 后端
cd 知识库; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — 前端
cd 知识库\frontend; npm run dev
```

## 📁 项目结构

```
知识库/
├── backend/                    # Python 后端
│   ├── main.py                # FastAPI 入口（含启动自动备份）
│   ├── config.py              # 配置读取
│   ├── requirements.txt
│   ├── api/                   # API 路由
│   │   ├── documents.py       # 文档 CRUD + 版本历史
│   │   ├── search.py          # 全文搜索（FTS5 trigram）
│   │   ├── chat.py            # AI 对话（SSE 流式）
│   │   ├── tags.py            # 标签管理
│   │   ├── trash.py           # 回收站
│   │   ├── system.py          # 设置读写 + 备份管理
│   │   └── stats.py           # 统计概览
│   ├── services/              # 业务服务
│   │   ├── parser.py          # 文档解析（插件式）
│   │   ├── chunker.py         # 语义切片
│   │   ├── embedding.py       # Embedding 向量化（本地 BGE/API）
│   │   ├── llm.py             # LLM 流式调用（支持热更新）
│   │   ├── rag.py             # RAG 检索 + Prompt 组装
│   │   └── backup.py          # 自动备份
│   ├── db/                    # 数据层
│   │   ├── database.py        # SQLAlchemy + sqlite-vec + FTS5
│   │   ├── models.py          # ORM 模型
│   │   └── schemas.py         # Pydantic Schema
│   └── utils/                 # 工具函数
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/             # 页面组件（含 Trash 回收站）
│   │   ├── components/        # 可复用组件
│   │   ├── api/               # 后端接口封装
│   │   └── stores/            # Pinia 状态管理
│   └── vite.config.js
├── data/                       # 运行时数据（自动创建）
│   ├── knowledge.db           # SQLite 数据库
│   └── files/                 # 原始文件存储
├── backup/                     # 自动备份目录（启动时自动生成）
├── .env                        # AI 配置（不提交到 git）
├── .env.example                # 配置模板
├── .gitignore
├── DESIGN.md                   # 完整设计文档
└── README.md
```

## 🔌 API 速查

### 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/documents/upload` | 上传文档（multipart/form-data） |
| GET | `/api/documents?page=1&page_size=20` | 文档列表 |
| GET | `/api/documents/{id}` | 文档详情 |
| GET | `/api/documents/{id}/preview` | Markdown 预览内容 |
| GET | `/api/documents/{id}/raw` | 下载原始文件 |
| PUT | `/api/documents/{id}` | 更新文档（标题/Markdown） |
| DELETE | `/api/documents/{id}` | 软删除 |
| POST | `/api/documents/{id}/restore` | 恢复已删除 |
| POST | `/api/documents/{id}/reparse` | 重新解析 |
| POST | `/api/documents/{id}/reindex` | 重建向量索引 |
| POST | `/api/documents/reindex-all` | 批量重建全部索引 |
| POST | `/api/documents/create-text` | 在线新建 Markdown 文档 |
| GET | `/api/documents/{id}/versions` | 版本历史列表 |
| GET | `/api/documents/{id}/versions/{vid}` | 版本内容 |
| POST | `/api/documents/{id}/versions/{vid}/restore` | 回滚到某版本 |

### 回收站

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/trash` | 已删除文档列表 |
| POST | `/api/trash/{id}/restore` | 恢复文档 |
| DELETE | `/api/trash/{id}` | 彻底删除（含原始文件） |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 读取当前配置（API Key 打码） |
| PUT | `/api/settings` | 保存配置到 .env 并热生效 |
| POST | `/api/backup` | 立即备份 |
| GET | `/api/backups` | 备份列表 |
| DELETE | `/api/backups/{name}` | 删除备份 |
| POST | `/api/stats/test-llm` | 测试 AI 连接 |

### 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search?q=xxx` | 全文搜索（FTS5 + 高亮） |

### AI 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 新建会话 |
| POST | `/api/chat/stream` | 指定文档对话（SSE 流式） |
| POST | `/api/chat/rag` | RAG 知识库问答（SSE 流式） |

### 健康检查

```
GET /api/health → {"status": "ok", "version": "1.0.0"}
```

## 🧪 快速测试（Python）

```python
import httpx

# 上传文档
with open("test.md", "rb") as f:
    r = httpx.post(
        "http://localhost:8000/api/documents/upload",
        files={"file": ("test.md", f, "text/markdown")},
    )
print(r.json())

# 列出文档
r = httpx.get("http://localhost:8000/api/documents")
print(r.json())
```

## ⚠️ 注意事项

| 项目 | 说明 |
|------|------|
| AI API 未配置 | 上传、搜索、备份正常；AI 对话会提示配置 API Key |
| Embedding 未就绪 | 本地 BGE 模型首次使用需联网下载（约 100MB），可设置 `HF_ENDPOINT=https://hf-mirror.com` 加速，或使用 modelscope 缓存 |
| PDF 是扫描件 | 无法提取文本，解析状态会标记为 `partial` 或 `failed` |
| sqlite-vec 扩展 | Windows 下首次加载需要 sqlite-vec 扩展文件，已随包安装 |
| FTS 中文搜索 | 使用 FTS5 trigram 分词器（SQLite ≥ 3.34），支持中文子串匹配；启动时自动迁移旧索引 |
| 数据备份 | 启动时自动备份到 `backup/`，保留 `BACKUP_KEEP_DAYS` 天；也可在设置页手动备份 |
| 文件大小限制 | 默认 20MB，在 `.env` 中修改 `MAX_FILE_SIZE` |

## 🛣️ 迭代路线

```
✅ 第一阶段：能存能看
   └─ 文档上传 → 解析 → 存储 → 列表 → 预览 → 删除

✅ 第二阶段：能问（AI 能力）
   ├─ 向量化 + sqlite-vec 检索
   ├─ 指定文档 AI 问答（SSE 流式）
   ├─ RAG 跨库语义问答
   └─ 多轮对话 + 会话管理

✅ 第三阶段：好用
   ├─ 全文搜索高亮（trigram 中文子串匹配）
   ├─ 标签系统
   ├─ 版本历史 + 回滚
   ├─ 回收站（恢复/彻底删除）
   ├─ 自动备份（启动 + 手动，保留 N 天）
   ├─ AI 自动摘要
   └─ 设置热更新（网页改配置即时生效）

📋 后续规划
   ├─ 网页剪藏扩展
   ├─ 文档间双向链接/图谱
   ├─ 全文搜索 + 向量检索混合排序
   └─ 移动端适配
```

## 📄 License

MIT
