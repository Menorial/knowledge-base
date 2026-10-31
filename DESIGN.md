# 个人知识库系统 — 功能与架构设计文档

> 版本：v1.7
> 日期：2026-10-31
>
> 本文档描述**当前实现**（以代码为准）。历次功能演进见[第九节](#九更新记录)。

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
| 后端 | Python 3.11+ / FastAPI | 异步 IO，AI 生态完善 |
| 前端 | Vue 3 / Vite / Element Plus | SPA，纯本地运行 |
| 关系数据库 | SQLite 3（WAL） | 文档、切片、标签、会话、版本、链接 |
| 全文检索 | SQLite FTS5（trigram） | 中文子串匹配；1–2 字走 LIKE 兜底 |
| 向量检索 | sqlite-vec（vec0） | 与主库同文件，无额外服务 |
| Embedding | 本地 BGE-small-zh（512 维）/ OpenAI 兼容 API | `AI_EMBEDDING_MODEL=local` 即全本地 |
| LLM | OpenAI 兼容接口 | DeepSeek / OpenAI / 通义等 |
| 文档解析 | PyMuPDF、python-docx、html2text、readability-lxml | 按格式选解析器 |
| 前端渲染 | markdown-it + highlight.js + DOMPurify | 渲染并净化 |
| 可视化 | ECharts（统计）、d3-force（图谱） | 仪表盘与知识图谱 |
| 测试 | pytest | 纯函数用例，CI 不装模型 |

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
│   ├── main.py                 # 入口：lifespan 启动任务 + 静态文件 + CORS
│   ├── config.py               # pydantic-settings 读取 .env
│   ├── api/                    # 路由层
│   │   ├── documents.py        # 上传/CRUD/解析/索引/剪藏/版本
│   │   ├── search.py           # FTS5 trigram 检索
│   │   ├── chat.py             # 三种对话模式 + SSE + 导出/重新生成
│   │   ├── tags.py             # 标签 CRUD
│   │   ├── trash.py            # 回收站（恢复/彻底删除/批量）
│   │   ├── graph.py            # 知识图谱数据
│   │   ├── stats.py            # 概览统计 + 连通性测试
│   │   └── system.py           # 设置读写 + 备份管理
│   ├── services/
│   │   ├── parser.py           # 解析器插件
│   │   ├── chunker.py          # 语义切片
│   │   ├── embedding.py        # 本地 BGE / API Embedding
│   │   ├── vec_store.py        # sqlite-vec 封装 + 写锁
│   │   ├── fts_sync.py         # FTS 索引同步
│   │   ├── llm.py              # OpenAI 兼容流式客户端（支持热更新）
│   │   ├── rag.py              # 检索 + Prompt 组装 + 长文档片段检索
│   │   ├── links.py            # 双向链接：提取/全量/增量/合并调度
│   │   ├── clipper.py          # 网页正文提取 + 图片本地化
│   │   ├── autotag.py          # AI 自动打标签
│   │   ├── tags_usage.py       # 标签计数重算
│   │   └── backup.py           # SQLite 在线备份
│   ├── db/
│   │   ├── database.py         # 引擎、WAL、FTS/向量表初始化与迁移
│   │   ├── models.py           # ORM 模型
│   │   └── schemas.py          # Pydantic Schema
│   └── utils/
│       ├── security.py         # 文件校验 / uuid 重命名
│       └── loop_lock.py        # 按事件循环取 asyncio.Lock
│
├── frontend/
│   ├── package.json / vite.config.js / index.html
│   └── src/
│       ├── App.vue / main.js / theme.js
│       ├── api/index.js        # 所有接口封装
│       ├── router/index.js     # 7 个页面路由
│       ├── utils/tagColor.js   # 标签稳定取色
│       └── views/              # Dashboard / Documents / Chat / Search / Graph / Trash / Settings
│
├── tests/                      # pytest 单元测试（纯函数，不依赖模型）
├── .github/workflows/ci.yml    # CI
├── data/                       # 运行时数据（.gitignore）
├── backup/                     # 备份目录（.gitignore）
├── .env / .env.example
└── DESIGN.md
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

#### 3.3.5 并发与锁模型

SQLite 是单写者模型，本项目用三层机制避免写冲突和数据错乱：

| 层 | 机制 | 作用 |
|----|------|------|
| 连接层 | WAL 模式 + `timeout=30` + `_with_retry` | 写等待与短暂重试，避免 `database is locked` |
| 原生 sqlite3 写 | 进程内 `threading.Lock`（`vec_store.db_write_lock`） | 串行化向量表 / FTS 的写入（这些调用跑在 `asyncio.to_thread` 里，不阻塞事件循环） |
| 业务级 | `loop_lock("links_rebuild")`、`loop_lock(f"index:{doc_id}")` | 链接重建互斥；同一文档的索引重建串行 |

**为什么需要 `loop_lock`**：`threading.Lock` 如果在 `async` 函数里跨 `await` 持有，
第二个协程会阻塞事件循环线程，导致持锁协程永远无法恢复（死锁）；
而模块级 `asyncio.Lock()` 在同一进程的多个事件循环里复用会报
"bound to a different event loop"。所以按「事件循环 + 名字」取锁，见 `utils/loop_lock.py`。

**索引写入为什么必须按文档串行**：重建流程是「删 chunk → 插 chunk → 插向量」，
SQLite 会复用被删掉的最大 rowid，两个并发任务拿到相同 chunk id 就会撞
`chunk_embeddings` 主键，表现为向量索引静默丢失。

#### 3.3.6 后台任务与索引一致性

| 动作 | 同步部分 | 后台部分 |
|------|----------|----------|
| 上传 | 校验、落盘、解析、写库、FTS | 切片 + 向量化 → 摘要 → 自动标签 |
| 编辑正文 | 写库、版本快照、FTS | 向量化 → 摘要（不阻塞保存） |
| 批量重建索引 | 立即返回 | 逐篇重建，完成后刷新可见 |
| 链接重建 | — | 全量或按文档增量，请求会合并 |
| 启动 | 建表/迁移、WAL | 备份、链接重建、标签计数校正、模型预热 |

- 软删除只清理 FTS，**保留** chunk 与向量，恢复时无需重建；彻底删除才清理。
- RAG 检索在 SQL 层过滤 `is_deleted`，并多召回一些再截断，避免删除文档占用名额。
- 版本历史每篇保留最近 **30** 份。
- 标签 `usage_count` 是冗余字段，所有关联变更后统一重算（`services/tags_usage.py`）。

## 四、数据库设计

### 4.1 表结构

```sql
-- ==================== 文档 ====================
CREATE TABLE documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    file_path       TEXT,                    -- files/uuid.pdf；剪藏与在线创建为 NULL
    content_md      TEXT,                    -- Markdown 版本（AI + 搜索用）
    file_type       TEXT,                    -- md / txt / pdf / docx / html / clip
    file_size       INTEGER DEFAULT 0,
    parse_status    TEXT DEFAULT 'pending',  -- pending/processing/success/partial/failed
    summary         TEXT,                    -- AI 自动摘要
    word_count      INTEGER DEFAULT 0,       -- 实际存的是字符数
    source_url      TEXT,                    -- 网页剪藏来源（旧库启动时自动 ALTER 添加）
    is_deleted      INTEGER DEFAULT 0,
    deleted_at      DATETIME,
    created_at      DATETIME,
    updated_at      DATETIME
);

-- ==================== 版本历史（每篇保留最近 30 份）====================
CREATE TABLE document_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES documents(id),
    content_md      TEXT,
    version_note    TEXT,                    -- 初始版本 / 自动保存 / 重新解析 / 回滚到版本 #n
    created_at      DATETIME
);

-- ==================== 标签 ====================
CREATE TABLE tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    color           TEXT DEFAULT '#666666',
    usage_count     INTEGER DEFAULT 0        -- 冗余字段，写操作后整体重算
);

CREATE TABLE document_tags (
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

-- ==================== 切片 ====================
CREATE TABLE chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    section_path    TEXT,                    -- 章节路径：第一章 > 1.1
    token_count     INTEGER DEFAULT 0,       -- 实际存的是字符数
    created_at      DATETIME
);

-- ==================== 对话 ====================
CREATE TABLE conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    mode            TEXT DEFAULT 'rag',      -- rag / direct / doc
    document_id     INTEGER REFERENCES documents(id),
    created_at      DATETIME,
    updated_at      DATETIME
);

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,           -- user / assistant
    content         TEXT NOT NULL,
    sources         TEXT,                    -- JSON：RAG 引用的片段
    created_at      DATETIME
);

-- ==================== 双向链接 ====================
CREATE TABLE document_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_doc_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    to_doc_id       INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source          TEXT DEFAULT 'auto',     -- auto（标题匹配）/ syntax（[[标题]]）
    created_at      DATETIME,
    UNIQUE (from_doc_id, to_doc_id)
);

CREATE INDEX ix_document_links_from_doc_id ON document_links(from_doc_id);
CREATE INDEX ix_document_links_to ON document_links(to_doc_id);

-- ==================== 全文索引（trigram 分词，手工同步）====================
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    content_md,
    tokenize='trigram'
);
```

> 除主键与 `document_links` 的索引外，其余表依赖 SQLite 的 rowid/唯一约束。
> 个人库规模（千篇以内）足够；再大建议补 `documents(is_deleted, created_at)`、
> `chunks(document_id)`、`messages(conversation_id)` 等索引。

### 4.2 sqlite-vec 向量存储

与主库同一个文件，不额外生成数据库：

```sql
CREATE VIRTUAL TABLE chunk_embeddings USING vec0(
    rowid        INTEGER PRIMARY KEY,   -- 等于 chunks.id
    document_id  INTEGER,               -- 便于按文档删除/统计
    embedding    float[512]             -- 维度 = VECTOR_DIM，本地 BGE-small 默认 512
);

-- 写入：rowid 即 chunk id
INSERT INTO chunk_embeddings(rowid, document_id, embedding) VALUES (?, ?, ?);

-- 检索：L2 距离升序
SELECT rowid, document_id, distance FROM chunk_embeddings
WHERE embedding MATCH ? ORDER BY distance LIMIT 20;
```

维度必须与 `VECTOR_DIM` 一致：启动时会读取现有向量维度校验，不一致则重建向量表
（需要再执行一次「重建索引」）。`vec0` 虚拟表只能用原生 `sqlite3` 连接创建，
`aiosqlite` 的代理连接无法加载扩展。

## 五、API 设计

### 5.1 统一响应格式

```json
// 成功
{ "code": 0, "data": { ... }, "msg": "ok" }

// 失败
{ "code": 4001, "data": null, "msg": "文件格式不支持" }
```

### 5.2 文档与索引

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/upload | 上传文档（multipart/form-data） |
| GET | /api/documents | 文档列表（分页、标题筛选） |
| GET | /api/documents/{id} | 文档详情 |
| GET | /api/documents/{id}/preview | Markdown 内容 |
| GET | /api/documents/{id}/raw | 下载原始文件 |
| PUT | /api/documents/{id} | 更新标题 / Markdown（后台重建索引） |
| DELETE | /api/documents/{id} | 软删除 |
| POST | /api/documents/{id}/restore | 从软删除恢复 |
| POST | /api/documents/batch-delete | 批量软删除 |
| POST | /api/documents/{id}/reparse | 重新解析（需有原始文件） |
| POST | /api/documents/{id}/reindex | 重建单篇向量索引 |
| POST | /api/documents/reindex-all | 批量重建（**后台执行，立即返回**） |
| POST | /api/documents/create-text | 在线新建 Markdown 文档 |
| POST | /api/documents/clip | 网页剪藏（url 或 html） |
| GET | /api/documents/{id}/links | 双向链接（outgoing / incoming） |
| GET | /api/documents/{id}/versions | 版本历史 |
| GET | /api/documents/{id}/versions/{v_id} | 版本内容 |
| POST | /api/documents/{id}/versions/{v_id}/restore | 回滚到指定版本 |

### 5.3 标签

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tags | 所有标签（按使用次数排序） |
| POST | /api/tags | 新建标签（空名/重名返回 400） |
| PUT | /api/tags/{id} | 重命名 / 改色 |
| DELETE | /api/tags/{id} | 删除标签 |
| POST | /api/tags/document/{doc_id} | 给文档加标签（body 为标签名数组） |
| DELETE | /api/tags/document/{doc_id}/{tag_id} | 移除标签 |

### 5.4 搜索与图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/search?q=&page=&page_size= | 全文搜索，返回高亮片段与 rank |
| GET | /api/graph | 图谱节点（含标签）与边（含来源类型） |

### 5.5 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/conversations | 会话列表 |
| POST | /api/conversations | 新建会话（mode: rag/direct/doc） |
| GET | /api/conversations/{id} | 会话详情 + 消息 |
| PUT | /api/conversations/{id} | 修改标题 / 模式 |
| DELETE | /api/conversations/{id} | 删除会话 |
| GET | /api/conversations/{id}/export | 导出为 Markdown |
| POST | /api/conversations/{id}/regenerate/{msg_id} | 重新生成某条回答 |
| POST | /api/chat/direct | 纯 AI 对话（SSE） |
| POST | /api/chat/stream | 指定文档问答（SSE） |
| POST | /api/chat/rag | 知识库 RAG 问答（SSE） |

### 5.6 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET / PUT | /api/settings | 读取 / 写入配置（写 .env 并热更新） |
| POST | /api/backup | 立即备份 |
| GET | /api/backups | 备份列表 |
| DELETE | /api/backups/{name} | 删除备份 |
| GET | /api/trash | 回收站列表 |
| POST | /api/trash/{id}/restore | 恢复 |
| DELETE | /api/trash/{id} | 彻底删除（含文件、向量、版本） |
| POST | /api/trash/batch-restore | 批量恢复 |
| POST | /api/trash/batch-purge | 批量彻底删除 |
| GET | /api/stats/overview | 概览统计 |
| POST | /api/stats/test-llm | AI 连通性测试 |
| GET | /api/health | 健康检查 |

### 5.7 对话请求体示例

```json
// 指定文档对话
{ "conversation_id": 1, "document_id": 42, "message": "这篇文档的核心观点是什么？" }

// RAG 知识库问答
{ "conversation_id": null, "message": "FastAPI 和 Flask 有什么区别？", "top_k": 5 }

// 纯 AI 对话
{ "conversation_id": 3, "message": "帮我写个正则" }
```

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

### 第一阶段：能存能看 ✅

- [x] FastAPI 项目初始化
- [x] SQLite + sqlite-vec + FTS5 建表
- [x] 文件上传 + 双版本存储
- [x] 解析器（Markdown / TXT / PDF / Word / HTML）
- [x] 文档列表 + 查看页面
- [x] 软删除

### 第二阶段：AI 对话 ✅

- [x] Embedding + 向量化（后台）
- [x] sqlite-vec 相似度检索
- [x] 指定文档对话（SSE 流式）
- [x] RAG 知识库问答（SSE + 引用来源）
- [x] 多轮对话 + 会话管理（含导出、重新生成）

### 第三阶段：好用 ✅

- [x] 全文搜索（trigram + 高亮 + 分页）
- [x] 标签系统（自动配色 + AI 自动打标签）
- [x] 版本历史 + 手动编辑 + 回滚（保留 30 份）
- [x] 自动备份（启动 + 手动）
- [x] AI 自动摘要
- [x] 双向链接 + 知识图谱
- [x] 网页剪藏（正文提取 + 图片本地化）
- [x] 仪表盘统计

### 第四阶段：稳定性与开源 ✅

- [x] 修复链接重建死锁（threading.Lock → 事件循环锁）
- [x] 修复并发保存导致的向量索引丢失（按文档串行化）
- [x] 索引/统计/标签计数一致性收敛
- [x] 搜索分页、连字符查询、LIKE 通配符转义
- [x] 单元测试 + GitHub Actions
- [ ] 全文 + 向量混合排序（RRF）
- [ ] 移动端适配

## 八、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| PDF 是扫描件 | 无法提取文本 | 标记 `parse_status=failed`，允许手动补 Markdown |
| LLM 上下文超限 | 长文档问答不完整 | 超过 12000 字的文档改为库内切片检索，只送最相关片段 |
| Embedding 模型切换 | 维度不兼容 | 启动校验维度并重建向量表，再执行「重建索引」 |
| 并发保存 | 索引错乱/丢失 | 按文档串行化索引写入 + 版本快照 |
| 并发重建链接 | 事件循环死锁 | 事件循环锁 + 请求合并 |
| 本地模型不可用 | 语义检索失效 | 启动预热有超时；失败时降级为关键词匹配 |
| 文件上传 | 路径穿越 / 恶意文件 | 扩展名白名单 + uuid 重命名 + 大小限制 |
| 数据丢失 | 灾难性 | 启动自动备份 + 软删除 + 版本历史 |
| 局域网暴露 | 无鉴权可被读写 | 默认只监听 127.0.0.1；CORS 收紧到本地前端 |
| API Key 泄露 | 费用风险 | `.env` 管理且已被 `.gitignore` 忽略 |

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

### v1.4（剪藏质量：正文提取 + 图片本地化）

- 新增 `services/clipper.py` 剪藏管线：
  - **噪声预清洗**：lxml 删除 `nav/footer/aside/script/style/iframe` 及 class/id 含 ad、ads、banner、sidebar、recommend、related、comment、copyright、advert 的元素
  - **正文提取**：readability-lxml 按文本密度提取文章主体，失败回退整页
  - **图片本地化**：正文内远程图片下载到 `data/files/clip/{doc_id}/`（限 5MB/张、仅 image/*、带 Referer 防防盗链、支持相对路径），markdown 引用改为 `/files/clip/{doc_id}/{uuid}.{ext}` 本地路径
- 后端挂载 `/files` 静态目录（uuid 文件名，安全直出），vite 代理 `/files` 到后端
- 彻底删除文档时清理对应剪藏图片目录
- `requirements.txt` 新增 `readability-lxml`；剪藏反爬（521/403 等）返回中文引导提示，弹窗内置书签安装指引

### v1.5（前端视觉升级：笔记风 + 暗色模式 + 图表）

- **设计系统**：全局 CSS 变量（暖白笔记色板 / 圆角 / 阴影 / 排版），亮暗双套变量，`html.dark` 切换
- **暗色模式**：侧边栏底部开关（亮色 → 暗色 → 跟随系统 三态循环），localStorage 持久化，跟随系统实时响应；Element Plus dark css-vars；所有页面颜色变量化
- **侧边栏重设计**：浅色笔记风、logo 区、active 指示条、底部主题开关
- **仪表盘**：ECharts 重写（近 7 日趋势面积图、解析状态环形图、Top 标签渐变条形图），统计卡 hover 动效
- **文档管理**：列表/卡片视图切换（localStorage 记忆），卡片含图标/标签/字数/状态，hover 抬升
- **对话/搜索/图谱/回收站/设置**：统一变量化配色与精致卡片、柔和阴影、过渡动效

### v1.6（标签自动适配：自动配色 + AI 自动打标签）

- **标签自动配色**：CSS 定义 8 组亮/暗双主题标签色变量；`utils/tagColor.js` 按标签名哈希稳定取色（同一标签全站颜色一致）；文档列表/卡片/查看器的标签自动配色，暗色模式自动切换变体
- **AI 自动打标签**：`services/autotag.py` —— LLM 根据内容生成 1-5 个标签（过滤宽泛词），文档已有标签时跳过（尊重手动），复用/创建 Tag 并更新 usage_count；随 `_bg_summarize` 在上传/新建/剪藏/编辑/回滚后后台触发
- 文档查看器新增标签展示区

### v1.7（稳定性加固 + 开源准备）

**修复**
- 链接重建死锁：`threading.Lock` 跨 `await` 持有会阻塞事件循环，改为按事件循环取 `asyncio.Lock`（`utils/loop_lock.py`）
- 并发保存导致向量索引静默丢失：两个重建任务交错删除/插入 chunk，SQLite 复用 rowid 撞 `chunk_embeddings` 主键；改为按 `doc_id` 串行化
- 软删除不再删除向量，恢复文档后可立即被 RAG 检索；历史缺向量的文档恢复时自动补建
- 标签计数只增不减：新增 `services/tags_usage.py`，写操作后统一重算
- 标签重名导致 500、空标签名可创建：改为 400 并统一 `strip()`
- 搜索：连字符查询拆词、`%`/`_` 转义、结果分页、相关度归一化（原公式恒 >100%）
- `reindex-all` 改为后台执行；版本历史裁剪到 30 份；`reparse` 失败时正确落库 `failed`
- 索引不再覆盖 `failed/partial` 解析状态
- 搜索结果 snippet 接入 DOMPurify（原为裸 `v-html`）

**架构**
- 链接重建支持按文档增量 + 请求合并，正文编辑不再触发全表扫描
- CORS 改为按路径放行：仅本地前端，剪藏接口保留任意来源（书签小工具）
- 新增 `tests/`（10 个纯函数用例）与 GitHub Actions
