# api/v1/docs.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import sqlite3
import os
import io
from utils.password_utils import verify_password
from docx import Document  # 处理docx
from PyPDF2 import PdfReader  # 处理pdf
from core.rag.rag_service import add_document_to_rag

router = APIRouter()

# 数据库连接函数（修正版，不使用with，新手友好）
def get_db_connection():
    """获取数据库连接，返回cursor+conn，手动关闭"""
    try:
        conn = sqlite3.connect("docs.db")
        cursor = conn.cursor()
        return cursor, conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库连接失败：{str(e)}")

# 新增工具函数：提取不同格式文件的文本内容
def extract_file_content(file: UploadFile) -> str:
    """
    提取文件内容：
    - txt：直接读取
    - docx：提取文本
    - pdf：提取文本
    """
    content = ""
    # 处理TXT文件
    if file.filename.endswith(".txt"):
        content = file.file.read().decode("utf-8", errors="ignore")
    # 处理DOCX文件
    elif file.filename.endswith(".docx"):
        doc = Document(io.BytesIO(file.file.read()))
        content = "\n".join([para.text for para in doc.paragraphs])
    # 处理PDF文件
    elif file.filename.endswith(".pdf"):
        pdf_reader = PdfReader(io.BytesIO(file.file.read()))
        content = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
    else:
        raise HTTPException(status_code=400, detail="仅支持上传txt、docx、pdf格式文件！")
    
    # 校验内容非空
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空，无法上传！")
    return content

# 1. 上传文档接口（核心：支持pdf/docx/txt，修复字段名错误）
@router.post("/upload", summary="上传文档（支持txt、docx、pdf）")
async def upload_document(file: UploadFile = File(...)):
    # 获取数据库连接
    cursor, conn = get_db_connection()
    try:
        # 第一步：提取文件内容（自动识别格式）
        file_content = extract_file_content(file)
        # 新增：加入RAG知识库
        add_document_to_rag(file_content)
        # 第二步：获取文件大小（字节）
        file.file.seek(0)  # 重置文件指针（读取内容后指针会到末尾）
        file_size = len(file.file.read())
        
        # 第三步：写入数据库（字段名是filename，修复之前的name错误）
        cursor.execute(
            "INSERT INTO documents (filename, content, file_size) VALUES (?, ?, ?)",
            (file.filename, file_content, file_size)
        )
        conn.commit()
        
        return {
            "code": 200,
            "msg": "文档上传成功！",
            "data": {
                "document_id": cursor.lastrowid,
                "filename": file.filename,
                "file_type": os.path.splitext(file.filename)[-1],
                "file_size": file_size,
                "content_length": len(file_content)
            }
        }
    except HTTPException as e:
        # 抛出已定义的业务异常（如格式错误、内容为空）
        raise e
    except Exception as e:
        # 捕获其他未知异常
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")
    finally:
        # 确保数据库连接和文件流关闭
        conn.close()
        await file.close()

# 2. 查询所有文档接口
@router.get("/list", summary="查询所有已上传文档")
async def list_documents():
    cursor, conn = get_db_connection()
    try:
        cursor.execute("SELECT id, filename, file_size, LENGTH(content) FROM documents")
        docs = cursor.fetchall()
        return {
            "code": 200,
            "msg": "查询成功",
            "data": [
                {
                    "id": doc[0],
                    "filename": doc[1],
                    "file_size": doc[2],
                    "content_length": doc[3]
                } for doc in docs
            ]
        }
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{str(e)}")
    finally:
        conn.close()

# 3. 删除文档接口（适配你的auth.py，用管理员密码校验，不用JWT）
@router.delete("/delete/{doc_id}", summary="删除文档（仅管理员可操作）")
async def delete_document(
    doc_id: int,
    admin_username: str,
    admin_password: str
):
    # 第一步：校验管理员身份（复用你auth.py的逻辑）
    conn_auth = sqlite3.connect("docs.db")
    cursor_auth = conn_auth.cursor()
    cursor_auth.execute("SELECT password, role FROM user_info WHERE username = ?", (admin_username,))
    admin = cursor_auth.fetchone()
    conn_auth.close()
    
    if not admin:
        raise HTTPException(status_code=401, detail="管理员用户名不存在")
    if admin[1] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除文档")
    if not verify_password(admin_password, admin[0]):
        raise HTTPException(status_code=401, detail="管理员密码错误")
    
    # 第二步：校验文档并删除
    cursor, conn = get_db_connection()
    try:
        cursor.execute("SELECT id FROM documents WHERE id = ?", (doc_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"文档ID {doc_id} 不存在")
        
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        
        return {
            "code": 200,
            "msg": f"文档ID {doc_id} 删除成功",
            "data": {"doc_id": doc_id}
        }
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")
    finally:
        conn.close()

# 4. 新增：根据ID查询单个文档（方便后续问答模块调用）
@router.get("/get/{doc_id}", summary="查询单个文档详情")
async def get_document(doc_id: int):
    cursor, conn = get_db_connection()
    try:
        cursor.execute("SELECT id, filename, content, file_size FROM documents WHERE id = ?", (doc_id,))
        doc = cursor.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail=f"文档ID {doc_id} 不存在")
        
        return {
            "code": 200,
            "msg": "查询成功",
            "data": {
                "id": doc[0],
                "filename": doc[1],
                "content": doc[2],
                "file_size": doc[3]
            }
        }
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{str(e)}")
    finally:
        conn.close()