# 贡献指南

## 开发环境

- Python 3.11 / 3.12（3.13+ 部分依赖暂无预编译轮子）
- Node.js 18+
- 后端依赖：`pip install -r backend/requirements.txt`
- 前端依赖：`cd frontend && npm install`

## 启动

```bash
# 项目根目录
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 另开终端
cd frontend && npm run dev
```

## 测试

```bash
pip install -r requirements-test.txt
pytest -q
```

测试只覆盖纯函数（切片、链接提取、FTS 查询构造、分页与转义），
不加载模型、不访问网络，CI 里几十秒内跑完。

## 代码约定

- 后端按 `api/`（路由）→ `services/`（业务）→ `db/`（数据）分层，不要在路由里写复杂逻辑；
- 所有会改动「文档-标签 / 链接 / 索引」的写操作，结束后要保持三者一致：
  标签调 `recompute_tag_usage`，链接调 `schedule_rebuild`，索引走 `_bg_vectorize` / `_do_chunk_and_vectorize`；
- 异步代码里不要用 `threading.Lock` 跨 `await` 持锁（会死锁事件循环），用 `utils/loop_lock.py`；
- 前端 Markdown 渲染一律经过 `DOMPurify.sanitize`。

## 提交

- 一个提交只做一件事，信息用中文或英文都可以，但要说明「为什么」；
- 不要提交 `data/`、`.env`、`backup/`、`node_modules/`、`dist/`（已在 `.gitignore`）。
