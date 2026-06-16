# FastAPI-RAG-Spark

这是一个基于 FastAPI 的 RAG 问答系统，目前已经具备以下能力：

- 文档上传与后台入库任务
- 混合检索（向量检索 + 稀疏检索）
- 多轮会话问答
- 模型 Provider 路由与 fallback
- Trace、评测、反馈与运营接口

## 当前能力

- FastAPI HTTP API
- SQLite 存储文档、会话、Trace、反馈和评测结果
- FAISS 稠密检索
- 基于 `document_chunks` 的稀疏检索
- 讯飞 Spark 作为主模型 Provider
- Mock Provider 作为 fallback 验证通道
- 内置可观测性与运营分析接口

## 快速开始

### 1. 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 创建本地配置

```powershell
Copy-Item .env.example .env
```

至少需要配置：

- `XF_APIKey`
- `XF_APISecret`
- `SECRET_KEY`

可选的模型路由配置：

- `LLM_PRIMARY_PROVIDER`
- `LLM_FALLBACK_PROVIDER`
- `LLM_REQUEST_TIMEOUT_SECONDS`

### 4. 启动服务

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

启动后访问：

- Swagger 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 根路径检查：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## 默认管理员账号

系统首次启动会自动创建：

- 用户名：`admin`
- 密码：`admin123456`

建议首次登录后立即修改密码。

## 推荐验证流程

### 1. 登录

调用 `POST /api/v1/auth/login`：

```json
{
  "username": "admin",
  "password": "admin123456"
}
```

### 2. 上传文档

调用 `POST /api/v1/docs/upload`。

现在这个接口的行为是：

- 先创建一条文档记录
- 再创建后台入库任务
- 后台完成解析、切块、索引构建

上传后建议检查：

- `GET /api/v1/docs/list`
- 等待文档 `status` 变成 `ready`

### 3. 发起一次 RAG 问答

调用 `POST /api/v1/question/ask`：

```json
{
  "question": "这个系统支持什么能力？",
  "mode": "rag",
  "top_k": 3,
  "return_references": true,
  "evaluate_answer": true
}
```

返回中会包含：

- `trace_id`
- `conversation_id`
- `rewritten_question`
- `provider_name`
- `timings_ms`
- `retrieval_quality`

### 4. 继续同一轮会话

使用上一步返回的 `conversation_id`：

```json
{
  "conversation_id": 1,
  "question": "那它的文档处理方式呢？",
  "mode": "rag",
  "top_k": 3,
  "return_references": true
}
```

### 5. 查看 Trace

调用：

- `GET /api/v1/question/traces`
- `GET /api/v1/question/traces/{trace_id}`

### 6. 提交用户反馈

调用 `POST /api/v1/question/feedback`：

```json
{
  "trace_id": "你的 trace_id",
  "rating": "up",
  "comment": "回答比较准确"
}
```

## 主要接口分组

### 认证接口

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/create-employee`
- `POST /api/v1/auth/change-pwd`

### 文档接口

- `POST /api/v1/docs/upload`
- `GET /api/v1/docs/list`
- `GET /api/v1/docs/get/{doc_id}`
- `DELETE /api/v1/docs/delete/{doc_id}`

### 问答接口

- `POST /api/v1/question/ask`
- `POST /api/v1/question/evaluate`
- `GET /api/v1/question/conversations`
- `GET /api/v1/question/conversations/{conversation_id}`

### 模型健康检查

- `GET /api/v1/question/llm/health`

返回内容包括：

- `primary_provider`
- `fallback_provider`
- `providers_health`

### Trace、反馈、评测接口

- `GET /api/v1/question/traces`
- `GET /api/v1/question/traces/{trace_id}`
- `POST /api/v1/question/feedback`
- `GET /api/v1/question/feedback`
- `GET /api/v1/question/evaluations`

### 运营接口

- `GET /api/v1/question/ops/overview`
- `GET /api/v1/question/ops/evaluations/low-score`
- `GET /api/v1/question/ops/traces/fallbacks`
- `GET /api/v1/question/ops/traces/low-overlap`

这些接口可以作为一个轻量的 RAG 运营后端来使用。

## 架构说明

### 文档入库

- 上传后先写入 `documents`
- 创建后台入库任务
- 后台解析文本
- 文本切块写入 `document_chunks`
- 稠密向量加载进内存 FAISS

### 检索

- 稠密检索来自 FAISS
- 稀疏检索来自 chunk 文本 token overlap
- 轻量 rerank 会融合并重排检索结果

### 会话

- 每次 `/ask` 可以新建或复用会话
- 最近历史会参与问题改写
- 用户消息和助手消息都会持久化

### 模型路由

- 默认主 Provider 是 `spark`
- `mock` 可以作为 fallback
- `/llm/health` 可以查看当前实际路由状态

### 可观测性

- 每次 `/ask` 都会生成 `trace_id`
- 会记录各阶段耗时
- 会保存检索摘要
- 会保存评测结果和用户反馈

## 评测说明

当前评测采用的是 `LLM-as-a-judge` 方式，不是系统自己拥有标准答案。

评测时会综合这些信息：

- 原始问题
- 模型回答
- 检索到的参考片段 `references`
- 可选的 `expected_answer`
- 评分规则 `rubric`

目前主要指标包括：

- `groundedness`：回答是否忠于检索上下文
- `relevance`：回答是否正面回应问题
- `completeness`：关键点是否覆盖充分
- `clarity`：表达是否清晰

如果想让“准确性”判断更可靠，建议结合：

- 更高质量的 `references`
- 人工构造的 `expected_answer`
- 真实用户反馈

## 内置评测集

项目已经提供了一套可直接运行的本地评测集结构：

```text
  eval_dataset/
    documents/
      system_overview.docx
      llm_and_eval_notes.pdf
      ingestion_and_ops.txt
    qa_cases.jsonl
    last_eval_report.json

scripts/
  run_eval.py
```

说明：

- `eval_dataset/documents/system_overview.docx`
  用于覆盖系统总览、问答模式、混合检索和 Trace 能力。
- `eval_dataset/documents/llm_and_eval_notes.pdf`
  用于覆盖 Provider、fallback、评测维度和评测落库。
- `eval_dataset/documents/ingestion_and_ops.txt`
  用于覆盖文档入库链路、文档状态和前端控制台操作。
- `eval_dataset/qa_cases.jsonl`
  保存 32 条评测样本，覆盖事实问答、总结问答、多轮追问和 doc 模式场景，并按三份文档分布。
- `scripts/run_eval.py`
  批量调用 `/ask` 和 `/evaluate`，自动上传三份样例文档并输出评测报告。

### 推荐使用方式

1. 先启动服务

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

2. 直接运行一键评测

```powershell
python scripts/run_eval.py
```

默认会自动完成：

- 从 `eval_dataset/qa_cases.jsonl` 读取样本
- 自动上传 `eval_dataset/documents/` 下的 3 份评测文档
- 自动等待 3 份文档全部入库完成
- 自动按 `source_doc` 为 doc 模式样本分配新的 `doc_id`
- 自动执行问答和评测
- 自动把结果保存到 `eval_dataset/last_eval_report.json`

可选参数：

```powershell
python scripts/run_eval.py --base-url http://127.0.0.1:8000 --cases eval_dataset/qa_cases.jsonl --documents-dir eval_dataset/documents
```

输出报告中会包含：

- `avg_score`
- `pass_rate`
- `avg_keyword_hit_ratio`
- `avg_reference_count`
- 每条样本的 `trace_id`、`provider_name`、`retrieval_quality`
- 本轮自动上传的文档列表和对应 `doc_id`

## 注意事项

- `core/redis_client.py` 目前仍是 mock 实现，所以启动项目不需要真实 Redis。
- embedding 模型采用懒加载，服务可以先启动，首次向量化时再加载模型。
- 第一次上传文档可能较慢，因为 `sentence-transformers` 可能会下载 `BAAI/bge-small-zh`。
- 如果 `faiss-cpu` 或 `sentence-transformers` 在 Python 3.13 下安装失败，建议切换到 Python 3.10 或 3.11。
- 如果修改 `.env` 后看起来没有生效，建议彻底停止 `uvicorn` 再重启，而不是只依赖热重载。
