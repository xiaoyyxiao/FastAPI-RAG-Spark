# 数据库连接
import sqlite3
from contextlib import contextmanager
from config.settings import settings

# 初始化数据库（仅启动时执行一次）
# core/database.py
def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                file_size INTEGER NOT NULL, 
                upload_time TEXT DEFAULT (datetime('now', 'localtime'))  
            )
        ''')
        conn.commit()

# 上下文管理器：自动管理连接的创建/提交/回滚/关闭
@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = sqlite3.connect("docs.db")
        yield conn
    except sqlite3.Error as e:
        if conn:
            conn.rollback()  # 出错回滚
        raise Exception(f"数据库操作失败：{str(e)}")
    finally:
        if conn:
            conn.close()  # 确保关闭连接