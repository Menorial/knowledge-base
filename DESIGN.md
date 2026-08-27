# 个人知识库系统 — 功能与架构设计文档

> 版本：v1.0  
> 日期：2026-08-06

---

## 一、项目概述

### 1.1 项目定位

一个面向个人的本地知识库系统，核心能力：

- **文档存储**：支持 Markdown / PDF / Word 等格式，双版本存储（原始文件 + Markdown 文本）
- **AI 调用文档**：AI 能读取指定文档做总结/分析
- **AI 跨库问答（RAG）**：基于知识库内容的语义检索与问答
- **全文搜索**：基于 SQLite FTS5 的轻量级全文检索

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **简单优先** | 零运维，单文件数据库，一个文件夹搞定 |
| **本地优先** | 数据全部存本地，不依赖云服务 |
| **安全底线** | API Key 不入代码，上传有校验，数据软删除 |
| **双版本存储** | 原始文件保真展示，Markdown 版本供 AI 和搜索 |
| **异步处理** | 解析/向量化不阻塞上传接口 |

### 1.3 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 后端 | Python 3.11+ / FastAPI | AI 生态最完善 |
| 前端 | Vue 3 + Vite | SPA，纯本地运行 |
| 关系数据库 | SQLite 3 | 文档元数据、对话、标签 |
| 向量数据库 | sqlite-vec | RAG 语义检索，与主库同文件 |
| 全文检索 | SQLite FTS5 | 中文支持 |
| AI 接口 | OpenAI 兼容 API | GPT / 通义 / DeepSeek 均可 |
| 文档解析 | python-docx + PyMuPDF + html2text | 按格式选解析器 |
| Markdown 渲染 | 前端 markdown-it | 实时预览 |

---

## 二、功能设计

### 2.1 功能清单

#### P0 — 核心必做

| 编号 | 功能 | 说明 |
|------|------|------|
| F01 | 文档上传 | 支持拖拽/点击上传，校验类型和大小（≤20MB） |
| F02 | 文档解析 | 自动提取文本，按格式转 Markdown |
| F03 | 双版本存储 | 原始文件存磁盘，Markdown 存数据库 |
| F04 | 文档列表 | 标题/时间/类型筛选，分页展示 |
| F05 | 文档查看 | 原始文件预览（PDF.js / Word 转图）+ Markdown 预览 |
| F06 | 全文搜索 | SQLite FTS5，标题 + 内容 + 标签，结果高亮 |
| F07 | 指定文档 AI 对话 | 用户选中文档，AI 读取内容做总结/问答 |
| F08 | 知识库 AI 问答（RAG） | 用户提问，AI 跨库检索相关片段回答，带引用来源 |
| F09 | 流式输出 | AI 回答 SSE 流式返回 |
| F10 | 软删除 | 标记删除，30 天后自动清理 |

#### P1 — 重要增强

| 编号 | 功能 | 说明 |
|------|------|------|
| F11 | 标签管理 | 多标签、标签树、按标签筛选 |
| F12 | 多轮对话 | 对话历史按会话保存，支持上下文连续问答 |
| F13 | 对话新建/切换 | 创建多个对话，按文档或主题分类 |
| F14 | 文档版本历史 | 每次编辑自动存版本，可查看和回退 |
| F15 | 手动编辑 Markdown | 修正解析错误的文档内容 |
| F16 | 自动备份 | 每天定时备份 SQLite + files 目录 |
| F17 | 异步解析 | 上传立即返回，后台处理解析+向量化 |

#### P2 — 锦上添花

| 编号 | 功能 | 说明 |
|------|------|------|
| F18 | 文档自动摘要 | AI 自动为新文档生成摘要 |
| F19 | 知识图谱 | 可视化文档间关联 |
| F20 | 统计面板 | 文档数、标签云、活跃时间段 |
| F21 | 网页剪藏 | 浏览器扩展一键保存网页 |
| F22 | 快捷键 | 全局搜索、新建文档快捷键 |

### 2.2 功能交互流程

#### 流程一：文档上传与入库

```
用户上传文件
    │
    ├── 校验：类型白名单 + 大小 ≤20MB
    ├── 重命名：uuid + 扩展名（防路径穿越）
    ├── 存原始文件 → data/files/uuid.pdf
    ├── 写入数据库：status=processing
    │
    └── 后台异步任务：
         │
         ├── 解析器 → Markdown 文本
         │    ├── PDF  → PyMuPDF
         │    ├── Word → python-docx
         │    ├── HTML → html2text
         │    └── MD   → 直接存
         │
         ├── 更新 content_md + parse_status
         ├── 语义切片（按标题/段落，重叠1-2句）
         ├── 调用 Embedding API 生成向量
         ├── 向量存入 sqlite-vec
         └── 更新 status=ready
```

#### 流程二：RAG 知识库问答

```
用户输入问题
    │
    ├── 可选：指定某篇文档 → 跳过检索直接用该文档
    │
    ├── Embedding API → 问题向量
    ├── sqlite-vec 相似度检索 → top-5 相关片段
    │
    ├── 组装 Prompt：
    │    System: 你是知识库助手，基于提供的文档内容回答...
    │    Context: 文档A片段1 + 文档B片段2 + ...
    │    Question: 用户问题
    │    Rule: 回答末尾标注引用来源 [来源：xxx]
    │
    ├── 调用 LLM（SSE 流式）
    ├── 逐 chunk 返回给前端
    └── 保存对话历史
```

#### 流程三：指定文档 AI 对话

```
用户选中文档 + 输入问题
    │
    ├── 取文档 content_md（Markdown 版本）
    ├── 若文档过长 → 切片 + 检索相关片段（同 RAG）
    ├── 组装 Prompt（加上文档标题）
    ├── 调用 LLM（SSE 流式）
    └── 保存对话历史（关联 document_id）
```

---

## 三、架构设计

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                      前端 Web (Vue 3)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ 文档管理  │  │ 全文搜索  │  │ AI 对话   │  │ 设置/备份  │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬─────┘ │
└────────┼────────────┼────────────┼───────────────┼───────┘
         │ HTTP / SSE │            │               │
┌────────┴────────────┴────────────┴───────────────┴───────┐
│                     后端 API (FastAPI)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐│
│  │ 文档路由      │  │ 搜索路由      │  │ 对话路由          ││
│  │ /api/docs/*  │  │ /api/search  │  │ /api/chat/*       ││
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘│
│         │                 │                    │            │
│  ┌──────┴─────────────────┴────────────────────┴──────────┐│
│  │                    Service 层                            ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  ││
│  │  │ 解析器    │ │ 切片器    │ │ Embedding│ │ RAG 检索    │  ││
│  │  │ Parser   │ │ Chunker  │ │ Service │ │ Retriever  │  ││
│  │  └──────────┘ └──────────┘ └──────────┘ └────────────┘  ││
│  └─────────────────────────┬───────────────────────────────┘│
│                            │                                │
│  ┌──────────────────────────┴───────────────────────────────┐│
│  │                 数据访问层 (SQLAlchemy)                    ││
│  └──────┬───────────────────────────────────────┬───────────┘│
└─────────┼───────────────────────────────────────┼────────────┘
          │                                       │
┌─────────┴─────────┐                   ┌─────────┴─────────┐
│    SQLite         │                   │   sqlite-vec       │
│  knowledge.db     │                   │ (嵌入同一 db 文件)   │
│  ├─ documents     │                   │  ├─ chunk vectors   │
│  ├─ chunks        │                   │  └─ metadata refs   │
│  ├─ tags          │                   └───────────────────┘
│  ├─ chat_history  │
│  ├─ versions      │                   ┌───────────────────┐
│  └─ FTS5 索引     │                   │  文件系统           │
└───────────────────┘                   │  data/files/*.pdf  │
                                        │  data/files/*.docx │
                                        └───────────────────┘
```

### 3.2 项目目录结构

```
知识库/
├── backend/
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # 配置读取（.env）
│   ├── requirements.txt
│   │
│   ├── api/                       # 路由层
│   │   ├── __init__.py
│   │   ├── documents.py           # 文档 CRUD
│   │   ├── search.py              # 全文搜索
│   │   ├── chat.py                # AI 对话
│   │   └── upload.py              # 文件上传
│   │
│   ├── services/                  # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── parser.py              # 文档解析（插件式）
│   │   ├── chunker.py             # 文本切片
│   │   ├── embedding.py           # Embedding 服务
│   │   ├── llm.py                 # LLM 调用（流式）
│   │   ├── rag.py                 # RAG 检索 + Prompt 组装
│   │   ├── backup.py              # 自动备份
│   │   └── tasks.py               # 异步后台任务
│   │
│   ├── db/                        # 数据层
│   │   ├── __init__.py
│   │   ├── database.py            # SQLAlchemy 初始化
│   │   ├── models.py              # ORM 模型
│   │   ├── schemas.py             # Pydantic Schema
│   │   └── vec_store.py           # sqlite-vec 封装
│   │
│   └── utils/
│       ├── __init__.py
│       └── security.py            # 文件校验、重命名
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.vue
│       ├── main.js
│       ├── style.css
│       ├── api/                   # 后端接口封装
│       │   ├── documents.js
│       │   ├── chat.js
│       │   └── search.js
│       ├── components/
│       │   ├── DocumentList.vue
│       │   ├── DocumentView.vue
│       │   ├── MarkdownPreview.vue
│       │   ├── ChatPanel.vue
│       │   ├── ChatMessage.vue
│       │   ├── TagInput.vue
│       │   └── SearchBar.vue
│       ├── views/
│       │   ├── Documents.vue
│       │   ├── Chat.vue
│       │   └── Settings.vue
│       └── stores/                # Pinia 状态管理
│           ├── documents.js
│           └── chat.js
│
├── data/                          # 运行时数据（加入 .gitignore）
│   ├── knowledge.db              # SQLite 主库
│   └── files/                    # 原始文件存储
│
├── backup/                        # 自动备份目录
│
├── .env                           # 环境变量（不入 git）
├── .env.example                   # 环境变量模板
├── .gitignore
└── DESIGN.md                      # 本文档
```

### 3.3 关键设计决策

#### 3.3.1 文档解析插件式架构

```python
# backend/services/parser.py

class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> str:
        """返回 Markdown 文本"""
        pass

class MarkdownParser(BaseParser): ...
class PDFParser(BaseParser): ...
class DocxParser(BaseParser): ...
class HTMLParser(BaseParser): ...

PARSERS: dict[str, BaseParser] = {
    ".md": MarkdownParser(),
    ".pdf": PDFParser(),
    ".docx": DocxParser(),
    ".html": HTMLParser(),
}

def parse(file_path: str, ext: str) -> str:
    parser = PARSERS.get(ext.lower())
    if not parser:
        raise UnsupportedFormat(f"不支持的格式: {ext}")
    return parser.parse(file_path)
```

#### 3.3.2 文本切片策略

```python
# backend/services/chunker.py

def chunk_markdown(content: str, max_size: int = 800, overlap: int = 100) -> list[Chunk]:
    """
    按标题/段落切分，确保每个片段语义完整。
    相邻片段 overlap 字符重叠，避免切断上下文。
    每个 chunk 携带所属文档标题和章节路径。
    """
```

切片示例：

```
文档：FastAPI 教程
├── [Chunk 1] title=FastAPI 教程 > 第一章 概述
│    内容：FastAPI 是一个现代化的 Python Web 框架...（末尾 100 字符重叠给 Chunk 2）
├── [Chunk 2] title=FastAPI 教程 > 第一章 概述 > 1.1 安装
│    内容：...（前 100 字符来自 Chunk 1 末尾）首先需要安装 Python 3.7+...
└── ...
```

#### 3.3.3 RAG Prompt 模板

```
System: 你是一个知识库助手。请严格基于下方提供的文档内容回答用户问题。
        如果文档中没有相关内容，请明确说明"知识库中未找到相关信息"，不要编造答案。
        在回答末尾标注引用来源，格式：[来源：文档标题]

Context:
[文档A] FastAPI 是一个现代化...
[文档B] Python 异步编程的核心是...

Question: 用户的问题

Answer:
```

#### 3.3.4 流式输出（SSE）

```python
# backend/api/chat.py
from fastapi.responses import StreamingResponse

async def chat_stream(request: ChatRequest):
    async def generate():
        async for chunk in llm.stream(prompt):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 四、数据库设计

### 4.1 表结构

```sql
-- ==================== 文档表 ====================
CREATE TABLE documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    file_path       TEXT,                -- 原始文件相对路径：files/uuid.pdf
    content_md      TEXT,                -- Markdown 版本（AI + 搜索用）
    file_type       TEXT,                -- md / pdf / docx / html / txt
    file_size       INTEGER DEFAULT 0,   -- 原文件大小（字节）
    parse_status    TEXT DEFAULT 'pending',  -- pending / processing / success / partial / failed
    summary         TEXT,                -- AI 自动摘要
    word_count      INTEGER DEFAULT 0,
    is_deleted      INTEGER DEFAULT 0,
    deleted_at      DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_title ON documents(title);
CREATE INDEX idx_documents_created ON documents(created_at);
CREATE INDEX idx_documents_deleted ON documents(is_deleted);

-- ==================== 文档版本历史 ====================
CREATE TABLE document_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL,
    content_md      TEXT,
    version_note    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_versions_doc ON document_versions(document_id);

-- ==================== 标签 ====================
CREATE TABLE tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    color           TEXT DEFAULT '#666666',
    usage_count     INTEGER DEFAULT 0
);

-- ==================== 文档-标签关联 ====================
CREATE TABLE document_tags (
    document_id     INTEGER NOT NULL,
    tag_id          INTEGER NOT NULL,
    PRIMARY KEY (document_id, tag_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- ==================== 文档切片 ====================
CREATE TABLE chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    section_path    TEXT,                -- 章节路径：第一章 > 1.1
    token_count     INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX idx_chunks_doc ON chunks(document_id);

-- ==================== 对话会话 ====================
CREATE TABLE conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,                -- 自动生成或用户自定义
    document_id     INTEGER,             -- 关联文档（指定文档对话时）
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_conv_doc ON conversations(document_id);
CREATE INDEX idx_conv_created ON conversations(created_at);

-- ==================== 对话消息 ====================
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT NOT NULL,        -- user / assistant / system
    content         TEXT NOT NULL,
    sources         TEXT,                 -- JSON: 引用的文档来源
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX idx_msg_conv ON messages(conversation_id);

-- ==================== 全文检索索引 ====================
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    content_md,
    content='' UNINDEXED,
    tokenize='unicode61'
);
```

### 4.2 sqlite-vec 向量存储

sqlite-vec 以虚拟表形式嵌入 SQLite，不额外生成文件：

```sql
-- 向量表（sqlite-vec 虚拟表）
CREATE VIRTUAL TABLE chunk_embeddings USING vec0(
    embedding float[1536]  -- 维度取决于 Embedding 模型（text-embedding-3-small 是 1536）
);

-- 存储：每个 chunk 的 embedding
-- 检索：cosine 相似度 top-k
SELECT chunk_id, distance
FROM chunk_embeddings
WHERE embedding MATCH ? ORDER BY distance LIMIT 5;
```

---

## 五、API 设计

### 5.1 统一响应格式

```json
// 成功
{ "code": 0, "data": { ... }, "msg": "ok" }

// 失败
{ "code": 4001, "data": null, "msg": "文件格式不支持" }
```

### 5.2 文档相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/upload | 上传文档（multipart/form-data） |
| GET | /api/documents | 文档列表（分页、筛选） |
| GET | /api/documents/{id} | 文档详情 |
| GET | /api/documents/{id}/raw | 获取原始文件（下载） |
| GET | /api/documents/{id}/preview | 获取 Markdown 内容 |
| PUT | /api/documents/{id} | 更新文档（标题/Markdown 内容） |
| DELETE | /api/documents/{id} | 软删除 |
| POST | /api/documents/{id}/restore | 恢复（从软删除） |
| POST | /api/documents/{id}/reparse | 重新解析 + 重新向量化 |
| GET | /api/documents/{id}/versions | 版本历史列表 |
| GET | /api/documents/{id}/versions/{v_id} | 指定版本内容 |
| POST | /api/documents/{id}/versions/{v_id}/restore | 回退到指定版本 |

### 5.3 标签相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tags | 所有标签 |
| POST | /api/tags | 新建标签 |
| PUT | /api/tags/{id} | 更新标签 |
| DELETE | /api/tags/{id} | 删除标签 |
| POST | /api/documents/{id}/tags | 给文档打标签 |

### 5.4 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/search?q=xxx | 全文搜索（FTS5），返回高亮片段 |

### 5.5 AI 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/conversations | 会话列表 |
| POST | /api/conversations | 新建会话（可指定 document_id） |
| GET | /api/conversations/{id} | 会话详情 + 消息历史 |
| DELETE | /api/conversations/{id} | 删除会话 |
| POST | /api/chat | 发送消息（指定文档对话） |
| POST | /api/chat/stream | 发送消息（SSE 流式，推荐） |
| POST | /api/chat/rag | RAG 知识库问答（SSE 流式） |

### 5.6 对话请求体示例

```json
// 指定文档对话
{
  "conversation_id": 1,
  "document_id": 42,
  "message": "这篇文档的核心观点是什么？"
}

// RAG 知识库问答
{
  "conversation_id": null,
  "message": "FastAPI 和 Flask 有什么区别？",
  "top_k": 5
}
```

---

## 六、配置说明

### 6.1 .env 文件

```env
# AI 接口配置
AI_API_KEY=sk-xxxxxxxxxxxxxxxx
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_EMBEDDING_MODEL=text-embedding-3-small

# 数据库
DB_PATH=data/knowledge.db
VECTOR_DIM=1536

# 文件存储
FILE_STORAGE_DIR=data/files
MAX_FILE_SIZE=20971520
ALLOWED_EXTENSIONS=.md,.txt,.pdf,.docx

# 备份
BACKUP_DIR=backup
BACKUP_KEEP_DAYS=7
```

### 6.2 兼容国产模型

只需修改 AI 相关配置即可，无需改代码：

```env
# 通义千问
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-plus
AI_EMBEDDING_MODEL=text-embedding-v3
VECTOR_DIM=1024

# DeepSeek
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
AI_EMBEDDING_MODEL=deepseek-embedding
VECTOR_DIM=1024
```

---

## 七、迭代计划

### 第一阶段：能存能看

- [ ] FastAPI 项目初始化
- [ ] SQLite + sqlite-vec + FTS5 建表
- [ ] 文件上传 + 双版本存储
- [ ] 基础解析器（先支持 Markdown / PDF）
- [ ] 文档列表 + 查看页面
- [ ] 软删除

### 第二阶段：AI 对话

- [ ] Embedding + 向量化（异步）
- [ ] sqlite-vec 相似度检索
- [ ] 指定文档对话（SSE 流式）
- [ ] RAG 知识库问答（SSE 流式 + 引用来源）
- [ ] 多轮对话 + 会话管理

### 第三阶段：好用

- [ ] 全文搜索 + 高亮
- [ ] 标签系统
- [ ] 版本历史 + 手动编辑
- [ ] 自动备份
- [ ] AI 自动摘要
- [ ] 解析插件补全（Word / HTML）
- [ ] 异步解析状态轮询 / WebSocket

---

## 八、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| PDF 解析质量差 | AI 读取内容不完整 | 标记 parse_status=partial，允许手动修正 Markdown |
| LLM 上下文超限 | 长文档问答失败 | 切片 + 检索相关片段再传入，不全量传 |
| Embedding 模型切换 | 向量维度不兼容 | 重建向量表时清空旧数据，重新向量化 |
| 文件上传安全 | 路径穿越 / 恶意文件 | 白名单校验 + uuid 重命名 + 存前检测 MIME |
| 数据丢失 | 灾难性 | 每日自动备份 + 软删除 + 版本历史 |
| API Key 泄露 | 费用风险 | .env 管理 + 加入 .gitignore + 启动时日志脱敏 |

---

## 九、更新记录

### v1.1（本次优化）

**缺陷修复**
- 文档列表/详情不再丢失标签（`_doc_to_response` 此前恒返回空标签）
- 编辑文档内容后向量索引现在会正确重建（原条件在赋值后恒为 False）
- 会话消息按 `id` 稳定排序，修复历史乱序
- 「重新生成」不再重复插入用户消息
- 全文搜索改为 FTS5 **trigram** 分词：中文子串匹配（原 unicode61 把整段中文当一个 token，段落中间的词搜不到）；1-2 字词走 LIKE 兜底；查询特殊字符安全净化
- FTS 表启动时自动从 unicode61 迁移到 trigram 并回填
- 向量表启动时校验维度与 `VECTOR_DIM` 一致，不一致自动重建（默认 512 匹配本地 BGE-small）
- vec0 虚拟表改用原生 sqlite3 连接创建（aiosqlite 代理连接无法加载扩展）
- Markdown 渲染接入 DOMPurify 净化，消除 XSS 风险

**新增功能**
- 回收站：列表 / 恢复 / 彻底删除（`/api/trash` + 前端页面）
- 版本历史：列表 / 内容预览 / 一键回滚（前端弹窗）
- 自动备份：启动时后台执行 + 设置页手动触发，保留 `BACKUP_KEEP_DAYS` 天（`services/backup.py`）
- 设置页真实生效：`GET/PUT /api/settings` 读写 `.env` 并热更新 LLM 客户端，无需重启
- AI 自动摘要：上传/编辑后后台生成文档摘要（`documents.summary`）
- 搜索页点击结果直接打开文档查看器（路由 `?open=<id>`）

**其他**
- `embedding_available()` 统一判断本地/API 型 Embedding 可用性（本地 BGE 不再依赖 API Key）
- 前端 API 封装整合（`src/api/index.js`），Vite vendor 分包
- README / .env.example 同步更新（VECTOR_DIM=512、热更新说明等）

### v1.2（双向链接 + 知识图谱）

**双向链接（A+B 方案）**
- 新增 `document_links` 表（from_doc_id / to_doc_id / source，唯一约束防重）
- `services/links.py`：
  - **A 自动标题匹配**：正文出现其他文档标题即建链，最长优先、跳过代码块/行内代码/已占用区间、长度 <2 不匹配防误连
  - **B `[[标题]]` 语法**：显式精确链接，优先级高于自动；同一目标只保留最高优先级来源
  - 全量重建串行化（threading.Lock），防止并发编辑互相覆盖
- 文档 上传/新建/编辑/重命名/重新解析/版本回滚/软删除/恢复/彻底删除 后均自动触发后台重建；启动时对存量库自动补建
- `GET /api/documents/{id}/links`：返回 outgoing（本文引用）+ incoming（被引用）
- `GET /api/graph`：图谱节点（含标签）+ 边（含链接来源类型）

**前端**
- 文档查看器新增「关联文档」区：引用/被引用标签页，来源着色（自动=蓝、语法=绿），点击即可切换查看
- 新增「知识图谱」页面 `/graph`：d3-force 力导向图，节点大小=连接数、边按来源着色、节点可拖拽、滚轮缩放、空白平移、点击节点直达文档
- 侧边栏新增「🕸️ 知识图谱」入口

### v1.3（网页剪藏）

- `documents` 表新增 `source_url` 字段（启动自动迁移），记录剪藏来源
- `POST /api/documents/clip`：两种输入
  - `url`：服务端抓取（httpx 流式限 5MB、20s 超时、UA 伪装、编码探测 `<meta charset>` / UTF-8）
  - `html`：直接接收页面 HTML（bookmarklet 用，绕开登录墙/抓取失败）
  - 均走 `html_to_markdown`（从 HTMLParser 抽出复用）转 Markdown，file_type=clip
  - 入库后自动触发：FTS 索引、后台向量化、双向链接重建、AI 摘要、可选标签
- 前端：「文档管理」新增「🌐 网页剪藏」弹窗（URL/标题/标签）；查看器显示来源链接（新窗口打开）
- 浏览器 Bookmarklet：任意网页点书签一键剪藏（README 附代码）
