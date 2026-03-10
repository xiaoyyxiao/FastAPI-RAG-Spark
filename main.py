# main.py
from fastapi import FastAPI
import sqlite3
# 导入密码加密工具（初始化管理员需要）
from utils.password_utils import encrypt_password
# 导入auth路由（核心：注册你的auth接口）
from api.v1 import auth, docs, question
# main.py 开头必须有这行
from config.settings import settings
app = FastAPI(title="智能文档问答系统", version="1.0.0")

# 只保留数据库初始化（整合user_info+documents表）
def init_db():
    """整合版：一次连接，初始化所有表（文档表+用户表）"""
    # 1. 只连接一次数据库（减少IO开销）
    conn = sqlite3.connect("docs.db")
    cursor = conn.cursor()

    # 2. 初始化原有documents表（保留你之前加的file_size字段）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,  
            content TEXT NOT NULL,    
            file_size INTEGER         
        )
    ''')
    '''
    CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,  # 文件名
            content TEXT NOT NULL,    # 文档内容
            file_size INTEGER         # 模块3要求的文件大小字段
        '''
    # 3. 新增user_info表初始化（多用户体系核心）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,  
            password TEXT NOT NULL,         
            role TEXT NOT NULL DEFAULT 'employee',  
            is_first_login INTEGER DEFAULT 1         
        )
    ''')
    '''
        CREATE TABLE IF NOT EXISTS user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,  # 唯一用户名（工号/管理员账户）
            password TEXT NOT NULL,         # 加密后的密码
            role TEXT NOT NULL DEFAULT 'employee',  # 角色：admin/employee
            is_first_login INTEGER DEFAULT 1         # 是否首次登录（1=是，0=否）
        '''
    # 4. 初始化超级管理员（仅第一次运行创建，避免重复）
    cursor.execute("SELECT * FROM user_info WHERE username = 'admin'")
    if not cursor.fetchone():  # 只有admin账户不存在时才创建
        admin_raw_pwd = "admin123456"  # 管理员初始密码（建议运行后立即改）
        admin_hashed_pwd = encrypt_password(admin_raw_pwd)  # 加密存储
        cursor.execute(
            "INSERT INTO user_info (username, password, role, is_first_login) VALUES (?, ?, ?, ?)",
            ("admin", admin_hashed_pwd, "admin", 0)  # 0=非首次登录
        )
        print(f"⚠️ 超级管理员初始密码：{admin_raw_pwd}（请立即修改！）")

    # 5. 统一提交+关闭连接（一次操作，所有表生效）
    conn.commit()
    conn.close()

init_db()

# 注册路由（auth路由现在指向api/v1/auth.py）
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(docs.router, prefix="/api/v1/docs", tags=["文档管理"])
app.include_router(question.router, prefix="/api/v1/question", tags=["智能问答"])

@app.get("/")
def root():
    return {"msg": f"{settings.APP_TITLE}运行中，访问 /docs 查看接口文档"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)