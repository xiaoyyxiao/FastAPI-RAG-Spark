# 文件解析工具  utils/doc_parser.py
import os
from fastapi import UploadFile, HTTPException
from config.settings import settings
from docx import Document
import pdfplumber

# 校验文件合法性（类型+大小）
def validate_file(file: UploadFile):
    # 1. 校验文件大小
    file.file.seek(0, os.SEEK_END)  # 移动到文件末尾
    file_size = file.file.tell()    # 获取文件大小
    file.file.seek(0)               # 重置指针，避免后续读取失败
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制(最大{settings.MAX_FILE_SIZE//1024//1024}MB)"
        )
    
    # 2. 校验文件后缀
    filename = file.filename or ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持{','.join(settings.ALLOWED_EXTENSIONS)}格式文件"
        )
    return file_size

# 读取文件内容（PDF/Word）
def parse_file_content(file: UploadFile) -> str:
    filename = file.filename or ""
    file_ext = filename.split(".")[-1].lower()
    content = ""
    
    try:
        if file_ext == "docx":
            # 读取Word
            doc = Document(file.file)
            content = "\n".join([para.text.strip() for para in doc.paragraphs if para.text.strip()])
        elif file_ext == "pdf":
            # 读取PDF
            with pdfplumber.open(file.file) as pdf:
                content = "\n".join([page.extract_text().strip() for page in pdf.pages if page.extract_text()])
        
        # 校验内容非空
        if not content:
            raise HTTPException(status_code=400, detail="文档内容为空，无法上传")
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档解析失败：{str(e)}")