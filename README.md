# FastAPI-RAG-Spark
**企业级智能文档问答系统** —— 基于 RAG (Retrieval-Augmented Generation) 架构，集成讯飞星火大模型与高性能向量数据库，实现私有知识库的精准问答。
---

## 核心特性 (Key Features)
- **异步高性能后端**：基于 **FastAPI** 异步框架，支持高并发接口请求。
- **混合问答模式**：
  - **知识库模式**：通过 **FAISS** 检索本地文档，结合上下文生成专业回答。
  - **通用模式**：当检索内容不相关时，自动切换至大模型通用对话模式（智能兜底）。
- **多格式文档支持**：自动化解析 PDF、Word、TXT 格式文档并进行语义分片。
- **工业级安全**：采用 **bcrypt** 加密存储，实现基于角色的访问控制 (RBAC)。
- **响应加速**：集成 **Redis** 缓存热点问答，大幅降低 API 调用成本及响应延迟。

---

## 系统架构
1. **数据层**：SQLite (元数据) + FAISS (向量索引)。
2. **检索层**：使用 `sentence-transformers` 进行语义嵌入 (Embedding)。
3. **生成层**：对接讯飞星火 Spark Lite 接口，通过 Prompt Engineering 引导回答。

---

## 技术栈
| 类别 | 技术选型 |
| :--- | :--- |
| **Web 框架** | FastAPI (Python) |
| **向量库** | FAISS |
| **大模型 API** | iFLYTEK Spark Lite |
| **数据库** | SQLite (Metadata), Redis (Cache) |
| **文档处理** | pdfplumber, python-docx |
| **安全性** | Bcrypt, JWT |

---
##
1. 环境准备
确保已安装 fastapi 且配置好 Redis。
2. 安装依赖
```bash
pip install -r requirements.txt
