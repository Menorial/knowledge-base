# 📚 个人知识库

一个面向个人的本地知识库系统，支持文档存储、双版本管理、AI 调用文档问答和 RAG 跨库检索。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📥 文档上传 | 支持 Markdown / PDF / Word / TXT / HTML，拖拽上传 |
| 💾 双版本存储 | 原始文件保留保真 + Markdown 版本供 AI/搜索使用 |
| 🔍 全文搜索 | SQLite FTS5，支持中文，结果高亮 |
| 🤖 AI 对话 | 指定文档问答 + 知识库 RAG 跨库检索 |
| 💬 流式输出 | SSE 逐字返回，体验丝滑 |
| 🏷️ 标签管理 | 多标签分类 |
| 📝 手动编辑 | 解析错了？直接手动修正 Markdown |
| 🔄 版本历史 | 每次修改自动存档，可回退 |
| 🗑️ 软删除 | 误删能恢复 |
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
# OpenAI
AI_API_KEY=sk-xxx
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIM=1536

# 通义千问
# AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# AI_MODEL=qwen-plus
# AI_EMBEDDING_MODEL=text-embedding-v3
# VECTOR_DIM=1024

# DeepSeek
# AI_BASE_URL=https://api.deepseek.com/v1
# AI_MODEL=deepseek-chat
# AI_EMBEDDING_MODEL=deepseek-embedding
# VECTOR_DIM=1024
```

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
# 终端 1 — 后端
cd 知识库; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2 — 前端
cd 知识库\frontend; npm run dev
```

## 📁 项目结构

```
知识库/
├── backend/                    # Python 后端
│   ├── main.py                # FastAPI 入口
│   ├── config.py              # 配置读取
│   ├── requirements.txt
│   ├── api/                   # API 路由
│   │   ├── documents.py       # 文档 CRUD
│   │   ├── search.py          # 全文搜索
│   │   ├── chat.py            # AI 对话（SSE 流式）
│   │   └── tags.py            # 标签管理
│   ├── services/              # 业务服务
│   │   ├── parser.py          # 文档解析（插件式）
│   │   ├── chunker.py         # 语义切片
│   │   ├── embedding.py       # Embedding 向量化
│   │   ├── llm.py             # LLM 流式调用
│   │   └── rag.py             # RAG 检索 + Prompt 组装
│   ├── db/                    # 数据层
│   │   ├── database.py        # SQLAlchemy + sqlite-vec
│   │   ├── models.py          # ORM 模型
│   │   └── schemas.py         # Pydantic Schema
│   └── utils/                 # 工具函数
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/             # 页面组件
│   │   ├── components/        # 可复用组件
│   │   ├── api/               # 后端接口封装
│   │   └── stores/            # Pinia 状态管理
│   └── vite.config.js
├── data/                       # 运行时数据（自动创建）
│   ├── knowledge.db           # SQLite 数据库
│   └── files/                 # 原始文件存储
├── backup/                     # 自动备份目录
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
| AI API 未配置 | 上传和搜索正常，AI 对话会提示配置 API Key |
| PDF 是扫描件 | 无法提取文本，解析状态会标记为 `partial` 或 `failed` |
| sqlite-vec 扩展 | Windows 下首次加载需要 sqlite-vec 扩展文件，已随包安装 |
| 数据备份 | 整个 `data/` 文件夹（knowledge.db + files）复制走即可 |
| 文件大小限制 | 默认 20MB，在 `.env` 中修改 `MAX_FILE_SIZE` |

## 🛣️ 迭代路线

```
✅ 第一阶段：能存能看
   └─ 文档上传 → 解析 → 存储 → 列表 → 预览 → 删除

🚧 第二阶段：能问（AI 能力）
   ├─ 向量化 + sqlite-vec 检索
   ├─ 指定文档 AI 问答（SSE 流式）
   ├─ RAG 跨库语义问答
   └─ 多轮对话 + 会话管理

📋 第三阶段：好用
   ├─ 全文搜索高亮
   ├─ 标签系统
   ├─ 版本历史 + 手动编辑
   ├─ 自动备份
   ├─ AI 自动摘要
   └─ 网页剪藏扩展
```

## 📄 License

MIT
